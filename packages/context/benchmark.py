"""
Fair context benchmark measurements for agent validation.

Compares OverHaust compact context against baselines that better represent
what a coding agent would actually read when exploring a repository.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from packages.context.agent_context import invoke_context_request
from packages.context.retrieval import search_project_knowledge
from packages.shared.config import get_context_max_files
from packages.tokenization.token_estimator import TokenEstimator


def _unique_paths_from_search(results: List[Dict[str, Any]]) -> List[str]:
    seen: Set[str] = set()
    paths: List[str] = []
    for row in results:
        meta = row.get("metadata") or {}
        path = meta.get("file_path") or meta.get("source_ref") or ""
        if path and path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def _read_full_file(root_path: str, rel_path: str) -> Optional[str]:
    """Read an entire indexed file with path containment checks."""
    from services.ingestion.project_indexer import ProjectIndexer, PathSecurityError

    try:
        indexer = ProjectIndexer()
        root = indexer._validate_root(root_path)
        rel = rel_path.replace("\\", "/").lstrip("/")
        if ".." in rel.split("/"):
            return None
        full = (root / rel).resolve()
        full.relative_to(root)
        return full.read_text(encoding="utf-8", errors="replace")
    except (PathSecurityError, ValueError, OSError):
        return None


def simulate_naive_agent_exploration(
    project_id: str,
    prompt: str,
    *,
    memory_store=None,
    search_limit: int = 10,
    max_files_to_read: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Baseline: agent searches, then reads full contents of top hit files.

    This approximates naïve repository exploration without OverHaust budgeting.
    """
    from services.ingestion.index_store import ProjectIndexStore

    if memory_store is None:
        from packages.memory.memory_store import get_memory_store
        memory_store = get_memory_store()

    max_files = max_files_to_read or get_context_max_files()
    root = ProjectIndexStore(memory_store).get_project_root(project_id)
    if not root:
        raise ValueError(f"No root path for project {project_id}")

    t0 = time.perf_counter()
    results = search_project_knowledge(
        project_id, prompt, memory_store=memory_store, limit=search_limit,
    )
    paths = _unique_paths_from_search(results)[:max_files]

    files_read: List[Dict[str, Any]] = []
    total_lines = 0
    combined_parts: List[str] = []
    for path in paths:
        content = _read_full_file(root, path)
        if not content:
            continue
        line_count = len(content.splitlines())
        total_lines += line_count
        files_read.append({"path": path, "lines": line_count, "bytes": len(content.encode("utf-8"))})
        combined_parts.append(f"// FILE: {path}\n{content}")

    combined_text = "\n\n".join(combined_parts)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    estimator = TokenEstimator()

    return {
        "label": "naive_agent_full_files",
        "description": "Search top hits then read full file contents (simulated agent exploration)",
        "files_inspected": len(paths),
        "files_read": len(files_read),
        "approx_source_lines": total_lines,
        "response_bytes": len(combined_text.encode("utf-8")),
        "estimated_context_tokens": estimator.estimate_tokens(combined_text),
        "token_estimate_note": "tiktoken estimate on concatenated full file contents",
        "latency_ms": latency_ms,
        "paths": [f["path"] for f in files_read],
    }


