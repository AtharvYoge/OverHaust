"""
Codex CLI adapter.

Launches nothing by itself. The runner starts `codex exec` and hands this
adapter the stdout JSONL, the session rollout, the hook debug file, and the
workspace diff. Mapping rules live in `codex_parse.py`.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from benchmarks.evaluate import evaluate_answer
from benchmarks.layer4 import SCHEMA_VERSION, TARGET_CODEX_VERSION
from benchmarks.layer4.codex_parse import (
    CODEX_USAGE_ACCOUNTING,
    HookObservation,
    RolloutObservation,
    agent_token_figures,
    overhaust_figures,
    parse_exec_jsonl,
    parse_hook_debug,
    parse_rollout_jsonl,
    tool_and_file_figures,
)
from benchmarks.layer4.condition import CODEX_EXEC_PERMISSIONS, INTEGRATION_HOOK
from benchmarks.layer4.schema import (
    Layer4SessionResult,
    MetricFigure,
    SessionOutcome,
    primary_metric_status_for,
    telemetry_gaps_for,
)
from benchmarks.schemas import BenchmarkTask


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


@dataclass
class CodexProbe:
    agent: str
    version: Optional[str]
    version_source: str
    binary: Optional[str]
    warning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "version": self.version,
            "version_source": self.version_source,
            "binary": self.binary,
            "warning": self.warning,
        }


@dataclass
class CodexSessionCapture:
    """Everything collected for one Codex session, including launch failures."""

    session_id: str
    condition: str
    task_id: str
    rep: int
    seed: int
    execution_order: int
    snapshot_hash: str
    prompt: str
    model_requested: Optional[str]
    agent_version: Optional[str]
    agent_version_source: str
    agent_version_warning: Optional[str]
    stdout: str
    stderr: str
    exit_code: Optional[int]
    timed_out: bool
    elapsed_ms: Optional[int]
    hook_debug: str
    rollout_text: str
    raw_telemetry_paths: Dict[str, Optional[str]]
    last_message: Optional[str]
    command: List[str]
    hook_command: Optional[str]
    integration_path: str
    snapshot_hash_before: Optional[str]
    snapshot_hash_after: Optional[str]
    files_changed_paths: List[str] = field(default_factory=list)
    files_changed_measured: bool = False
    restore_verified: bool = False
    restore_detail: Optional[str] = None
    launch_error: Optional[str] = None
    started_at: str = ""
    finished_at: str = ""
    fresh_codex_home: bool = True
    pair_id: str = ""
    order_in_pair: int = 1
    condition_order: str = ""
    original_pair_id: Optional[str] = None
    original_planned_position: Optional[int] = None


class CodexAdapter:
    agent_id = "codex"

    def __init__(self, binary: Optional[str] = None) -> None:
        self.binary = binary

    def probe(self) -> CodexProbe:
        return probe_codex(self.binary)

    def build_session_result(
        self,
        capture: CodexSessionCapture,
        task: BenchmarkTask,
    ) -> Layer4SessionResult:
        return session_from_capture(capture, task)


def probe_codex(binary: Optional[str]) -> CodexProbe:
    if not binary:
        return CodexProbe(
            agent="codex",
            version=None,
            version_source="unavailable",
            binary=None,
            warning="codex binary not found on PATH",
        )
    try:
        out = subprocess.check_output(
            [binary, "--version"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return CodexProbe(
            agent="codex",
            version=None,
            version_source="unavailable",
            binary=binary,
            warning=f"codex --version failed: {exc}",
        )
    text = (out or "").strip()
    version = text.split()[-1] if text else None
    warning = None
    if version and not _version_matches_target(version):
        warning = (
            f"Codex {version} is outside {TARGET_CODEX_VERSION}, which is the "
            "exec JSONL schema this adapter was checked against "
            "(openai/codex tag rust-v0.146.0). Fields this CLI does not emit "
            "stay unavailable."
        )
    return CodexProbe(
        agent="codex",
        version=version,
        version_source="codex_cli_version",
        binary=binary,
        warning=warning,
    )


def _version_matches_target(version: str) -> bool:
    head = version.split("-", 1)[0]
    return head == TARGET_CODEX_VERSION or head.startswith(f"{TARGET_CODEX_VERSION}.")


def _context_injected(hook: HookObservation) -> bool:
    report = hook.last or {}
    if report.get("error"):
        return False
    try:
        return int(report.get("context_bytes") or 0) > 0
    except (TypeError, ValueError):
        return False


def _answer_text(exec_messages: List[str], last_message: Optional[str]) -> Optional[str]:
    if exec_messages:
        return exec_messages[-1]
    if last_message and last_message.strip():
        return last_message
    return None


def session_from_capture(
    capture: CodexSessionCapture,
    task: BenchmarkTask,
) -> Layer4SessionResult:
    exec_obs = parse_exec_jsonl(capture.stdout)
    rollout = parse_rollout_jsonl(capture.rollout_text) if capture.rollout_text else RolloutObservation()
    hook = parse_hook_debug(capture.hook_debug)

    token_figures, disagreement, supplemental = agent_token_figures(exec_obs, rollout)
    figures: Dict[str, MetricFigure] = {}
    figures.update(token_figures)
    figures.update(overhaust_figures(hook, condition=capture.condition))
    figures.update(tool_and_file_figures(exec_obs))

    if capture.files_changed_measured:
        figures["files_changed"] = MetricFigure.exact(
            len(capture.files_changed_paths),
            "snapshot_diff",
            "Paths whose bytes differ from the session snapshot after the "
            "process exits. Includes shell writes. Independent of file_change events.",
        )
    else:
        figures["files_changed"] = MetricFigure.unavailable(
            "snapshot_diff",
            "Workspace snapshot diff was not measured for this session.",
        )

    if capture.elapsed_ms is None:
        figures["elapsed_ms"] = MetricFigure.unavailable(
            "harness_wall_clock",
            "Wall clock was not recorded.",
        )
    else:
        figures["elapsed_ms"] = MetricFigure.exact(
            capture.elapsed_ms,
            "harness_wall_clock",
            "Milliseconds around the codex exec subprocess, including hook time.",
        )

    invalid: List[str] = []
    if not capture.restore_verified:
        invalid.append("snapshot_restore_failed")
    if (
        capture.snapshot_hash_before
        and capture.snapshot_hash
        and capture.snapshot_hash_before != capture.snapshot_hash
    ):
        invalid.append("snapshot_mismatch_before_session")
    if not capture.fresh_codex_home:
        invalid.append("codex_home_not_fresh")
    if capture.prompt != task.prompt:
        invalid.append("prompt_modified")
    if capture.command and capture.command[-1] != task.prompt:
        invalid.append("prompt_modified")
    if "<!-- overhaust-context -->" in (capture.prompt or ""):
        invalid.append("context_pasted_into_prompt")
    if capture.condition == "overhaust":
        if capture.integration_path != INTEGRATION_HOOK:
            invalid.append("overhaust_hook_not_configured")
        if capture.hook_command and "overhaust_user_prompt_hook" not in capture.hook_command:
            invalid.append("overhaust_hook_command_mismatch")
        if not hook.fired:
            invalid.append("overhaust_hook_did_not_fire")
        elif hook.last and hook.last.get("error"):
            invalid.append("overhaust_hook_error")
        elif not _context_injected(hook):
            invalid.append("overhaust_context_not_injected")
    elif capture.condition == "baseline" and hook.fired:
        invalid.append("baseline_hook_contamination")

    # de-duplicate while keeping order
    deduped: List[str] = []
    for reason in invalid:
        if reason not in deduped:
            deduped.append(reason)
    invalid = deduped

    launch_error = capture.launch_error
    if invalid:
        outcome = SessionOutcome.INVALID.value
        valid = False
    elif capture.timed_out or launch_error:
        outcome = SessionOutcome.ERROR.value
        valid = False
    elif exec_obs.turn_failed or (
        exec_obs.turn_completed and capture.exit_code not in (0, None)
    ):
        # The turn ran. A non-zero exit or turn.failed is a failed session,
        # and the telemetry is kept.
        outcome = SessionOutcome.FAILED.value
        valid = True
    elif exec_obs.turn_completed and capture.exit_code in (0, None):
        outcome = SessionOutcome.COMPLETED.value
        valid = True
    else:
        # Non-zero exit with no terminal turn, or empty output: the CLI did
        # not produce a session. Not a valid measurement.
        outcome = SessionOutcome.ERROR.value
        valid = False
        launch_error = launch_error or (
            "Codex produced no terminal turn.completed or turn.failed event."
            + (
                f" (exit {capture.exit_code})"
                if capture.exit_code not in (0, None)
                else ""
            )
        )

    answer = _answer_text(exec_obs.agent_messages, capture.last_message)
    if (
        answer
        and capture.last_message
        and capture.last_message.strip()
        and exec_obs.agent_messages
        and capture.last_message.strip() != answer.strip()
    ):
        supplemental["last_message_disagrees_with_exec_jsonl"] = True
    correctness = evaluate_answer(task, answer)

    model_reported = rollout.model
    if capture.model_requested:
        model = capture.model_requested
        model_source = "cli_flag"
    elif model_reported:
        model = model_reported
        model_source = "codex_session_rollout"
    else:
        model = None
        model_source = "unavailable"
    if (
        capture.model_requested
        and model_reported
        and capture.model_requested != model_reported
    ):
        supplemental["model_flag_disagrees_with_rollout"] = {
            "requested": capture.model_requested,
            "reported": model_reported,
        }

    if exec_obs.usage is not None:
        raw_source = "codex_exec_jsonl"
    elif rollout.total_usage is not None:
        raw_source = "codex_session_rollout"
    else:
        raw_source = "unavailable"

    if rollout.cli_version and capture.agent_version and rollout.cli_version != capture.agent_version:
        supplemental["rollout_cli_version"] = rollout.cli_version
    if capture.stderr:
        supplemental["stderr_preview"] = capture.stderr[-2000:]
    if exec_obs.non_json_lines:
        supplemental["non_json_stdout_lines"] = exec_obs.non_json_lines
    if exec_obs.parse_errors:
        supplemental["exec_jsonl_parse_errors"] = exec_obs.parse_errors[:20]
    if hook.last:
        supplemental["hook_debug"] = {
            key: hook.last.get(key)
            for key in (
                "project_id",
                "context_bytes",
                "estimated_context_tokens",
                "latency_ms",
                "error",
                "injection_mode",
                "relevant_files",
                "insufficient_evidence",
            )
        }

    error = launch_error
    if exec_obs.failure_message and not error:
        error = exec_obs.failure_message
    elif exec_obs.failure_message and error:
        error = f"{error}; {exec_obs.failure_message}"

    gaps = telemetry_gaps_for(figures)
    status = primary_metric_status_for(figures)
    pair_id = capture.pair_id or f"{capture.task_id}-r{capture.rep}"
    if capture.condition_order:
        condition_order = capture.condition_order
    elif capture.condition == "overhaust":
        condition_order = "overhaust->baseline"
    else:
        condition_order = "baseline->overhaust"

    return Layer4SessionResult(
        schema_version=SCHEMA_VERSION,
        session_id=capture.session_id,
        agent="codex",
        agent_version=capture.agent_version,
        agent_version_source=capture.agent_version_source,
        agent_version_warning=capture.agent_version_warning,
        model=model,
        model_requested=capture.model_requested,
        model_reported=model_reported,
        model_source=model_source,
        condition=capture.condition,
        task_id=capture.task_id,
        rep=capture.rep,
        seed=capture.seed,
        pair_id=pair_id,
        order_in_pair=capture.order_in_pair,
        condition_order=condition_order,
        execution_order=capture.execution_order,
        original_pair_id=capture.original_pair_id,
        original_planned_position=capture.original_planned_position,
        snapshot_hash=capture.snapshot_hash,
        snapshot_hash_before=capture.snapshot_hash_before,
        snapshot_hash_after=capture.snapshot_hash_after,
        raw_telemetry_source=raw_source,
        raw_telemetry_paths=dict(capture.raw_telemetry_paths),
        outcome=outcome,
        valid=valid,
        invalid_reasons=invalid,
        telemetry_gaps=gaps,
        primary_metric_status=status,
        token_accounting_note=CODEX_USAGE_ACCOUNTING,
        error=error,
        answer_text=answer,
        correctness=correctness.correct,
        evidence_score=correctness.evidence_score,
        correctness_detail=correctness.to_dict(),
        integration_path=capture.integration_path,
        hook_command=capture.hook_command,
        hook_fired=hook.fired,
        context_injected=_context_injected(hook) if hook.fired else False,
        permissions=dict(CODEX_EXEC_PERMISSIONS),
        command=list(capture.command),
        exit_code=capture.exit_code,
        timed_out=capture.timed_out,
        codex_thread_id=exec_obs.thread_id,
        tool_call_types=dict(exec_obs.tool_call_types),
        tool_invocations=list(exec_obs.tool_invocations),
        files_changed_paths=list(capture.files_changed_paths),
        supplemental_telemetry=supplemental,
        telemetry_disagreement=disagreement,
        started_at=capture.started_at,
        finished_at=capture.finished_at,
        prompt_sha256=prompt_sha256(capture.prompt),
        **figures,
    )
