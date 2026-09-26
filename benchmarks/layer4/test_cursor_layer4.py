"""Layer 4 Cursor adapter tests. Recorded stream-json only; no live cursor-agent."""

from __future__ import annotations

import gc
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from benchmarks.layer4.adapters import require_adapter
from benchmarks.layer4.cli import build_parser, main
from benchmarks.layer4.cursor_adapter import (
    CursorAdapter,
    CursorProbe,
    CursorSessionCapture,
    prompt_sha256,
    session_from_capture,
)
from benchmarks.layer4.cursor_condition import (
    CURSOR_DEFAULT_MODEL,
    PROMPT_CACHE_POLICY,
    CursorStateGuard,
    prepare_session_workspace,
    verify_hook_layout,
)
from benchmarks.layer4.cursor_parse import (
    OVERHAUST_MCP_TOOL_NAMES,
    parse_stream_json,
)
from benchmarks.layer4.cursor_runner import (
    CURSOR_CLAIM_POLICY,
    CursorRunConfig,
    format_cursor_dry_run,
    run_cursor,
    run_cursor_preflight,
)
from benchmarks.layer4.cursor_store import inspect_session_store
from benchmarks.layer4.matrix import load_full_tasks, load_pilot_tasks, plan_matrix, preset_reps
from benchmarks.layer4.runner import Layer4Workspace, ProcessResult, RunConfig, run_pilot
from benchmarks.layer4.schema import Layer4SessionResult
from benchmarks.repro import capture_repository_snapshot
from benchmarks.tasks_loader import load_task_set
from packages.integrations.interception import CONTEXT_MARKER

@pytest.fixture(autouse=True)
def _finalize_native_resources_before_the_next_test():
    """Close sqlite finalizers while the interpreter is still healthy.

    A full-suite run on macOS can abort at shutdown with
    `recursive_mutex lock failed` if sqlite or tokenizer objects are still
    alive after another native library (faiss, torch) has been imported.
    """
    yield
    gc.collect()


FIXTURES = Path(__file__).resolve().parent / "fixtures"
SUCCESS = (FIXTURES / "cursor_stream_success.jsonl").read_text(encoding="utf-8")
SERVER = Path(__file__).resolve().parents[2] / "services" / "mcp_server" / "server.py"


def _workspace(tmp_path: Path):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "kot_generator.ts").write_text(
        "export function generateKOT(orderId: string) { return { orderId }; }\n",
        encoding="utf-8",
    )
    snapshot = capture_repository_snapshot(str(root))

    def builder(_tasks):
        return Layer4Workspace(
            root=root,
            db_path=str(tmp_path / "bench.db"),
            project_id="bench-labkot",
            snapshot=snapshot,
            snapshot_hash=snapshot["tree_hash"],
            repo_size="medium",
        )

    return builder, root, snapshot


def _hook_line() -> str:
    return json.dumps({
        "fired": True,
        "error": None,
        "context_bytes": 240,
        "context_bytes_kind": "exact",
        "estimated_context_tokens": 60,
        "estimated_context_tokens_kind": "estimated",
        "latency_ms": 18,
        "latency_ms_kind": "exact",
        "injection_mode": "cursor_session_start_additional_context",
        "project_id": "bench-labkot",
        "prompt_hash": "abc",
        "prompt_length": 40,
        "harness_session_id": "bound",
        "cursor_session_id": "sess-1",
    })


def _write_store(home: Path, session_id: str, text: str) -> None:
    directory = home / ".cursor" / "chats" / "hash" / session_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "meta.json").write_text("{}\n", encoding="utf-8")
    connection = sqlite3.connect(directory / "store.db")
    try:
        connection.execute("CREATE TABLE blobs (data TEXT)")
        connection.execute("INSERT INTO blobs (data) VALUES (?)", (text,))
        connection.commit()
    finally:
        connection.close()


