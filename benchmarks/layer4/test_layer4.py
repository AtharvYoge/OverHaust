"""
Layer 4 instrumentation tests.

Uses recorded Codex JSONL and a fake process runner. No network and no API key.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.layer4.adapters import UnsupportedAgent, require_adapter
from benchmarks.layer4.codex_adapter import (
    CodexProbe,
    CodexSessionCapture,
    session_from_capture,
)
from benchmarks.layer4.codex_parse import (
    parse_exec_jsonl,
    parse_rollout_jsonl,
)
from benchmarks.layer4.condition import (
    build_exec_command,
    build_exec_env,
    prepare_codex_home,
)
from benchmarks.layer4.matrix import (
    PILOT_CONDITIONS,
    PILOT_REPS,
    PILOT_SEED,
    PILOT_TASK_IDS,
    load_pilot_tasks,
    plan_matrix,
)
from benchmarks.layer4.runner import (
    Layer4Workspace,
    ProcessResult,
    RunConfig,
    allocate_result_paths,
    diff_snapshot_paths,
    run_pilot,
)
from benchmarks.layer4.schema import FigureKind, Layer4SessionResult, MetricFigure
from benchmarks.repro import capture_repository_snapshot
from benchmarks.tasks_loader import load_task_set


FIXTURES = Path(__file__).resolve().parent / "fixtures"
COMPLETED = (FIXTURES / "codex_exec_completed.jsonl").read_text(encoding="utf-8")
MISSING_CACHED = (FIXTURES / "codex_exec_missing_cached.jsonl").read_text(encoding="utf-8")
FAILED = (FIXTURES / "codex_exec_failed.jsonl").read_text(encoding="utf-8")
ROLLOUT = (FIXTURES / "codex_rollout.jsonl").read_text(encoding="utf-8")
HOOK = (FIXTURES / "hook_debug.jsonl").read_text(encoding="utf-8")


def _task(task_id: str = "sym_generate_kot"):
    return next(task for task in load_task_set("initial") if task.task_id == task_id)


def _capture(**overrides) -> CodexSessionCapture:
    task = _task()
    data = dict(
        session_id="sym_generate_kot-baseline-r0",
        condition="baseline",
        task_id=task.task_id,
        rep=0,
        seed=1,
        execution_order=0,
        snapshot_hash="abc",
        prompt=task.prompt,
        model_requested="gpt-5.4",
        agent_version="0.146.0",
        agent_version_source="codex_cli_version",
        agent_version_warning=None,
        stdout=COMPLETED,
        stderr="",
        exit_code=0,
        timed_out=False,
        elapsed_ms=20,
        hook_debug="",
        rollout_text="",
        raw_telemetry_paths={"exec_jsonl": "exec.jsonl"},
        last_message=None,
        command=["codex", "exec", "--json", task.prompt],
        hook_command=None,
        integration_path="none",
        snapshot_hash_before="abc",
        snapshot_hash_after="abc",
        files_changed_paths=[],
        files_changed_measured=True,
        restore_verified=True,
        fresh_codex_home=True,
    )
    data.update(overrides)
    return CodexSessionCapture(**data)


def test_metric_figure_rejects_mixed_provenance():
    with pytest.raises(ValueError):
        MetricFigure(0, FigureKind.UNAVAILABLE.value, "not_reported")
    with pytest.raises(ValueError):
        MetricFigure(None, FigureKind.EXACT.value, "codex")
    with pytest.raises(ValueError):
        MetricFigure(1.5, FigureKind.EXACT.value, "codex")
    assert MetricFigure.exact(0, "codex_exec_jsonl.turn.completed.usage.cached_input_tokens").value == 0


def test_exec_jsonl_usage_is_exact_and_not_summed():
    result = session_from_capture(_capture(), _task())
    assert result.outcome == "completed"
    assert result.valid is True
    assert result.primary_metric_status == "complete"
    assert result.agent_input_tokens.value == 1000
    assert result.agent_input_tokens.kind == "exact"
    assert result.agent_cached_input_tokens.value == 200
    assert result.agent_output_tokens.value == 50
    assert result.agent_reasoning_output_tokens.value == 8
    assert result.agent_cache_write_input_tokens.value == 0
    assert result.agent_total_tokens.is_unavailable
    assert result.agent_total_tokens.value is None
    assert result.tool_calls.value == 1
    assert result.tool_calls.kind == "exact"
    assert result.files_inspected.is_unavailable
    assert "files_inspected" in result.telemetry_gaps
    assert result.files_changed.value == 0
    assert result.files_changed.kind == "exact"
    assert result.overhaust_context_tokens.is_unavailable
    assert result.correctness is True
    assert result.codex_thread_id == "0199a213-81c0-7800-8aa1-bbab2a035a53"
    assert result.raw_telemetry_source == "codex_exec_jsonl"


def test_missing_cached_is_not_zero_and_total_is_not_invented():
    result = session_from_capture(_capture(stdout=MISSING_CACHED), _task())
    assert result.primary_metric_status == "partial"
    assert result.agent_input_tokens.value == 10
    assert result.agent_output_tokens.value == 2
    assert result.agent_cached_input_tokens.is_unavailable
    assert result.agent_cached_input_tokens.value is None
    assert result.agent_reasoning_output_tokens.is_unavailable
    assert result.agent_total_tokens.is_unavailable
    assert result.agent_input_tokens.value + result.agent_output_tokens.value != (
        result.agent_total_tokens.value
    )


def test_rollout_total_is_used_only_when_components_match_and_last_is_ignored():
    result = session_from_capture(
        _capture(stdout=COMPLETED, rollout_text=ROLLOUT),
        _task(),
    )
    assert result.agent_input_tokens.value == 1000
    assert result.agent_total_tokens.value == 1050
    assert result.agent_total_tokens.kind == "exact"
    assert "total_tokens" in result.agent_total_tokens.source
    assert result.agent_input_tokens.value != 40
    assert result.supplemental_telemetry["rollout_last_token_usage"]["input_tokens"] == 40
    assert result.model_reported == "gpt-5.4"

    mismatched = ROLLOUT.replace('"input_tokens":1000', '"input_tokens":9999', 1)
    disagreed = session_from_capture(
        _capture(stdout=COMPLETED, rollout_text=mismatched),
        _task(),
    )
    assert disagreed.agent_input_tokens.value == 1000
    assert disagreed.agent_total_tokens.is_unavailable
    assert "input_tokens" in disagreed.telemetry_disagreement


def test_rollout_alone_supplies_exact_usage_when_exec_usage_is_absent():
    stdout = '{"type":"turn.completed"}\n'
    result = session_from_capture(
        _capture(stdout=stdout, rollout_text=ROLLOUT),
        _task(),
    )
    assert result.raw_telemetry_source == "codex_session_rollout"
    assert result.agent_input_tokens.value == 1000
    assert result.agent_input_tokens.source.startswith(
        "codex_session_rollout.token_count.total_token_usage"
    )
    assert result.agent_input_tokens.value != 40


def test_cli_startup_failure_is_an_error_not_a_valid_session():
    result = session_from_capture(
        _capture(stdout="error: unexpected argument\n", exit_code=2),
        _task(),
    )
    assert result.outcome == "error"
    assert result.valid is False
    assert result.agent_input_tokens.is_unavailable
    assert "exit 2" in (result.error or "")


def test_failed_turn_is_recorded():
    result = session_from_capture(
        _capture(stdout=FAILED, exit_code=1),
        _task(),
    )
    assert result.outcome == "failed"
    assert result.valid is True
    assert result.agent_input_tokens.is_unavailable
    assert result.primary_metric_status == "missing"
    assert "stream disconnected" in (result.error or "")


def test_overhaust_tokens_stay_estimated_and_are_not_subtracted():
    task = _task()
    result = session_from_capture(
        _capture(
            condition="overhaust",
            session_id="sym_generate_kot-overhaust-r0",
            hook_debug=HOOK,
            integration_path="codex_user_prompt_submit_hook",
            hook_command='python3 "/repo/scripts/integrations/overhaust_user_prompt_hook.py"',
        ),
        task,
    )
    assert result.overhaust_context_tokens.kind == "estimated"
    assert result.overhaust_context_tokens.value == 310
    assert result.overhaust_context_bytes.value == 1200
    assert result.overhaust_context_bytes.kind == "exact"
    assert result.overhaust_hook_latency_ms.value == 42
    assert result.overhaust_retrieval_latency_ms.is_unavailable
    assert result.agent_input_tokens.value == 1000
    assert result.valid is True
    assert result.context_injected is True
    data = result.to_dict()
    data["agent_input_tokens"]["kind"] = "estimated"
    with pytest.raises(ValueError):
        Layer4SessionResult.from_dict(data)


def test_baseline_hook_output_invalidates_but_keeps_the_session():
    result = session_from_capture(_capture(hook_debug=HOOK), _task())
    assert result.outcome == "invalid"
    assert result.valid is False
    assert "baseline_hook_contamination" in result.invalid_reasons
    assert result.agent_input_tokens.value == 1000


def test_overhaust_hook_miss_is_invalid_and_retained():
    result = session_from_capture(
        _capture(
            condition="overhaust",
            integration_path="codex_user_prompt_submit_hook",
            hook_command="python3 overhaust_user_prompt_hook.py",
            hook_debug="",
        ),
        _task(),
    )
    assert result.outcome == "invalid"
    assert "overhaust_hook_did_not_fire" in result.invalid_reasons
    assert result.agent_output_tokens.value == 50


def test_last_turn_completed_usage_is_the_session_total():
    text = (
        '{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":1,'
        '"output_tokens":2,"reasoning_output_tokens":0,"cache_write_input_tokens":0}}\n'
        '{"type":"turn.completed","usage":{"input_tokens":30,"cached_input_tokens":4,'
        '"output_tokens":5,"reasoning_output_tokens":1,"cache_write_input_tokens":0}}\n'
    )
    obs = parse_exec_jsonl(text)
    assert obs.usage["input_tokens"] == 30
    assert obs.turn_completed == 2


def test_parse_rollout_model_and_cli_version():
    obs = parse_rollout_jsonl(ROLLOUT)
    assert obs.model == "gpt-5.4"
    assert obs.cli_version == "0.146.0"
    assert obs.total_usage["total_tokens"] == 1050
    assert obs.last_usage["input_tokens"] == 40


def test_round_trip_schema():
    result = session_from_capture(_capture(), _task())
    again = Layer4SessionResult.from_dict(result.to_dict())
    assert again.to_dict() == result.to_dict()


def test_pilot_matrix_is_eight_sessions_and_stable():
    tasks = load_pilot_tasks()
    assert [task.task_id for task in tasks] == list(PILOT_TASK_IDS)
    first = plan_matrix(tasks, seed=PILOT_SEED)
    second = plan_matrix(tasks, seed=PILOT_SEED)
    assert len(first) == len(PILOT_TASK_IDS) * len(PILOT_CONDITIONS) * PILOT_REPS
    assert [(p.task_id, p.condition, p.rep, p.execution_order) for p in first] == [
        (p.task_id, p.condition, p.rep, p.execution_order) for p in second
    ]
    assert {p.condition for p in first} == {"baseline", "overhaust"}
    assert {p.rep for p in first} == {0, 1}
    assert len({p.session_id for p in first}) == 8
    shuffled = plan_matrix(tasks, seed=PILOT_SEED + 1)
    assert [p.execution_order for p in first] == list(range(8))
    assert [(p.task_id, p.condition, p.rep) for p in first] != [
        (p.task_id, p.condition, p.rep) for p in shuffled
    ]


def test_condition_toggle_uses_the_existing_hook_and_does_not_alter_the_prompt(tmp_path: Path):
    repo = Path(__file__).resolve().parents[2]
    task = _task()
    baseline = prepare_codex_home(
        tmp_path / "baseline",
        condition="baseline",
        repo_root=repo,
        auth_mode="api_key",
    )
    over = prepare_codex_home(
        tmp_path / "over",
        condition="overhaust",
        repo_root=repo,
        auth_mode="api_key",
    )
    assert baseline.integration_path == "none"
    assert not (baseline.path / "hooks.json").exists()
    assert over.integration_path == "codex_user_prompt_submit_hook"
    assert over.hook_command is not None
    assert "overhaust_user_prompt_hook.py" in over.hook_command
    command = build_exec_command(
        binary="codex",
        prompt=task.prompt,
        cwd=tmp_path / "repo",
        model="gpt-5.4",
        last_message_path=tmp_path / "last.txt",
    )
    assert command[-1] == task.prompt
    assert "<!-- overhaust-context -->" not in " ".join(command)
    assert "--json" in command
    assert "--dangerously-bypass-hook-trust" in command
    assert command[command.index("--sandbox") + 1] == "workspace-write"
    env = build_exec_env(
        {"OPENAI_API_KEY": "sk-test-secret", "PATH": "/usr/bin"},
        codex_home=over.path,
        db_path=str(tmp_path / "bench.db"),
        project_id=task.project_id,
        hook_debug_path=tmp_path / "hook.jsonl",
        auth_mode="api_key",
    )
    assert env["CODEX_HOME"] == str(over.path)
    assert env["CODEX_API_KEY"] == "sk-test-secret"
    assert env["OVERHAUST_PROJECT_ID"] == task.project_id
    assert not (over.path / "auth.json").exists()

    login_home = tmp_path / "login-source"
    login_home.mkdir()
    (login_home / "auth.json").write_text('{"token":"secret"}\n', encoding="utf-8")
    logged = prepare_codex_home(
        tmp_path / "logged",
        condition="baseline",
        repo_root=repo,
        auth_mode="codex_login",
        auth_source=login_home / "auth.json",
    )
    assert (logged.path / "auth.json").read_text(encoding="utf-8").startswith("{")
    assert not (logged.path / "sessions").exists()


def test_result_files_are_new_and_not_overwritten(tmp_path: Path):
    first = allocate_result_paths(tmp_path, "20260925T000000Z")
    first["json"].write_text("{}\n", encoding="utf-8")
    second = allocate_result_paths(tmp_path, "20260925T000000Z")
    assert first["json"] != second["json"]
    assert first["json"].read_text(encoding="utf-8") == "{}\n"
    assert not second["json"].exists()


def test_snapshot_diff_lists_only_changed_paths(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "keep.txt").write_text("same", encoding="utf-8")
    (root / "edit.txt").write_text("before", encoding="utf-8")
    before = capture_repository_snapshot(str(root))
    (root / "edit.txt").write_text("after", encoding="utf-8")
    (root / "new.txt").write_text("new", encoding="utf-8")
    after = capture_repository_snapshot(str(root))
    assert diff_snapshot_paths(before, after) == ["edit.txt", "new.txt"]


def test_pilot_runner_records_eight_sessions_from_fake_codex(tmp_path: Path):
    tasks = load_pilot_tasks()
    root = tmp_path / "repo"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "kot.ts").write_text("export function generateKOT(){return {orderId:1}}\n", encoding="utf-8")
    snapshot = capture_repository_snapshot(str(root))
    seen = []

    def builder(_tasks):
        return Layer4Workspace(
            root=root,
            db_path=str(tmp_path / "bench.db"),
            project_id=tasks[0].project_id,
            snapshot=snapshot,
            snapshot_hash=snapshot["tree_hash"],
            repo_size="medium",
        )

    def fake_runner(command, env, cwd, timeout):
        prompt = command[-1]
        assert "<!-- overhaust-context -->" not in prompt
        assert env["OVERHAUST_DB_PATH"] == str(tmp_path / "bench.db")
        assert "overhaust_memory.db" not in env["OVERHAUST_DB_PATH"]
        home = Path(env["CODEX_HOME"])
        assert not (home / "auth.json").exists()
        hooks = home / "hooks.json"
        if hooks.exists():
            assert "overhaust_user_prompt_hook.py" in hooks.read_text(encoding="utf-8")
            Path(env["OVERHAUST_INTEGRATION_DEBUG_FILE"]).write_text(HOOK, encoding="utf-8")
        else:
            assert not hooks.exists()
        rollout_dir = home / "sessions" / "2026" / "09" / "25"
        rollout_dir.mkdir(parents=True)
        (rollout_dir / "rollout.jsonl").write_text(ROLLOUT, encoding="utf-8")
        if "Quikot" in prompt or "hardware" in prompt:
            text = (
                "The kitchen order subsystem calls generateKOT and notifyKitchen, "
                "then sendOrderToQuikotPrinter in the quikot hardware client "
                "(src/kitchen/order_service.ts, src/kitchen/kot_generator.ts, "
                "src/hardware/quikot_client.ts)."
            )
        else:
            text = (
                "generateKOT is defined in src/kitchen/kot_generator.ts and returns orderId."
            )
        stdout = COMPLETED.replace(
            "generateKOT is defined in src/kitchen/kot_generator.ts and returns an object that includes orderId.",
            text,
        )
        seen.append(
            {
                "prompt": prompt,
                "home": str(home),
                "condition_hook": hooks.exists(),
                "argv": list(command),
            }
        )
        return ProcessResult(
            returncode=0,
            stdout=stdout,
            stderr="OPENAI key sk-test-secret leaked",
            elapsed_ms=12,
            timed_out=False,
        )

    report = run_pilot(
        RunConfig(
            model="gpt-5.4",
            seed=PILOT_SEED,
            results_dir=tmp_path / "results",
            codex_bin="codex",
            env={"OPENAI_API_KEY": "sk-test-secret", "PATH": "/usr/bin"},
            command_runner=fake_runner,
            workspace_builder=builder,
            probe=CodexProbe(
                agent="codex",
                version="0.146.0",
                version_source="codex_cli_version",
                binary="codex",
            ),
        )
    )
    assert report["recorded_session_count"] == 8
    assert report["dropped_session_count"] == 0
    assert report["planned_session_count"] == 8
    assert len(seen) == 8
    assert len({item["home"] for item in seen}) == 8
    assert sum(1 for item in seen if item["condition_hook"]) == 4
    sessions = report["sessions"]
    assert len(sessions) == 8
    by_key = {(s["task_id"], s["condition"], s["rep"]): s for s in sessions}
    assert len(by_key) == 8
    base = by_key[("sym_generate_kot", "baseline", 0)]
    over = by_key[("sym_generate_kot", "overhaust", 0)]
    assert base["agent_input_tokens"]["value"] == 1000
    assert base["agent_input_tokens"]["kind"] == "exact"
    assert base["overhaust_context_tokens"]["kind"] == "unavailable"
    assert over["overhaust_context_tokens"]["value"] == 310
    assert over["overhaust_context_tokens"]["kind"] == "estimated"
    assert over["agent_input_tokens"]["value"] == 1000
    assert base["files_inspected"]["kind"] == "unavailable"
    assert base["overhaust_retrieval_latency_ms"]["kind"] == "unavailable"
    assert over["overhaust_hook_latency_ms"]["value"] == 42
    assert over["agent_total_tokens"]["value"] == 1050
    assert base["valid"] is True
    assert over["valid"] is True
    assert "sk-test-secret" not in json.dumps(base)
    prompts = {item["prompt"] for item in seen}
    assert prompts == {task.prompt for task in tasks}
    json_path = Path(report["_output_paths"]["json"])
    assert json_path.name.startswith("layer4-")
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["dropped_session_count"] == 0
    assert loaded["mode"] == "pilot"
    raw = Path(base["raw_telemetry_paths"]["exec_jsonl"])
    assert raw.is_file()
    assert raw.parent == json_path.parent
    assert raw.name.startswith(json_path.stem + "-")


def test_dry_run_does_not_launch_codex(tmp_path: Path):
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

    def explode(*_args, **_kwargs):
        raise AssertionError("dry run launched Codex")

    report = run_pilot(
        RunConfig(
            dry_run=True,
            results_dir=tmp_path / "results",
            env={},
            command_runner=explode,
            workspace_builder=builder,
            stamp="dry",
        )
    )
    assert report["mode"] == "dry_run"
    assert report["recorded_session_count"] == 0
    assert report["planned_session_count"] == 8
    assert report["dropped_session_count"] == 0
    assert Path(report["_output_paths"]["json"]).is_file()


def test_cursor_and_claude_adapters_are_not_built():
    assert require_adapter("codex").agent_id == "codex"
    with pytest.raises(UnsupportedAgent):
        require_adapter("cursor")
    with pytest.raises(UnsupportedAgent):
        require_adapter("claude_code")


def test_timeout_is_recorded_and_not_dropped(tmp_path: Path):
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

    def fake_runner(command, env, cwd, timeout):
        return ProcessResult(None, "", "timed out", timeout * 1000, True)

    report = run_pilot(
        RunConfig(
            model="gpt-5.4",
            results_dir=tmp_path / "results",
            codex_bin="codex",
            env={"OPENAI_API_KEY": "sk-test-secret"},
            command_runner=fake_runner,
            workspace_builder=builder,
            probe=CodexProbe("codex", "0.146.0", "codex_cli_version", "codex"),
            stamp="timeout",
            timeout_s=5,
        )
    )
    assert report["recorded_session_count"] == 8
    assert report["dropped_session_count"] == 0
    for session in report["sessions"]:
        assert session["timed_out"] is True
        assert "exceeded 5s" in (session["error"] or "")
        assert session["agent_input_tokens"]["kind"] == "unavailable"
        if session["condition"] == "baseline":
            assert session["outcome"] == "error"
            assert session["valid"] is False
        else:
            assert session["outcome"] == "invalid"
            assert "overhaust_hook_did_not_fire" in session["invalid_reasons"]


def test_pinned_model_is_recorded_on_every_session(tmp_path: Path):
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

    def fake_runner(command, env, cwd, timeout):
        return ProcessResult(0, COMPLETED, "", 5, False)

    probe = CodexProbe(
        agent="codex",
        version="0.146.0",
        version_source="codex_cli_version",
        binary="codex",
        warning=None,
    )
    report = run_pilot(
        RunConfig(
            model="gpt-5.4",
            results_dir=tmp_path / "results",
            codex_bin="codex",
            env={"OPENAI_API_KEY": "sk-test-secret"},
            command_runner=fake_runner,
            workspace_builder=builder,
            probe=probe,
            stamp="probe",
        )
    )
    assert report["agent_version"] == "0.146.0"
    assert report["sessions"][0]["agent"] == "codex"
    assert report["sessions"][0]["model"] == "gpt-5.4"
    assert report["sessions"][0]["model_source"] == "cli_flag"
