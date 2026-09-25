"""Subprocess end-to-end tests for the UserPromptSubmit hook script."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from packages.integrations.interception import CONTEXT_MARKER
from packages.memory.memory_store import MemoryStore
from packages.retrieval.test_fixtures import make_kot_tree
from services.ingestion.index_store import ProjectIndexStore

ROOT = Path(__file__).resolve().parents[2]
HOOK_SCRIPT = ROOT / "scripts" / "integrations" / "overhaust_user_prompt_hook.py"


@pytest.fixture
def indexed_env(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()
    root = Path(tmpdir)
    make_kot_tree(root)
    store = MemoryStore(db.name)
    store.add_project("e2e-p", "E2E", "", str(root))
    ProjectIndexStore(store).sync_project("e2e-p", str(root))

    monkeypatch.setenv("OVERHAUST_DB_PATH", db.name)
    yield str(root), db.name
    if os.path.exists(db.name):
        os.unlink(db.name)


def _run_hook(stdin_payload: dict, env: dict | None = None) -> subprocess.CompletedProcess:
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    return subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps(stdin_payload),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        env=run_env,
        timeout=60,
    )


def test_hook_script_e2e_produces_additional_context(indexed_env):
    root, _ = indexed_env
    proc = _run_hook({"prompt": "Where is the KOT generated?", "cwd": root})
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert CONTEXT_MARKER in ctx
    assert "KOT" in ctx or "kot" in ctx.lower()


def test_hook_script_e2e_debug_stderr(indexed_env):
    root, _ = indexed_env
    proc = _run_hook(
        {"prompt": "Add kitchen printers", "cwd": root},
        env={"OVERHAUST_INTEGRATION_DEBUG": "1"},
    )
    assert proc.returncode == 0
    assert proc.stderr.strip()
    debug = json.loads(proc.stderr.strip().splitlines()[-1])
    assert debug["project_id"] == "e2e-p"
    assert "prompt_hash" in debug
    assert "Add kitchen printers" not in proc.stderr


def test_hook_script_fail_open_bad_cwd(indexed_env):
    proc = _run_hook({"prompt": "hello", "cwd": "/no/such/project"})
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["hookSpecificOutput"]["additionalContext"] == ""


def test_hook_script_cursor_event_does_not_emit_additional_context(indexed_env):
    root, _ = indexed_env
    proc = _run_hook({
        "prompt": "Where is the KOT generated?",
        "workspace_roots": [root],
        "hook_event_name": "beforeSubmitPrompt",
    })
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out.get("continue") is True
    assert "additionalContext" not in json.dumps(out)
    assert "hookSpecificOutput" not in out