class FakeCursor:
    def __init__(
        self,
        *,
        stream: str = SUCCESS,
        timeout: bool = False,
        fail: bool = False,
        mutate_home: Path | None = None,
        projects_state: Path | None = None,
        disable_mode: str = "new-slug",
        model_failure: str | None = None,
        store_extra: str | None = None,
    ):
        self.stream = stream
        self.timeout = timeout
        self.fail = fail
        self.mutate_home = mutate_home
        self.projects_state = projects_state
        self.disable_mode = disable_mode
        self.model_failure = model_failure
        self.store_extra = store_extra
        self.calls: list[list[str]] = []
        self.cwds: list[str] = []
        self.launches: list[dict] = []

    def __call__(self, command, env, cwd, timeout):
        argv = [str(part) for part in command]
        self.calls.append(argv)
        self.cwds.append(str(cwd))
        if "--version" in argv:
            return ProcessResult(0, "2026.09.26-dd393fe\n", "", 1, False)
        if "status" in argv:
            return ProcessResult(0, "logged in\n", "", 1, False)
        if "models" in argv or "--list-models" in argv:
            return ProcessResult(0, "gpt-5.5-medium\nGPT-5.5 272K Medium\n", "", 1, False)
        if len(argv) >= 3 and argv[1] == "mcp" and argv[2] == "list":
            if self.projects_state is not None:
                return ProcessResult(0, self._mcp_list_text(), "", 1, False)
            home = Path(env.get("HOME") or cwd)
            mcp = home / ".cursor" / "mcp.json"
            text = mcp.read_text(encoding="utf-8") if mcp.is_file() else ""
            return ProcessResult(0, text, "", 1, False)
        if len(argv) >= 3 and argv[1] == "mcp" and argv[2] == "disable":
            if self.projects_state is not None:
                self._write_disabled_slug(Path(cwd))
            return ProcessResult(0, "disabled overhaust\n", "", 1, False)
        if "-p" in argv and self.model_failure == "raise":
            raise RuntimeError("model exploded")
        if "-p" in argv and self.model_failure == "interrupt":
            raise KeyboardInterrupt()
        if "-p" not in argv:
            return ProcessResult(1, "", "unexpected command", 1, False)
        root = Path(cwd)
        hooks = root / ".cursor" / "hooks.json"
        self.launches.append({
            "command": argv,
            "cwd": cwd,
            "hooks": hooks.is_file(),
            "hooks_text": hooks.read_text(encoding="utf-8") if hooks.is_file() else "",
            "rules": (root / ".cursor" / "rules").exists(),
            "mcp": (root / ".cursor" / "mcp.json").exists(),
            "cursor_files": sorted(path.name for path in (root / ".cursor").rglob("*")) if (root / ".cursor").exists() else [],
            "prompt_file": env.get("OVERHAUST_CURSOR_PROMPT_FILE"),
            "prompt_payload": (
                json.loads(Path(env["OVERHAUST_CURSOR_PROMPT_FILE"]).read_text(encoding="utf-8"))
                if env.get("OVERHAUST_CURSOR_PROMPT_FILE")
                else None
            ),
            "session_env": env.get("OVERHAUST_CURSOR_SESSION_ID"),
            "home": env.get("HOME"),
            "db": env.get("OVERHAUST_DB_PATH"),
            "project": env.get("OVERHAUST_PROJECT_ID"),
        })
        if self.mutate_home is not None:
            path = self.mutate_home / ".cursor" / "cli-config.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["model"] = "gpt-5.5-medium"
            data["selectedModel"] = "gpt-5.5-medium"
            data["hasChangedDefaultModel"] = True
            path.write_text(json.dumps(data), encoding="utf-8")
            (self.mutate_home / ".cursor" / "agent-cli-state.json").write_text('{"mutated": true}', encoding="utf-8")
            (self.mutate_home / ".cursor" / "statsig-cache.json").write_text('{"mutated": true}', encoding="utf-8")
        prompt_file = env.get("OVERHAUST_CURSOR_PROMPT_FILE")
        debug = env.get("OVERHAUST_INTEGRATION_DEBUG_FILE")
        if prompt_file and debug:
            Path(debug).write_text(_hook_line() + "\n", encoding="utf-8")
        if env.get("HOME"):
            marker = CONTEXT_MARKER + "\n\nrelevant files"
            if prompt_file:
                body = marker
            else:
                body = "baseline session has no overhaust marker"
            if self.store_extra:
                body = body + "\n" + self.store_extra
            _write_store(Path(env["HOME"]), "sess-1", body)
        (root / "notes.txt").write_text("agent wrote this\n", encoding="utf-8")
        if self.timeout:
            return ProcessResult(None, "", "timed out", timeout * 1000, True)
        if self.fail:
            failed = SUCCESS.replace('"is_error":false', '"is_error":true').replace(
                '"subtype":"success"',
                '"subtype":"error"',
            )
            return ProcessResult(1, failed, "", 20, False)
        return ProcessResult(0, self.stream, "", 20, False)

    def _projects(self) -> Path:
        assert self.projects_state is not None
        return self.projects_state / ".cursor" / "projects"

    def _mcp_list_text(self) -> str:
        projects = self._projects()
        hidden = False
        if projects.is_dir():
            for child in projects.iterdir():
                disabled = child / "mcp-disabled.json"
                if disabled.is_file() and b"overhaust" in disabled.read_bytes():
                    hidden = True
        if hidden:
            return "gmail\nprisma\n"
        return "overhaust\nget_relevant_context\n"

    def _write_disabled_slug(self, cwd: Path) -> None:
        projects = self._projects()
        projects.mkdir(parents=True, exist_ok=True)
        session_workspace = (cwd / "src").is_dir()
        if self.disable_mode == "preexisting" and session_workspace:
            slug = projects / "user-project"
            slug.mkdir(parents=True, exist_ok=True)
            path = slug / "mcp-disabled.json"
            previous = path.read_bytes() if path.is_file() else b""
            path.write_bytes(previous + b'["overhaust"]\n')
            return
        digest = hashlib.sha256(str(cwd).encode()).hexdigest()[:12]
        slug = projects / f"slug-{digest}"
        slug.mkdir(parents=True, exist_ok=True)
        (slug / "mcp-disabled.json").write_text('["overhaust"]\n', encoding="utf-8")


def _config(tmp_path: Path, fake: FakeCursor, **overrides) -> CursorRunConfig:
    builder, _root, _snapshot = _workspace(tmp_path)
    state = tmp_path / "userhome"
    (state / ".cursor").mkdir(parents=True, exist_ok=True)
    (state / ".cursor" / "cli-config.json").write_text(json.dumps({
        "model": "user-default",
        "selectedModel": "user-default",
        "modelParameters": {"thinking": "medium"},
        "hasChangedDefaultModel": False,
        "modelSelectionHistory": ["user-default"],
        "unrelated": "keep-me",
    }), encoding="utf-8")
    (state / ".cursor" / "agent-cli-state.json").write_text('{"ok": true}', encoding="utf-8")
    (state / ".cursor" / "statsig-cache.json").write_text('{"ok": true}', encoding="utf-8")
    values = dict(
        model="gpt-5.5-medium",
        seed=1,
        results_dir=tmp_path / "results",
        cursor_bin="cursor-agent",
        isolation="isolated-home",
        env={"CURSOR_API_KEY": "test-cursor-key"},
        command_runner=fake,
        workspace_builder=builder,
        state_home=state,
        stamp="cursor-test",
        preset="pilot",
    )
    values.update(overrides)
    return CursorRunConfig(**values)


def test_adapter_init_probes_version_only():
    seen = []

    def runner(command, env, cwd, timeout):
        seen.append(list(command))
        return ProcessResult(0, "2026.09.26-dd393fe\n", "", 1, False)

    adapter = require_adapter("cursor")("cursor-agent", runner=runner)
    assert isinstance(adapter, CursorAdapter)
    assert adapter.agent_id == "cursor"
    probe = adapter.probe()
    assert probe.version == "2026.09.26-dd393fe"
    assert seen == [["cursor-agent", "--version"]]
    assert "-p" not in seen[0]


def test_stream_json_usage_tools_and_derived_sum_are_labeled():
    obs = parse_stream_json(SUCCESS)
    assert obs.model_display_name == "GPT-5.5 272K Medium"
    assert obs.session_id == "sess-1"
    assert obs.duration_ms == 1200
    assert obs.duration_api_ms == 900
    assert obs.usage == {
        "inputTokens": 451,
        "outputTokens": 80,
        "cacheReadTokens": 29696,
        "cacheWriteTokens": 12,
    }
    assert obs.tool_call_types == {"readToolCall": 1, "grepToolCall": 1}
    assert obs.read_paths == ["src/kitchen/kot_generator.ts"]
    assert len(obs.tool_invocations) == 2
    task = next(task for task in load_task_set("initial") if task.task_id == "sym_generate_kot")
    capture = _capture(stdout=SUCCESS, hook_debug=_hook_line() + "\n")
    session = session_from_capture(capture, task)
    assert session.agent_input_tokens.value == 451
    assert session.agent_input_tokens.kind == "exact"
    assert session.agent_cached_input_tokens.value == 29696
    assert session.agent_cached_input_tokens.is_exact
    assert session.agent_output_tokens.value == 80
    assert session.agent_cache_write_input_tokens.value == 12
    assert session.agent_reasoning_output_tokens.is_unavailable
    assert session.agent_total_tokens.is_unavailable
    assert session.agent_total_tokens.value is None
    derived = session.supplemental_telemetry["derived_usage_component_sum"]
    assert derived["kind"] == "DERIVED"
    assert derived["value"] == 451 + 80 + 29696 + 12
    assert derived["complete"] is True
    assert session.tool_calls.value == 2
    assert session.files_inspected.value == 1
    assert session.supplemental_telemetry["files_inspected_paths"] == ["src/kitchen/kot_generator.ts"]
    assert session.overhaust_context_tokens.is_estimated
    assert session.overhaust_context_bytes.value == 240
    assert session.overhaust_retrieval_latency_ms.is_unavailable
    assert session.correctness is True
    assert session.evidence_score is not None
    assert session.primary_metric_status == "complete"
    round_trip = Layer4SessionResult.from_dict(session.to_dict())
    assert round_trip.agent_input_tokens.value == 451
    assert round_trip.agent_cached_input_tokens.value == 29696
    assert "total_tokens" not in (round_trip.agent_total_tokens.source)


