"""
Plan and execute a Layer 4 session matrix.

Results are new timestamped files under `benchmarks/results/` (the same
local-results directory the rest of the harness uses). Existing files are
never overwritten. A failed or partially instrumented session is written;
it is not dropped.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from benchmarks import BENCHMARK_VERSION
from benchmarks.layer4 import PROTOCOL_VERSION, RUN_SCHEMA_VERSION, SCHEMA_VERSION
from benchmarks.layer4.codex_adapter import (
    CodexProbe,
    CodexSessionCapture,
    probe_codex,
    session_from_capture,
)
from benchmarks.layer4.codex_parse import iter_rollout_files
from benchmarks.layer4.condition import (
    CODEX_EXEC_PERMISSIONS,
    build_exec_command,
    build_exec_env,
    detect_auth_mode,
    prepare_codex_home,
)
from benchmarks.layer4.matrix import (
    PILOT_NAME,
    PILOT_SEED,
    SessionPlan,
    load_pilot_tasks,
    plan_matrix,
)
from benchmarks.layer4.schema import (
    Layer4SessionResult,
    unavailable_metrics,
    telemetry_gaps_for,
)
from benchmarks.repro import capture_repository_snapshot, restore_repository_snapshot
from benchmarks.schemas import BenchmarkTask


CLAIM_POLICY = (
    "Layer 4 instrumentation record. Session totals are whatever the agent "
    "reported. OverHaust context tokens are separate and were not subtracted. "
    "This file is not a product token-reduction result."
)


class PreflightError(RuntimeError):
    """The matrix cannot start. No result file is written."""


@dataclass
class ProcessResult:
    returncode: Optional[int]
    stdout: str
    stderr: str
    elapsed_ms: int
    timed_out: bool = False


@dataclass
class Layer4Workspace:
    root: Path
    db_path: str
    project_id: str
    snapshot: Dict[str, Any]
    snapshot_hash: str
    repo_size: str
    close: Callable[[], None] = field(default=lambda: None)


@dataclass
class RunConfig:
    model: Optional[str] = None
    seed: int = PILOT_SEED
    timeout_s: int = 600
    results_dir: Optional[Path] = None
    dry_run: bool = False
    codex_bin: Optional[str] = None
    repo_root: Optional[Path] = None
    env: Optional[Dict[str, str]] = None
    command_runner: Optional[Callable[..., ProcessResult]] = None
    workspace_builder: Optional[Callable[..., Layer4Workspace]] = None
    probe: Optional[CodexProbe] = None
    python: Optional[str] = None
    stamp: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def default_results_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "results"


def default_command_runner(
    command: Sequence[str],
    env: Dict[str, str],
    cwd: str,
    timeout: int,
) -> ProcessResult:
    import time

    started = time.perf_counter()
    try:
        proc = subprocess.run(
            list(command),
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        return ProcessResult(
            returncode=None,
            stdout=_as_text(exc.stdout),
            stderr=_as_text(exc.stderr),
            elapsed_ms=elapsed,
            timed_out=True,
        )
    elapsed = int((time.perf_counter() - started) * 1000)
    return ProcessResult(
        returncode=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        elapsed_ms=elapsed,
        timed_out=False,
    )


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _redact(text: str, env: Dict[str, str]) -> str:
    redacted = text or ""
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"):
        secret = (env.get(key) or "").strip()
        if len(secret) >= 8:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted


def build_fixture_workspace(
    tasks: Sequence[BenchmarkTask],
    *,
    repo_size: Optional[str] = None,
) -> Layer4Workspace:
    from benchmarks.repos import prepare_sized_fixture

    project_ids = {task.project_id for task in tasks}
    if len(project_ids) != 1:
        raise PreflightError(
            "Layer 4 pilot tasks must share one project_id so one indexed "
            f"fixture can serve every session. Got {sorted(project_ids)}."
        )
    sizes = {task.repository_size for task in tasks}
    if repo_size is None:
        if len(sizes) != 1:
            raise PreflightError(
                "Pilot tasks name different repository_size values: "
                f"{sorted(sizes)}."
            )
        repo_size = next(iter(sizes))
    project_id = next(iter(project_ids))
    fixture = prepare_sized_fixture(repo_size, project_id=project_id)  # type: ignore[arg-type]
    snapshot = capture_repository_snapshot(str(fixture.root))
    if not snapshot.get("ok") or not snapshot.get("tree_hash"):
        fixture.close()
        raise PreflightError("Could not hash the fixture snapshot.")

    def _close() -> None:
        fixture.close()

    return Layer4Workspace(
        root=fixture.root,
        db_path=fixture.db_path,
        project_id=project_id,
        snapshot=snapshot,
        snapshot_hash=str(snapshot["tree_hash"]),
        repo_size=str(repo_size),
        close=_close,
    )


def diff_snapshot_paths(before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
    before_files = before.get("files") or {}
    after_files = after.get("files") or {}
    names = sorted(set(before_files) | set(after_files))
    return [name for name in names if before_files.get(name) != after_files.get(name)]


def allocate_result_paths(results_dir: Path, stamp: Optional[str] = None) -> Dict[str, Path]:
    """Pick a fresh layer4-<stamp> pair. Never returns a path that already exists."""
    results_dir.mkdir(parents=True, exist_ok=True)
    base = stamp or _stamp()
    n = 0
    while True:
        suffix = "" if n == 0 else f"-{n}"
        json_path = results_dir / f"layer4-{base}{suffix}.json"
        md_path = results_dir / f"layer4-{base}{suffix}.md"
        if not json_path.exists() and not md_path.exists():
            return {"json": json_path, "md": md_path, "stamp": base + suffix}
        n += 1
        if n > 1000:
            raise PreflightError(f"Could not allocate a free result name under {results_dir}")


def _read_rollout(codex_home: Path) -> tuple[str, List[str]]:
    paths = list(iter_rollout_files(codex_home))
    chunks = []
    names = []
    for path in paths:
        names.append(str(path))
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except OSError:
            continue
    return "\n".join(chunks), names


def _error_result(
    plan: SessionPlan,
    *,
    snapshot_hash: str,
    probe: CodexProbe,
    message: str,
    started_at: str,
    finished_at: str,
) -> Layer4SessionResult:
    figures = unavailable_metrics(message)
    return Layer4SessionResult(
        schema_version=SCHEMA_VERSION,
        session_id=plan.session_id,
        agent="codex",
        agent_version=probe.version,
        agent_version_source=probe.version_source,
        agent_version_warning=probe.warning,
        model=None,
        model_requested=None,
        model_reported=None,
        model_source="unavailable",
        condition=plan.condition,
        task_id=plan.task_id,
        rep=plan.rep,
        seed=plan.seed,
        execution_order=plan.execution_order,
        snapshot_hash=snapshot_hash,
        snapshot_hash_before=None,
        snapshot_hash_after=None,
        raw_telemetry_source="unavailable",
        raw_telemetry_paths={},
        outcome="error",
        valid=False,
        invalid_reasons=[],
        telemetry_gaps=telemetry_gaps_for(figures),
        primary_metric_status="missing",
        error=message,
        started_at=started_at,
        finished_at=finished_at,
        prompt_sha256="",
        **figures,
    )


def _execute_session(
    plan: SessionPlan,
    task: BenchmarkTask,
    workspace: Layer4Workspace,
    config: RunConfig,
    *,
    probe: CodexProbe,
    binary: str,
    auth_mode: str,
    env: Dict[str, str],
    repo_root: Path,
    run_dir: Path,
    runner: Callable[..., ProcessResult],
) -> Layer4SessionResult:
    started = _now()
    session_dir = run_dir / plan.session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    codex_home = session_dir / "codex-home"
    hook_debug_path = session_dir / "hook-debug.jsonl"
    last_message_path = session_dir / "last-message.txt"

    restore = restore_repository_snapshot(str(workspace.root), workspace.snapshot)
    before = capture_repository_snapshot(str(workspace.root))
    before_hash = before.get("tree_hash")
    restore_ok = bool(restore.get("verified")) and before_hash == workspace.snapshot_hash

    home = prepare_codex_home(
        codex_home,
        condition=plan.condition,
        repo_root=repo_root,
        auth_mode=auth_mode,
        python=config.python or sys.executable,
    )
    sessions_dir = codex_home / "sessions"
    fresh = not sessions_dir.exists() or not any(sessions_dir.rglob("*"))
    command = build_exec_command(
        binary=binary,
        prompt=plan.prompt,
        cwd=workspace.root,
        model=config.model,
        last_message_path=last_message_path,
    )
    child_env = build_exec_env(
        env,
        codex_home=codex_home,
        db_path=workspace.db_path,
        project_id=plan.project_id,
        hook_debug_path=hook_debug_path,
        auth_mode=auth_mode,
    )

    stdout = ""
    stderr = ""
    exit_code: Optional[int] = None
    timed_out = False
    elapsed: Optional[int] = None
    launch_error: Optional[str] = None
    files_changed: List[str] = []
    measured = False
    after_hash: Optional[str] = None

    if not restore_ok:
        launch_error = restore.get("detail") or "snapshot restore was not verified"
    else:
        try:
            result = runner(command, child_env, str(workspace.root), config.timeout_s)
        except Exception as exc:
            launch_error = f"{type(exc).__name__}: {exc}"
            result = None
        if result is not None:
            stdout = result.stdout
            stderr = _redact(result.stderr, child_env)
            exit_code = result.returncode
            timed_out = result.timed_out
            elapsed = result.elapsed_ms
            if result.timed_out:
                launch_error = f"codex exec exceeded {config.timeout_s}s"
        after = capture_repository_snapshot(str(workspace.root))
        after_hash = after.get("tree_hash")
        files_changed = diff_snapshot_paths(before, after)
        measured = True

    rollout_text, _rollout_paths = _read_rollout(codex_home)
    hook_text = ""
    if hook_debug_path.is_file():
        hook_text = hook_debug_path.read_text(encoding="utf-8")
    last_message = None
    if last_message_path.is_file():
        last_message = last_message_path.read_text(encoding="utf-8")

    stdout_path = session_dir / "exec.jsonl"
    stdout_path.write_text(stdout, encoding="utf-8")
    rollout_copy = session_dir / "rollout.jsonl"
    if rollout_text:
        rollout_copy.write_text(rollout_text, encoding="utf-8")
    hook_copy = session_dir / "hook.jsonl"
    if hook_text:
        hook_copy.write_text(hook_text, encoding="utf-8")

    finished = _now()
    capture = CodexSessionCapture(
        session_id=plan.session_id,
        condition=plan.condition,
        task_id=plan.task_id,
        rep=plan.rep,
        seed=plan.seed,
        execution_order=plan.execution_order,
        snapshot_hash=workspace.snapshot_hash,
        prompt=plan.prompt,
        model_requested=config.model,
        agent_version=probe.version,
        agent_version_source=probe.version_source,
        agent_version_warning=probe.warning,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        timed_out=timed_out,
        elapsed_ms=elapsed,
        hook_debug=hook_text,
        rollout_text=rollout_text,
        raw_telemetry_paths={
            "exec_jsonl": str(stdout_path),
            "rollout_jsonl": str(rollout_copy) if rollout_text else None,
            "hook_debug": str(hook_copy) if hook_text else None,
            "last_message": str(last_message_path) if last_message is not None else None,
            "codex_home": str(home.path),
        },
        last_message=last_message,
        command=command,
        hook_command=home.hook_command,
        integration_path=home.integration_path,
        snapshot_hash_before=str(before_hash) if before_hash else None,
        snapshot_hash_after=str(after_hash) if after_hash else None,
        files_changed_paths=files_changed,
        files_changed_measured=measured,
        restore_verified=restore_ok,
        restore_detail=None if restore_ok else launch_error,
        launch_error=launch_error,
        started_at=started,
        finished_at=finished,
        fresh_codex_home=fresh,
    )
    return session_from_capture(capture, task)


def _persist_raw_telemetry(
    sessions: Sequence[Layer4SessionResult],
    results_dir: Path,
    stamp: Optional[str],
) -> tuple[str, str]:
    """
    Copy per-session JSONL out of the temp Codex home into flat result files.

    Flat files sit next to the report and match the results/.gitignore rule,
    which ignores names in that directory but not files nested in a subdirectory.
    """
    results_dir.mkdir(parents=True, exist_ok=True)
    allocated = allocate_result_paths(results_dir, stamp)
    stem = allocated["json"].stem
    for session in sessions:
        paths = session.raw_telemetry_paths
        moved: Dict[str, Optional[str]] = {}
        for key, suffix in (
            ("exec_jsonl", "exec.jsonl"),
            ("rollout_jsonl", "rollout.jsonl"),
            ("hook_debug", "hook.jsonl"),
            ("last_message", "last-message.txt"),
        ):
            source = paths.get(key)
            if not source or not Path(source).is_file():
                moved[key] = None
                continue
            dest = results_dir / f"{stem}-{session.session_id}.{suffix}"
            if dest.exists():
                raise PreflightError(f"Refusing to overwrite raw telemetry {dest}")
            shutil.copyfile(source, dest)
            moved[key] = str(dest)
        moved["codex_home"] = None
        session.raw_telemetry_paths = moved
    return str(results_dir), str(allocated["stamp"])


def _summarize(sessions: Sequence[Layer4SessionResult]) -> Dict[str, Any]:
    outcomes: Dict[str, int] = {}
    for session in sessions:
        outcomes[session.outcome] = outcomes.get(session.outcome, 0) + 1
    return {
        "executed_session_count": len(sessions),
        "outcomes": outcomes,
        "valid_sessions": sum(1 for session in sessions if session.valid),
        "primary_metric_complete": sum(
            1 for session in sessions if session.primary_metric_status == "complete"
        ),
        "primary_metric_partial": sum(
            1 for session in sessions if session.primary_metric_status == "partial"
        ),
        "primary_metric_missing": sum(
            1 for session in sessions if session.primary_metric_status == "missing"
        ),
    }


def _markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Layer 4 instrumentation run",
        "",
        report["claim_policy"],
        "",
        f"- Mode: `{report['mode']}`",
        f"- Preset: `{report['preset']}`",
        f"- Agent: `{report.get('agent')}` {report.get('agent_version') or 'version unavailable'}",
        f"- Model requested: `{report.get('model_requested') or 'unpinned'}`",
        f"- Auth: `{report.get('auth_mode')}`",
        f"- Seed: `{report.get('seed')}`",
        f"- Snapshot: `{report.get('snapshot_hash')}`",
        f"- Sessions recorded: {report.get('recorded_session_count')}",
        f"- Sessions dropped: {report.get('dropped_session_count')}",
        "",
        "| Order | Session | Task | Condition | Rep | Outcome | Valid | Primary | Input | Cached | Output |",
        "|------:|---------|------|-----------|----:|---------|-------|---------|------:|-------:|-------:|",
    ]
    for session in report.get("sessions") or []:
        def _cell(name: str) -> str:
            figure = session.get(name) or {}
            if figure.get("kind") == "unavailable":
                return "unavailable"
            return f"{figure.get('value')} ({figure.get('kind')})"

        lines.append(
            "| {order} | `{sid}` | `{task}` | {cond} | {rep} | {outcome} | {valid} | {primary} | {inp} | {cached} | {out} |".format(
                order=session.get("execution_order"),
                sid=session.get("session_id"),
                task=session.get("task_id"),
                cond=session.get("condition"),
                rep=session.get("rep"),
                outcome=session.get("outcome"),
                valid=session.get("valid"),
                primary=session.get("primary_metric_status"),
                inp=_cell("agent_input_tokens"),
                cached=_cell("agent_cached_input_tokens"),
                out=_cell("agent_output_tokens"),
            )
        )
    lines.extend([
        "",
        "OverHaust context tokens, when present, are estimated hook counts and",
        "are not subtracted from the agent columns above.",
        "",
        "Codex CLI 0.146.0 does not emit a structured files-inspected count or",
        "a pure retrieval-latency field. Those metrics stay `unavailable`.",
        "",
    ])
    return "\n".join(lines)


def write_layer4_report(
    report: Dict[str, Any],
    results_dir: Path,
    *,
    stamp: Optional[str] = None,
) -> Dict[str, str]:
    paths = allocate_result_paths(results_dir, stamp)
    json_path = paths["json"]
    md_path = paths["md"]
    payload = json.dumps(report, indent=2) + "\n"
    tmp_json = json_path.with_suffix(json_path.suffix + ".tmp")
    tmp_md = md_path.with_suffix(md_path.suffix + ".tmp")
    tmp_json.write_text(payload, encoding="utf-8")
    tmp_md.write_text(_markdown(report), encoding="utf-8")
    os.replace(tmp_json, json_path)
    os.replace(tmp_md, md_path)
    return {"json": str(json_path), "md": str(md_path)}


def run_pilot(config: Optional[RunConfig] = None) -> Dict[str, Any]:
    """Execute the 8-session pilot, or write its plan when `dry_run` is set."""
    config = config or RunConfig()
    tasks = load_pilot_tasks()
    plans = plan_matrix(tasks, seed=config.seed)
    by_id = {task.task_id: task for task in tasks}
    env = dict(config.env if config.env is not None else os.environ)
    repo_root = config.repo_root or Path(__file__).resolve().parents[2]
    results_dir = config.results_dir or default_results_dir()
    auth_mode = detect_auth_mode(env)
    binary = config.codex_bin or shutil.which("codex") or ""

    if not config.dry_run:
        if not binary:
            raise PreflightError(
                "codex is not on PATH. Install Codex CLI "
                f"{config.probe.version if config.probe and config.probe.version else '0.146.0'} "
                "or pass --codex-bin. The pilot does not start without it."
            )
        if auth_mode == "missing":
            raise PreflightError(
                "Codex auth is missing. Set OPENAI_API_KEY or CODEX_API_KEY, "
                "or run `codex login` so ~/.codex/auth.json exists. "
                "The pilot does not start unauthenticated sessions."
            )

    builder = config.workspace_builder or (
        lambda task_list: build_fixture_workspace(task_list)
    )
    workspace = builder(tasks)
    try:
        probe = config.probe
        if probe is None and not config.dry_run:
            probe = probe_codex(binary)
        if probe is None:
            probe = CodexProbe(
                agent="codex",
                version=None,
                version_source="unavailable",
                binary=binary or None,
                warning="dry run did not probe the Codex binary",
            )

        sessions: List[Layer4SessionResult] = []
        raw_note = None
        used_stamp = config.stamp
        if not config.dry_run:
            runner = config.command_runner or default_command_runner
            run_dir = Path(tempfile.mkdtemp(prefix="layer4-codex-"))
            try:
                for plan in plans:
                    try:
                        sessions.append(
                            _execute_session(
                                plan,
                                by_id[plan.task_id],
                                workspace,
                                config,
                                probe=probe,
                                binary=binary,
                                auth_mode=auth_mode,
                                env=env,
                                repo_root=repo_root,
                                run_dir=run_dir,
                                runner=runner,
                            )
                        )
                    except Exception as exc:
                        sessions.append(
                            _error_result(
                                plan,
                                snapshot_hash=workspace.snapshot_hash,
                                probe=probe,
                                message=f"{type(exc).__name__}: {exc}",
                                started_at=_now(),
                                finished_at=_now(),
                            )
                        )
                raw_note, used_stamp = _persist_raw_telemetry(
                    sessions, results_dir, config.stamp
                )
            finally:
                shutil.rmtree(run_dir, ignore_errors=True)

        summary = _summarize(sessions)
        report: Dict[str, Any] = {
            "schema_version": RUN_SCHEMA_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "benchmark_version": BENCHMARK_VERSION,
            "layer": 4,
            "preset": PILOT_NAME,
            "mode": "dry_run" if config.dry_run else "pilot",
            "instrumentation_only": True,
            "claim_policy": CLAIM_POLICY,
            "generated_at": _now(),
            "seed": config.seed,
            "agent": "codex",
            "agent_version": probe.version,
            "agent_version_source": probe.version_source,
            "agent_version_warning": probe.warning,
            "model_requested": config.model,
            "model_pinned": bool(config.model),
            "auth_mode": auth_mode if not config.dry_run else detect_auth_mode(env),
            "permissions": dict(CODEX_EXEC_PERMISSIONS),
            "snapshot_hash": workspace.snapshot_hash,
            "repo_size": workspace.repo_size,
            "project_id": workspace.project_id,
            "repository": str(workspace.root),
            "task_ids": [task.task_id for task in tasks],
            "reps": 2,
            "conditions": ["baseline", "overhaust"],
            "planned_session_count": len(plans),
            "recorded_session_count": len(sessions),
            "dropped_session_count": len(plans) - len(sessions) if not config.dry_run else 0,
            "summary": summary,
            "plans": [plan.to_dict() for plan in plans],
            "sessions": [session.to_dict() for session in sessions],
            "raw_dir": raw_note,
            "token_accounting_note": (
                "Agent input, cached input, and output are copied from Codex "
                "when Codex reports them. Missing fields stay null with kind "
                "unavailable. Estimated OverHaust context tokens are a separate "
                "field and are never subtracted."
            ),
        }
        if config.dry_run:
            report["dry_run_note"] = (
                "No Codex process was started. This file is the session plan, "
                "not measurements."
            )
        paths = write_layer4_report(report, results_dir, stamp=used_stamp)
        report["_output_paths"] = paths
        return report
    finally:
        workspace.close()
