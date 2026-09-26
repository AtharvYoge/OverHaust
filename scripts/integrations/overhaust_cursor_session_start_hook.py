#!/usr/bin/env python3
"""
Cursor sessionStart hook for headless cursor-agent.

Reads sessionStart stdin, loads the per-session task prompt written by the
Layer 4 harness, calls invoke_context_request, and prints
{"additional_context": "..."} . On any error it prints {} and logs the error.

The task prompt is not in the environment. See
packages.integrations.cursor_session_start for the file-binding rules.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.integrations.cursor_session_start import (  # noqa: E402
    run_cursor_session_start,
)


def _release_before_exit() -> None:
    """Close sqlite and drop cyclic native objects before C++ shutdown.

    On macOS, leaving those finalizers until interpreter teardown can abort
    with `recursive_mutex lock failed` once another native library is loaded.
    """
    import gc
    import sqlite3

    def _close_open_connections() -> None:
        for obj in gc.get_objects():
            if isinstance(obj, sqlite3.Connection):
                try:
                    obj.close()
                except sqlite3.Error:
                    pass

    _close_open_connections()
    gc.collect()
    _close_open_connections()


def main() -> int:
    raw = sys.stdin.read()
    try:
        result = run_cursor_session_start(raw)
        sys.stdout.write(result.stdout)
        sys.stdout.write("\n")
        sys.stdout.flush()
        return 0
    except Exception as exc:
        # The runner already fail-opens. This catches import-time surprises
        # after that call. Still return no context.
        sys.stderr.write(f"cursor sessionStart hook failed: {type(exc).__name__}\n")
        sys.stdout.write("{}\n")
        sys.stdout.flush()
        return 0
    finally:
        _release_before_exit()


if __name__ == "__main__":
    raise SystemExit(main())