def measure_search_metadata_only(
    project_id: str,
    prompt: str,
    *,
    memory_store=None,
    search_limit: int = 10,
) -> Dict[str, Any]:
    """Legacy baseline: search JSON metadata only (NOT comparable to snippet context)."""
    if memory_store is None:
        from packages.memory.memory_store import get_memory_store
        memory_store = get_memory_store()

    t0 = time.perf_counter()
    results = search_project_knowledge(
        project_id, prompt, memory_store=memory_store, limit=search_limit,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    payload = json.dumps({"results": results}, default=str)
    estimator = TokenEstimator()
    paths = _unique_paths_from_search(results)

    return {
        "label": "search_metadata_json",
        "description": "Search API JSON only — metadata, no disk reads (NOT a fair agent baseline)",
        "files_inspected": len(paths),
        "files_read": 0,
        "approx_source_lines": len(results),
        "response_bytes": len(payload.encode("utf-8")),
        "estimated_context_tokens": estimator.estimate_tokens(payload),
        "token_estimate_note": "tiktoken estimate on search JSON",
        "latency_ms": latency_ms,
        "paths": paths,
    }


def measure_overhaust_context(
    project_id: str,
    prompt: str,
    *,
    memory_store=None,
    include_code_flow: str | bool = "auto",
) -> Dict[str, Any]:
    """OverHaust condition: compact get_relevant_context."""
    if memory_store is None:
        from packages.memory.memory_store import get_memory_store
        memory_store = get_memory_store()

    t0 = time.perf_counter()
    response = invoke_context_request(
        project_id,
        prompt,
        memory_store=memory_store,
        include_code_flow=include_code_flow,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    payload = response.to_dict()
    estimator = TokenEstimator()
    context_text = payload.get("context", "")

    return {
        "label": "overhaust_compact_context",
        "description": "OverHaust get_relevant_context compact package",
        "files_inspected": payload["metrics"]["files_count"],
        "files_read": payload["metrics"]["files_count"],
        "symbols_count": payload["metrics"]["symbols_count"],
        "approx_source_lines": payload["metrics"]["approx_source_lines"],
        "response_bytes": payload["metrics"]["response_bytes"],
        "estimated_context_tokens": estimator.estimate_tokens(context_text),
        "token_estimate_note": "tiktoken estimate on context field only",
        "latency_ms": latency_ms,
        "code_flow_included": payload["metrics"]["code_flow_included"],
        "confidence": payload["confidence"],
        "insufficient_evidence": payload["insufficient_evidence"],
        "paths": [f.get("path", "") for f in payload.get("relevant_files", [])],
        "symbols": [
            {"file": s.get("file"), "name": s.get("name")}
            for s in payload.get("relevant_symbols", [])
        ],
        "payload": payload,
        "code_flow_steps": len((payload.get("code_flow") or {}).get("steps") or []),
    }


def _reduction_pct(a: float, b: float) -> Optional[float]:
    if a <= 0:
        return None
    return round((1.0 - (b / a)) * 100.0, 2)


def measure_hook_interception(
    project_id: str,
    prompt: str,
    *,
    root_path: str,
    memory_store=None,
) -> Dict[str, Any]:
    """OverHaust via UserPromptSubmit hook adapter (parse + invoke_context_request)."""
    from packages.integrations.hook_io import HookInput
    from packages.integrations.interception import run_user_prompt_interception

    if memory_store is None:
        from packages.memory.memory_store import get_memory_store
        memory_store = get_memory_store()

    t0 = time.perf_counter()
    result = run_user_prompt_interception(
        HookInput(prompt=prompt, cwd=root_path, project_id_override=project_id),
        memory_store=memory_store,
        include_naive_baseline=False,
    )
    total_latency_ms = int((time.perf_counter() - t0) * 1000)
    payload = result.response_payload or {}
    context_text = result.additional_context
    estimator = TokenEstimator()

    return {
        "label": "overhaust_hook_interception",
        "description": "UserPromptSubmit hook adapter calling invoke_context_request",
        "files_inspected": payload.get("metrics", {}).get("files_count", 0),
        "files_read": payload.get("metrics", {}).get("files_count", 0),
        "symbols_count": payload.get("metrics", {}).get("symbols_count", 0),
        "approx_source_lines": payload.get("metrics", {}).get("approx_source_lines", 0),
        "response_bytes": len(context_text.encode("utf-8")),
        "estimated_context_tokens": estimator.estimate_tokens(context_text),
        "token_estimate_note": "tiktoken estimate on hook additionalContext",
        "latency_ms": total_latency_ms,
        "engine_latency_ms": payload.get("metrics", {}).get("latency_ms", 0),
        "hook_overhead_ms": max(0, total_latency_ms - payload.get("metrics", {}).get("latency_ms", 0)),
        "code_flow_included": payload.get("metrics", {}).get("code_flow_included", False),
        "paths": [f.get("path", "") for f in payload.get("relevant_files", [])],
        "error": result.debug.error,
    }


def run_agent_benchmark(
    project_id: str,
    prompt: str,
    *,
    memory_store=None,
    search_limit: int = 10,
) -> Dict[str, Any]:
    """Run all benchmark conditions and compute fair reductions."""
    naive = simulate_naive_agent_exploration(
        project_id, prompt, memory_store=memory_store, search_limit=search_limit,
    )
    metadata = measure_search_metadata_only(
        project_id, prompt, memory_store=memory_store, search_limit=search_limit,
    )
    overhaust = measure_overhaust_context(
        project_id, prompt, memory_store=memory_store,
    )

    hook_path: Optional[Dict[str, Any]] = None
    try:
        from services.ingestion.index_store import ProjectIndexStore

        if memory_store is None:
            from packages.memory.memory_store import get_memory_store
            memory_store = get_memory_store()
        root = ProjectIndexStore(memory_store).get_project_root(project_id)
        if root:
            hook_path = measure_hook_interception(
                project_id, prompt, root_path=root, memory_store=memory_store,
            )
    except Exception:
        hook_path = None

    fair_reduction = {
        "tokens_vs_naive_full_files_pct": _reduction_pct(
            naive["estimated_context_tokens"],
            overhaust["estimated_context_tokens"],
        ),
        "bytes_vs_naive_full_files_pct": _reduction_pct(
            naive["response_bytes"],
            overhaust["response_bytes"],
        ),
        "lines_vs_naive_full_files_pct": _reduction_pct(
            naive["approx_source_lines"],
            overhaust["approx_source_lines"],
        ),
        "files_vs_naive_full_files_pct": _reduction_pct(
            naive["files_read"],
            overhaust["files_read"],
        ),
        "latency_overhead_ms": overhaust["latency_ms"] - naive["latency_ms"],
    }

    return {
        "project_id": project_id,
        "prompt": prompt,
        "baseline_fair": naive,
        "baseline_legacy_metadata": metadata,
        "overhaust": overhaust,
        "hook_interception": hook_path,
        "fair_reduction": fair_reduction,
        "baseline_recommendation": (
            "Use baseline_fair (naive_agent_full_files) as the primary comparison. "
            "It simulates an agent reading full contents of top search hits. "
            "search_metadata_json is NOT comparable because it omits source reads."
        ),
        "task_success_measurable": False,
        "task_success_note": (
            "Autonomous agent task completion cannot be measured in this harness. "
            "Context quality and size are measured; human/agent completion requires "
            "a live MCP-connected coding agent session."
        ),
        "cursor_observability": {
            "overhaust_context_size": "measurable (bytes, files, symbols, lines, flow steps, MCP latency)",
            "repository_exploration_tool_activity": (
                "not directly observable from OverHaust; count Glob/Grep/Read in a "
                "manual Cursor Agent session with and without the alwaysApply rule"
            ),
            "cursor_model_token_usage": (
                "not exposed by Cursor's API; do not treat hook merge logs as model tokens"
            ),
        },
    }
