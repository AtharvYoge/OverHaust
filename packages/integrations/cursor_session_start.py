"""
Cursor headless `sessionStart` hook.

The desktop Cursor integration stays MCP + alwaysApply rule:
`beforeSubmitPrompt` does not inject model context, and it does not fire in
headless `cursor-agent` runs. Headless runs do fire `sessionStart`, and that
hook's `additional_context` reaches the model. This module is that path.

It calls `invoke_context_request(project_id, prompt, memory_store=...)` only.
It does not retrieve context itself.

Prompt source
-------------
`sessionStart` stdin has no user prompt, and Cursor's own `session_id` does
not exist until the hook runs, so the harness cannot key the prompt on that
id in advance. The harness writes a per-session JSON file (mode 0600) and
points this process at it with `OVERHAUST_CURSOR_PROMPT_FILE`. The file holds
the harness session id, the workspace root, and the task prompt. The hook
reads it only when:

- `OVERHAUST_CURSOR_SESSION_ID` matches the file's harness session id, and
- the file's workspace root is one of stdin `workspace_roots`.

The prompt is not taken from the environment, not written into the debug
record (hash and length only), and not reused for a different workspace.
A resolver or seam error returns no context and is logged.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from packages.context.agent_context import invoke_context_request, resolve_project_id
from packages.integrations.debug import prompt_hash
from packages.integrations.interception import CONTEXT_MARKER
from packages.tokenization.token_estimator import TokenEstimator

logger = logging.getLogger("overhaust.integration")

PROMPT_FILE_ENV = "OVERHAUST_CURSOR_PROMPT_FILE"
SESSION_ID_ENV = "OVERHAUST_CURSOR_SESSION_ID"
INJECTION_MODE = "cursor_session_start_additional_context"
HOOK_EVENT = "sessionStart"
_MAX_PROMPT_FILE_BYTES = 1_000_000
_MAX_ERROR_CHARS = 500


@dataclass
class SessionStartInput:
    session_id: str
    conversation_id: str
    generation_id: str
    workspace_roots: List[str]
    model: str
    cursor_version: str
    hook_event_name: str


@dataclass
class SessionStartResult:
    stdout: str
    additional_context: str
    project_id: str
    debug: Dict[str, Any] = field(default_factory=dict)


def _safe_error(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    if len(text) > _MAX_ERROR_CHARS:
        return text[:_MAX_ERROR_CHARS] + "…"
    return text


def _workspace_roots(data: Dict[str, Any]) -> List[str]:
    raw = data.get("workspace_roots") or data.get("workspaceRoots") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    roots: List[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            roots.append(text)
    return roots


def parse_session_start_stdin(raw: str) -> SessionStartInput:
    if not raw or not raw.strip():
        raise ValueError("empty sessionStart stdin")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("sessionStart stdin must be a JSON object")
    event = str(data.get("hook_event_name") or "").strip()
    if event != HOOK_EVENT:
        raise ValueError(f"expected hook_event_name {HOOK_EVENT!r}, got {event!r}")
    session_id = str(data.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("sessionStart stdin is missing session_id")
    roots = _workspace_roots(data)
    if not roots:
        raise ValueError("sessionStart stdin is missing workspace_roots")
    return SessionStartInput(
        session_id=session_id,
        conversation_id=str(data.get("conversation_id") or ""),
        generation_id=str(data.get("generation_id") or ""),
        workspace_roots=roots,
        model=str(data.get("model") or ""),
        cursor_version=str(data.get("cursor_version") or ""),
        hook_event_name=event,
    )


def _paths_match(left: str, right: str) -> bool:
    return Path(left).expanduser().resolve() == Path(right).expanduser().resolve()


def load_task_prompt(workspace_roots: List[str]) -> tuple[str, str]:
    """
    Return `(prompt, harness_session_id)` from the harness prompt file.

    Raises ValueError when the file is missing, unbound, or for another
    workspace. Does not fall back to any other prompt source.
    """
    file_raw = os.environ.get(PROMPT_FILE_ENV, "").strip()
    expected_session = os.environ.get(SESSION_ID_ENV, "").strip()
    if not file_raw:
        raise ValueError(f"{PROMPT_FILE_ENV} is not set")
    if not expected_session:
        raise ValueError(f"{SESSION_ID_ENV} is not set")
    path = Path(file_raw).expanduser()
    if not path.is_file():
        raise ValueError("task prompt file is missing")
    size = path.stat().st_size
    if size > _MAX_PROMPT_FILE_BYTES:
        raise ValueError("task prompt file is unexpectedly large")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"task prompt file is not JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("task prompt file must be a JSON object")
    file_session = str(payload.get("harness_session_id") or "").strip()
    if file_session != expected_session:
        raise ValueError("prompt file session id does not match the harness session")
    workspace = str(payload.get("workspace_root") or "").strip()
    if not workspace or not any(_paths_match(workspace, root) for root in workspace_roots):
        raise ValueError("prompt file workspace does not match sessionStart workspace_roots")
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("task prompt file is empty")
    return prompt, file_session


def format_session_start_output(additional_context: str) -> str:
    """Return JSON. No context is `{}`, not an empty additional_context string."""
    text = additional_context or ""
    if not text:
        return "{}"
    return json.dumps({"additional_context": text}, separators=(",", ":"))


def _format_injectable(context: str) -> str:
    text = (context or "").strip()
    if not text:
        return ""
    return f"{CONTEXT_MARKER}\n\n{text}"


def _open_memory_store(memory_store):
    if memory_store is not None:
        return memory_store
    db_path = os.environ.get("OVERHAUST_DB_PATH", "").strip()
    if not db_path or not Path(db_path).is_file():
        raise ValueError("OVERHAUST_DB_PATH is missing")
    from packages.memory.memory_store import MemoryStore

    return MemoryStore(db_path)


def _resolve_project(workspace_root: str, memory_store) -> str:
    override = os.environ.get("OVERHAUST_PROJECT_ID", "").strip()
    if override:
        return override
    resolved = resolve_project_id(workspace_root, memory_store=memory_store)
    if not resolved:
        raise ValueError(
            f"no registered OverHaust project for cwd={workspace_root!r}; "
            "register and index the project first"
        )
    return resolved


def _debug_payload(
    *,
    error: Optional[str],
    context_bytes: Optional[int],
    estimated_tokens: Optional[int],
    latency_ms: int,
    project_id: str,
    prompt: str,
    harness_session_id: str,
    cursor_session_id: str,
) -> Dict[str, Any]:
    bytes_known = context_bytes is not None
    tokens_known = estimated_tokens is not None
    return {
        "fired": True,
        "error": error,
        "context_bytes": context_bytes if bytes_known else None,
        "context_bytes_kind": "exact" if bytes_known else "unavailable",
        "estimated_context_tokens": estimated_tokens if tokens_known else None,
        "estimated_context_tokens_kind": "estimated" if tokens_known else "unavailable",
        "latency_ms": latency_ms,
        "latency_ms_kind": "exact",
        "injection_mode": INJECTION_MODE,
        "project_id": project_id,
        "prompt_length": len(prompt),
        "prompt_hash": prompt_hash(prompt) if prompt else "",
        "harness_session_id": harness_session_id,
        "cursor_session_id": cursor_session_id,
        "hook_event_name": HOOK_EVENT,
    }


def _emit_debug(payload: Dict[str, Any]) -> None:
    line = json.dumps(payload, separators=(",", ":"))
    debug_file = os.environ.get("OVERHAUST_INTEGRATION_DEBUG_FILE", "").strip()
    debug_on = os.environ.get("OVERHAUST_INTEGRATION_DEBUG", "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    if debug_on:
        print(line, file=__import__("sys").stderr, flush=True)
    if debug_file:
        path = os.path.expanduser(debug_file)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    if payload.get("error"):
        logger.warning(
            "cursor_session_start project_id=%s error=%s latency_ms=%s",
            payload.get("project_id") or "-",
            payload.get("error"),
            payload.get("latency_ms"),
        )


def run_cursor_session_start(raw: str, *, memory_store=None) -> SessionStartResult:
    """
    Resolve the project, call the production context seam, emit additional_context.

    Fail-open: every error path returns `{}` and writes a debug record.
    """
    started = time.perf_counter()
    prompt = ""
    harness_session_id = ""
    cursor_session_id = ""
    project_id = ""

    def finish(
        *,
        error: Optional[str],
        additional: str,
        context_bytes: Optional[int],
        estimated_tokens: Optional[int],
    ) -> SessionStartResult:
        latency_ms = int((time.perf_counter() - started) * 1000)
        debug = _debug_payload(
            error=error,
            context_bytes=context_bytes,
            estimated_tokens=estimated_tokens,
            latency_ms=latency_ms,
            project_id=project_id,
            prompt=prompt,
            harness_session_id=harness_session_id,
            cursor_session_id=cursor_session_id,
        )
        _emit_debug(debug)
        return SessionStartResult(
            stdout=format_session_start_output(additional),
            additional_context=additional,
            project_id=project_id,
            debug=debug,
        )

    try:
        hook_input = parse_session_start_stdin(raw)
        cursor_session_id = hook_input.session_id
        prompt, harness_session_id = load_task_prompt(hook_input.workspace_roots)
        store = _open_memory_store(memory_store)
        project_id = _resolve_project(hook_input.workspace_roots[0], store)
        response = invoke_context_request(project_id, prompt, memory_store=store)
        additional = _format_injectable(response.context)
        if not additional:
            return finish(
                error="empty context",
                additional="",
                context_bytes=0,
                estimated_tokens=TokenEstimator().estimate_tokens(""),
            )
        estimated = TokenEstimator().estimate_tokens(additional)
        return finish(
            error=None,
            additional=additional,
            context_bytes=len(additional.encode("utf-8")),
            estimated_tokens=estimated,
        )
    except Exception as exc:
        return finish(
            error=_safe_error(exc),
            additional="",
            context_bytes=None,
            estimated_tokens=None,
        )
