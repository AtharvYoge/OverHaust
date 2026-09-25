"""Fail-closed checks before a live Layer 3 experiment. Ingest does not use this."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence


class ExperimentIntegrityError(RuntimeError):
    """Live Layer 3 must not start when isolation or configuration is unproven."""


def validate_layer3_live_ready(
    *,
    model: Optional[str],
    tasks: Sequence[Any],
    requested_repo_size: str,
    fixture_repository_size: Optional[str],
    restore_status: Optional[Dict[str, Any]],
    tool_set_hash_value: Optional[str],
    temperature: Optional[float],
    max_tool_calls: Optional[int],
    timeout_s: Optional[int],
    max_output_tokens: Optional[int],
) -> Dict[str, Any]:
    problems = []
    if not model:
        problems.append("missing model")
    if not tasks:
        problems.append("missing task prompt")
    for task in tasks:
        prompt = getattr(task, "prompt", None)
        task_id = getattr(task, "task_id", None)
        if not prompt:
            problems.append(f"missing task prompt: {task_id}")
    if requested_repo_size != fixture_repository_size:
        problems.append(
            f"requested repo size {requested_repo_size!r} != "
            f"fixture repository size {fixture_repository_size!r}"
        )
    status = restore_status or {}
    if status.get("status") != "KNOWN" or status.get("verified") is not True:
        problems.append("repository restoration unavailable when isolation is required")
    if not tool_set_hash_value:
        problems.append("missing tool contract")
    if temperature is None or max_tool_calls is None or timeout_s is None or max_output_tokens is None:
        problems.append("mismatched condition configuration")
    if problems:
        raise ExperimentIntegrityError("; ".join(problems))
    return {
        "ok": True,
        "model": model,
        "requested_repo_size": requested_repo_size,
        "fixture_repository_size": fixture_repository_size,
        "restore_status": status.get("status"),
        "restore_verified": True,
        "tool_set_hash": tool_set_hash_value,
    }