def test_missing_usage_is_unavailable_not_zero():
    text = SUCCESS.replace(
        '"usage":{"inputTokens":451,"outputTokens":80,"cacheReadTokens":29696,"cacheWriteTokens":12}',
        '"usage":{"inputTokens":451,"outputTokens":80}',
    )
    task = next(task for task in load_task_set("initial") if task.task_id == "sym_generate_kot")
    session = session_from_capture(_capture(stdout=text, hook_debug=_hook_line() + "\n"), task)
    assert session.agent_input_tokens.value == 451
    assert session.agent_cached_input_tokens.is_unavailable
    assert session.agent_cached_input_tokens.value is None
    assert session.agent_cache_write_input_tokens.is_unavailable
    assert session.primary_metric_status == "partial"
    derived = session.supplemental_telemetry["derived_usage_component_sum"]
    assert derived["value"] is None
    assert derived["complete"] is False
    assert derived["partial_sum"] == 451 + 80


def test_reported_zero_cache_read_stays_exact_zero():
    text = SUCCESS.replace('"cacheReadTokens":29696', '"cacheReadTokens":0')
    obs = parse_stream_json(text)
    assert obs.usage["cacheReadTokens"] == 0


def test_mcp_tool_names_match_the_production_server():
    source = SERVER.read_text(encoding="utf-8")
    for name in OVERHAUST_MCP_TOOL_NAMES:
        assert f'name="{name}"' in source


def test_store_marker_and_unreadable_store(tmp_path: Path):
    home = tmp_path / "home"
    _write_store(home, "sess-1", CONTEXT_MARKER + "\ncontext")
    found = inspect_session_store([home], "sess-1")
    assert found.parseable is True
    assert found.verification == "store+hook"
    assert found.marker_present is True
    assert found.overhaust_tools == []

    catalog = home / ".cursor" / "chats" / "hash" / "sess-2"
    catalog.mkdir(parents=True)
    connection = sqlite3.connect(catalog / "store.db")
    try:
        connection.execute("CREATE TABLE blobs (data TEXT)")
        connection.execute(
            "INSERT INTO blobs (data) VALUES (?)",
            (CONTEXT_MARKER + '\n{"name": "get_relevant_context", "server": "overhaust"}',),
        )
        connection.commit()
    finally:
        connection.close()
    tools = inspect_session_store([home], "sess-2")
    assert "get_relevant_context" in tools.overhaust_tools
    assert "server:overhaust" in tools.overhaust_tools

    broken = home / ".cursor" / "chats" / "hash" / "sess-3"
    broken.mkdir(parents=True)
    (broken / "store.db").write_text("this is not sqlite", encoding="utf-8")
    missed = inspect_session_store([home], "sess-3")
    assert missed.parseable is False
    assert missed.verification == "hook-log-only"
    absent = inspect_session_store([home], "missing-session")
    assert absent.verification == "hook-log-only"


def test_condition_separation_and_cli_config_restore(tmp_path: Path):
    state = tmp_path / "userhome"
    fake = FakeCursor(mutate_home=state)
    # state dir is created by _config; point mutate at that same path.
    report = run_cursor(_config(tmp_path, fake, state_home=state))
    assert report["recorded_session_count"] == 10
    assert report["dropped_session_count"] == 0
    assert report["planned_session_count"] == 10
    launches = fake.launches
    assert len(launches) == 10
    baseline = [item for item in launches if not item["hooks"]]
    over = [item for item in launches if item["hooks"]]
    assert len(baseline) == 5 and len(over) == 5
    for item in baseline:
        assert item["rules"] is False
        assert item["mcp"] is False
        assert item["cursor_files"] == []
        assert item["prompt_file"] is None
        assert item["home"]
        assert "test-cursor-key" not in item["home"]
    for item in over:
        assert item["rules"] is False
        assert item["mcp"] is False
        assert item["cursor_files"] == ["hooks.json"]
        assert "overhaust_cursor_session_start_hook.py" in item["hooks_text"]
        assert "overhaust_user_prompt_hook.py" not in item["hooks_text"]
        assert item["prompt_file"]
        payload = item["prompt_payload"]
        assert payload["harness_session_id"] == item["session_env"]
        assert payload["prompt"]
        assert item["session_env"] not in (item.get("command") or [])
    commands = {item["command"][-1] for item in launches}
    assert len({tuple(item["command"][:-1]) for item in launches}) == 1
    assert "--trust" in launches[0]["command"]
    assert "--force" not in launches[0]["command"]
    assert "-p" in launches[0]["command"]
    assert not any(call[1:3] == ["mcp", "disable"] for call in fake.calls)
    forbidden_cwd = {state.resolve(), Path.home().resolve()}
    assert all(Path(cwd).resolve() not in forbidden_cwd for cwd in fake.cwds)
    assert commands
    for session in report["sessions"]:
        assert session["agent"] == "cursor"
        if session["condition"] == "overhaust":
            assert session["integration_path"] == "cursor_session_start_hook"
            assert session["context_injected"] is True
            assert session["supplemental_telemetry"]["injection_verification"] == "store+hook"
            assert session["valid"] is True
        else:
            assert session["integration_path"] == "none"
            assert session["hook_fired"] is False
            assert session["valid"] is True
        assert "notes.txt" in session["files_changed_paths"]
        assert ".cursor/hooks.json" not in session["files_changed_paths"]
        assert session["files_changed"]["value"] == 1
        assert session["files_changed"]["kind"] == "exact"
    restored = json.loads((state / ".cursor" / "cli-config.json").read_text(encoding="utf-8"))
    assert restored["model"] == "user-default"
    assert restored["selectedModel"] == "user-default"
    assert restored["hasChangedDefaultModel"] is False
    assert restored["unrelated"] == "keep-me"
    assert json.loads((state / ".cursor" / "agent-cli-state.json").read_text(encoding="utf-8")) == {"ok": True}
    assert report["state_restore"]["model_keys_restored"] is True
    assert report["state_restore"]["files_restored"] is True
    md = Path(report["_output_paths"]["md"]).read_text(encoding="utf-8")
    assert PROMPT_CACHE_POLICY in md
    assert CURSOR_CLAIM_POLICY in md
    assert "hook-log-only" in md or "store+hook" in md
    assert "Do not compare" in md
    assert Path(report["_output_paths"]["json"]).name.startswith("layer4-cursor-")


