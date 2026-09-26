"""Release native resources before the pytest process exits.

A full-suite run on macOS can pass every test and then abort at interpreter
shutdown (`recursive_mutex lock failed: Invalid argument`) when a sqlite
finalizer or an unreaped child runs after another native library has torn
down libc++ mutexes. This hook runs while the interpreter is still healthy.
"""

from __future__ import annotations

import gc
import sqlite3
import subprocess


def _close_sqlite_connections() -> None:
    for obj in gc.get_objects():
        if isinstance(obj, sqlite3.Connection):
            try:
                obj.close()
            except sqlite3.Error:
                pass


def _reap_subprocess_children() -> None:
    active = list(getattr(subprocess, "_active", []) or [])
    for proc in active:
        try:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.wait()
            except Exception:
                pass


def pytest_sessionfinish(session, exitstatus):
    del session, exitstatus
    gc.collect()
    _close_sqlite_connections()
    gc.collect()
    _close_sqlite_connections()
    _reap_subprocess_children()
