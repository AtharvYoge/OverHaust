"""
Parse UserPromptSubmit hook stdin and format agent-facing stdout JSON.

Codex/Claude consume hookSpecificOutput.additionalContext.
Cursor beforeSubmitPrompt does not have a supported model-injection field;
Cursor output must not pretend additionalContext reaches the agent.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


HOOK_EVENT_NAME = "UserPromptSubmit"
CURSOR_HOOK_EVENT = "beforeSubmitPrompt"


@dataclass
class HookInput:
    prompt: str
    cwd: str
    hook_event_name: str = HOOK_EVENT_NAME
    project_id_override: Optional[str] = None
    workspace_roots: List[str] = field(default_factory=list)
    cwd_from_stdin: bool = False


def is_cursor_hook_event(event_name: str) -> bool:
    return (event_name or "").strip() == CURSOR_HOOK_EVENT


def is_cursor_hook(hook_input: HookInput) -> bool:
    """True for Cursor beforeSubmitPrompt, including workspace_roots-only stdin."""
    if is_cursor_hook_event(hook_input.hook_event_name):
        return True
    return (not hook_input.cwd_from_stdin) and bool(hook_input.workspace_roots)


def _workspace_roots_from_payload(data: Dict[str, Any]) -> List[str]:
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


def parse_hook_input(raw: str) -> HookInput:
    """Parse Codex/Claude/Cursor UserPromptSubmit stdin JSON."""
    if not raw or not raw.strip():
        raise ValueError("empty hook stdin")

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("hook stdin must be a JSON object")

    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required in hook stdin")

    roots = _workspace_roots_from_payload(data)
    raw_cwd = (data.get("cwd") or "").strip()
    cwd_from_stdin = bool(raw_cwd)
    cwd = raw_cwd
    if not cwd and roots:
        cwd = roots[0]
    if not cwd:
        cwd = os.getcwd().strip()

    event = (data.get("hook_event_name") or "").strip() or HOOK_EVENT_NAME

    override = os.getenv("OVERHAUST_PROJECT_ID", "").strip() or None

    return HookInput(
        prompt=prompt,
        cwd=cwd,
        hook_event_name=event,
        project_id_override=override,
        workspace_roots=roots,
        cwd_from_stdin=cwd_from_stdin,
    )


def format_hook_output(additional_context: str) -> str:
    """Emit Claude/Codex-compatible UserPromptSubmit hook stdout JSON."""
    payload: Dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT_NAME,
            "additionalContext": additional_context,
        }
    }
    return json.dumps(payload, separators=(",", ":"))


def format_empty_hook_output() -> str:
    """Fail-open: valid Codex/Claude hook JSON with empty additional context."""
    return format_hook_output("")


def format_cursor_hook_output() -> str:
    """Native Cursor beforeSubmitPrompt response — continue only, no injection fields."""
    return json.dumps({"continue": True}, separators=(",", ":"))


def peek_hook_event_name(raw: str) -> str:
    """Best-effort event name from raw stdin; empty on parse failure."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("hook_event_name") or "").strip()


def peek_is_cursor_stdin(raw: str) -> bool:
    """Fail-open helper: detect Cursor stdin without fully parsing prompt."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(data, dict):
        return False
    if is_cursor_hook_event(str(data.get("hook_event_name") or "")):
        return True
    cwd = (data.get("cwd") or "").strip()
    return (not cwd) and bool(_workspace_roots_from_payload(data))
