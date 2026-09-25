#!/usr/bin/env python3
"""
OverHaust → Cline UserPromptSubmit hook.

Cline stdin/stdout protocol (NOT Codex/Claude hook_io):
  Input:  { userPromptSubmit: { prompt }, workspaceRoots, clineVersion, ... }
  Output: { cancel: bool, contextModification: str, errorMessage: str }

Calls invoke_context_request() only. Does not use packages.integrations.hook_io
formatters (those emit Codex/Claude additionalContext).

Fail-open: empty contextModification + cancel=false on any error.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONTEXT_MARKER = "<!-- overhaust-context -->"


def _empty() -> str:
    return json.dumps(
        {"cancel": False, "contextModification": "", "errorMessage": ""},
        separators=(",", ":"),
    )


def _emit(context: str, *, cancel: bool = False, error: str = "") -> str:
    return json.dumps(
        {
            "cancel": cancel,
            "contextModification": context,
            "errorMessage": error,
        },
        separators=(",", ":"),
    )


def _parse_cline_stdin(raw: str) -> Dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("hook stdin must be a JSON object")
    return data


def _prompt_from(data: Dict[str, Any]) -> str:
    nested = data.get("userPromptSubmit")
    if isinstance(nested, dict):
        prompt = (nested.get("prompt") or "").strip()
        if prompt:
            return prompt
    return (data.get("prompt") or "").strip()


def _cwd_from(data: Dict[str, Any]) -> str:
    roots = data.get("workspaceRoots") or data.get("workspace_roots") or []
    if isinstance(roots, str):
        roots = [roots]
    if isinstance(roots, list):
        for item in roots:
            text = str(item or "").strip()
            if text:
                return text
    cwd = (data.get("cwd") or "").strip()
    return cwd or os.getcwd()


def main() -> int:
    raw = sys.stdin.read()
    try:
        data = _parse_cline_stdin(raw)
        prompt = _prompt_from(data)
        if not prompt:
            print(_empty(), end="", flush=True)
            return 0

        cwd = _cwd_from(data)
        from packages.context.agent_context import invoke_context_request, resolve_project_id
        from packages.memory.memory_store import get_memory_store

        memory_store = get_memory_store()
        override = os.getenv("OVERHAUST_PROJECT_ID", "").strip() or None
        project_id = override or resolve_project_id(cwd, memory_store=memory_store)
        if not project_id:
            print(_empty(), end="", flush=True)
            return 0

        response = invoke_context_request(
            project_id,
            prompt,
            memory_store=memory_store,
        )
        text = (response.context or "").strip()
        if not text:
            print(_empty(), end="", flush=True)
            return 0
        print(_emit(f"{CONTEXT_MARKER}\n\n{text}"), end="", flush=True)
        return 0
    except Exception:
        print(_empty(), end="", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
