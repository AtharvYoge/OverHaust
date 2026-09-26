"""
Layer 4 instrumentation tests.

Uses recorded Codex JSONL and a fake process runner. No network and no API key.
"""

from __future__ import annotations

import json
from collections import Counter
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
    PROMPT_CACHE_POLICY,
    build_exec_command,
    build_exec_env,
    prepare_codex_home,
)
from benchmarks.layer4.cli import main
from benchmarks.layer4.matrix import (
    FULL_TASK_IDS,
    PILOT_CONDITIONS,
    PILOT_REPS,
    PILOT_SEED,
    PILOT_TASK_IDS,
    load_full_tasks,
    load_pilot_tasks,
    normalize_conditions,
    plan_matrix,
)
from benchmarks.layer4.runner import (
    EXECUTION_ORDER_POLICY,
    Layer4Workspace,
    PreflightError,
    ProcessResult,
    RunConfig,
    agent_behavior,
    allocate_result_paths,
    cache_analysis,
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
ZERO_TOOLS = (FIXTURES / "codex_exec_zero_tools.jsonl").read_text(encoding="utf-8")
TWO_TOOLS = (FIXTURES / "codex_exec_two_tools.jsonl").read_text(encoding="utf-8")
PROTOCOL = Path(__file__).resolve().parent / "PROTOCOL.md"


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


def _assert_pairs_are_adjacent_and_balanced(plans, *, reps: int):
    by_pair = {}
    for plan in plans:
        by_pair.setdefault(plan.pair_id, []).append(plan)
    assert len(by_pair) * 2 == len(plans)
    orders_by_task = {}
    for pair_id, members in by_pair.items():
        assert len(members) == 2
        ordered = sorted(members, key=lambda item: item.execution_order)
        assert ordered[1].execution_order == ordered[0].execution_order + 1
        assert ordered[0].execution_order % 2 == 0
        assert [item.order_in_pair for item in ordered] == [1, 2]
        assert ordered[0].condition_order == ordered[1].condition_order
        assert [item.condition for item in ordered] == ordered[0].condition_order.split("->")
        assert ordered[0].seed == ordered[1].seed
        assert ordered[0].rep == ordered[1].rep
        assert pair_id == f"{ordered[0].task_id}-r{ordered[0].rep}"
        orders_by_task.setdefault(ordered[0].task_id, []).append(ordered[0].condition_order)
    for _task_id, orders in orders_by_task.items():
        assert len(orders) == reps
        counts = Counter(orders)
        assert set(counts) <= {"baseline->overhaust", "overhaust->baseline"}
        assert abs(counts["baseline->overhaust"] - counts["overhaust->baseline"]) <= 1
        if reps == 2:
            assert counts["baseline->overhaust"] == 1
            assert counts["overhaust->baseline"] == 1


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
    _assert_pairs_are_adjacent_and_balanced(first, reps=PILOT_REPS)
    _assert_pairs_are_adjacent_and_balanced(shuffled, reps=PILOT_REPS)


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
    assert not any("cache" in part.lower() for part in command if part.startswith("--"))
    assert command[-1] == task.prompt
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
    planned_ids = [entry["session_id"] for entry in report["planned_execution_order"]]
    actual_ids = [entry["session_id"] for entry in report["actual_execution_order"]]
    assert actual_ids == planned_ids
    assert actual_ids == [session["session_id"] for session in sessions]
    for session in sessions:
        assert session["seed"] == PILOT_SEED
        assert session["order_in_pair"] in (1, 2)
        assert session["condition_order"] in {"baseline->overhaust", "overhaust->baseline"}
        assert session["pair_id"] == f"{session['task_id']}-r{session['rep']}"
        assert session["agent_input_tokens"]["value"] == 1000
        assert session["agent_cached_input_tokens"]["value"] == 200
    md = Path(report["_output_paths"]["md"]).read_text(encoding="utf-8")
    assert PROMPT_CACHE_POLICY in md
    assert "| Tools |" in md
    baseline = next(
        row for row in report["cache_analysis"]["by_condition"] if row["condition"] == "baseline"
    )
    assert baseline["n_sessions"] == 4
    assert baseline["mean_input_tokens"] == 1000
    assert baseline["mean_cached_input_tokens"] == 200
    assert baseline["cached_input_rate"] == 0.2
    assert baseline["mean_total_tokens"] == 1050
    over = next(
        row for row in report["cache_analysis"]["by_condition"] if row["condition"] == "overhaust"
    )
    assert over["mean_input_tokens"] == 1000
    assert over["mean_input_tokens"] != 1000 + 310


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
    assert report["preset"] == "pilot"
    assert report["recorded_session_count"] == 0
    assert report["planned_session_count"] == 8
    assert report["dropped_session_count"] == 0
    assert len(report["planned_execution_order"]) == 8
    assert report["actual_execution_order"] == []
    assert report["cache_control_note"] == PROMPT_CACHE_POLICY
    md = Path(report["_output_paths"]["md"]).read_text(encoding="utf-8")
    assert PROMPT_CACHE_POLICY in md
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


def _workspace(tmp_path: Path, tasks):
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

    return builder


def _session_for(task_id: str, **overrides):
    task = _task(task_id)
    capture = _capture(
        task_id=task.task_id,
        prompt=task.prompt,
        command=["codex", "exec", "--json", task.prompt],
        session_id=overrides.pop("session_id", f"{task.task_id}-baseline-r0"),
        **overrides,
    )
    return session_from_capture(capture, task)


def test_condition_order_is_balanced_deterministic_and_adjacent():
    tasks = load_pilot_tasks()
    first = plan_matrix(tasks, seed=PILOT_SEED)
    again = plan_matrix(tasks, seed=PILOT_SEED)
    assert [plan.to_dict() for plan in first] == [plan.to_dict() for plan in again]
    _assert_pairs_are_adjacent_and_balanced(first, reps=2)
    other = plan_matrix(tasks, seed=PILOT_SEED + 7)
    assert [(plan.pair_id, plan.condition_order, plan.execution_order) for plan in first] != [
        (plan.pair_id, plan.condition_order, plan.execution_order) for plan in other
    ]
    for seed in (1, 2, 99):
        _assert_pairs_are_adjacent_and_balanced(plan_matrix(tasks, seed=seed), reps=2)
    one_task = tasks[:1]
    for reps in (1, 3, 5):
        planned = plan_matrix(one_task, reps=reps, seed=PILOT_SEED)
        _assert_pairs_are_adjacent_and_balanced(planned, reps=reps)
        assert len(planned) == reps * 2


def test_full_preset_has_twenty_sessions_with_balanced_composition(tmp_path: Path):
    tasks = load_full_tasks()
    assert [task.task_id for task in tasks] == list(FULL_TASK_IDS)
    assert len(tasks) == 5
    plans = plan_matrix(tasks, seed=PILOT_SEED)
    assert len(plans) == 20
    keys = Counter((plan.task_id, plan.condition, plan.rep) for plan in plans)
    assert len(keys) == 20
    for task_id in FULL_TASK_IDS:
        for condition in ("baseline", "overhaust"):
            for rep in (0, 1):
                assert keys[(task_id, condition, rep)] == 1
    _assert_pairs_are_adjacent_and_balanced(plans, reps=2)
    assert [plan.execution_order for plan in plans] == list(range(20))
    # Locked to random.Random(1) pair counterbalancing of the five Layer 3 tasks.
    assert [plan.session_id for plan in plans] == [
        "cross_order_to_printer-overhaust-r0",
        "cross_order_to_printer-baseline-r0",
        "flow_order_to_kitchen-overhaust-r1",
        "flow_order_to_kitchen-baseline-r1",
        "flow_order_to_kitchen-baseline-r0",
        "flow_order_to_kitchen-overhaust-r0",
        "cross_order_to_printer-baseline-r1",
        "cross_order_to_printer-overhaust-r1",
        "arch_kitchen_hardware-overhaust-r0",
        "arch_kitchen_hardware-baseline-r0",
        "arch_kitchen_hardware-baseline-r1",
        "arch_kitchen_hardware-overhaust-r1",
        "sym_generate_kot-baseline-r0",
        "sym_generate_kot-overhaust-r0",
        "impact_change_generate_kot-overhaust-r0",
        "impact_change_generate_kot-baseline-r0",
        "sym_generate_kot-overhaust-r1",
        "sym_generate_kot-baseline-r1",
        "impact_change_generate_kot-baseline-r1",
        "impact_change_generate_kot-overhaust-r1",
    ]

    report = run_pilot(
        RunConfig(
            preset="full",
            dry_run=True,
            seed=PILOT_SEED,
            results_dir=tmp_path / "results",
            env={},
            command_runner=lambda *_a, **_k: (_ for _ in ()).throw(
                AssertionError("dry run launched Codex")
            ),
            workspace_builder=_workspace(tmp_path, tasks),
            stamp="full-dry",
        )
    )
    assert report["preset"] == "full"
    assert report["mode"] == "dry_run"
    assert report["planned_session_count"] == 20
    assert report["recorded_session_count"] == 0
    assert report["actual_execution_order"] == []
    assert len(report["planned_execution_order"]) == 20
    assert [entry["session_id"] for entry in report["planned_execution_order"]] == [
        plan.session_id for plan in plans
    ]
    md = Path(report["_output_paths"]["md"]).read_text(encoding="utf-8")
    assert PROMPT_CACHE_POLICY in md
    assert PROMPT_CACHE_POLICY in PROTOCOL.read_text(encoding="utf-8")


def test_full_preset_records_twenty_sessions(tmp_path: Path):
    tasks = load_full_tasks()
    seen = []

    def fake_runner(command, env, cwd, timeout):
        seen.append(command[-1])
        return ProcessResult(0, COMPLETED, "", 5, False)

    report = run_pilot(
        RunConfig(
            preset="full",
            model="gpt-4o-mini",
            seed=PILOT_SEED,
            results_dir=tmp_path / "results",
            codex_bin="codex",
            env={"OPENAI_API_KEY": "sk-test-secret"},
            command_runner=fake_runner,
            workspace_builder=_workspace(tmp_path, tasks),
            probe=CodexProbe("codex", "0.146.0", "codex_cli_version", "codex"),
            stamp="full-live",
        )
    )
    assert report["mode"] == "full"
    assert report["planned_session_count"] == 20
    assert report["recorded_session_count"] == 20
    assert report["dropped_session_count"] == 0
    assert len(seen) == 20
    composition = Counter(
        (session["task_id"], session["condition"], session["rep"])
        for session in report["sessions"]
    )
    assert len(composition) == 20
    assert set(composition) == {
        (task_id, condition, rep)
        for task_id in FULL_TASK_IDS
        for condition in ("baseline", "overhaust")
        for rep in (0, 1)
    }
    assert [entry["session_id"] for entry in report["actual_execution_order"]] == [
        entry["session_id"] for entry in report["planned_execution_order"]
    ]
    for entry in report["actual_execution_order"]:
        assert entry["seed"] == PILOT_SEED
        assert entry["order_in_pair"] in (1, 2)
        assert "->" in entry["condition_order"]


def test_run_result_records_planned_and_actual_order_fields(tmp_path: Path):
    tasks = load_pilot_tasks()
    seen = []

    def fake_runner(command, env, cwd, timeout):
        seen.append(Path(env["CODEX_HOME"]).parent.name)
        return ProcessResult(0, COMPLETED, "", 4, False)

    report = run_pilot(
        RunConfig(
            model="gpt-4o-mini",
            seed=PILOT_SEED,
            results_dir=tmp_path / "results",
            codex_bin="codex",
            env={"OPENAI_API_KEY": "sk-test-secret"},
            command_runner=fake_runner,
            workspace_builder=_workspace(tmp_path, tasks),
            probe=CodexProbe("codex", "0.146.0", "codex_cli_version", "codex"),
            stamp="order",
        )
    )
    assert seen == [entry["session_id"] for entry in report["actual_execution_order"]]
    assert seen == [entry["session_id"] for entry in report["planned_execution_order"]]
    by_id = {session["session_id"]: session for session in report["sessions"]}
    for entry in report["planned_execution_order"]:
        session = by_id[entry["session_id"]]
        assert session["pair_id"] == entry["pair_id"]
        assert session["order_in_pair"] == entry["order_in_pair"]
        assert session["condition_order"] == entry["condition_order"]
        assert session["seed"] == entry["seed"] == PILOT_SEED
        assert session["execution_order"] == entry["execution_order"]


def test_cache_analysis_math_excludes_invalid_and_unavailable():
    rollout = ROLLOUT.replace('"total_tokens":1050', '"total_tokens":1234', 1)
    sym = "sym_generate_kot"
    arch = "arch_kitchen_hardware"
    sessions = [
        _session_for(sym, stdout=COMPLETED, session_id=f"{sym}-baseline-r0", rep=0),
        _session_for(
            sym,
            stdout=COMPLETED,
            rollout_text=rollout,
            session_id=f"{sym}-baseline-r1",
            rep=1,
        ),
        _session_for(
            sym,
            stdout=MISSING_CACHED,
            session_id=f"{sym}-baseline-r2",
            rep=2,
        ),
        _session_for(
            sym,
            stdout=COMPLETED,
            hook_debug=HOOK,
            session_id=f"{sym}-baseline-invalid",
            rep=3,
        ),
        _session_for(
            arch,
            stdout=TWO_TOOLS,
            session_id=f"{arch}-baseline-r0",
            rep=0,
        ),
        _session_for(
            sym,
            stdout=ZERO_TOOLS,
            condition="overhaust",
            session_id=f"{sym}-overhaust-r0",
            hook_debug=HOOK,
            integration_path="codex_user_prompt_submit_hook",
            hook_command='python3 "/repo/scripts/integrations/overhaust_user_prompt_hook.py"',
        ),
    ]
    assert sessions[0].valid and sessions[0].agent_total_tokens.is_unavailable
    assert sessions[1].agent_total_tokens.value == 1234
    assert sessions[2].valid and sessions[2].agent_cached_input_tokens.is_unavailable
    assert sessions[2].tool_calls.value == 0
    assert sessions[3].valid is False
    assert sessions[4].valid is True
    assert sessions[4].tool_calls.value == 2
    assert sessions[5].valid is True
    assert sessions[5].overhaust_context_tokens.value == 310
    assert sessions[5].overhaust_context_tokens.kind == "estimated"
    assert sessions[5].agent_input_tokens.value == 1000
    assert sessions[5].agent_cached_input_tokens.value == 0
    assert sessions[5].tool_calls.value == 0

    analysis = cache_analysis(sessions)
    assert "overhaust_context" not in json.dumps(analysis)
    by_key = {
        (row["task_id"], row["condition"]): row
        for row in analysis["by_task_condition"]
    }
    sym_base = by_key[(sym, "baseline")]
    assert sym_base["n_sessions"] == 3
    assert sym_base["n_invalid_excluded"] == 1
    assert sym_base["mean_input_tokens"] == 670
    assert sym_base["n_input"] == 3
    assert sym_base["input_unavailable"] == 0
    assert sym_base["mean_cached_input_tokens"] == 200
    assert sym_base["n_cached_input"] == 2
    assert sym_base["cached_input_unavailable"] == 1
    assert sym_base["cached_input_rate"] == 0.2
    assert sym_base["n_cached_input_rate"] == 2
    assert sym_base["cached_input_rate_excluded"] == 1
    assert sym_base["mean_output_tokens"] == 34
    assert sym_base["mean_total_tokens"] == 1234
    assert sym_base["n_total"] == 1
    assert sym_base["total_unavailable"] == 2
    assert sym_base["mean_input_tokens"] != 800

    arch_base = by_key[(arch, "baseline")]
    assert arch_base["n_sessions"] == 1
    assert arch_base["mean_input_tokens"] == 100
    assert arch_base["mean_cached_input_tokens"] == 25
    assert arch_base["cached_input_rate"] == 0.25
    assert arch_base["mean_output_tokens"] == 10
    assert arch_base["mean_total_tokens"] is None
    assert arch_base["total_unavailable"] == 1

    sym_over = by_key[(sym, "overhaust")]
    assert sym_over["n_sessions"] == 1
    assert sym_over["mean_input_tokens"] == 1000
    assert sym_over["mean_cached_input_tokens"] == 0
    assert sym_over["cached_input_rate"] == 0.0
    assert sym_over["mean_output_tokens"] == 50
    assert sym_over["mean_total_tokens"] is None
    assert sym_over["total_unavailable"] == 1
    assert sym_over["mean_input_tokens"] != 1310

    by_condition = {row["condition"]: row for row in analysis["by_condition"]}
    baseline = by_condition["baseline"]
    assert baseline["n_sessions"] == 4
    assert baseline["n_invalid_excluded"] == 1
    assert baseline["mean_input_tokens"] == 527.5
    assert baseline["n_cached_input"] == 3
    assert baseline["cached_input_unavailable"] == 1
    assert baseline["cached_input_rate"] == pytest.approx(425 / 2100)
    assert baseline["mean_output_tokens"] == 28
    assert baseline["mean_total_tokens"] == 1234
    assert baseline["n_total"] == 1
    assert baseline["total_unavailable"] == 3
    over = by_condition["overhaust"]
    assert over["mean_input_tokens"] == 1000
    assert over["n_invalid_excluded"] == 0

    behavior = agent_behavior(sessions)
    behavior_key = {
        (row["task_id"], row["condition"]): row
        for row in behavior["by_task_condition"]
    }
    assert behavior_key[(sym, "baseline")]["mean_tool_calls"] == pytest.approx(2 / 3)
    assert behavior_key[(sym, "baseline")]["zero_tool_call_sessions"] == 1
    assert behavior_key[(sym, "baseline")]["n_invalid_excluded"] == 1
    assert behavior_key[(sym, "baseline")]["tool_calls_unavailable"] == 0
    assert behavior_key[(arch, "baseline")]["mean_tool_calls"] == 2
    assert behavior_key[(arch, "baseline")]["zero_tool_call_sessions"] == 0
    assert behavior_key[(sym, "overhaust")]["mean_tool_calls"] == 0
    assert behavior_key[(sym, "overhaust")]["zero_tool_call_sessions"] == 1

    empty = cache_analysis([])
    assert empty["by_task_condition"] == []
    assert empty["by_condition"] == []


def test_markdown_session_table_includes_tool_call_counts(tmp_path: Path):
    tasks = load_pilot_tasks()

    def fake_runner(command, env, cwd, timeout):
        home = Path(env["CODEX_HOME"])
        if (home / "hooks.json").exists():
            Path(env["OVERHAUST_INTEGRATION_DEBUG_FILE"]).write_text(HOOK, encoding="utf-8")
            return ProcessResult(0, ZERO_TOOLS, "", 4, False)
        return ProcessResult(0, COMPLETED, "", 4, False)

    report = run_pilot(
        RunConfig(
            model="gpt-4o-mini",
            seed=PILOT_SEED,
            results_dir=tmp_path / "results",
            codex_bin="codex",
            env={"OPENAI_API_KEY": "sk-test-secret"},
            command_runner=fake_runner,
            workspace_builder=_workspace(tmp_path, tasks),
            probe=CodexProbe("codex", "0.146.0", "codex_cli_version", "codex"),
            stamp="tools",
        )
    )
    md = Path(report["_output_paths"]["md"]).read_text(encoding="utf-8")
    assert PROMPT_CACHE_POLICY in md
    assert "| Order | Session | Task | Condition | Rep | Outcome | Valid | Primary | Input | Cached | Output | Total | Tools |" in md
    for session in report["sessions"]:
        if session["condition"] == "overhaust":
            assert session["valid"] is True
            assert session["tool_calls"]["value"] == 0
        else:
            assert session["tool_calls"]["value"] == 1
    session_section = md.split("## Sessions", 1)[1].split("## Cache analysis", 1)[0]
    for line in session_section.splitlines():
        if not line.startswith("|"):
            continue
        if "-overhaust-" in line:
            assert line.endswith("| 0 |")
        if "-baseline-" in line:
            assert line.endswith("| 1 |")
    over_rows = [
        row for row in report["agent_behavior"]["by_task_condition"] if row["condition"] == "overhaust"
    ]
    assert over_rows
    assert all(row["zero_tool_call_sessions"] == row["n_sessions"] for row in over_rows)
    assert all(row["mean_tool_calls"] == 0 for row in over_rows)


# Baseline rows of benchmarks/results/layer4-20260926T081938Z.json
# actual_execution_order, seed 1, preset full. That file is a local result
# (gitignored). The order is the baseline half of the locked two-condition plan.
FULL_SEED1_BASELINE_ORDER = (
    ("cross_order_to_printer", 0),
    ("flow_order_to_kitchen", 1),
    ("flow_order_to_kitchen", 0),
    ("cross_order_to_printer", 1),
    ("arch_kitchen_hardware", 0),
    ("arch_kitchen_hardware", 1),
    ("sym_generate_kot", 0),
    ("impact_change_generate_kot", 0),
    ("sym_generate_kot", 1),
    ("impact_change_generate_kot", 1),
)
FULL_SEED1_BASELINE_POSITIONS = (1, 3, 4, 6, 9, 10, 12, 15, 17, 18)
RECORDED_FULL_RUN = (
    Path(__file__).resolve().parents[1] / "results" / "layer4-20260926T081938Z.json"
)


def test_baseline_only_seed1_full_order_matches_recorded_baseline_sessions():
    tasks = load_full_tasks()
    full = plan_matrix(tasks, seed=PILOT_SEED)
    baseline = plan_matrix(tasks, seed=PILOT_SEED, conditions=("baseline",))
    overhaust = plan_matrix(tasks, seed=PILOT_SEED, conditions="overhaust")
    full_baseline = [plan for plan in full if plan.condition == "baseline"]
    full_overhaust = [plan for plan in full if plan.condition == "overhaust"]

    assert [(plan.task_id, plan.rep) for plan in full_baseline] == list(FULL_SEED1_BASELINE_ORDER)
    assert [plan.execution_order for plan in full_baseline] == list(FULL_SEED1_BASELINE_POSITIONS)
    assert [(plan.task_id, plan.rep) for plan in baseline] == list(FULL_SEED1_BASELINE_ORDER)
    assert [plan.execution_order for plan in baseline] == list(range(10))
    assert len(baseline) == 10
    for index, (kept, source) in enumerate(zip(baseline, full_baseline)):
        assert kept.session_id == source.session_id
        assert kept.condition == "baseline"
        assert kept.pair_id == source.pair_id == f"{source.task_id}-r{source.rep}"
        assert kept.original_pair_id == source.pair_id
        assert kept.original_planned_position == source.execution_order == FULL_SEED1_BASELINE_POSITIONS[index]
        assert kept.order_in_pair == source.order_in_pair
        assert kept.condition_order == source.condition_order
        assert kept.prompt == source.prompt
        assert kept.project_id == source.project_id
        assert kept.seed == source.seed == PILOT_SEED
        assert kept.rep == source.rep
        recorded = kept.to_dict()
        assert recorded["original_pair_id"] == source.pair_id
        assert recorded["original_planned_position"] == source.execution_order
    assert [(plan.task_id, plan.rep) for plan in overhaust] == [
        (plan.task_id, plan.rep) for plan in full_overhaust
    ]
    assert [plan.original_planned_position for plan in overhaust] == [
        plan.execution_order for plan in full_overhaust
    ]

    if RECORDED_FULL_RUN.is_file():
        payload = json.loads(RECORDED_FULL_RUN.read_text(encoding="utf-8"))
        recorded_baseline = [
            (entry["task_id"], entry["rep"])
            for entry in payload["actual_execution_order"]
            if entry["condition"] == "baseline"
        ]
        assert recorded_baseline == list(FULL_SEED1_BASELINE_ORDER)


def test_default_conditions_keep_two_condition_plan_and_report(tmp_path: Path):
    tasks = load_full_tasks()
    default = plan_matrix(tasks, seed=PILOT_SEED)
    explicit = plan_matrix(tasks, seed=PILOT_SEED, conditions=("baseline", "overhaust"))
    reversed_both = plan_matrix(tasks, seed=PILOT_SEED, conditions=("overhaust", "baseline"))
    comma_both = plan_matrix(tasks, seed=PILOT_SEED, conditions="baseline,overhaust")
    assert [plan.to_dict() for plan in default] == [plan.to_dict() for plan in explicit]
    assert [plan.to_dict() for plan in default] == [plan.to_dict() for plan in reversed_both]
    assert [plan.to_dict() for plan in default] == [plan.to_dict() for plan in comma_both]
    assert len(default) == 20
    assert [plan.execution_order for plan in default] == list(range(20))
    assert set(default[0].to_dict()) == {
        "session_id",
        "task_id",
        "condition",
        "rep",
        "seed",
        "execution_order",
        "prompt",
        "project_id",
        "pair_id",
        "order_in_pair",
        "condition_order",
    }
    assert all(plan.original_pair_id is None and plan.original_planned_position is None for plan in default)
    assert normalize_conditions(None) == PILOT_CONDITIONS
    pilot = plan_matrix(load_pilot_tasks(), seed=PILOT_SEED)
    assert len(pilot) == 8
    assert [(plan.task_id, plan.condition, plan.rep) for plan in pilot] == [
        (plan.task_id, plan.condition, plan.rep)
        for plan in plan_matrix(load_pilot_tasks(), seed=PILOT_SEED, conditions=None)
    ]

    report = run_pilot(
        RunConfig(
            preset="full",
            dry_run=True,
            seed=PILOT_SEED,
            model="gpt-4o",
            results_dir=tmp_path / "results",
            env={},
            command_runner=lambda *_a, **_k: (_ for _ in ()).throw(
                AssertionError("dry run launched Codex")
            ),
            workspace_builder=_workspace(tmp_path, tasks),
            stamp="default-both",
        )
    )
    assert report["conditions"] == ["baseline", "overhaust"]
    assert "single_condition" not in report
    assert report["planned_session_count"] == 20
    assert report["execution_order_policy"] == EXECUTION_ORDER_POLICY
    assert report["cache_control_note"] == PROMPT_CACHE_POLICY
    assert "original_planned_position" not in report["plans"][0]
    assert "original_pair_id" not in report["planned_execution_order"][0]
    md = Path(report["_output_paths"]["md"]).read_text(encoding="utf-8")
    assert "single-condition" not in md
    assert "Original position" not in md
    assert PROMPT_CACHE_POLICY in md
    assert "## Cache analysis" in md
    assert "## Agent behavior" in md
    with pytest.raises(ValueError):
        plan_matrix(tasks, conditions=("baseline", "other"))
    bad_ws = tmp_path / "bad-ws"
    bad_ws.mkdir()
    with pytest.raises(PreflightError, match="duplicates"):
        run_pilot(
            RunConfig(
                preset="pilot",
                dry_run=True,
                conditions=("baseline", "baseline"),
                results_dir=tmp_path / "bad",
                env={},
                workspace_builder=_workspace(bad_ws, load_pilot_tasks()),
            )
        )


def test_single_condition_report_and_markdown_omit_comparison(tmp_path: Path):
    tasks = load_full_tasks()
    seen = []

    def fake_runner(command, env, cwd, timeout):
        home = Path(env["CODEX_HOME"])
        assert not (home / "hooks.json").exists()
        assert command[command.index("--model") + 1] == "gpt-4o"
        assert "--dangerously-bypass-hook-trust" in command
        seen.append(command[-1])
        return ProcessResult(0, COMPLETED, "", 5, False)

    report = run_pilot(
        RunConfig(
            preset="full",
            model="gpt-4o",
            seed=PILOT_SEED,
            conditions=["baseline"],
            timeout_s=600,
            results_dir=tmp_path / "results",
            codex_bin="codex",
            env={"OPENAI_API_KEY": "sk-test-secret"},
            command_runner=fake_runner,
            workspace_builder=_workspace(tmp_path, tasks),
            probe=CodexProbe("codex", "0.146.0", "codex_cli_version", "codex"),
            stamp="baseline-only",
        )
    )
    assert report["conditions"] == ["baseline"]
    assert report["single_condition"] == "baseline"
    assert report["planned_session_count"] == 10
    assert report["recorded_session_count"] == 10
    assert report["dropped_session_count"] == 0
    assert report["mode"] == "full"
    assert report["seed"] == PILOT_SEED
    assert report["reps"] == 2
    assert report["cache_control_note"] == PROMPT_CACHE_POLICY
    assert [session["condition"] for session in report["sessions"]] == ["baseline"] * 10
    assert [(session["task_id"], session["rep"]) for session in report["sessions"]] == list(
        FULL_SEED1_BASELINE_ORDER
    )
    assert [entry["original_planned_position"] for entry in report["planned_execution_order"]] == list(
        FULL_SEED1_BASELINE_POSITIONS
    )
    assert [entry["original_pair_id"] for entry in report["actual_execution_order"]] == [
        f"{task_id}-r{rep}" for task_id, rep in FULL_SEED1_BASELINE_ORDER
    ]
    for session in report["sessions"]:
        assert session["original_pair_id"] == session["pair_id"]
        assert session["original_planned_position"] in FULL_SEED1_BASELINE_POSITIONS
        assert session["integration_path"] == "none"
        assert session["hook_command"] is None
        assert "original_planned_position" in session
    assert {row["condition"] for row in report["cache_analysis"]["by_condition"]} == {"baseline"}
    assert {row["condition"] for row in report["cache_analysis"]["by_task_condition"]} == {"baseline"}
    assert report["agent_behavior"]["by_task_condition"]
    assert {row["condition"] for row in report["agent_behavior"]["by_task_condition"]} == {"baseline"}
    assert len(seen) == 10

    md = Path(report["_output_paths"]["md"]).read_text(encoding="utf-8")
    assert "This is a single-condition run (`baseline` only). " in md
    assert "No cross-condition comparison or reduction is reported." in md
    assert PROMPT_CACHE_POLICY in md
    assert md.count(PROMPT_CACHE_POLICY) >= 2
    assert "## Cache analysis" in md
    assert "## Agent behavior" in md
    assert "Figures below are for `baseline` only." in md
    assert "Tool-call figures below are for `baseline` only." in md
    assert "| baseline |" in md
    assert "Original position" in md
    assert "| Tools |" in md
    lowered = md.lower()
    for phrase in (
        "compared with",
        "compared to",
        "percent reduction",
        "reduction_pct",
        "fewer tokens",
        "| reduction |",
    ):
        assert phrase not in lowered

    dry_ws = tmp_path / "dry-ws"
    dry_ws.mkdir()
    dry = run_pilot(
        RunConfig(
            preset="full",
            dry_run=True,
            seed=PILOT_SEED,
            model="gpt-4o",
            conditions=("baseline",),
            timeout_s=600,
            results_dir=tmp_path / "dry",
            env={},
            command_runner=lambda *_a, **_k: (_ for _ in ()).throw(
                AssertionError("dry run launched Codex")
            ),
            workspace_builder=_workspace(dry_ws, tasks),
            stamp="baseline-dry",
        )
    )
    assert dry["planned_session_count"] == 10
    assert dry["recorded_session_count"] == 0
    assert dry["actual_execution_order"] == []
    assert dry["conditions"] == ["baseline"]
    assert dry["model_requested"] == "gpt-4o"
    dry_md = Path(dry["_output_paths"]["md"]).read_text(encoding="utf-8")
    assert "This is a single-condition run (`baseline` only)." in dry_md
    assert "## Cache analysis" in dry_md
    assert "## Agent behavior" in dry_md
    assert PROMPT_CACHE_POLICY in dry_md


def test_cli_dry_run_full_baseline_plans_ten_sessions(tmp_path: Path, monkeypatch):
    tasks = load_full_tasks()
    monkeypatch.setattr(
        "benchmarks.layer4.runner.build_fixture_workspace",
        _workspace(tmp_path, tasks),
    )
    results = tmp_path / "results"
    code = main([
        "--dry-run",
        "--preset",
        "full",
        "--conditions",
        "baseline",
        "--model",
        "gpt-4o",
        "--results-dir",
        str(results),
        "--seed",
        "1",
    ])
    assert code == 0
    report = json.loads(next(results.glob("layer4-*.json")).read_text(encoding="utf-8"))
    assert report["planned_session_count"] == 10
    assert report["recorded_session_count"] == 0
    assert report["conditions"] == ["baseline"]
    assert report["model_requested"] == "gpt-4o"
    assert report["seed"] == 1
    assert report["preset"] == "full"
    assert [(entry["task_id"], entry["rep"]) for entry in report["planned_execution_order"]] == list(
        FULL_SEED1_BASELINE_ORDER
    )
    md = next(results.glob("layer4-*.md")).read_text(encoding="utf-8")
    assert "single-condition" in md
    assert PROMPT_CACHE_POLICY in md

    default_results = tmp_path / "default"
    code = main(["--dry-run", "--results-dir", str(default_results), "--seed", "1"])
    assert code == 0
    default_report = json.loads(next(default_results.glob("layer4-*.json")).read_text(encoding="utf-8"))
    assert default_report["conditions"] == ["baseline", "overhaust"]
    assert default_report["planned_session_count"] == 8
    assert "single_condition" not in default_report
