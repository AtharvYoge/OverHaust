"""
UserPromptSubmit interception adapter — calls invoke_context_request() only
for Codex/Claude. Cursor beforeSubmitPrompt is not a model-injection path.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from packages.context.agent_context import (
    invoke_context_request,
    resolve_project_id,
)
from packages.context.benchmark import simulate_naive_agent_exploration
from packages.integrations.debug import (
    InterceptionDebugReport,
    emit_debug_report,
    prompt_hash,
)
from packages.integrations.hook_io import (
    HookInput,
    format_cursor_hook_output,
    format_hook_output,
    is_cursor_hook,
)
from packages.tokenization.token_estimator import TokenEstimator

CONTEXT_MARKER = "<!-- overhaust-context -->"

CURSOR_INJECTION_MODE = "none_cursor_uses_mcp_rule"
CODEX_INJECTION_MODE = "codex_additional_context"


@dataclass
class InterceptionResult:
    hook_stdout: str
    additional_context: str
    project_id: str
    debug: InterceptionDebugReport
    response_payload: Optional[Dict[str, Any]] = None


def _format_injectable_context(context: str) -> str:
    text = (context or "").strip()
    if not text:
        return ""
    return f"{CONTEXT_MARKER}\n\n{text}"


def _resolve_project(hook_input: HookInput, memory_store) -> Optional[str]:
    if hook_input.project_id_override:
        return hook_input.project_id_override
    return resolve_project_id(hook_input.cwd, memory_store=memory_store)


def run_cursor_before_submit_hook(
    hook_input: HookInput,
    *,
    memory_store=None,
) -> InterceptionResult:
    """
    Cursor beforeSubmitPrompt handler.

    Does not assemble or inject context. Cursor Agent must call MCP
    get_relevant_context via the alwaysApply rule. Fail-open with continue.
    """
    t0 = time.perf_counter()
    debug = InterceptionDebugReport(
        prompt_length=len(hook_input.prompt),
        prompt_hash=prompt_hash(hook_input.prompt),
        injection_mode=CURSOR_INJECTION_MODE,
    )
    try:
        if memory_store is None:
            from packages.memory.memory_store import get_memory_store
            memory_store = get_memory_store()
        debug.project_id = _resolve_project(hook_input, memory_store) or ""
    except Exception as exc:
        debug.error = str(exc)

    debug.latency_ms = int((time.perf_counter() - t0) * 1000)
    emit_debug_report(debug)
    return InterceptionResult(
        hook_stdout=format_cursor_hook_output(),
        additional_context="",
        project_id=debug.project_id,
        debug=debug,
        response_payload=None,
    )


def run_user_prompt_interception(
    hook_input: HookInput,
    *,
    memory_store=None,
    include_naive_baseline: Optional[bool] = None,
) -> InterceptionResult:
    """
    Resolve project from cwd, invoke canonical context engine, format hook output.

    Codex/Claude: hookSpecificOutput.additionalContext.
    Cursor beforeSubmitPrompt: continue only — no model injection.

    Fail-open on errors.
    """
    if is_cursor_hook(hook_input):
        return run_cursor_before_submit_hook(hook_input, memory_store=memory_store)

    if memory_store is None:
        from packages.memory.memory_store import get_memory_store
        memory_store = get_memory_store()

    if include_naive_baseline is None:
        include_naive_baseline = os.getenv(
            "OVERHAUST_INTEGRATION_DEBUG", "",
        ).strip().lower() in {"1", "true", "yes", "on"}

    debug = InterceptionDebugReport(
        prompt_length=len(hook_input.prompt),
        prompt_hash=prompt_hash(hook_input.prompt),
        injection_mode=CODEX_INJECTION_MODE,
    )
    t0 = time.perf_counter()

    try:
        project_id = _resolve_project(hook_input, memory_store)
        if not project_id:
            raise ValueError(
                f"no registered OverHaust project for cwd={hook_input.cwd!r}; "
                "register and index the project first"
            )

        debug.project_id = project_id
        response = invoke_context_request(
            project_id,
            hook_input.prompt,
            memory_store=memory_store,
        )
        additional = _format_injectable_context(response.context)
        payload = response.to_dict()

        estimator = TokenEstimator()
        debug.relevant_files = [
            f.get("path", "") for f in payload.get("relevant_files", []) if f.get("path")
        ]
        debug.relevant_symbols = [
            s.get("name", "") for s in payload.get("relevant_symbols", []) if s.get("name")
        ]
        debug.context_bytes = len(additional.encode("utf-8"))
        debug.estimated_context_tokens = estimator.estimate_tokens(additional)
        debug.latency_ms = response.metrics.latency_ms
        debug.code_flow_used = response.metrics.code_flow_included
        debug.insufficient_evidence = response.insufficient_evidence

        if include_naive_baseline:
            try:
                naive = simulate_naive_agent_exploration(
                    project_id,
                    hook_input.prompt,
                    memory_store=memory_store,
                )
                naive_tokens = naive["estimated_context_tokens"]
                debug.estimated_naive_tokens = naive_tokens
                if naive_tokens > 0:
                    debug.reduction_pct = round(
                        (1.0 - (debug.estimated_context_tokens / naive_tokens)) * 100.0,
                        2,
                    )
            except Exception:
                pass

        hook_stdout = format_hook_output(additional)
        debug.latency_ms = int((time.perf_counter() - t0) * 1000)
        emit_debug_report(debug)

        return InterceptionResult(
            hook_stdout=hook_stdout,
            additional_context=additional,
            project_id=project_id,
            debug=debug,
            response_payload=payload,
        )

    except Exception as exc:
        debug.latency_ms = int((time.perf_counter() - t0) * 1000)
        debug.error = str(exc)
        emit_debug_report(debug)
        return InterceptionResult(
            hook_stdout=format_hook_output(""),
            additional_context="",
            project_id=debug.project_id,
            debug=debug,
            response_payload=None,
        )