def test_mcp_violation_marks_the_session_invalid_and_stops_the_run(tmp_path: Path):
    stream = SUCCESS.replace(
        '"grepToolCall":{"args":{"pattern":"generateKOT","path":"src"}}',
        '"mcpToolCall":{"args":{"server":"overhaust","toolName":"get_relevant_context","name":"get_relevant_context"}}',
    )
    for condition in ("baseline", "overhaust"):
        state = tmp_path / "userhome"
        fake = FakeCursor(stream=stream, mutate_home=state)
        report = run_cursor(_config(
            tmp_path,
            fake,
            state_home=state,
            conditions=[condition],
            stamp=f"mcp-stop-{condition}",
            results_dir=tmp_path / f"results-{condition}",
        ))
        assert report["planned_session_count"] == 5
        assert report["recorded_session_count"] == 1
        assert report["dropped_session_count"] == 4
        assert len(fake.launches) == 1
        assert report["stopped_early"] is True
        assert report["stopped_at_session"] == report["sessions"][0]["session_id"]
        assert "Neither condition may have the OverHaust MCP" in report["stop_reason"]
        session = report["sessions"][0]
        assert session["condition"] == condition
        assert session["outcome"] == "invalid"
        assert session["valid"] is False
        assert "overhaust_mcp_tool_called" in session["invalid_reasons"]
        assert session["agent_input_tokens"]["value"] == 451
        assert Path(report["_output_paths"]["json"]).is_file()
        restored = json.loads((state / ".cursor" / "cli-config.json").read_text(encoding="utf-8"))
        assert restored["model"] == "user-default"
        assert report["state_restore"]["files_restored"] is True
        assert report["state_restore"]["mcp_json_byte_identical"] is True
        md = Path(report["_output_paths"]["md"]).read_text(encoding="utf-8")
        assert "Stopped early" in md


def test_mcp_catalog_marks_the_session_invalid_and_stops_the_run(tmp_path: Path):
    catalog = '{"name": "get_relevant_context", "serverName": "overhaust"}'
    for condition in ("baseline", "overhaust"):
        state = tmp_path / "userhome"
        fake = FakeCursor(store_extra=catalog, mutate_home=state)
        report = run_cursor(_config(
            tmp_path,
            fake,
            state_home=state,
            conditions=[condition],
            stamp=f"mcp-catalog-{condition}",
            results_dir=tmp_path / f"catalog-{condition}",
        ))
        assert report["recorded_session_count"] == 1
        assert report["dropped_session_count"] == 4
        assert len(fake.launches) == 1
        assert report["stopped_early"] is True
        session = report["sessions"][0]
        assert session["condition"] == condition
        assert session["valid"] is False
        assert "overhaust_mcp_tool_available" in session["invalid_reasons"]
        assert "overhaust_mcp_tool_called" not in session["invalid_reasons"]
        assert Path(report["_output_paths"]["json"]).is_file()
        assert report["state_restore"]["mcp_json_byte_identical"] is True
        restored = json.loads((state / ".cursor" / "cli-config.json").read_text(encoding="utf-8"))
        assert restored["model"] == "user-default"


def test_timeout_and_failed_sessions_stay_in_the_dataset(tmp_path: Path):
    timeout = FakeCursor(timeout=True)
    timed = run_cursor(_config(tmp_path, timeout, conditions=["baseline"], stamp="timeout"))
    assert timed["recorded_session_count"] == 5
    assert all(session["timed_out"] is True for session in timed["sessions"])
    assert all(session["outcome"] == "error" for session in timed["sessions"])
    assert all(session["valid"] is True for session in timed["sessions"])
    assert timed["cache_analysis"]["by_task_condition"]

    failed = FakeCursor(fail=True)
    report = run_cursor(_config(
        tmp_path,
        failed,
        conditions=["overhaust"],
        stamp="failed",
        results_dir=tmp_path / "failed-results",
    ))
    assert report["dropped_session_count"] == 0
    assert any(session["outcome"] == "failed" for session in report["sessions"])
    assert all(session["valid"] is True for session in report["sessions"])
    assert any(session["correctness"] is True for session in report["sessions"])
    means = report["cache_analysis"]["by_task_condition"]
    assert means
    assert all(row["n_sessions"] == 1 for row in means)


def test_fixture_with_cursor_rules_is_rejected(tmp_path: Path):
    builder, root, _snapshot = _workspace(tmp_path)
    rules = root / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "overhaust-context.mdc").write_text("alwaysApply: true\n", encoding="utf-8")
    # Rebuild the snapshot so the planted rules are part of the fixture the
    # preparer sees, which it must reject.
    snapshot = capture_repository_snapshot(str(root))

    def planted(_tasks):
        return Layer4Workspace(
            root=root,
            db_path=str(tmp_path / "bench.db"),
            project_id="bench-labkot",
            snapshot=snapshot,
            snapshot_hash=snapshot["tree_hash"],
            repo_size="medium",
        )

    fake = FakeCursor()
    report = run_cursor(_config(tmp_path, fake, workspace_builder=planted, conditions=["baseline"]))
    assert fake.launches == []
    assert report["recorded_session_count"] == 5
    assert all("hook_layout_mismatch" in session["invalid_reasons"] for session in report["sessions"])


