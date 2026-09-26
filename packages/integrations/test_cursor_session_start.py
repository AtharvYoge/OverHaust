"""Cursor sessionStart hook tests. No cursor-agent process."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from packages.integrations.cursor_session_start import (
    INJECTION_MODE,
    PROMPT_FILE_ENV,
    SESSION_ID_ENV,
    format_session_start_output,
    run_cursor_session_start,
)
from packages.integrations.interception import CONTEXT_MARKER
from packages.memory.memory_store import MemoryStore
from packages.retrieval.test_fixtures import make_kot_tree
from services.ingestion.index_store import ProjectIndexStore

ROOT = Path(__file__).resolve().parents[2]
HOOK_SCRIPT = ROOT / "scripts" / "integrations" / "overhaust_cursor_session_start_hook.py"


@pytest.fixture
def indexed_project(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()
    root = Path(tmpdir)
    make_kot_tree(root)
    store = MemoryStore(db.name)
    store.add_project("hook-p", "HookTest", "", str(root))
    ProjectIndexStore(store).sync_project("hook-p", str(root))
    monkeypatch.delenv("OVERHAUST_PROJECT_ID", raising=False)
    monkeypatch.delenv(PROMPT_FILE_ENV, raising=False)
    monkeypatch.delenv(SESSION_ID_ENV, raising=False)
    yield store, root, db.name
    if os.path.exists(db.name):
        os.unlink(db.name)


def _stdin(root: Path, session_id: str = "cursor-sess") -> str:
    return json.dumps({
        "conversation_id": "conv",
        "cursor_version": "3.21.16",
        "generation_id": "gen",
        "hook_event_name": "sessionStart",
        "is_background_agent": False,
        "model": "GPT-5.5 272K Medium",
        "session_id": session_id,
        "transcript_path": None,
        "user_email": "person@example.com",
        "workspace_roots": [str(root)],
    })


def _prompt_file(tmp: Path, workspace: Path, prompt: str, harness_id: str = "task-overhaust-r0") -> Path:
    path = tmp / "task-prompt.json"
    path.write_text(json.dumps({
        "harness_session_id": harness_id,
        "workspace_root": str(workspace),
        "prompt": prompt,
    }), encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def _bind(monkeypatch, prompt_path: Path, harness_id: str = "task-overhaust-r0") -> None:
    monkeypatch.setenv(PROMPT_FILE_ENV, str(prompt_path))
    monkeypatch.setenv(SESSION_ID_ENV, harness_id)


def test_session_start_resolves_project_and_injects(indexed_project, monkeypatch, tmp_path):
    store, root, _db = indexed_project
    prompt = "Where is the KOT generated?"
    path = _prompt_file(tmp_path, root, prompt)
    _bind(monkeypatch, path)
    debug_path = tmp_path / "hook.jsonl"
    monkeypatch.setenv("OVERHAUST_INTEGRATION_DEBUG_FILE", str(debug_path))
    result = run_cursor_session_start(_stdin(root), memory_store=store)
    payload = json.loads(result.stdout)
    assert CONTEXT_MARKER in payload["additional_context"]
    assert result.project_id == "hook-p"
    assert result.debug["fired"] is True
    assert result.debug["error"] is None
    assert result.debug["context_bytes_kind"] == "exact"
    assert result.debug["context_bytes"] > 0
    assert result.debug["estimated_context_tokens_kind"] == "estimated"
    assert result.debug["estimated_context_tokens"] > 0
    assert result.debug["latency_ms_kind"] == "exact"
    assert result.debug["injection_mode"] == INJECTION_MODE
    assert "person@example.com" not in debug_path.read_text(encoding="utf-8")
    assert prompt not in debug_path.read_text(encoding="utf-8")


def test_missing_project_returns_no_context(indexed_project, monkeypatch, tmp_path):
    store, _root, _db = indexed_project
    other = tmp_path / "other-project"
    other.mkdir()
    path = _prompt_file(other, other, "Where is the KOT generated?")
    _bind(monkeypatch, path)
    result = run_cursor_session_start(_stdin(other), memory_store=store)
    assert result.stdout == "{}"
    assert result.additional_context == ""
    assert result.debug["fired"] is True
    assert result.debug["error"]
    assert result.debug["context_bytes"] is None
    assert result.debug["context_bytes_kind"] == "unavailable"
    assert result.debug["estimated_context_tokens"] is None


def test_empty_context_is_not_injected(indexed_project, monkeypatch, tmp_path):
    store, root, _db = indexed_project
    path = _prompt_file(tmp_path, root, "Where is the KOT generated?")
    _bind(monkeypatch, path)

    class Empty:
        context = "  "

    monkeypatch.setattr(
        "packages.integrations.cursor_session_start.invoke_context_request",
        lambda *args, **kwargs: Empty(),
    )
    result = run_cursor_session_start(_stdin(root), memory_store=store)
    assert result.stdout == "{}"
    assert result.debug["error"] == "empty context"
    assert result.debug["context_bytes"] == 0
    assert result.debug["context_bytes_kind"] == "exact"
    assert result.debug["estimated_context_tokens"] == 0
    assert result.debug["estimated_context_tokens_kind"] == "estimated"


def test_prompt_file_does_not_cross_sessions_or_workspaces(indexed_project, monkeypatch, tmp_path):
    store, root, _db = indexed_project
    path = _prompt_file(tmp_path, root, "Where is the KOT generated?", harness_id="session-a")
    _bind(monkeypatch, path, harness_id="session-b")
    mismatch = run_cursor_session_start(_stdin(root), memory_store=store)
    assert mismatch.stdout == "{}"
    assert "session id" in (mismatch.debug["error"] or "")

    other = tmp_path / "elsewhere"
    other.mkdir()
    path = _prompt_file(tmp_path, other, "Where is the KOT generated?", harness_id="session-a")
    _bind(monkeypatch, path, harness_id="session-a")
    wrong_workspace = run_cursor_session_start(_stdin(root), memory_store=store)
    assert wrong_workspace.stdout == "{}"
    assert "workspace" in (wrong_workspace.debug["error"] or "")


def test_project_id_override_is_used_for_a_workspace_copy(indexed_project, monkeypatch, tmp_path):
    store, _root, _db = indexed_project
    copy = tmp_path / "copy"
    copy.mkdir()
    monkeypatch.setenv("OVERHAUST_PROJECT_ID", "hook-p")
    path = _prompt_file(tmp_path, copy, "Where is the KOT generated?")
    _bind(monkeypatch, path)
    result = run_cursor_session_start(_stdin(copy), memory_store=store)
    assert result.project_id == "hook-p"
    assert CONTEXT_MARKER in result.additional_context


def test_missing_prompt_file_fails_open(indexed_project, monkeypatch, tmp_path):
    store, root, _db = indexed_project
    monkeypatch.setenv(PROMPT_FILE_ENV, str(tmp_path / "missing.json"))
    monkeypatch.setenv(SESSION_ID_ENV, "task-overhaust-r0")
    result = run_cursor_session_start(_stdin(root), memory_store=store)
    assert result.stdout == "{}"
    assert "missing" in (result.debug["error"] or "")


def test_format_omits_empty_additional_context():
    assert format_session_start_output("") == "{}"
    encoded = json.loads(format_session_start_output("hello"))
    assert encoded == {"additional_context": "hello"}


def test_hook_script_uses_the_production_seam_and_fails_open(indexed_project, tmp_path):
    source = (ROOT / "packages" / "integrations" / "cursor_session_start.py").read_text(encoding="utf-8")
    assert "invoke_context_request" in source
    assert "packages.retrieval" not in source
    _store, root, db_name = indexed_project
    prompt_path = _prompt_file(tmp_path, root, "Where is the KOT generated?")
    debug_path = tmp_path / "debug.jsonl"
    env = dict(os.environ)
    env["OVERHAUST_DB_PATH"] = db_name
    env["OVERHAUST_PROJECT_ID"] = "hook-p"
    env[PROMPT_FILE_ENV] = str(prompt_path)
    env[SESSION_ID_ENV] = "task-overhaust-r0"
    env["OVERHAUST_INTEGRATION_DEBUG_FILE"] = str(debug_path)
    proc = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=_stdin(root),
        text=True,
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert CONTEXT_MARKER in payload["additional_context"]
    debug = json.loads(debug_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert debug["fired"] is True
    assert "Where is the KOT generated?" not in debug_path.read_text(encoding="utf-8")

    broken = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input="not-json",
        text=True,
        capture_output=True,
        env=env,
        timeout=30,
        check=False,
    )
    assert broken.returncode == 0
    assert json.loads(broken.stdout) == {}
