"""
Plan and execute the Layer 4 Cursor matrix.

Pilot is all 5 Layer 3 tasks × baseline/overhaust × 1 rep (10 sessions).
Full is the same tasks × 2 reps (20 sessions). Order is the shared
pair-counterbalanced plan. Codex presets are unchanged.

Results are `benchmarks/results/layer4-cursor-<UTC stamp>.json` and `.md`.
Existing files are never overwritten. Failed and incorrect sessions stay in
the file.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from benchmarks import BENCHMARK_VERSION
from benchmarks.layer4 import SCHEMA_VERSION
from benchmarks.layer4.cursor_adapter import (
    CursorProbe,
    CursorSessionCapture,
    error_session,
    prompt_sha256,
    session_from_capture,
)
from benchmarks.layer4.cursor_condition import (
    CURSOR_DEFAULT_MODEL,
    CURSOR_PERMISSIONS,
    ISOLATION_HOME,
    ISOLATION_MCP,
    ISOLATIONS,
    MCP_COMMANDS_NOTE,
    PROMPT_CACHE_POLICY,
    CursorStateGuard,
    WorkspaceMcpDisable,
    build_cursor_command,
    build_cursor_env,
    cursor_hook_command,
    prepare_session_workspace,
    redact_cursor,
    telemetry_catalog_lines,
    verify_hook_layout,
    write_prompt_file,
)
from benchmarks.layer4.cursor_parse import (
    CURSOR_TOKEN_ACCOUNTING,
    TELEMETRY_CATALOG,
    parse_stream_json,
)
from benchmarks.layer4.cursor_store import inspect_session_store
from benchmarks.layer4.matrix import (
    FULL_NAME,
    PILOT_NAME,
    PILOT_SEED,
    SessionPlan,
    load_full_tasks,
    normalize_conditions,
    plan_matrix,
)
from benchmarks.layer4.runner import (
    EXECUTION_ORDER_POLICY,
    Layer4Workspace,
    PreflightError,
    ProcessResult,
    _exact_values,
    _fmt_number,
    _mean,
    _now,
    _order_entry,
    _stamp,
    agent_behavior,
    build_fixture_workspace,
    cache_analysis,
    default_results_dir,
    diff_snapshot_paths,
)
from benchmarks.layer4.schema import Layer4SessionResult
from benchmarks.repro import capture_repository_snapshot
from benchmarks.schemas import BenchmarkTask


CURSOR_PROTOCOL_VERSION = "layer4-cursor-protocol-v1"
CURSOR_RUN_SCHEMA_VERSION = "layer4-cursor-run-v1"
CURSOR_PILOT_REPS = 1
CURSOR_FULL_REPS = 2

CURSOR_CLAIM_POLICY = (
    "Layer 4 instrumentation record. Session totals are whatever the Cursor "
    "agent reported. OverHaust context tokens are separate and were not "
    "subtracted. This file is not a product token-reduction result. "
    "Cursor token figures are not comparable to Codex token figures."
)

CURSOR_CACHE_NOTE = (
    "Cursor result.usage.cacheReadTokens is a separate bucket. It is not "
    "included in inputTokens and is not subtracted from inputTokens. Means "
    "use valid sessions whose figure is exact, including failed and incorrect "
    "sessions. Invalid sessions stay in the dataset and are excluded from "
    "means. A missing figure is unavailable and is not treated as zero. "
    "cached_input_rate is sum(cacheReadTokens)/sum(inputTokens) over valid "
    "sessions where both are exact. That rate is a ratio of two separate "
    "buckets, not a share of input. mean total uses a provider-reported total "
    "only; Cursor does not report one, so that mean stays unavailable and is "
    "not replaced with the derived component sum. Estimated OverHaust context "
    "tokens are not included. Do not compare these figures to Codex."
)

MEANS_POLICY = (
    "Primary means include every valid session, including failed outcomes and "
    "incorrect answers. Invalid sessions (isolation, hook, or MCP-catalog "
    "failures) stay in the dataset and are excluded from means. Unavailable "
    "figures are left out of a mean and are not stored as zero."
)

PROMPT_FILE_POLICY = (
    "sessionStart stdin has no user prompt, and Cursor's session_id does not "
    "exist until the hook runs. The harness writes a mode-0600 JSON file per "
    "session containing the harness session id, the workspace root, and the "
    "task prompt. The child environment receives OVERHAUST_CURSOR_PROMPT_FILE "
    "and OVERHAUST_CURSOR_SESSION_ID, not the prompt text. The hook reads the "
    "file only when both the harness session id and the workspace root match. "
    "Baseline does not get the file or the hook."
)


@dataclass
class CursorRunConfig:
    model: Optional[str] = None
    seed: int = PILOT_SEED
    timeout_s: int = 600
    results_dir: Optional[Path] = None
    dry_run: bool = False
    cursor_bin: Optional[str] = None
    isolation: str = ISOLATION_HOME
    repo_root: Optional[Path] = None
    env: Optional[Dict[str, str]] = None
    command_runner: Optional[Callable[..., ProcessResult]] = None
    workspace_builder: Optional[Callable[..., Layer4Workspace]] = None
    probe: Optional[CursorProbe] = None
    python: Optional[str] = None
    stamp: Optional[str] = None
    preset: str = PILOT_NAME
    conditions: Optional[Sequence[str]] = None
    state_home: Optional[Path] = None


def cursor_reps(preset: str) -> int:
    if preset == PILOT_NAME:
        return CURSOR_PILOT_REPS
    if preset == FULL_NAME:
        return CURSOR_FULL_REPS
    raise ValueError(f"unknown preset: {preset}")


def default_cursor_command_runner(
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
            cwd=cwd or None,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
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


def allocate_cursor_result_paths(results_dir: Path, stamp: Optional[str] = None) -> Dict[str, Path]:
    results_dir.mkdir(parents=True, exist_ok=True)
    base = stamp or _stamp()
    n = 0
    while True:
        suffix = "" if n == 0 else f"-{n}"
        name = f"layer4-cursor-{base}{suffix}"
        json_path = results_dir / f"{name}.json"
        md_path = results_dir / f"{name}.md"
        if not json_path.exists() and not md_path.exists():
            return {"json": json_path, "md": md_path, "stamp": base + suffix}
        n += 1
        if n > 1000:
            raise PreflightError(f"Could not allocate a free result name under {results_dir}")


def overhaust_commit(repo_root: Path) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (out or "").strip()
    return text or None


def _run_mode(config: CursorRunConfig) -> str:
    if config.dry_run:
        return "dry_run"
    if config.preset == FULL_NAME:
        return "full"
    return "pilot"


_ISOLATION_NOT_CHECKED = {
    "checked": False,
    "usable": None,
    "detail": "not checked; preflight probes only the isolation selected by --isolation",
}


def _preflight_cwd(cwd: Path, state_home: Path) -> None:
    """Every preflight process cwd is a throwaway directory."""
    resolved = cwd.resolve()
    forbidden = {state_home.resolve(), Path.home().resolve()}
    if resolved in forbidden:
        raise PreflightError(
            "Refusing to run cursor-agent preflight with cwd set to the user "
            "home or the Cursor state home."
        )


def run_cursor_preflight(
    *,
    binary: str,
    env: Dict[str, str],
    isolation: str,
    model: str,
    state_home: Path,
    runner: Callable[..., ProcessResult],
) -> Dict[str, Any]:
    """
    Check the CLI, auth, model list, and only the selected isolation strategy.

    Does not pass `-p` and does not start a model session. No step uses the
    user home or a project directory as cwd. `isolated-home` does not call
    `mcp disable`. `mcp-toggle` disables OverHaust in a throwaway directory
    and deletes only the project slug that command created.
    """
    if isolation not in ISOLATIONS:
        raise PreflightError(
            f"Unknown isolation {isolation!r}. Use {ISOLATION_HOME!r} or {ISOLATION_MCP!r}."
        )
    scratch = Path(tempfile.mkdtemp(prefix="layer4-cursor-preflight-"))
    try:
        _preflight_cwd(scratch, state_home)
        return _preflight_report(
            binary=binary,
            env=env,
            isolation=isolation,
            model=model,
            state_home=state_home,
            runner=runner,
            scratch=scratch,
        )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _preflight_report(
    *,
    binary: str,
    env: Dict[str, str],
    isolation: str,
    model: str,
    state_home: Path,
    runner: Callable[..., ProcessResult],
    scratch: Path,
) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "cli_present": False,
        "version": None,
        "version_source": "unavailable",
        "auth": "api_key" if (env.get("CURSOR_API_KEY") or "").strip() else "missing",
        "model": model,
        "model_listed": None,
        "model_listed_kind": "unavailable",
        "isolation_requested": isolation,
        "isolated_home": dict(_ISOLATION_NOT_CHECKED),
        "mcp_toggle": dict(_ISOLATION_NOT_CHECKED),
        "model_session_launched": False,
        "preflight_cwd": "throwaway",
    }
    if not binary:
        report["detail"] = "cursor-agent is not on PATH"
        report["selected_usable"] = False
        return report

    version = runner([binary, "--version"], dict(env), str(scratch), 15)
    version_text = (version.stdout or "").strip()
    report["cli_present"] = version.returncode == 0 and bool(version_text)
    if not report["cli_present"]:
        report["detail"] = "cursor-agent --version failed"
        report["selected_usable"] = False
        return report
    report["version"] = version_text.split()[-1]
    report["version_source"] = "cursor_agent_cli_version"

    if report["auth"] != "api_key":
        status = runner([binary, "status"], dict(env), str(scratch), 15)
        blob = ((status.stdout or "") + (status.stderr or "")).lower()
        if status.returncode == 0 and ("logged in" in blob or "logged-in" in blob):
            report["auth"] = "login"

    listed, listed_kind, listed_detail = _probe_model(runner, binary, env, scratch, model)
    report["model_listed"] = listed
    report["model_listed_kind"] = listed_kind
    report["model_detail"] = listed_detail
    if isolation == ISOLATION_HOME:
        report["isolated_home"] = _probe_isolated_home(runner, binary, env, state_home)
    else:
        report["mcp_toggle"] = _probe_mcp_toggle(runner, binary, env, state_home)

    if isolation == ISOLATION_HOME and report["auth"] != "api_key":
        home_probe = dict(report["isolated_home"])
        home_probe["usable"] = False
        home_probe["detail"] = (
            "isolated-home does not copy Cursor credentials. CURSOR_API_KEY is required. "
            + str(home_probe.get("detail") or "")
        )
        report["isolated_home"] = home_probe

    selected = report["isolated_home"] if isolation == ISOLATION_HOME else report["mcp_toggle"]
    auth_ok = report["auth"] == "api_key" or (
        isolation == ISOLATION_MCP and report["auth"] == "login"
    )
    report["selected_usable"] = bool(
        selected.get("usable") and listed is True and auth_ok and report["cli_present"]
    )
    return report


def _probe_model(runner, binary, env, cwd: Path, model) -> Tuple[Optional[bool], str, str]:
    attempts = (
        [binary, "models"],
        [binary, "models", "list"],
        [binary, "--list-models"],
    )
    errors: List[str] = []
    for command in attempts:
        result = runner(command, dict(env), str(cwd), 20)
        text = (result.stdout or "") + "\n" + (result.stderr or "")
        if result.returncode == 0 and (result.stdout or "").strip():
            return (model in text), "exact", " ".join(command[1:])
        errors.append(" ".join(command[1:]) + f" exit={result.returncode}")
    return None, "unavailable", "no models command succeeded: " + "; ".join(errors)


def _probe_isolated_home(runner, binary, env, state_home: Path) -> Dict[str, Any]:
    probe_home = Path(tempfile.mkdtemp(prefix="layer4-cursor-home-"))
    sentinel = "layer4-home-sentinel"
    try:
        _preflight_cwd(probe_home, state_home)
        cursor_dir = probe_home / ".cursor"
        cursor_dir.mkdir(parents=True)
        (cursor_dir / "mcp.json").write_text(
            json.dumps({"mcpServers": {sentinel: {"command": "true"}}}),
            encoding="utf-8",
        )
        child = dict(env)
        child["HOME"] = str(probe_home)
        listed = runner([binary, "mcp", "list"], child, str(probe_home), 20)
        text = (listed.stdout or "") + (listed.stderr or "")
        honors = sentinel in text and "overhaust" not in text.lower()
        if honors:
            detail = (
                "cursor-agent mcp list under a temp HOME showed the sentinel "
                "server and did not show overhaust. "
                + MCP_COMMANDS_NOTE
                + " This probe called mcp list once and did not call mcp disable."
            )
        else:
            detail = (
                "cursor-agent did not show that it honors HOME. Global MCP "
                f"servers would still load. exit={listed.returncode}."
            )
        return {
            "checked": True,
            "usable": honors,
            "detail": detail,
            "exit_code": listed.returncode,
        }
    finally:
        shutil.rmtree(probe_home, ignore_errors=True)


def _probe_mcp_toggle(runner, binary, env, state_home: Path) -> Dict[str, Any]:
    """Disable in a throwaway cwd and delete only the slug that command created."""
    workspace = Path(tempfile.mkdtemp(prefix="layer4-cursor-mcp-probe-"))
    toggle = WorkspaceMcpDisable(state_home, workspace, binary, runner, env)
    usable = False
    detail = "mcp-toggle probe did not finish"
    evidence: Dict[str, Any] = {}
    cleanup: Dict[str, Any] = {"cleanup_verified": False}
    try:
        _preflight_cwd(workspace, state_home)
        toggle.snapshot()
        evidence = toggle.disable_and_verify()
        if evidence.get("disable_timed_out") or evidence.get("disable_exit_code") not in (0,):
            detail = "cursor-agent mcp disable overhaust failed in the throwaway workspace."
        elif evidence.get("overhaust_listed"):
            detail = (
                "cursor-agent mcp list from the throwaway workspace still shows "
                "overhaust. mcp-toggle cannot hide the OverHaust MCP tools there."
            )
        elif evidence.get("refused_preexisting_slugs"):
            detail = (
                "mcp disable wrote into a pre-existing ~/.cursor/projects slug. "
                "The harness did not modify that directory. "
                + ", ".join(evidence.get("refused_preexisting_slugs") or [])
            )
        else:
            usable = True
            detail = (
                "Disabled overhaust with cwd set to a throwaway workspace. "
                "mcp list from that cwd did not show overhaust. "
                "Other global MCP servers stay loaded. "
                + MCP_COMMANDS_NOTE
            )
    except Exception as exc:
        usable = False
        detail = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            cleanup = toggle.cleanup()
        except Exception as exc:
            cleanup = {"cleanup_verified": False, "detail": str(exc)}
        shutil.rmtree(workspace, ignore_errors=True)
    if not cleanup.get("cleanup_verified"):
        usable = False
        detail += " Cleanup of the project slug did not verify: " + json.dumps(cleanup)
    return {
        "checked": True,
        "usable": usable,
        "detail": detail,
        "cleanup": cleanup,
        "created_slugs": evidence.get("created_slugs"),
        "refused_preexisting_slugs": evidence.get("refused_preexisting_slugs"),
        "note": MCP_COMMANDS_NOTE,
    }


def _execute_session(
    plan: SessionPlan,
    task: BenchmarkTask,
    workspace: Layer4Workspace,
    config: CursorRunConfig,
    *,
    probe: CursorProbe,
    binary: str,
    env: Dict[str, str],
    run_dir: Path,
    runner: Callable[..., ProcessResult],
    hook_command: str,
    state_home: Path,
    commit: Optional[str],
) -> Layer4SessionResult:
    started = _now()
    session_dir = run_dir / plan.session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    dest = session_dir / "workspace"
    hook_debug_path = session_dir / "hook-debug.jsonl"
    prompt_path = session_dir / "task-prompt.json"
    session_home = session_dir / "home"
    session_home.mkdir(parents=True, exist_ok=True)

    prepared = prepare_session_workspace(
        workspace.root,
        workspace.snapshot,
        dest,
        condition=plan.condition,
        hook_command=hook_command,
    )
    prompt_written = False
    if plan.condition == "overhaust" and prepared.restore_verified and prepared.layout.ok:
        try:
            write_prompt_file(
                prompt_path,
                harness_session_id=plan.session_id,
                workspace_root=dest,
                prompt=plan.prompt,
            )
            prompt_written = True
        except OSError as exc:
            prepared.detail = f"prompt file was not written: {exc}"
            prepared.layout.ok = False
            prepared.layout.problems.append("prompt file was not written")

    model = config.model or CURSOR_DEFAULT_MODEL
    command = build_cursor_command(binary=binary, prompt=plan.prompt, model=model)
    child_home = session_home if config.isolation == ISOLATION_HOME else None
    child_env = build_cursor_env(
        env,
        db_path=workspace.db_path,
        project_id=plan.project_id,
        hook_debug_path=hook_debug_path,
        prompt_file=prompt_path if prompt_written else None,
        harness_session_id=plan.session_id,
        home=child_home,
    )

    stdout = ""
    stderr = ""
    exit_code: Optional[int] = None
    timed_out = False
    elapsed: Optional[int] = None
    launch_error: Optional[str] = prepared.detail
    files_changed: List[str] = []
    measured = False
    after_hash: Optional[str] = None
    before_agent = None
    toggle: Optional[WorkspaceMcpDisable] = None
    isolation_evidence: Dict[str, Any] = {
        "strategy": config.isolation,
        "applied": config.isolation != ISOLATION_MCP,
        "mcp_disable_called": False,
        "note": (
            MCP_COMMANDS_NOTE
            if config.isolation == ISOLATION_MCP
            else "isolated-home uses a temp HOME. This session does not call mcp disable or mcp list."
        ),
    }

    try:
        if config.isolation == ISOLATION_MCP and dest.is_dir():
            toggle = WorkspaceMcpDisable(state_home, dest, binary, runner, child_env)
            try:
                toggle.snapshot()
                isolation_evidence = toggle.disable_and_verify()
            except Exception as exc:
                isolation_evidence = {
                    "strategy": ISOLATION_MCP,
                    "applied": False,
                    "mcp_disable_called": True,
                    "overhaust_listed": True,
                    "disable_exit_code": None,
                    "error": f"{type(exc).__name__}: {exc}",
                    "note": MCP_COMMANDS_NOTE,
                }
                launch_error = isolation_evidence["error"]

        if prepared.restore_verified and prepared.layout.ok and dest.is_dir() and launch_error is None:
            before_agent = capture_repository_snapshot(str(dest))
            launch_error = None
            try:
                result = runner(command, child_env, str(dest), config.timeout_s)
            except Exception as exc:
                launch_error = f"{type(exc).__name__}: {exc}"
                result = None
            if result is not None:
                stdout = result.stdout
                stderr = redact_cursor(result.stderr, child_env)
                exit_code = result.returncode
                timed_out = result.timed_out
                elapsed = result.elapsed_ms
                if result.timed_out:
                    launch_error = f"cursor-agent exceeded {config.timeout_s}s"
            if before_agent is not None and dest.is_dir():
                after = capture_repository_snapshot(str(dest))
                after_hash = after.get("tree_hash")
                files_changed = diff_snapshot_paths(before_agent, after)
                measured = True
    finally:
        if toggle is not None:
            try:
                isolation_evidence.update(toggle.cleanup())
            except Exception as exc:
                isolation_evidence["cleanup_verified"] = False
                isolation_evidence["cleanup_error"] = f"{type(exc).__name__}: {exc}"

    post_layout = prepared.layout
    if dest.is_dir():
        post_layout = verify_hook_layout(dest, condition=plan.condition, hook_command=hook_command)
        if prepared.layout.ok and not post_layout.ok:
            post_layout.problems = list(prepared.layout.problems) + [
                "hook layout changed during the session: " + "; ".join(post_layout.problems)
            ]
            post_layout.ok = False

    stream_path = session_dir / "stream.jsonl"
    stream_path.write_text(stdout, encoding="utf-8")
    hook_text = ""
    if hook_debug_path.is_file():
        hook_text = hook_debug_path.read_text(encoding="utf-8")
    if hook_text:
        (session_dir / "hook.jsonl").write_text(hook_text, encoding="utf-8")
    if prompt_path.exists():
        prompt_path.unlink()

    observed = parse_stream_json(stdout)
    homes: List[Path] = [session_home, state_home]
    store = inspect_session_store(homes, observed.session_id)
    finished = _now()
    capture = CursorSessionCapture(
        session_id=plan.session_id,
        condition=plan.condition,
        task_id=plan.task_id,
        rep=plan.rep,
        seed=plan.seed,
        execution_order=plan.execution_order,
        pair_id=plan.pair_id,
        order_in_pair=plan.order_in_pair,
        condition_order=plan.condition_order,
        original_pair_id=plan.original_pair_id,
        original_planned_position=plan.original_planned_position,
        snapshot_hash=workspace.snapshot_hash,
        prompt=plan.prompt,
        model_requested=model,
        agent_version=probe.version,
        agent_version_source=probe.version_source,
        agent_version_warning=probe.warning,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        timed_out=timed_out,
        elapsed_ms=elapsed,
        hook_debug=hook_text,
        command=command,
        hook_command=prepared.hook_command,
        integration_path=prepared.integration_path,
        isolation=config.isolation,
        hook_layout=post_layout.to_dict(),
        store=store,
        raw_telemetry_paths={
            "stream_jsonl": str(stream_path),
            "hook_debug": str(session_dir / "hook.jsonl") if hook_text else None,
            "workspace": str(dest),
        },
        snapshot_hash_before=prepared.pre_agent_hash,
        snapshot_hash_after=str(after_hash) if after_hash else None,
        files_changed_paths=files_changed,
        files_changed_measured=measured,
        restore_verified=prepared.restore_verified,
        launch_error=launch_error,
        started_at=started,
        finished_at=finished,
        overhaust_commit=commit,
        prompt_file_written=prompt_written,
        isolation_evidence=isolation_evidence,
    )
    return session_from_capture(capture, task)


def _persist_raw(sessions: Sequence[Layer4SessionResult], results_dir: Path, stamp: str) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    stem = f"layer4-cursor-{stamp}"
    for session in sessions:
        paths = dict(session.raw_telemetry_paths)
        moved: Dict[str, Optional[str]] = {}
        for key, suffix in (("stream_jsonl", "stream.jsonl"), ("hook_debug", "hook.jsonl")):
            source = paths.get(key)
            if not source or not Path(source).is_file():
                moved[key] = None
                continue
            dest = results_dir / f"{stem}-{session.session_id}.{suffix}"
            if dest.exists():
                raise PreflightError(f"Refusing to overwrite raw telemetry {dest}")
            shutil.copyfile(source, dest)
            moved[key] = str(dest)
        moved["workspace"] = None
        session.raw_telemetry_paths = moved


def _files_inspected_analysis(sessions: Sequence[Layer4SessionResult]) -> Dict[str, Any]:
    grouped: Dict[Tuple[str, str], List[Layer4SessionResult]] = {}
    for session in sessions:
        grouped.setdefault((session.task_id, session.condition), []).append(session)
    rows = []
    for (task_id, condition), group in sorted(grouped.items()):
        valid = [session for session in group if session.valid]
        values, unavailable = _exact_values(valid, "files_inspected")
        rows.append({
            "task_id": task_id,
            "condition": condition,
            "n_sessions": len(valid),
            "n_invalid_excluded": len(group) - len(valid),
            "mean_files_inspected": _mean(values),
            "n_files_inspected": len(values),
            "files_inspected_unavailable": unavailable,
        })
    return {
        "note": (
            "Files inspected are unique readToolCall paths. The count is exact "
            "only when tool events were parsed. It is never inferred from the "
            "prompt. Means use valid sessions, including failed and incorrect ones."
        ),
        "by_task_condition": rows,
    }


def _correctness_summary(sessions: Sequence[Layer4SessionResult]) -> Dict[str, Any]:
    grouped: Dict[Tuple[str, str], List[Layer4SessionResult]] = {}
    for session in sessions:
        grouped.setdefault((session.task_id, session.condition), []).append(session)
    rows = []
    for (task_id, condition), group in sorted(grouped.items()):
        valid = [session for session in group if session.valid]
        rows.append({
            "task_id": task_id,
            "condition": condition,
            "n_in_dataset": len(group),
            "n_valid": len(valid),
            "n_invalid_excluded_from_means": len(group) - len(valid),
            "n_correct": sum(1 for session in valid if session.correctness is True),
            "n_incorrect": sum(1 for session in valid if session.correctness is False),
            "n_unscored": sum(1 for session in valid if session.correctness is None),
            "n_failed_outcome": sum(1 for session in valid if session.outcome == "failed"),
            "n_error_outcome": sum(1 for session in valid if session.outcome == "error"),
        })
    return {
        "note": MEANS_POLICY,
        "by_task_condition": rows,
    }


def _context_metrics(sessions: Sequence[Layer4SessionResult]) -> Dict[str, Any]:
    rows = []
    verification_counts: Dict[str, int] = {}
    for session in sessions:
        supplemental = session.supplemental_telemetry or {}
        verification = str(supplemental.get("injection_verification") or "unavailable")
        verification_counts[verification] = verification_counts.get(verification, 0) + 1
        if session.condition != "overhaust":
            continue
        rows.append({
            "session_id": session.session_id,
            "task_id": session.task_id,
            "valid": session.valid,
            "context_tokens": session.overhaust_context_tokens.to_dict(),
            "context_bytes": session.overhaust_context_bytes.to_dict(),
            "hook_latency_ms": session.overhaust_hook_latency_ms.to_dict(),
            "retrieval_latency_ms": session.overhaust_retrieval_latency_ms.to_dict(),
            "hook_fired": session.hook_fired,
            "context_injected": session.context_injected,
            "injection_verification": verification,
        })
    return {
        "note": (
            "OverHaust context tokens are TokenEstimator counts (ESTIMATED). "
            "They are not subtracted from provider tokens. Retrieval latency "
            "stays UNAVAILABLE. injection_verification is store+hook when the "
            "local session store was readable, otherwise hook-log-only."
        ),
        "injection_verification_counts": verification_counts,
        "overhaust_sessions": rows,
    }


def _markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Layer 4 Cursor instrumentation run",
        "",
        report["claim_policy"],
        "",
        PROMPT_CACHE_POLICY,
        "",
        "Cursor `cacheReadTokens` is a separate bucket from `inputTokens`. "
        "Do not compare these figures to Codex.",
        "",
        "## Methodology",
        "",
        report.get("methodology") or "",
        "",
        "### Telemetry availability",
        "",
        "| Field | Label |",
        "|-------|-------|",
    ]
    for item in report.get("telemetry_catalog") or []:
        lines.append(f"| `{item['field']}` | {item['label']} |")
    lines.extend([
        "",
        f"- Mode: `{report['mode']}`",
        f"- Preset: `{report['preset']}` ({report.get('planned_session_count')} planned sessions)",
        f"- Agent: `{report.get('agent')}` {report.get('agent_version') or 'version unavailable'}",
        f"- Model requested: `{report.get('model_requested')}`",
        f"- Isolation: `{report.get('isolation')}`",
        f"- Integration: OverHaust uses `{report.get('integration_mode')}`; baseline uses `none`",
        f"- Seed: `{report.get('seed')}`",
        f"- Fixture hash: `{report.get('snapshot_hash')}`",
        f"- OverHaust commit: `{report.get('overhaust_commit') or 'unavailable'}`",
        f"- Repository: `{report.get('repository')}`",
        f"- Sessions recorded: {report.get('recorded_session_count')}",
        f"- Sessions dropped: {report.get('dropped_session_count')}",
        "",
        MEANS_POLICY,
        "",
        "## Planned execution order",
        "",
        "| Seq | Session | Task | Condition | Rep | Integration | Prompt sha256 |",
        "|----:|---------|------|-----------|----:|-------------|---------------|",
    ])
    for entry in report.get("planned_execution_order") or []:
        lines.append(
            "| {seq} | `{sid}` | `{task}` | {cond} | {rep} | `{mode}` | `{prompt}` |".format(
                seq=entry.get("sequence"),
                sid=entry.get("session_id"),
                task=entry.get("task_id"),
                cond=entry.get("condition"),
                rep=entry.get("rep"),
                mode=entry.get("integration_mode"),
                prompt=entry.get("prompt_sha256"),
            )
        )
    lines.extend(["", "## Sessions", ""])
    if not report.get("sessions"):
        lines.append("No sessions were executed.")
        lines.append("")
    else:
        lines.extend([
            "| Order | Session | Task | Condition | Rep | Outcome | Valid | Correct | Input | cacheRead | Output | Tools | Files | Context tokens |",
            "|------:|---------|------|-----------|----:|---------|-------|---------|------:|----------:|-------:|------:|------:|---------------:|",
        ])
        for session in report["sessions"]:
            lines.append(_session_row(session))
        lines.append("")
    lines.extend([
        "## Means by task and condition",
        "",
        (report.get("cache_analysis") or {}).get("note") or CURSOR_CACHE_NOTE,
        "",
        "| Task | Condition | n | Mean input | Mean cacheRead | cacheRead/input | Mean output | Mean total |",
        "|------|-----------|--:|-----------:|---------------:|----------------:|------------:|-----------:|",
    ])
    for row in (report.get("cache_analysis") or {}).get("by_task_condition") or []:
        lines.append(
            "| `{task}` | {cond} | {n} | {inp} | {cached} | {rate} | {out} | {total} |".format(
                task=row.get("task_id"),
                cond=row.get("condition"),
                n=row.get("n_sessions"),
                inp=_fmt_number(row.get("mean_input_tokens")),
                cached=_fmt_number(row.get("mean_cached_input_tokens")),
                rate=_fmt_number(row.get("cached_input_rate")),
                out=_fmt_number(row.get("mean_output_tokens")),
                total=_fmt_number(row.get("mean_total_tokens")),
            )
        )
    lines.extend([
        "",
        "### Tool calls",
        "",
        "| Task | Condition | n | Mean tool calls | Zero-tool sessions | Unavailable | Invalid excluded |",
        "|------|-----------|--:|----------------:|-------------------:|------------:|-----------------:|",
    ])
    for row in ((report.get("agent_behavior") or {}).get("by_task_condition")) or []:
        lines.append(
            "| `{task}` | {cond} | {n} | {mean} | {zero} | {unavail} | {invalid} |".format(
                task=row.get("task_id"),
                cond=row.get("condition"),
                n=row.get("n_sessions"),
                mean=_fmt_number(row.get("mean_tool_calls")),
                zero=row.get("zero_tool_call_sessions"),
                unavail=row.get("tool_calls_unavailable"),
                invalid=row.get("n_invalid_excluded"),
            )
        )
    lines.extend([
        "",
        "### Files inspected",
        "",
        ((report.get("files_inspected_analysis") or {}).get("note") or ""),
        "",
        "| Task | Condition | n | Mean files inspected | Unavailable | Invalid excluded |",
        "|------|-----------|--:|---------------------:|------------:|-----------------:|",
    ])
    for row in ((report.get("files_inspected_analysis") or {}).get("by_task_condition")) or []:
        lines.append(
            "| `{task}` | {cond} | {n} | {mean} | {unavail} | {invalid} |".format(
                task=row.get("task_id"),
                cond=row.get("condition"),
                n=row.get("n_sessions"),
                mean=_fmt_number(row.get("mean_files_inspected")),
                unavail=row.get("files_inspected_unavailable"),
                invalid=row.get("n_invalid_excluded"),
            )
        )
    lines.extend([
        "",
        "### Correctness",
        "",
        "| Task | Condition | In dataset | Valid | Correct | Incorrect | Unscored | Failed |",
        "|------|-----------|-----------:|------:|--------:|----------:|---------:|-------:|",
    ])
    for row in ((report.get("correctness") or {}).get("by_task_condition")) or []:
        lines.append(
            "| `{task}` | {cond} | {dataset} | {valid} | {ok} | {bad} | {none} | {failed} |".format(
                task=row.get("task_id"),
                cond=row.get("condition"),
                dataset=row.get("n_in_dataset"),
                valid=row.get("n_valid"),
                ok=row.get("n_correct"),
                bad=row.get("n_incorrect"),
                none=row.get("n_unscored"),
                failed=row.get("n_failed_outcome"),
            )
        )
    lines.extend([
        "",
        "### Context metrics",
        "",
        ((report.get("context_metrics") or {}).get("note") or ""),
        "",
        f"Injection verification counts: `{json.dumps((report.get('context_metrics') or {}).get('injection_verification_counts') or {})}`",
        "",
    ])
    if report.get("mode") == "dry_run":
        lines.extend(["## Dry run", "", "No cursor-agent process was started.", ""])
    lines.append(PROMPT_CACHE_POLICY)
    lines.append("")
    return "\n".join(lines)


def _cell(session: Dict[str, Any], name: str) -> str:
    figure = session.get(name) or {}
    if figure.get("kind") == "unavailable" or figure.get("value") is None:
        return "unavailable"
    return f"{figure.get('value')} ({figure.get('kind')})"


def _session_row(session: Dict[str, Any]) -> str:
    return (
        "| {order} | `{sid}` | `{task}` | {cond} | {rep} | {outcome} | {valid} | {correct} | "
        "{inp} | {cached} | {out} | {tools} | {files} | {ctx} |"
    ).format(
        order=session.get("execution_order"),
        sid=session.get("session_id"),
        task=session.get("task_id"),
        cond=session.get("condition"),
        rep=session.get("rep"),
        outcome=session.get("outcome"),
        valid=session.get("valid"),
        correct=session.get("correctness"),
        inp=_cell(session, "agent_input_tokens"),
        cached=_cell(session, "agent_cached_input_tokens"),
        out=_cell(session, "agent_output_tokens"),
        tools=_cell(session, "tool_calls"),
        files=_cell(session, "files_inspected"),
        ctx=_cell(session, "overhaust_context_tokens"),
    )


def format_cursor_dry_run(report: Dict[str, Any]) -> str:
    lines = [
        "Dry run only. Launching nothing.",
        f"preset: {report.get('preset')}",
        f"repository: {report.get('repository')}",
        f"fixture: {report.get('repo_size')}",
        f"fixture_hash: {report.get('snapshot_hash')}",
        f"commit: {report.get('overhaust_commit') or 'unavailable'}",
        f"model: {report.get('model_requested')}",
        f"isolation: {report.get('isolation')}",
        f"integration_mode: {report.get('integration_mode')}",
        f"output_dir: {report.get('output_dir')}",
        f"planned_sessions: {report.get('planned_session_count')}",
        "task_order:",
    ]
    for entry in report.get("planned_execution_order") or []:
        lines.append(
            "  {seq}. task={task} condition={cond} rep={rep} "
            "integration={mode} prompt_sha256={prompt} session={sid}".format(
                seq=entry.get("sequence"),
                task=entry.get("task_id"),
                cond=entry.get("condition"),
                rep=entry.get("rep"),
                mode=entry.get("integration_mode"),
                prompt=entry.get("prompt_sha256"),
                sid=entry.get("session_id"),
            )
        )
    lines.append("telemetry:")
    for row in telemetry_catalog_lines():
        lines.append(f"  {row}")
    lines.append(PROMPT_CACHE_POLICY)
    return "\n".join(lines)


def _methodology() -> str:
    return "\n".join([
        "The Cursor condition compares baseline headless `cursor-agent` sessions "
        "with the same argv plus one `sessionStart` hook. The hook calls "
        "`invoke_context_request` and returns `additional_context`. There is "
        "no benchmark-only retrieval path. The task prompts and the Layer 3 "
        "rubric are unchanged.",
        "",
        PROMPT_FILE_POLICY,
        "",
        "Two isolation strategies are implemented. `isolated-home` runs each "
        "session with HOME set to an empty directory and authenticates with "
        "CURSOR_API_KEY. No credential files are copied. Its preflight checks "
        "whether `cursor-agent mcp list` honors that HOME, and it does not "
        "call `mcp disable`. `mcp-toggle` runs `cursor-agent mcp disable overhaust` "
        "with cwd set to each session's fresh temp workspace (both conditions "
        "the same way), then `mcp list` from that same cwd. The CLI writes "
        "`~/.cursor/projects/<slug>/mcp-disabled.json` for that cwd. The "
        "harness finds the slug by diffing `~/.cursor/projects` and deletes "
        "only directories that appeared for that call. A slug that already "
        "existed is not modified. Preflight does the same in a throwaway "
        "directory and probes only the strategy named by `--isolation`. "
        "No preflight command uses the user home or a project directory as "
        "cwd. `mcp list` and `mcp disable` start MCP servers, so each "
        "workspace calls each of them once. Other global MCP servers stay "
        "loaded under mcp-toggle. A session where overhaust is still listed "
        "or loaded is invalid.",
        "",
        "Injection is checked from the hook debug record (fired, error, exact "
        "context bytes, ESTIMATED TokenEstimator tokens, latency). When "
        "`~/.cursor/chats/<hash>/<session>/store.db` can be scanned, the "
        "OverHaust marker must be present for OverHaust sessions and absent "
        "for baseline. If the store cannot be parsed, verification is recorded "
        "as hook-log-only.",
        "",
        "Passing `--model` rewrites `cli-config.json` model keys "
        "(`model`, `selectedModel`, `modelParameters`, `hasChangedDefaultModel`, "
        "`modelSelectionHistory`). The harness snapshots those keys, plus "
        "`agent-cli-state.json` and `statsig-cache.json`, and restores them "
        "after the run, including on failure.",
        "",
        PROMPT_CACHE_POLICY,
        "",
        CURSOR_CLAIM_POLICY,
    ])


def _mcp_cleanup_report(
    sessions: Sequence[Layer4SessionResult],
    isolation: str,
) -> Optional[Dict[str, Any]]:
    if isolation != ISOLATION_MCP:
        return None
    rows = []
    ok = True
    for session in sessions:
        evidence = (session.supplemental_telemetry or {}).get("isolation_evidence") or {}
        verified = evidence.get("cleanup_verified") is True
        ok = ok and verified
        rows.append({
            "session_id": session.session_id,
            "cleanup_verified": verified,
            "created_slugs": evidence.get("created_slugs"),
            "removed_slugs": evidence.get("removed_slugs"),
            "refused_preexisting_slugs": evidence.get("refused_preexisting_slugs"),
            "overhaust_listed": evidence.get("overhaust_listed"),
        })
    return {"cleanup_verified": ok, "restored": ok, "sessions": rows}


def _integration_mode(condition: str) -> str:
    if condition == "overhaust":
        return "cursor_session_start_hook"
    return "none"


def _planned_entry(plan: SessionPlan, index: int) -> Dict[str, Any]:
    entry = _order_entry(plan, index)
    entry["integration_mode"] = _integration_mode(plan.condition)
    entry["prompt_sha256"] = prompt_sha256(plan.prompt)
    return entry


def write_cursor_report(
    report: Dict[str, Any],
    results_dir: Path,
    *,
    stamp: Optional[str] = None,
) -> Dict[str, str]:
    paths = allocate_cursor_result_paths(results_dir, stamp)
    payload = json.dumps(report, indent=2) + "\n"
    json_path = paths["json"]
    md_path = paths["md"]
    tmp_json = json_path.with_suffix(json_path.suffix + ".tmp")
    tmp_md = md_path.with_suffix(md_path.suffix + ".tmp")
    tmp_json.write_text(payload, encoding="utf-8")
    tmp_md.write_text(_markdown(report), encoding="utf-8")
    os.replace(tmp_json, json_path)
    os.replace(tmp_md, md_path)
    return {"json": str(json_path), "md": str(md_path), "stamp": str(paths["stamp"])}


def run_cursor(config: Optional[CursorRunConfig] = None) -> Dict[str, Any]:
    """Execute a Cursor preset, or write its plan when `dry_run` is set."""
    config = config or CursorRunConfig()
    if config.preset not in {PILOT_NAME, FULL_NAME}:
        raise PreflightError(
            f"Unknown preset {config.preset!r}. Use {PILOT_NAME!r} or {FULL_NAME!r}."
        )
    if config.isolation not in ISOLATIONS:
        raise PreflightError(
            f"Unknown isolation {config.isolation!r}. "
            f"Use {ISOLATION_HOME!r} or {ISOLATION_MCP!r}."
        )
    model = config.model or CURSOR_DEFAULT_MODEL
    config.model = model
    tasks = load_full_tasks()
    reps = cursor_reps(config.preset)
    try:
        selected = normalize_conditions(config.conditions)
    except ValueError as exc:
        raise PreflightError(str(exc)) from exc
    plans = plan_matrix(tasks, seed=config.seed, reps=reps, conditions=selected)
    by_id = {task.task_id: task for task in tasks}
    env = dict(config.env if config.env is not None else os.environ)
    repo_root = config.repo_root or Path(__file__).resolve().parents[2]
    results_dir = Path(config.results_dir or default_results_dir())
    state_home = config.state_home or Path.home()
    binary = config.cursor_bin or shutil.which("cursor-agent") or ""
    commit = overhaust_commit(repo_root)
    hook_command = cursor_hook_command(repo_root, config.python or sys.executable)

    builder = config.workspace_builder or (lambda task_list: build_fixture_workspace(task_list))
    workspace = builder(tasks)
    try:
        runner = config.command_runner or default_cursor_command_runner
        preflight: Optional[Dict[str, Any]] = None
        probe = config.probe
        sessions: List[Layer4SessionResult] = []
        state_restore: Optional[Dict[str, Any]] = None
        mcp_cleanup: Optional[Dict[str, Any]] = None
        reserved = allocate_cursor_result_paths(results_dir, config.stamp)
        used_stamp = str(reserved["stamp"])

        if not config.dry_run:
            if not binary:
                raise PreflightError(
                    "cursor-agent is not on PATH. Install it or pass --cursor-bin. "
                    "The run does not start without it."
                )
            preflight = run_cursor_preflight(
                binary=binary,
                env=env,
                isolation=config.isolation,
                model=model,
                state_home=state_home,
                runner=runner,
            )
            if not preflight.get("selected_usable"):
                raise PreflightError(
                    "Cursor preflight failed. No model session was started. "
                    + json.dumps(preflight)
                )
            if probe is None:
                probe = CursorProbe(
                    agent="cursor",
                    version=preflight.get("version"),
                    version_source=str(preflight.get("version_source") or "unavailable"),
                    binary=binary,
                    warning=None,
                )
            guard = CursorStateGuard(state_home)
            guard.snapshot()
            run_dir = Path(tempfile.mkdtemp(prefix="layer4-cursor-"))
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
                                env=env,
                                run_dir=run_dir,
                                runner=runner,
                                hook_command=hook_command,
                                state_home=state_home,
                                commit=commit,
                            )
                        )
                    except Exception as exc:
                        sessions.append(
                            error_session(
                                plan,
                                snapshot_hash=workspace.snapshot_hash,
                                probe=probe,
                                message=f"{type(exc).__name__}: {exc}",
                                started_at=_now(),
                                finished_at=_now(),
                                model_requested=model,
                                isolation=config.isolation,
                            )
                        )
                _persist_raw(sessions, results_dir, used_stamp)
            finally:
                shutil.rmtree(run_dir, ignore_errors=True)
                state_restore = guard.restore()
                mcp_cleanup = _mcp_cleanup_report(sessions, config.isolation)
        else:
            probe = probe or CursorProbe(
                agent="cursor",
                version=None,
                version_source="unavailable",
                binary=binary or None,
                warning="dry run did not probe cursor-agent",
            )

        if probe is None:
            probe = CursorProbe(
                agent="cursor",
                version=None,
                version_source="unavailable",
                binary=binary or None,
                warning=None,
            )

        cache = cache_analysis(sessions)
        cache["note"] = CURSOR_CACHE_NOTE
        planned = [_planned_entry(plan, index) for index, plan in enumerate(plans)]
        actual = [_order_entry(session, index) for index, session in enumerate(sessions)]
        for entry, session in zip(actual, sessions):
            entry["integration_mode"] = session.integration_path
        output_dir = str(results_dir)
        report: Dict[str, Any] = {
            "schema_version": CURSOR_RUN_SCHEMA_VERSION,
            "protocol_version": CURSOR_PROTOCOL_VERSION,
            "session_schema_version": SCHEMA_VERSION,
            "benchmark_version": BENCHMARK_VERSION,
            "layer": 4,
            "preset": config.preset,
            "mode": _run_mode(config),
            "instrumentation_only": True,
            "claim_policy": CURSOR_CLAIM_POLICY,
            "cache_control_note": PROMPT_CACHE_POLICY,
            "methodology": _methodology(),
            "prompt_file_policy": PROMPT_FILE_POLICY,
            "means_policy": MEANS_POLICY,
            "telemetry_catalog": [dict(item) for item in TELEMETRY_CATALOG],
            "generated_at": _now(),
            "seed": config.seed,
            "execution_order_policy": (
                EXECUTION_ORDER_POLICY
                + " Cursor pilot uses all 5 tasks and 1 rep. Cursor full uses "
                "all 5 tasks and 2 reps. The generator is the shared pair plan."
            ),
            "agent": "cursor",
            "agent_version": probe.version,
            "agent_version_source": probe.version_source,
            "agent_version_warning": probe.warning,
            "model_requested": model,
            "model_pinned": True,
            "isolation": config.isolation,
            "integration_mode": "cursor_session_start_hook",
            "permissions": dict(CURSOR_PERMISSIONS),
            "snapshot_hash": workspace.snapshot_hash,
            "repo_size": workspace.repo_size,
            "project_id": workspace.project_id,
            "repository": str(workspace.root),
            "overhaust_commit": commit,
            "fixture_commit": None,
            "fixture_commit_kind": "unavailable",
            "task_ids": [task.task_id for task in tasks],
            "reps": reps,
            "conditions": list(selected),
            "planned_session_count": len(plans),
            "recorded_session_count": len(sessions),
            "dropped_session_count": 0 if config.dry_run else len(plans) - len(sessions),
            "planned_execution_order": planned,
            "actual_execution_order": actual,
            "plans": [plan.to_dict() for plan in plans],
            "sessions": [session.to_dict() for session in sessions],
            "cache_analysis": cache,
            "agent_behavior": agent_behavior(sessions),
            "files_inspected_analysis": _files_inspected_analysis(sessions),
            "correctness": _correctness_summary(sessions),
            "context_metrics": _context_metrics(sessions),
            "preflight": preflight,
            "state_restore": state_restore,
            "mcp_cleanup": mcp_cleanup,
            "output_dir": output_dir,
            "token_accounting_note": CURSOR_TOKEN_ACCOUNTING,
            "comparability": (
                "Do not compare Cursor token figures to Codex token figures. "
                "cacheReadTokens is not included in inputTokens."
            ),
        }
        if len(selected) == 1:
            report["single_condition"] = selected[0]
        if config.dry_run:
            report["dry_run_note"] = "No cursor-agent process was started."
            report["dry_run_text"] = format_cursor_dry_run(report)
        paths = write_cursor_report(report, results_dir, stamp=used_stamp)
        report["_output_paths"] = paths
        report["output_dir"] = str(results_dir)
        if config.dry_run:
            report["dry_run_text"] = format_cursor_dry_run(report)
        return report
    finally:
        workspace.close()
