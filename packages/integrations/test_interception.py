"""Tests for hook I/O and interception adapter."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from packages.integrations.debug import InterceptionDebugReport, prompt_hash
from packages.integrations.hook_io import (
    CURSOR_HOOK_EVENT,
    HOOK_EVENT_NAME,
    format_cursor_hook_output,
    format_hook_output,
    parse_hook_input,
)
from packages.integrations.interception import (
    CONTEXT_MARKER,
    CURSOR_INJECTION_MODE,
    run_user_prompt_interception,
)
from packages.integrations.hook_io import HookInput
from packages.memory.memory_store import MemoryStore
from packages.retrieval.test_fixtures import make_kot_tree
from services.ingestion.index_store import ProjectIndexStore


@pytest.fixture
def indexed_project():
    tmpdir = tempfile.mkdtemp()
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()
    root = Path(tmpdir)
    make_kot_tree(root)
    store = MemoryStore(db.name)
    store.add_project("hook-p", "HookTest", "", str(root))
    ProjectIndexStore(store).sync_project("hook-p", str(root))
    yield store, str(root), db.name
    if os.path.exists(db.name):
        os.unlink(db.name)


def test_prompt_hash_is_prefix_only():
    h = prompt_hash("hello world")
    assert len(h) == 12
    assert h != "hello world"


def test_parse_hook_input_requires_prompt():
    with pytest.raises(ValueError, match="prompt"):
        parse_hook_input('{"cwd": "/tmp"}')


def test_parse_hook_input_reads_fields():
    raw = json.dumps({"prompt": "Add printers", "cwd": "/repo", "hook_event_name": "UserPromptSubmit"})
    parsed = parse_hook_input(raw)
    assert parsed.prompt == "Add printers"
    assert parsed.cwd == "/repo"
    assert parsed.hook_event_name == HOOK_EVENT_NAME


def test_parse_hook_input_workspace_roots_when_cwd_absent():
    raw = json.dumps({
        "prompt": "Add printers",
        "workspace_roots": ["/repo/from/roots"],
        "hook_event_name": "beforeSubmitPrompt",
    })
    parsed = parse_hook_input(raw)
    assert parsed.cwd == "/repo/from/roots"
    assert parsed.workspace_roots == ["/repo/from/roots"]
    assert parsed.hook_event_name == CURSOR_HOOK_EVENT
    assert parsed.cwd_from_stdin is False


def test_parse_hook_input_cwd_wins_over_workspace_roots():
    raw = json.dumps({
        "prompt": "Add printers",
        "cwd": "/explicit/cwd",
        "workspace_roots": ["/repo/from/roots"],
    })
    parsed = parse_hook_input(raw)
    assert parsed.cwd == "/explicit/cwd"
    assert parsed.workspace_roots == ["/repo/from/roots"]


def test_format_cursor_hook_output_has_no_additional_context():
    out = json.loads(format_cursor_hook_output())
    assert out == {"continue": True}
    assert "additionalContext" not in json.dumps(out)
    assert "hookSpecificOutput" not in out
    assert "user_message" not in out


def test_format_hook_output_shape():
    out = format_hook_output("context body")
    data = json.loads(out)
    assert data["hookSpecificOutput"]["hookEventName"] == HOOK_EVENT_NAME
    assert data["hookSpecificOutput"]["additionalContext"] == "context body"


def test_run_interception_resolves_project_from_cwd(indexed_project):
    store, root, _ = indexed_project
    hook_input = HookInput(prompt="Where is the KOT generated?", cwd=root)
    result = run_user_prompt_interception(
        hook_input,
        memory_store=store,
        include_naive_baseline=False,
    )
    assert result.project_id == "hook-p"
    assert CONTEXT_MARKER in result.additional_context
    assert result.additional_context
    assert result.debug.prompt_length > 0
    assert result.debug.prompt_hash
    assert result.debug.relevant_files
    assert result.debug.latency_ms >= 0


def test_codex_hook_keeps_additional_context_when_cwd_present(indexed_project):
    store, root, _ = indexed_project
    hook_input = parse_hook_input(json.dumps({
        "prompt": "Where is the KOT generated?",
        "cwd": root,
        "workspace_roots": [root],
        "hook_event_name": "UserPromptSubmit",
    }))
    result = run_user_prompt_interception(
        hook_input,
        memory_store=store,
        include_naive_baseline=False,
    )
    assert hook_input.cwd_from_stdin is True
    assert CONTEXT_MARKER in result.additional_context
    assert "additionalContext" in result.hook_stdout


def test_workspace_roots_without_event_name_does_not_inject(indexed_project):
    store, root, _ = indexed_project
    hook_input = parse_hook_input(json.dumps({
        "prompt": "Where is the KOT generated?",
        "workspace_roots": [root],
    }))
    result = run_user_prompt_interception(
        hook_input,
        memory_store=store,
        include_naive_baseline=False,
    )
    assert hook_input.cwd_from_stdin is False
    assert result.additional_context == ""
    assert "additionalContext" not in result.hook_stdout
    assert json.loads(result.hook_stdout).get("continue") is True
    assert result.debug.injection_mode == CURSOR_INJECTION_MODE
    assert result.project_id == "hook-p"


def test_cursor_before_submit_does_not_inject_additional_context(indexed_project):
    store, root, _ = indexed_project
    hook_input = parse_hook_input(json.dumps({
        "prompt": "Where is the KOT generated?",
        "workspace_roots": [root],
        "hook_event_name": "beforeSubmitPrompt",
    }))
    result = run_user_prompt_interception(
        hook_input,
        memory_store=store,
        include_naive_baseline=False,
    )
    assert result.additional_context == ""
    stdout = json.loads(result.hook_stdout)
    assert stdout.get("continue") is True
    assert "additionalContext" not in json.dumps(stdout)
    assert result.debug.injection_mode == CURSOR_INJECTION_MODE
    assert result.project_id == "hook-p"


def test_run_interception_fail_open_unknown_cwd(indexed_project):
    store, _, _ = indexed_project
    hook_input = HookInput(prompt="Add printers", cwd="/nonexistent/path")
    result = run_user_prompt_interception(
        hook_input,
        memory_store=store,
        include_naive_baseline=False,
    )
    assert result.additional_context == ""
    assert result.debug.error


def test_debug_report_never_contains_full_prompt(indexed_project, capsys):
    store, root, _ = indexed_project
    secret_prompt = "SECRET_PROMPT_TOKEN_xyz Add kitchen printers"
    os.environ["OVERHAUST_INTEGRATION_DEBUG"] = "1"
    try:
        hook_input = HookInput(prompt=secret_prompt, cwd=root)
        run_user_prompt_interception(
            hook_input,
            memory_store=store,
            include_naive_baseline=True,
        )
        captured = capsys.readouterr()
        assert secret_prompt not in captured.err
        debug = json.loads(captured.err.strip().splitlines()[-1])
        assert debug["prompt_length"] == len(secret_prompt)
        assert debug["prompt_hash"] == prompt_hash(secret_prompt)
        assert "reduction_pct" in debug or debug.get("estimated_naive_tokens") is not None
    finally:
        os.environ.pop("OVERHAUST_INTEGRATION_DEBUG", None)


def test_interception_debug_report_fields():
    report = InterceptionDebugReport(
        prompt_length=10,
        prompt_hash="abc",
        project_id="p",
        relevant_files=["a.dart"],
        relevant_symbols=["Foo"],
        context_bytes=100,
        estimated_context_tokens=25,
        latency_ms=50,
        code_flow_used=True,
    )
    d = report.to_dict()
    assert d["relevant_files"] == ["a.dart"]
    assert d["code_flow_used"] is True
