"""
Layer 2 — deterministic agent / tool simulator.

Simulates realistic repository exploration with a fixed tool set:

  search  — substring search across source files
  read_file — read a file's full contents
  list_dir — list directory entries

BASELINE: starts with the task prompt only.
OVERHAUST: prepends invoke_context_request() context, then the same tools.

This does NOT prove Layer 3 (real model) or Layer 4 (IDE) results.
Token counts here are ESTIMATED (conversation transcript via TokenCounter).
"""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from benchmarks.evaluate import evaluate_answer
from benchmarks.fixture import FixtureProject
from benchmarks.repro import collect_reproducibility
from benchmarks.schemas import BenchmarkTask, Condition, MeasurementSource, TokenKind
from benchmarks.tokens import TokenCounter
from benchmarks.trace import AgentTrace, summarize_tool_activity

_SOURCE_GLOBS = ("*.ts", "*.tsx", "*.dart", "*.py", "*.js", "*.md")


class RepoTools:
    """Shared tool surface for baseline and OverHaust conditions."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def _safe(self, rel: str) -> Path:
        rel = rel.replace("\\", "/").lstrip("/")
        if ".." in rel.split("/"):
            raise ValueError("path escape")
        full = (self.root / rel).resolve()
        full.relative_to(self.root)
        return full

    def list_dir(self, rel: str = ".") -> List[str]:
        path = self._safe(rel) if rel not in (".", "") else self.root
        if not path.is_dir():
            return []
        return sorted(p.name + ("/" if p.is_dir() else "") for p in path.iterdir())

    def search(self, query: str, *, max_hits: int = 20) -> List[Dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        hits: List[Dict[str, Any]] = []
        pattern = re.compile(re.escape(q), re.I)
        for glob in _SOURCE_GLOBS:
            for path in self.root.rglob(glob):
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if pattern.search(line):
                        rel = str(path.relative_to(self.root)).replace("\\", "/")
                        hits.append({"path": rel, "line": i, "text": line.strip()[:200]})
                        if len(hits) >= max_hits:
                            return hits
        return hits

    def read_file(self, rel: str) -> str:
        return self._safe(rel).read_text(encoding="utf-8", errors="replace")


def _keywords(prompt: str) -> List[str]:
    stop = {
        "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "is",
        "are", "what", "where", "how", "does", "do", "we", "if", "change",
        "which", "likely", "explain", "between", "from", "with",
    }
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", prompt)
    out: List[str] = []
    for w in words:
        if w.lower() in stop:
            continue
        if w not in out:
            out.append(w)
    return out[:8]


def _evidence_blob(files_content: Dict[str, str], search_hits: List[Dict[str, Any]]) -> str:
    parts = list(files_content.values())
    parts.extend(h.get("text", "") for h in search_hits)
    parts.extend(h.get("path", "") for h in search_hits)
    return "\n".join(parts)


def _rubric_satisfied(task: BenchmarkTask, blob: str) -> bool:
    result = evaluate_answer(task, blob)
    # For the simulator stop condition, require required facts present.
    return bool(result.correct)


def run_simulated_agent(
    task: BenchmarkTask,
    *,
    fixture: FixtureProject,
    condition: str,
    max_tool_calls: int = 12,
    model: Optional[str] = None,
    seed: Optional[int] = None,
    counter: Optional[TokenCounter] = None,
) -> AgentTrace:
    """
    Deterministic exploration loop.

    Strategy (identical for both conditions; only initial context differs):
      1. Optionally inject OverHaust context (overhaust condition).
      2. Search for each keyword from the prompt.
      3. Read top unique hit files.
      4. Stop early when rubric facts appear in accumulated evidence,
         else stop at max_tool_calls and emit best-effort answer.
    """
    if condition not in {Condition.BASELINE.value, Condition.OVERHAUST.value}:
        raise ValueError(condition)

    counter = counter or TokenCounter(model=model)
    tools = RepoTools(fixture.root)
    run_id = str(uuid.uuid4())
    t0 = time.perf_counter()

    messages: List[Dict[str, Any]] = []
    tool_calls: List[Dict[str, Any]] = []
    tool_results: List[Dict[str, Any]] = []
    files_content: Dict[str, str] = {}
    all_hits: List[Dict[str, Any]] = []
    overhaust_ctx = ""
    overhaust_tokens = None
    overhaust_kind = TokenKind.UNAVAILABLE.value
    error = None

    messages.append({"role": "user", "content": task.prompt})

    if condition == Condition.OVERHAUST.value:
        try:
            from packages.context.agent_context import invoke_context_request

            resp = invoke_context_request(
                fixture.project_id,
                task.prompt,
                memory_store=fixture.memory_store,
            )
            overhaust_ctx = resp.context or ""
            m = counter.count_context(overhaust_ctx)
            overhaust_tokens = m.value
            overhaust_kind = m.kind.value
            messages.append({
                "role": "system",
                "content": (
                    "OverHaust repository context (injected before exploration):\n\n"
                    + overhaust_ctx
                ),
                "name": "overhaust_context",
            })
            # If context alone satisfies the rubric, still allow zero tool calls.
            if _rubric_satisfied(task, overhaust_ctx):
                answer = _compose_answer(task, overhaust_ctx, files_content, all_hits)
                return _finish_trace(
                    run_id=run_id, task=task, fixture=fixture, condition=condition,
                    messages=messages, tool_calls=tool_calls, tool_results=tool_results,
                    answer=answer, overhaust_tokens=overhaust_tokens,
                    overhaust_kind=overhaust_kind, t0=t0, model=model, seed=seed,
                    counter=counter, max_tool_calls=max_tool_calls, error=None,
                )
        except Exception as exc:
            error = f"overhaust context failed: {exc}"

    keywords = _keywords(task.prompt)
    # Prefer expected symbols as search terms when present (still available to
    # both conditions equally — not OverHaust-specific hints).
    for sym in task.expected_symbols:
        if sym not in keywords:
            keywords.insert(0, sym)

    call_i = 0
    read_paths: Set[str] = set()

    def _budget() -> bool:
        return call_i < max_tool_calls

    try:
        for kw in keywords:
            if not _budget():
                break
            call_i += 1
            hits = tools.search(kw)
            all_hits.extend(hits)
            tool_calls.append({
                "id": f"call_{call_i}",
                "tool_type": "search",
                "name": "search",
                "arguments": {"query": kw},
                "result_preview": str(hits[:3]),
                "result_bytes": len(str(hits).encode("utf-8")),
            })
            tool_results.append({"tool_call_id": f"call_{call_i}", "content": hits})
            messages.append({"role": "assistant", "content": f"search({kw!r})"})
            messages.append({"role": "tool", "content": str(hits[:5]), "name": "search"})

            blob = _evidence_blob(files_content, all_hits)
            if overhaust_ctx:
                blob = overhaust_ctx + "\n" + blob
            if _rubric_satisfied(task, blob):
                break

            for hit in hits:
                path = hit["path"]
                if path in read_paths:
                    continue
                if not _budget():
                    break
                call_i += 1
                content = tools.read_file(path)
                read_paths.add(path)
                files_content[path] = content
                tool_calls.append({
                    "id": f"call_{call_i}",
                    "tool_type": "read_file",
                    "name": "read_file",
                    "arguments": {"path": path},
                    "result_preview": content[:200],
                    "result_bytes": len(content.encode("utf-8")),
                })
                tool_results.append({"tool_call_id": f"call_{call_i}", "content": content})
                messages.append({"role": "assistant", "content": f"read_file({path!r})"})
                messages.append({"role": "tool", "content": content[:2000], "name": "read_file"})

                blob = _evidence_blob(files_content, all_hits)
                if overhaust_ctx:
                    blob = overhaust_ctx + "\n" + blob
                if _rubric_satisfied(task, blob):
                    break
            else:
                continue
            break
    except Exception as exc:
        error = str(exc)

    answer_blob = (overhaust_ctx + "\n" if overhaust_ctx else "") + _evidence_blob(
        files_content, all_hits
    )
    answer = _compose_answer(task, answer_blob, files_content, all_hits)
    return _finish_trace(
        run_id=run_id, task=task, fixture=fixture, condition=condition,
        messages=messages, tool_calls=tool_calls, tool_results=tool_results,
        answer=answer, overhaust_tokens=overhaust_tokens,
        overhaust_kind=overhaust_kind, t0=t0, model=model, seed=seed,
        counter=counter, max_tool_calls=max_tool_calls, error=error,
    )


def _compose_answer(
    task: BenchmarkTask,
    blob: str,
    files_content: Dict[str, str],
    hits: List[Dict[str, Any]],
) -> str:
    """
    Deterministic answer synthesis from evidence — not an LLM.

    FOUND facts are stated affirmatively. MISSING facts are reported without
    treating the mere label echo as success (evaluate checks FOUND markers).
    """
    lines = [f"Task: {task.title}", ""]
    rubric = task.get_rubric()
    blob_l = blob.lower()

    def present(item: str) -> bool:
        return item.lower() in blob_l

    for fact in rubric.required_facts:
        if present(fact):
            lines.append(f"FOUND: {fact}")
        else:
            lines.append("MISSING: required evidence not located in repository search/reads.")
    for group in rubric.required_any_of:
        if any(present(g) for g in group):
            hit = next(g for g in group if present(g))
            lines.append(f"FOUND: {hit}")
        else:
            lines.append(
                "MISSING: none of the acceptable alternatives were found "
                f"({', '.join(group)})."
            )
    for sym in rubric.required_symbols or task.expected_symbols:
        if present(sym):
            lines.append(f"FOUND symbol: {sym}")
        else:
            lines.append(f"MISSING symbol: {sym} — no definition located.")
    for path in rubric.required_files or task.expected_files:
        if present(path) or path in files_content:
            lines.append(f"FOUND file: {path}")
        else:
            lines.append(f"MISSING file: {path}")
    if files_content:
        lines.append("")
        lines.append("Files read:")
        for p in files_content:
            lines.append(f"  - {p}")
    if hits:
        lines.append("")
        lines.append("Search hits (sample):")
        for h in hits[:5]:
            lines.append(f"  - {h.get('path')}:{h.get('line')} {h.get('text')}")
    return "\n".join(lines)


def _finish_trace(
    *,
    run_id: str,
    task: BenchmarkTask,
    fixture: FixtureProject,
    condition: str,
    messages: List[Dict[str, Any]],
    tool_calls: List[Dict[str, Any]],
    tool_results: List[Dict[str, Any]],
    answer: str,
    overhaust_tokens: Optional[int],
    overhaust_kind: str,
    t0: float,
    model: Optional[str],
    seed: Optional[int],
    counter: TokenCounter,
    max_tool_calls: int,
    error: Optional[str],
) -> AgentTrace:
    duration_ms = int((time.perf_counter() - t0) * 1000)
    activity = summarize_tool_activity(tool_calls)
    scored = evaluate_answer(task, answer)
    msg_tokens = counter.count_messages(messages)
    out_tokens = counter.count_text(answer)

    est_total = None
    if msg_tokens.value is not None and out_tokens.value is not None:
        est_total = msg_tokens.value + out_tokens.value

    size = getattr(fixture, "repository_size", task.repository_size)
    label = getattr(fixture, "repository_label", task.repository)

    return AgentTrace(
        run_id=run_id,
        layer=2,
        provider="simulated",
        model=model or "deterministic-sim-agent",
        condition=condition,
        repository=label,
        repository_size=size,
        task_id=task.task_id,
        prompt=task.prompt,
        messages=messages,
        tool_calls=tool_calls,
        tool_results=[{"tool_call_id": r["tool_call_id"], "bytes": len(str(r.get("content", "")))}
                      for r in tool_results],
        input_tokens=None,
        output_tokens=None,
        cached_input_tokens=None,
        total_tokens=None,
        estimated_input_tokens=msg_tokens.value,
        estimated_output_tokens=out_tokens.value,
        estimated_total_tokens=est_total,
        estimated_tokens_note=msg_tokens.note,
        tool_call_count=activity["tool_call_count"],
        tool_call_types=activity["tool_call_types"],
        files_opened=activity["files_opened"],
        files_read_count=activity["files_read_count"],
        searches_performed=activity["searches_performed"],
        overhaust_context_tokens=overhaust_tokens if condition == "overhaust" else None,
        overhaust_context_tokens_kind=overhaust_kind if condition == "overhaust" else TokenKind.UNAVAILABLE.value,
        duration_ms=duration_ms,
        final_answer=answer,
        correctness=scored.correct,
        evidence_score=scored.evidence_score,
        correctness_detail=scored.to_dict(),
        measurement_source=MeasurementSource.AUTOMATED.value,
        error=error,
        config={
            "max_tool_calls": max_tool_calls,
            "layer": 2,
            "disclaimer": (
                "Layer 2 deterministic simulation. Does NOT prove Layer 3/4. "
                "Token fields are estimated_token_count only."
            ),
        },
        reproducibility=collect_reproducibility(
            repository_path=str(fixture.root),
            model=model or "deterministic-sim-agent",
            provider="simulated",
            seed=seed,
            config={"max_tool_calls": max_tool_calls, "condition": condition},
        ),
    )


def run_layer2_pair(
    task: BenchmarkTask,
    *,
    fixture: FixtureProject,
    max_tool_calls: int = 12,
    model: Optional[str] = None,
    seed: Optional[int] = None,
) -> Dict[str, AgentTrace]:
    """Run baseline then overhaust with identical tool budgets."""
    counter = TokenCounter(model=model)
    return {
        "baseline": run_simulated_agent(
            task, fixture=fixture, condition="baseline",
            max_tool_calls=max_tool_calls, model=model, seed=seed, counter=counter,
        ),
        "overhaust": run_simulated_agent(
            task, fixture=fixture, condition="overhaust",
            max_tool_calls=max_tool_calls, model=model, seed=seed, counter=counter,
        ),
    }
