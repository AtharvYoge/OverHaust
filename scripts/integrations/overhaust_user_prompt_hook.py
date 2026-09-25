#!/usr/bin/env python3
"""
OverHaust agent hook adapter.

Codex / Claude Code UserPromptSubmit:
  reads stdin JSON, calls invoke_context_request(), prints
  hookSpecificOutput.additionalContext.

Cursor beforeSubmitPrompt:
  does not inject model context. Prints native {continue: true}.
  Cursor Agent must call MCP get_relevant_context via the alwaysApply rule.

Usage (configured by agent hooks):
  python3 scripts/integrations/overhaust_user_prompt_hook.py

Environment:
  OVERHAUST_PROJECT_ID     Force project_id (optional; default: resolve from cwd)
  OVERHAUST_INTEGRATION_DEBUG=1   Emit safe debug JSON to stderr
  OVERHAUST_INTEGRATION_DEBUG_FILE  Append debug JSON lines to file
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.integrations.hook_io import (  # noqa: E402
    format_cursor_hook_output,
    format_empty_hook_output,
    parse_hook_input,
    peek_is_cursor_stdin,
)
from packages.integrations.interception import run_user_prompt_interception  # noqa: E402


def main() -> int:
    raw = sys.stdin.read()
    try:
        hook_input = parse_hook_input(raw)
        result = run_user_prompt_interception(hook_input)
        print(result.hook_stdout, end="", flush=True)
        return 0
    except Exception:
        if peek_is_cursor_stdin(raw):
            print(format_cursor_hook_output(), end="", flush=True)
        else:
            print(format_empty_hook_output(), end="", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