def test_prepare_workspace_hooks_only_on_overhaust(tmp_path: Path):
    _builder, root, snapshot = _workspace(tmp_path)
    command = 'python3 "/repo/scripts/integrations/overhaust_cursor_session_start_hook.py"'
    baseline = prepare_session_workspace(
        root, snapshot, tmp_path / "base", condition="baseline", hook_command=command,
    )
    over = prepare_session_workspace(
        root, snapshot, tmp_path / "over", condition="overhaust", hook_command=command,
    )
    assert baseline.layout.ok
    assert not (baseline.root / ".cursor").exists()
    assert over.layout.ok
    checked = verify_hook_layout(over.root, condition="overhaust", hook_command=command)
    assert checked.ok
    assert checked.events == ["sessionStart"]
    data = json.loads((over.root / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
    assert list(data["hooks"]) == ["sessionStart"]


def test_cli_config_guard_restores_model_keys_after_mutation(tmp_path: Path):
    home = tmp_path / "home"
    cursor = home / ".cursor"
    cursor.mkdir(parents=True)
    original = {
        "model": "user-default",
        "selectedModel": "user-default",
        "modelParameters": {"a": 1},
        "hasChangedDefaultModel": False,
        "modelSelectionHistory": ["user-default"],
    }
    (cursor / "cli-config.json").write_text(json.dumps(original), encoding="utf-8")
    (cursor / "agent-cli-state.json").write_text("{}", encoding="utf-8")
    (cursor / "statsig-cache.json").write_text("{}", encoding="utf-8")
    guard = CursorStateGuard(home)
    guard.snapshot()
    mutated = dict(original)
    mutated["model"] = "gpt-5.5-medium"
    mutated["hasChangedDefaultModel"] = True
    (cursor / "cli-config.json").write_text(json.dumps(mutated), encoding="utf-8")
    (cursor / "statsig-cache.json").write_text('{"changed": true}', encoding="utf-8")
    restored = guard.restore()
    assert restored["model_keys_restored"] is True
    assert restored["files_restored"] is True
    assert json.loads((cursor / "cli-config.json").read_text(encoding="utf-8"))["model"] == "user-default"


def test_dry_run_prints_plan_and_launches_nothing(tmp_path: Path):
    fake = FakeCursor()

    def explode(*_args, **_kwargs):
        raise AssertionError("dry run launched cursor-agent")

    report = run_cursor(_config(tmp_path, fake, dry_run=True, command_runner=explode, cursor_bin="cursor-agent-missing"))
    assert report["mode"] == "dry_run"
    assert report["planned_session_count"] == 10
    assert report["recorded_session_count"] == 0
    assert report["model_requested"] == CURSOR_DEFAULT_MODEL
    assert report["isolation"] == "isolated-home"
    assert report["integration_mode"] == "cursor_session_start_hook"
    assert report["snapshot_hash"]
    text = format_cursor_dry_run(report)
    assert "Launching nothing" in text
    assert "fixture_hash:" in text
    assert "commit:" in text
    assert "isolation: isolated-home" in text
    assert "agent_input_tokens: EXACT|UNAVAILABLE" in text
    assert "agent_reasoning_output_tokens: UNAVAILABLE" in text
    assert "derived_usage_component_sum: DERIVED" in text
    assert "overhaust_context_tokens: ESTIMATED|UNAVAILABLE" in text
    assert PROMPT_CACHE_POLICY in text
    assert fake.calls == []
    again = run_cursor(_config(
        tmp_path,
        fake,
        dry_run=True,
        command_runner=explode,
        results_dir=tmp_path / "other",
        stamp="cursor-test-2",
    ))
    assert [row["session_id"] for row in report["planned_execution_order"]] == [
        row["session_id"] for row in again["planned_execution_order"]
    ]
    pairs = [row["pair_id"] for row in report["planned_execution_order"]]
    assert pairs[0::2] == pairs[1::2]


def test_full_preset_matches_shared_pair_order_and_codex_pilot_stays_eight(tmp_path: Path):
    fake = FakeCursor()
    full = run_cursor(_config(tmp_path, fake, preset="full", dry_run=True, command_runner=lambda *a, **k: (_ for _ in ()).throw(AssertionError("launched"))))
    expected = plan_matrix(load_full_tasks(), reps=2, seed=1)
    assert full["planned_session_count"] == 20
    assert [row["session_id"] for row in full["planned_execution_order"]] == [plan.session_id for plan in expected]
    codex_pilot = plan_matrix(load_pilot_tasks(), reps=preset_reps("pilot"), seed=1)
    assert len(codex_pilot) == 8
    cursor_pilot = plan_matrix(load_full_tasks(), reps=1, seed=1)
    assert len(cursor_pilot) == 10


def test_codex_dry_run_is_unchanged(tmp_path: Path):
    tasks = load_pilot_tasks()
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.txt").write_text("a", encoding="utf-8")
    snapshot = capture_repository_snapshot(str(root))

    def builder(_tasks):
        return Layer4Workspace(
            root=root,
            db_path=str(tmp_path / "bench.db"),
            project_id=tasks[0].project_id,
            snapshot=snapshot,
            snapshot_hash=snapshot["tree_hash"],
            repo_size="medium",
        )

    report = run_pilot(RunConfig(
        dry_run=True,
        results_dir=tmp_path / "results",
        env={},
        command_runner=lambda *a, **k: (_ for _ in ()).throw(AssertionError("codex launched")),
        workspace_builder=builder,
        stamp="codex-still",
    ))
    assert report["agent"] == "codex"
    assert report["planned_session_count"] == 8
    assert report["schema_version"] == "layer4-run-v2"


def test_preflight_checks_isolation_without_a_model_session(tmp_path: Path):
    fake = FakeCursor()
    state = tmp_path / "userhome"
    state.mkdir()
    report = run_cursor_preflight(
        binary="cursor-agent",
        env={"CURSOR_API_KEY": "test-cursor-key"},
        isolation="isolated-home",
        model="gpt-5.5-medium",
        state_home=state,
        runner=fake,
    )
    assert report["model_session_launched"] is False
    assert report["selected_usable"] is True
    assert report["isolated_home"]["usable"] is True
    assert report["isolated_home"]["checked"] is True
    assert report["mcp_toggle"]["checked"] is False
    assert report["cli_present"] is True
    assert report["model_listed"] is True
    assert all("-p" not in call for call in fake.calls)
    assert not any(call[1:3] == ["mcp", "disable"] for call in fake.calls)
    forbidden_cwd = {state.resolve(), Path.home().resolve()}
    assert all(Path(cwd).resolve() not in forbidden_cwd for cwd in fake.cwds)

    seen = []

    def ignores_home(command, env, cwd, timeout):
        argv = [str(part) for part in command]
        seen.append((argv, str(cwd)))
        if "--version" in argv:
            return ProcessResult(0, "2026.09.26-dd393fe\n", "", 1, False)
        if "models" in argv:
            return ProcessResult(0, "gpt-5.5-medium\n", "", 1, False)
        if "mcp" in argv and "list" in argv:
            return ProcessResult(0, "overhaust\nget_relevant_context\n", "", 1, False)
        if "mcp" in argv and "disable" in argv:
            return ProcessResult(0, "", "", 1, False)
        return ProcessResult(0, "", "", 1, False)

    blocked = run_cursor_preflight(
        binary="cursor-agent",
        env={"CURSOR_API_KEY": "test-cursor-key"},
        isolation="isolated-home",
        model="gpt-5.5-medium",
        state_home=state,
        runner=ignores_home,
    )
    assert blocked["isolated_home"]["usable"] is False
    assert blocked["mcp_toggle"]["checked"] is False
    assert blocked["selected_usable"] is False
    assert not any(argv[1:3] == ["mcp", "disable"] for argv, _cwd in seen)
    assert all(Path(cwd).resolve() not in forbidden_cwd for _argv, cwd in seen)


def test_cli_dry_run_and_preflight_flags(tmp_path: Path, monkeypatch, capsys):
    tasks = load_full_tasks()
    builder, _root, _snapshot = _workspace(tmp_path)
    monkeypatch.setattr("benchmarks.layer4.cursor_runner.build_fixture_workspace", builder)
    results = tmp_path / "cli-results"
    code = main([
        "--agent", "cursor",
        "--dry-run",
        "--preset", "pilot",
        "--results-dir", str(results),
        "--seed", "1",
        "--isolation", "mcp-toggle",
        "--cursor-bin", "cursor-agent",
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "Launching nothing" in out
    assert "planned 10 sessions, launched 0." in out
    assert "model: gpt-5.5-medium" in out
    assert "isolation: mcp-toggle" in out
    assert PROMPT_CACHE_POLICY in out
    report = json.loads(next(results.glob("layer4-cursor-*.json")).read_text(encoding="utf-8"))
    assert report["planned_session_count"] == 10
    assert report["agent"] == "cursor"
    assert "cacheReadTokens is not included in inputTokens" in report["token_accounting_note"]

    def fake_preflight(**kwargs):
        assert kwargs["isolation"] == "isolated-home"
        assert kwargs["model"] == "gpt-5.5-medium"
        return {
            "selected_usable": False,
            "model_session_launched": False,
            "isolation_requested": kwargs["isolation"],
        }

    monkeypatch.setattr("benchmarks.layer4.cursor_runner.run_cursor_preflight", fake_preflight)
    code = main([
        "--agent", "cursor",
        "--preflight",
        "--isolation", "isolated-home",
        "--model", "gpt-5.5-medium",
    ])
    assert code == 2
    printed = json.loads(capsys.readouterr().out)
    assert printed["model_session_launched"] is False

    code = main(["--preflight", "--dry-run", "--results-dir", str(tmp_path / "nope")])
    assert code == 2

    def stopped_run(_config):
        return {
            "mode": "pilot",
            "recorded_session_count": 1,
            "dropped_session_count": 9,
            "stopped_early": True,
            "stop_reason": "OverHaust MCP tool was available or called.",
            "state_restore": {"model_keys_restored": True, "files_restored": True},
            "_output_paths": {"json": "report.json", "md": "report.md"},
        }

    monkeypatch.setattr("benchmarks.layer4.cursor_runner.run_cursor", stopped_run)
    code = main([
        "--agent", "cursor",
        "--results-dir", str(tmp_path / "stopped"),
        "--cursor-bin", "cursor-agent",
    ])
    assert code == 2
    assert "OverHaust MCP tool was available or called." in capsys.readouterr().err


def _assert_cwd_is_throwaway(fake: FakeCursor, state: Path) -> None:
    forbidden = {state.resolve(), Path.home().resolve()}
    assert fake.cwds
    assert all(Path(cwd).resolve() not in forbidden for cwd in fake.cwds)


def test_preflight_probes_only_the_selected_isolation(tmp_path: Path):
    state = tmp_path / "userhome"
    state.mkdir()
    kept = state / ".cursor" / "projects" / "user-project"
    kept.mkdir(parents=True)
    (kept / "keep.txt").write_text("leave-me\n", encoding="utf-8")
    home_fake = FakeCursor()
    home = run_cursor_preflight(
        binary="cursor-agent",
        env={"CURSOR_API_KEY": "test-cursor-key"},
        isolation="isolated-home",
        model="gpt-5.5-medium",
        state_home=state,
        runner=home_fake,
    )
    assert home["selected_usable"] is True
    assert home["isolated_home"]["checked"] is True
    assert home["mcp_toggle"]["checked"] is False
    assert not any(call[1:3] == ["mcp", "disable"] for call in home_fake.calls)
    _assert_cwd_is_throwaway(home_fake, state)
    assert (kept / "keep.txt").read_text(encoding="utf-8") == "leave-me\n"

    toggle_fake = FakeCursor(projects_state=state)
    toggled = run_cursor_preflight(
        binary="cursor-agent",
        env={"CURSOR_API_KEY": "test-cursor-key"},
        isolation="mcp-toggle",
        model="gpt-5.5-medium",
        state_home=state,
        runner=toggle_fake,
    )
    assert toggled["selected_usable"] is True
    assert toggled["mcp_toggle"]["checked"] is True
    assert toggled["isolated_home"]["checked"] is False
    disables = [call for call in toggle_fake.calls if call[1:3] == ["mcp", "disable"]]
    lists = [call for call in toggle_fake.calls if call[1:3] == ["mcp", "list"]]
    assert disables == [["cursor-agent", "mcp", "disable", "overhaust"]]
    assert lists == [["cursor-agent", "mcp", "list"]]
    assert not any("layer4-home-sentinel" in "".join(call) for call in toggle_fake.calls)
    _assert_cwd_is_throwaway(toggle_fake, state)
    projects = state / ".cursor" / "projects"
    assert sorted(path.name for path in projects.iterdir()) == ["user-project"]
    assert (kept / "keep.txt").read_text(encoding="utf-8") == "leave-me\n"
    assert not (kept / "mcp-disabled.json").exists()


def test_mcp_toggle_disables_per_workspace_and_cleans_created_slugs(tmp_path: Path):
    state = tmp_path / "userhome"
    kept = state / ".cursor" / "projects" / "user-project"
    kept.mkdir(parents=True)
    (kept / "keep.txt").write_text("leave-me\n", encoding="utf-8")
    fake = FakeCursor(projects_state=state)
    report = run_cursor(_config(
        tmp_path,
        fake,
        state_home=state,
        isolation="mcp-toggle",
    ))
    assert report["recorded_session_count"] == 10
    launches = fake.launches
    assert len(launches) == 10
    assert sum(1 for item in launches if item["hooks"]) == 5
    assert sum(1 for item in launches if not item["hooks"]) == 5
    disable_cwds = [
        cwd for argv, cwd in zip(fake.calls, fake.cwds) if argv[1:3] == ["mcp", "disable"]
    ]
    list_cwds = [
        cwd for argv, cwd in zip(fake.calls, fake.cwds) if argv[1:3] == ["mcp", "list"]
    ]
    # One preflight pair, then one pair per session. No extra mcp calls.
    assert len(disable_cwds) == 11
    assert len(list_cwds) == 11
    launch_cwds = [item["cwd"] for item in launches]
    assert disable_cwds[1:] == launch_cwds
    assert list_cwds[1:] == launch_cwds
    _assert_cwd_is_throwaway(fake, state)
    projects = state / ".cursor" / "projects"
    assert sorted(path.name for path in projects.iterdir()) == ["user-project"]
    assert (kept / "keep.txt").read_text(encoding="utf-8") == "leave-me\n"
    assert report["mcp_cleanup"]["cleanup_verified"] is True
    for session in report["sessions"]:
        evidence = session["supplemental_telemetry"]["isolation_evidence"]
        assert evidence["applied"] is True
        assert evidence["overhaust_listed"] is False
        assert evidence["cleanup_verified"] is True
        assert evidence["refused_preexisting_slugs"] == []
        assert evidence["created_slugs"]
        assert evidence["removed_slugs"] == evidence["created_slugs"]
        assert session["valid"] is True
        assert "user-project" not in evidence["created_slugs"]


def test_mcp_toggle_refuses_preexisting_project_slugs(tmp_path: Path):
    state = tmp_path / "userhome"
    kept = state / ".cursor" / "projects" / "user-project"
    kept.mkdir(parents=True)
    (kept / "keep.txt").write_text("leave-me\n", encoding="utf-8")
    fake = FakeCursor(projects_state=state, disable_mode="preexisting")
    report = run_cursor(_config(
        tmp_path,
        fake,
        state_home=state,
        isolation="mcp-toggle",
        conditions=["baseline"],
    ))
    assert report["recorded_session_count"] == 5
    assert (kept / "keep.txt").read_text(encoding="utf-8") == "leave-me\n"
    assert kept.is_dir()
    disabled = (kept / "mcp-disabled.json").read_bytes()
    assert b"overhaust" in disabled
    projects = state / ".cursor" / "projects"
    assert sorted(path.name for path in projects.iterdir()) == ["user-project"]
    assert report["mcp_cleanup"]["cleanup_verified"] is False
    for session in report["sessions"]:
        evidence = session["supplemental_telemetry"]["isolation_evidence"]
        assert evidence["refused_preexisting_slugs"] == ["user-project"]
        assert evidence["removed_slugs"] == []
        assert session["valid"] is False
        assert "mcp_toggle_preexisting_slug" in session["invalid_reasons"]
        assert "user-project" not in (evidence.get("created_slugs") or [])


def test_mcp_toggle_cleans_up_when_the_model_command_fails(tmp_path: Path):
    state = tmp_path / "userhome"
    kept = state / ".cursor" / "projects" / "user-project"
    kept.mkdir(parents=True)
    (kept / "keep.txt").write_text("leave-me\n", encoding="utf-8")
    fake = FakeCursor(projects_state=state, model_failure="raise")
    report = run_cursor(_config(
        tmp_path,
        fake,
        state_home=state,
        isolation="mcp-toggle",
        conditions=["baseline"],
    ))
    assert report["recorded_session_count"] == 5
    assert fake.launches == []
    projects = state / ".cursor" / "projects"
    assert sorted(path.name for path in projects.iterdir()) == ["user-project"]
    assert not (kept / "mcp-disabled.json").exists()
    assert (kept / "keep.txt").read_text(encoding="utf-8") == "leave-me\n"
    assert report["mcp_cleanup"]["cleanup_verified"] is True
    for session in report["sessions"]:
        evidence = session["supplemental_telemetry"]["isolation_evidence"]
        assert evidence["cleanup_verified"] is True
        assert evidence["overhaust_listed"] is False
        assert session["valid"] is True
        assert session["outcome"] == "error"
        assert "model exploded" in (session["error"] or "")

    interrupt = FakeCursor(projects_state=state, model_failure="interrupt")
    with pytest.raises(KeyboardInterrupt):
        run_cursor(_config(
            tmp_path,
            interrupt,
            state_home=state,
            isolation="mcp-toggle",
            conditions=["baseline"],
            stamp="cursor-interrupt",
        ))
    assert sorted(path.name for path in projects.iterdir()) == ["user-project"]
    assert not (kept / "mcp-disabled.json").exists()
    assert (kept / "keep.txt").read_text(encoding="utf-8") == "leave-me\n"


def _mutate_cursor_state(state: Path, command) -> None:
    argv = [str(part) for part in command]
    cursor = state / ".cursor"
    cursor.mkdir(parents=True, exist_ok=True)
    config = cursor / "cli-config.json"
    data = json.loads(config.read_text(encoding="utf-8")) if config.is_file() else {}
    data["model"] = "mutated-by-" + (argv[1] if len(argv) > 1 else "cmd")
    config.write_text(json.dumps(data), encoding="utf-8")
    (cursor / "agent-cli-state.json").write_text('{"mutated": true}', encoding="utf-8")
    (cursor / "statsig-cache.json").write_text('{"mutated": true}', encoding="utf-8")
    (cursor / "mcp.json").write_text('{"mcpServers": {"mutated": {}}}', encoding="utf-8")
    if any(part in argv for part in ("--version", "status", "models", "mcp")):
        projects = cursor / "projects"
        projects.mkdir(parents=True, exist_ok=True)
        slug = projects / ("slug-" + hashlib.sha256(" ".join(argv).encode()).hexdigest()[:8])
        slug.mkdir(exist_ok=True)
        (slug / "mcp-disabled.json").write_text('["overhaust"]\n', encoding="utf-8")


def test_preflight_restores_cursor_state_and_new_slugs(tmp_path: Path):
    state = tmp_path / "userhome"
    cursor = state / ".cursor"
    cursor.mkdir(parents=True)
    original_mcp = '{"mcpServers": {"gmail": {}}}\n'
    (cursor / "cli-config.json").write_text(
        json.dumps({"model": "user-default", "selectedModel": "user-default"}),
        encoding="utf-8",
    )
    (cursor / "agent-cli-state.json").write_text('{"ok": true}', encoding="utf-8")
    (cursor / "statsig-cache.json").write_text('{"ok": true}', encoding="utf-8")
    (cursor / "mcp.json").write_text(original_mcp, encoding="utf-8")
    kept = cursor / "projects" / "user-project"
    kept.mkdir(parents=True)
    (kept / "keep.txt").write_text("leave-me\n", encoding="utf-8")

    def runner(command, env, cwd, timeout):
        argv = [str(part) for part in command]
        assert Path(cwd).resolve() != state.resolve()
        assert Path(cwd).resolve() != Path.home().resolve()
        _mutate_cursor_state(state, command)
        if "--version" in argv:
            return ProcessResult(0, "2026.09.26-dd393fe\n", "", 1, False)
        if "models" in argv:
            return ProcessResult(0, "gpt-5.5-medium\n", "", 1, False)
        if "mcp" in argv and "list" in argv:
            return ProcessResult(0, "layer4-home-sentinel\n", "", 1, False)
        return ProcessResult(0, "", "", 1, False)

    report = run_cursor_preflight(
        binary="cursor-agent",
        env={"CURSOR_API_KEY": "test-cursor-key"},
        isolation="isolated-home",
        model="gpt-5.5-medium",
        state_home=state,
        runner=runner,
    )
    assert report["mcp_json_byte_identical"] is True
    assert report["state_restore"]["files_restored"] is True
    assert report["state_restore"]["mcp_json_byte_identical"] is True
    assert (cursor / "mcp.json").read_text(encoding="utf-8") == original_mcp
    assert json.loads((cursor / "cli-config.json").read_text(encoding="utf-8"))["model"] == "user-default"
    assert json.loads((cursor / "agent-cli-state.json").read_text(encoding="utf-8")) == {"ok": True}
    projects = cursor / "projects"
    assert sorted(path.name for path in projects.iterdir()) == ["user-project"]
    assert (kept / "keep.txt").read_text(encoding="utf-8") == "leave-me\n"
    assert report["preflight_projects_cleanup"]["cleanup_verified"] is True
    assert not any(call for call in report["preflight_projects_cleanup"]["removed_slugs"] if call == "user-project")

    def boom(command, env, cwd, timeout):
        _mutate_cursor_state(state, command)
        argv = [str(part) for part in command]
        if "--version" in argv:
            return ProcessResult(0, "2026.09.26-dd393fe\n", "", 1, False)
        raise RuntimeError("models exploded")

    with pytest.raises(RuntimeError, match="models exploded"):
        run_cursor_preflight(
            binary="cursor-agent",
            env={"CURSOR_API_KEY": "test-cursor-key"},
            isolation="isolated-home",
            model="gpt-5.5-medium",
            state_home=state,
            runner=boom,
        )
    assert (cursor / "mcp.json").read_text(encoding="utf-8") == original_mcp
    assert json.loads((cursor / "cli-config.json").read_text(encoding="utf-8"))["model"] == "user-default"
    assert sorted(path.name for path in projects.iterdir()) == ["user-project"]
    assert (kept / "keep.txt").read_text(encoding="utf-8") == "leave-me\n"


def test_isolated_home_preflight_treats_a_real_projects_slug_as_not_honoring_home(tmp_path: Path):
    state = tmp_path / "userhome"
    cursor = state / ".cursor"
    cursor.mkdir(parents=True)
    (cursor / "mcp.json").write_text("{}\n", encoding="utf-8")
    kept = cursor / "projects" / "user-project"
    kept.mkdir(parents=True)
    (kept / "keep.txt").write_text("leave-me\n", encoding="utf-8")

    def ignores_home(command, env, cwd, timeout):
        argv = [str(part) for part in command]
        if "--version" in argv:
            return ProcessResult(0, "2026.09.26-dd393fe\n", "", 1, False)
        if "models" in argv:
            return ProcessResult(0, "gpt-5.5-medium\n", "", 1, False)
        if "mcp" in argv and "list" in argv:
            leaked = cursor / "projects" / "ignored-home"
            leaked.mkdir(parents=True, exist_ok=True)
            (leaked / "mcp-disabled.json").write_text("[]\n", encoding="utf-8")
            return ProcessResult(0, "layer4-home-sentinel\n", "", 1, False)
        return ProcessResult(0, "", "", 1, False)

    report = run_cursor_preflight(
        binary="cursor-agent",
        env={"CURSOR_API_KEY": "test-cursor-key"},
        isolation="isolated-home",
        model="gpt-5.5-medium",
        state_home=state,
        runner=ignores_home,
    )
    assert report["isolated_home"]["usable"] is False
    assert report["isolated_home"]["wrote_real_projects_slug"] is True
    assert report["selected_usable"] is False
    assert report["mcp_json_byte_identical"] is True
    projects = cursor / "projects"
    assert sorted(path.name for path in projects.iterdir()) == ["user-project"]
    assert (kept / "keep.txt").read_text(encoding="utf-8") == "leave-me\n"
    assert not (projects / "ignored-home").exists()


def test_preset_help_states_cursor_pilot_is_ten_sessions():
    parser = build_parser()
    preset_help = parser._option_string_actions["--preset"].help
    assert "10 sessions" in preset_help
    assert "8 sessions" in preset_help
    assert "20 sessions" in preset_help


def test_prompt_hashes_are_stable():
    assert prompt_sha256("abc") == prompt_sha256("abc")
    assert len(prompt_sha256("abc")) == 64


def _capture(**overrides) -> CursorSessionCapture:
    from benchmarks.layer4.cursor_store import StoreInspection

    values = dict(
        session_id="sym_generate_kot-overhaust-r0",
        condition="overhaust",
        task_id="sym_generate_kot",
        rep=0,
        seed=1,
        execution_order=0,
        pair_id="sym_generate_kot-r0",
        order_in_pair=1,
        condition_order="baseline->overhaust",
        snapshot_hash="abc",
        prompt="Where is generateKOT defined and what does it return?",
        model_requested="gpt-5.5-medium",
        agent_version="2026.09.26-dd393fe",
        agent_version_source="cursor_agent_cli_version",
        agent_version_warning=None,
        stdout=SUCCESS,
        stderr="",
        exit_code=0,
        timed_out=False,
        elapsed_ms=50,
        hook_debug=_hook_line() + "\n",
        command=["cursor-agent", "-p", "--output-format", "stream-json", "--trust", "--model", "gpt-5.5-medium",
                 "Where is generateKOT defined and what does it return?"],
        hook_command="python3 hook.py",
        integration_path="cursor_session_start_hook",
        isolation="isolated-home",
        hook_layout={"ok": True, "problems": []},
        store=StoreInspection(False, "hook-log-only", detail="test"),
        raw_telemetry_paths={},
        files_changed_paths=[],
        files_changed_measured=True,
        restore_verified=True,
        prompt_file_written=True,
    )
    values.update(overrides)
    return CursorSessionCapture(**values)
