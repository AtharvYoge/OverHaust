"""
OpenAI-compatible Layer-3 runner (ONE provider implementation).

Uses httpx against the Chat Completions API (tools + usage).
The same runner executes baseline and OverHaust; only context injection differs.

Requires OPENAI_API_KEY (or OVERHAUST_L3_API_KEY) for live calls.
Tests inject a fake transport — no live network required for unit tests.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from benchmarks import BENCHMARK_VERSION
from benchmarks.evaluate import evaluate_answer
from benchmarks.layer3.accounting import normalize_openai_usage
from benchmarks.layer3.contract import ExperimentContract, FieldPresence
from benchmarks.layer3.prompts import (
    LAYER3_SYSTEM_PROMPT,
    sha256_text,
    system_prompt_hash,
    user_prompt_hash,
)
from benchmarks.layer3.states import RunState
from benchmarks.layer3.tools import CANONICAL_TOOL_SPECS, RepoToolExecutor, tool_set_hash
from benchmarks.repro import collect_reproducibility
from benchmarks.schemas import BenchmarkTask, Condition, MeasurementSource, TokenKind
from benchmarks.tokens import TokenCounter
from benchmarks.trace import AgentTrace, summarize_tool_activity


DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


@dataclass
class Layer3RunResult:
    trace: AgentTrace
    contract: ExperimentContract


def _repo_commit(root: Path) -> Tuple[Optional[str], str]:
    """Return (commit, presence_status)."""
    from benchmarks.repro import _git

    commit = _git(["git", "rev-parse", "HEAD"], cwd=str(root))
    if commit:
        return commit, FieldPresence.KNOWN.value
    # Fixture trees: stable content hash so pairs can match.
    digest = sha256_text(str(sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())))
    return f"fixture-tree:{digest[:16]}", FieldPresence.KNOWN.value


def _build_messages(
    *,
    user_prompt: str,
    overhaust_context: Optional[str],
) -> List[Dict[str, str]]:
    messages = [
        {"role": "system", "content": LAYER3_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    if overhaust_context:
        # Intentional sole difference: OverHaust context as an additional
        # system message after the shared system prompt + same user prompt.
        messages.append({
            "role": "system",
            "content": (
                "OverHaust repository context (injected before tool use):\n\n"
                + overhaust_context
            ),
        })
    return messages


def _serialize_messages_for_accounting(messages: List[Dict[str, Any]]) -> str:
    return json.dumps(messages, sort_keys=True, separators=(",", ":"))


def _prove_context_inclusion(
    messages: List[Dict[str, Any]],
    overhaust_context: Optional[str],
) -> Tuple[str, Optional[int], Optional[int]]:
    """
    Returns (included_flag, overhaust_context_tokens_est, serialized_input_tokens_est).

    included_flag is "true" only when context string is present in model input
    message content (not merely a side-channel field). Serialization is used for
    independent token estimates; substring proof uses raw content because JSON
    escaping would otherwise false-negative on newlines.
    """
    serialized = _serialize_messages_for_accounting(messages)
    counter = TokenCounter(model=DEFAULT_MODEL)
    ser_tokens = counter.count_text(serialized).value
    if not overhaust_context:
        return "n/a", None, ser_tokens
    ctx_tokens = counter.count_text(overhaust_context).value
    present = any(
        isinstance(m.get("content"), str) and overhaust_context in m["content"]
        for m in messages
    )
    if present:
        return "true", ctx_tokens, ser_tokens
    return "false", ctx_tokens, ser_tokens


class OpenAICompatibleRunner:
    """
    Single runner for both conditions.

    Provider selected: OpenAI Chat Completions (tools + usage), via httpx.
    """

    name = "openai"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        model_version: Optional[str] = None,
        temperature: float = 0.0,
        seed: Optional[int] = None,
        max_tool_calls: int = 12,
        timeout_s: int = 120,
        max_output_tokens: int = 1024,
        transport: Optional[httpx.BaseTransport] = None,
        http_client: Optional[httpx.Client] = None,
    ):
        self.api_key = api_key or os.environ.get("OVERHAUST_L3_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_version = model_version or model
        self.temperature = temperature
        self.seed = seed
        self.max_tool_calls = max_tool_calls
        self.timeout_s = timeout_s
        self.max_output_tokens = max_output_tokens
        self._transport = transport
        self._http_client = http_client

    def is_available(self) -> bool:
        return bool(self.api_key) or self._http_client is not None or self._transport is not None

    def _client(self) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client
        headers = {"Authorization": f"Bearer {self.api_key or 'test-key}'}"}
        return httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout_s,
            transport=self._transport,
        )

    def _chat(self, client: httpx.Client, body: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(body)
        # Seed is best-effort; OpenAI may ignore on some models.
        if self.seed is not None:
            payload["seed"] = self.seed
        resp = client.post("/chat/completions", json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"API_ERROR {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    def run_task(
        self,
        task: BenchmarkTask,
        *,
        condition: str,
        repository_root: str,
        overhaust_context: Optional[str],
        experiment_id: str,
        pair_id: str,
        execution_order: str,
        session_id: Optional[str] = None,
        attempt_count: int = 1,
        retry_count: int = 0,
        repository_size: Optional[str] = None,
    ) -> Layer3RunResult:
        if condition not in {Condition.BASELINE.value, Condition.OVERHAUST.value}:
            raise ValueError(condition)
        if condition == Condition.BASELINE.value and overhaust_context:
            raise ValueError("baseline must not receive OverHaust context")
        if condition == Condition.OVERHAUST.value and not overhaust_context:
            # Empty context is allowed but inclusion will be false/n/a — pair validator
            # will block exact savings. Still run.
            overhaust_context = overhaust_context or ""

        session_id = session_id or str(uuid.uuid4())
        root = Path(repository_root)
        commit, _ = _repo_commit(root)
        tools = RepoToolExecutor(root)

        messages: List[Dict[str, Any]] = _build_messages(
            user_prompt=task.prompt,
            overhaust_context=overhaust_context if condition == Condition.OVERHAUST.value else None,
        )
        included, ctx_tokens, ser_tokens = _prove_context_inclusion(
            messages,
            overhaust_context if condition == Condition.OVERHAUST.value else None,
        )
        if condition == Condition.BASELINE.value:
            included = "n/a"

        tool_calls_log: List[Dict[str, Any]] = []
        tool_results_log: List[Dict[str, Any]] = []
        usage_acc: Dict[str, int] = {}
        raw_usages: List[Dict[str, Any]] = []
        final_answer = None
        state = RunState.SUCCESS
        error = None
        t0 = time.perf_counter()

        seed_status = (
            FieldPresence.KNOWN.value if self.seed is not None else "UNSUPPORTED"
        )
        # OpenAI supports seed on some models; if None we mark UNSUPPORTED rather than inventing.

        owns_client = self._http_client is None
        client = self._client()
        try:
            calls = 0
            while calls <= self.max_tool_calls:
                body = {
                    "model": self.model,
                    "temperature": self.temperature,
                    "max_tokens": self.max_output_tokens,
                    "messages": messages,
                    "tools": CANONICAL_TOOL_SPECS,
                    "tool_choice": "auto",
                }
                try:
                    data = self._chat(client, body)
                except Exception as exc:
                    msg = str(exc)
                    if "timeout" in msg.lower() or isinstance(exc, httpx.TimeoutException):
                        state = RunState.TIMEOUT
                    else:
                        state = RunState.API_ERROR
                    error = msg
                    break

                usage = data.get("usage") or {}
                raw_usages.append(usage)
                for k, v in usage.items():
                    if isinstance(v, int):
                        usage_acc[k] = usage_acc.get(k, 0) + v
                # Merge nested cached if present on last usage only for details —
                # prefer last response usage for normalize; sum prompt/completion.
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                messages.append(msg)

                tcalls = msg.get("tool_calls") or []
                if not tcalls:
                    final_answer = msg.get("content") or ""
                    finish = choice.get("finish_reason")
                    if finish == "length":
                        state = RunState.INCOMPLETE
                    break

                for tc in tcalls:
                    if calls >= self.max_tool_calls:
                        state = RunState.INCOMPLETE
                        error = "max_tool_calls exhausted"
                        break
                    calls += 1
                    fn = tc.get("function") or {}
                    name = fn.get("name") or "other"
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                        state = RunState.TOOL_ERROR
                        error = "invalid tool arguments JSON"
                        break
                    try:
                        result = tools.dispatch(name, args)
                    except Exception as exc:
                        state = RunState.TOOL_ERROR
                        error = str(exc)
                        result = json.dumps({"error": str(exc)})
                    tool_type = {
                        "read_file": "read_file",
                        "list_dir": "list_dir",
                        "search_text": "search",
                        "search_repo": "search",
                    }.get(name, "other")
                    tool_calls_log.append({
                        "id": tc.get("id") or f"call_{calls}",
                        "tool_type": tool_type,
                        "name": name,
                        "arguments": args,
                        "result_preview": (result or "")[:200],
                        "result_bytes": len((result or "").encode("utf-8")),
                    })
                    tool_results_log.append({
                        "tool_call_id": tc.get("id"),
                        "content": result,
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id"),
                        "content": result,
                    })
                if state in {RunState.TOOL_ERROR, RunState.INCOMPLETE}:
                    break
            else:
                if final_answer is None:
                    state = RunState.INCOMPLETE
                    error = error or "loop ended without final answer"
        finally:
            if owns_client:
                client.close()

        duration_ms = int((time.perf_counter() - t0) * 1000)

        # Aggregate usage: sum prompt/completion across turns; cached from last if present
        merged_usage = {
            "prompt_tokens": usage_acc.get("prompt_tokens"),
            "completion_tokens": usage_acc.get("completion_tokens"),
            "total_tokens": usage_acc.get("total_tokens"),
        }
        # Prefer last usage details for cache
        if raw_usages:
            last = raw_usages[-1]
            if "prompt_tokens_details" in last:
                merged_usage["prompt_tokens_details"] = last["prompt_tokens_details"]
            # If totals missing but we summed components:
            if merged_usage["total_tokens"] is None:
                p, c = merged_usage["prompt_tokens"], merged_usage["completion_tokens"]
                if p is not None and c is not None:
                    merged_usage["total_tokens"] = p + c

        # Drop None keys for normalize
        merged_usage = {k: v for k, v in merged_usage.items() if v is not None or k == "prompt_tokens_details"}
        normalized = normalize_openai_usage(merged_usage if merged_usage else None)

        scored = None
        if final_answer:
            scored = evaluate_answer(task, final_answer)
        elif state == RunState.SUCCESS:
            state = RunState.CORRECTNESS_UNEVALUABLE

        activity = summarize_tool_activity(tool_calls_log)
        ctx_hash = sha256_text(overhaust_context) if (
            condition == Condition.OVERHAUST.value and overhaust_context
        ) else None

        contract = ExperimentContract(
            experiment_id=experiment_id,
            pair_id=pair_id,
            condition=condition,
            provider=self.name,
            model=self.model,
            model_version=self.model_version,
            repository=str(root),
            repository_commit=commit,
            task_id=task.task_id,
            user_prompt=task.prompt,
            user_prompt_hash=user_prompt_hash(task.prompt),
            system_prompt=LAYER3_SYSTEM_PROMPT,
            system_prompt_hash=system_prompt_hash(),
            tool_set_hash=tool_set_hash(),
            temperature=self.temperature,
            temperature_status=FieldPresence.KNOWN.value,
            seed=self.seed,
            seed_status=seed_status,
            max_tool_calls=self.max_tool_calls,
            timeout_s=self.timeout_s,
            max_output_tokens=self.max_output_tokens,
            execution_order=execution_order,
            session_id=session_id,
            attempt_count=attempt_count,
            retry_count=retry_count,
            failure_status=state.value,
            overhaust_context_hash=ctx_hash,
            overhaust_context_tokens=ctx_tokens,
            overhaust_context_included_in_input=included,
            provider_input_tokens=normalized.raw_input_tokens,
            serialized_input_tokens=ser_tokens,
            token_accounting=normalized.to_dict(),
            benchmark_version=BENCHMARK_VERSION,
        )

        trace = AgentTrace(
            run_id=str(uuid.uuid4()),
            layer=3,
            provider=self.name,
            model=self.model,
            condition=condition,
            repository=str(root),
            repository_size=repository_size or getattr(task, "repository_size", "medium"),
            task_id=task.task_id,
            prompt=task.prompt,
            messages=messages,
            tool_calls=tool_calls_log,
            tool_results=[{"tool_call_id": r.get("tool_call_id"), "bytes": len(str(r.get("content", "")))}
                          for r in tool_results_log],
            input_tokens=normalized.raw_input_tokens,
            output_tokens=normalized.raw_output_tokens,
            cached_input_tokens=normalized.cached_input_tokens,
            total_tokens=normalized.total_billable_tokens,
            input_tokens_kind=(
                TokenKind.EXACT.value if normalized.raw_input_tokens is not None
                else TokenKind.UNAVAILABLE.value
            ),
            output_tokens_kind=(
                TokenKind.EXACT.value if normalized.raw_output_tokens is not None
                else TokenKind.UNAVAILABLE.value
            ),
            cached_input_tokens_kind=normalized.cached_input_tokens_kind,
            total_tokens_kind=normalized.total_billable_tokens_kind,
            tool_call_count=activity["tool_call_count"],
            tool_call_types=activity["tool_call_types"],
            files_opened=activity["files_opened"],
            files_read_count=activity["files_read_count"],
            searches_performed=activity["searches_performed"],
            overhaust_context_tokens=ctx_tokens if condition == Condition.OVERHAUST.value else None,
            overhaust_context_tokens_kind=(
                TokenKind.ESTIMATED.value if ctx_tokens is not None else TokenKind.UNAVAILABLE.value
            ),
            duration_ms=duration_ms,
            final_answer=final_answer,
            correctness=scored.correct if scored else None,
            evidence_score=scored.evidence_score if scored else None,
            correctness_detail=scored.to_dict() if scored else None,
            measurement_source=MeasurementSource.AUTOMATED.value,
            error=error,
            provider_raw={"usages": raw_usages},
            config={
                "experiment_contract": contract.to_dict(),
                "max_tool_calls": self.max_tool_calls,
                "timeout_s": self.timeout_s,
                "max_output_tokens": self.max_output_tokens,
                "sole_difference": "OverHaust context availability only",
            },
            reproducibility=collect_reproducibility(
                repository_path=str(root),
                model=self.model,
                model_version=self.model_version,
                provider=self.name,
                seed=self.seed,
                config={
                    "temperature": self.temperature,
                    "execution_order": execution_order,
                    "session_id": session_id,
                    "pair_id": pair_id,
                },
            ),
        )
        trace.contract = contract  # type: ignore[attr-defined]
        try:
            trace.validate_token_kinds()
        except ValueError:
            pass
        return Layer3RunResult(trace=trace, contract=contract)


def run_layer3_pair(
    task: BenchmarkTask,
    *,
    repository_root: str,
    overhaust_context: str,
    runner: Optional[OpenAICompatibleRunner] = None,
    experiment_id: Optional[str] = None,
    pair_id: Optional[str] = None,
    overhaust_first: bool = False,
    repository_size: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute both conditions with the SAME runner.
    Randomize order via overhaust_first.
    Fresh session_id per condition.
    Repository is snapshotted and restored before each condition.
    """
    from benchmarks.repro import capture_repository_snapshot, isolate_repository

    runner = runner or OpenAICompatibleRunner()
    if not runner.is_available():
        raise RuntimeError(
            "OpenAI Layer-3 runner unavailable (set OPENAI_API_KEY or inject http client)."
        )
    experiment_id = experiment_id or str(uuid.uuid4())
    pair_id = pair_id or str(uuid.uuid4())
    order = ["overhaust", "baseline"] if overhaust_first else ["baseline", "overhaust"]
    execution_order = "overhaust_first" if overhaust_first else "baseline_first"
    recorded_size = repository_size or getattr(task, "repository_size", "medium")

    results: Dict[str, Layer3RunResult] = {}
    restore_log: List[Dict[str, Any]] = []
    snapshot = capture_repository_snapshot(repository_root)
    for cond in order:
        isolation = isolate_repository(repository_root, snapshot)
        restore_log.append(isolation)
        if not isolation.get("verified"):
            return _unproven_restore_pair(
                experiment_id=experiment_id,
                pair_id=pair_id,
                execution_order=execution_order,
                restore_log=restore_log,
                results=results,
            )
        ctx = overhaust_context if cond == "overhaust" else None
        results[cond] = runner.run_task(
            task,
            condition=cond,
            repository_root=repository_root,
            overhaust_context=ctx,
            experiment_id=experiment_id,
            pair_id=pair_id,
            execution_order=execution_order,
            session_id=str(uuid.uuid4()),
            repository_size=recorded_size,
        )

    from benchmarks.layer3.pairing import validate_layer3_pair
    from benchmarks.layer3.pairwise import pairwise_reduction

    validation = validate_layer3_pair(results["baseline"].trace, results["overhaust"].trace)
    metrics = pairwise_reduction(
        results["baseline"].trace, results["overhaust"].trace, validation
    )
    return {
        "experiment_id": experiment_id,
        "pair_id": pair_id,
        "execution_order": execution_order,
        "baseline": results["baseline"].trace,
        "overhaust": results["overhaust"].trace,
        "validation": validation.to_dict(),
        "pairwise_metrics": metrics,
        "repository_restore": restore_log,
        "isolation_proven": True,
    }


def _unproven_restore_pair(
    *,
    experiment_id: str,
    pair_id: str,
    execution_order: str,
    restore_log: List[Dict[str, Any]],
    results: Dict[str, Layer3RunResult],
) -> Dict[str, Any]:
    """Do not invent traces or exact reductions when isolation is unproven."""
    return {
        "experiment_id": experiment_id,
        "pair_id": pair_id,
        "execution_order": execution_order,
        "baseline": results.get("baseline"),
        "overhaust": results.get("overhaust"),
        "validation": {
            "comparable": False,
            "limited": True,
            "allow_exact_token_reduction": False,
            "reasons": [{
                "field": "repository_restore",
                "baseline": (restore_log[-1].get("status") if restore_log else None),
                "overhaust": (restore_log[-1].get("status") if restore_log else None),
                "status": "UNPROVEN",
                "detail": "Repository restoration could not be proven.",
            }],
            "summary": "NOT comparable — repository restoration could not be proven.",
        },
        "pairwise_metrics": None,
        "repository_restore": restore_log,
        "isolation_proven": False,
    }
