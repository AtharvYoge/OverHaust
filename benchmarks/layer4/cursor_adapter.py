"""
Cursor agent adapter for Layer 4.

The runner starts `cursor-agent` and passes the stream-json transcript, the
sessionStart hook debug file, the workspace diff, and the local-store
inspection here. This module does not launch a model session by itself.
`probe` runs `cursor-agent --version` only.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from benchmarks.evaluate import evaluate_answer
from benchmarks.layer4 import SCHEMA_VERSION
from benchmarks.layer4.condition import PROMPT_CACHE_POLICY
from benchmarks.layer4.cursor_condition import (
    CURSOR_PERMISSIONS,
    INTEGRATION_HOOK,
    ISOLATION_MCP,
    TARGET_CURSOR_AGENT_VERSION,
)
from benchmarks.layer4.cursor_parse import (
    CURSOR_TOKEN_ACCOUNTING,
    CursorStreamObservation,
    agent_token_figures,
    hook_figures,
    parse_hook_debug,
    parse_stream_json,
    tool_and_file_figures,
)
from benchmarks.layer4.cursor_store import StoreInspection
from benchmarks.layer4.schema import (
    Layer4SessionResult,
    MetricFigure,
    SessionOutcome,
    primary_metric_status_for,
    telemetry_gaps_for,
    unavailable_metrics,
)
from benchmarks.schemas import BenchmarkTask


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


@dataclass
class CursorProbe:
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
class CursorSessionCapture:
    session_id: str
    condition: str
    task_id: str
    rep: int
    seed: int
    execution_order: int
    pair_id: str
    order_in_pair: int
    condition_order: str
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
    command: List[str]
    hook_command: Optional[str]
    integration_path: str
    isolation: str
    hook_layout: Dict[str, Any]
    store: StoreInspection
    raw_telemetry_paths: Dict[str, Optional[str]]
    snapshot_hash_before: Optional[str] = None
    snapshot_hash_after: Optional[str] = None
    files_changed_paths: List[str] = field(default_factory=list)
    files_changed_measured: bool = False
    restore_verified: bool = False
    launch_error: Optional[str] = None
    started_at: str = ""
    finished_at: str = ""
    original_pair_id: Optional[str] = None
    original_planned_position: Optional[int] = None
    overhaust_commit: Optional[str] = None
    prompt_file_written: bool = False
    isolation_evidence: Dict[str, Any] = field(default_factory=dict)


class CursorAdapter:
    agent_id = "cursor"

    def __init__(self, binary: Optional[str] = None, runner: Any = None) -> None:
        self.binary = binary
        self.runner = runner

    def probe(self) -> CursorProbe:
        return probe_cursor(self.binary, runner=self.runner)

    def build_session_result(
        self,
        capture: CursorSessionCapture,
        task: BenchmarkTask,
    ) -> Layer4SessionResult:
        return session_from_capture(capture, task)


def probe_cursor(binary: Optional[str], runner: Any = None) -> CursorProbe:
    """Version only. Does not pass `-p` and does not start a model session."""
    if not binary:
        return CursorProbe(
            agent="cursor",
            version=None,
            version_source="unavailable",
            binary=None,
            warning="cursor-agent binary not found on PATH",
        )
    command = [binary, "--version"]
    try:
        if runner is not None:
            result = runner(command, {}, ".", 5)
            if result.timed_out or result.returncode not in (0, None):
                raise OSError(result.stderr or "cursor-agent --version failed")
            text = (result.stdout or "").strip()
        else:
            text = subprocess.check_output(
                command,
                text=True,
                stderr=subprocess.STDOUT,
                timeout=5,
                stdin=subprocess.DEVNULL,
            ).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return CursorProbe(
            agent="cursor",
            version=None,
            version_source="unavailable",
            binary=binary,
            warning=f"cursor-agent --version failed: {exc}",
        )
    version = text.split()[-1] if text else None
    warning = None
    if version and version != TARGET_CURSOR_AGENT_VERSION:
        warning = (
            f"cursor-agent {version} is outside {TARGET_CURSOR_AGENT_VERSION}, "
            "which is the stream-json shape this adapter was checked against. "
            "Fields this CLI does not emit stay unavailable."
        )
    return CursorProbe(
        agent="cursor",
        version=version,
        version_source="cursor_agent_cli_version",
        binary=binary,
        warning=warning,
    )


def _context_injected(report: Optional[Dict[str, Any]]) -> bool:
    if not report or report.get("error"):
        return False
    try:
        return int(report.get("context_bytes") or 0) > 0
    except (TypeError, ValueError):
        return False


def _answer_text(obs: CursorStreamObservation) -> Optional[str]:
    if obs.result_text and obs.result_text.strip():
        return obs.result_text
    if obs.assistant_texts:
        return obs.assistant_texts[-1]
    return None


def error_session(
    plan: Any,
    *,
    snapshot_hash: str,
    probe: CursorProbe,
    message: str,
    started_at: str,
    finished_at: str,
    model_requested: Optional[str],
    isolation: str,
) -> Layer4SessionResult:
    figures = unavailable_metrics(message)
    return Layer4SessionResult(
        schema_version=SCHEMA_VERSION,
        session_id=plan.session_id,
        agent="cursor",
        agent_version=probe.version,
        agent_version_source=probe.version_source,
        agent_version_warning=probe.warning,
        model=model_requested,
        model_requested=model_requested,
        model_reported=None,
        model_source="unavailable",
        condition=plan.condition,
        task_id=plan.task_id,
        rep=plan.rep,
        seed=plan.seed,
        pair_id=plan.pair_id,
        order_in_pair=plan.order_in_pair,
        condition_order=plan.condition_order,
        execution_order=plan.execution_order,
        original_pair_id=plan.original_pair_id,
        original_planned_position=plan.original_planned_position,
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
        token_accounting_note=CURSOR_TOKEN_ACCOUNTING,
        error=message,
        started_at=started_at,
        finished_at=finished_at,
        prompt_sha256="",
        integration_path="none",
        permissions=dict(CURSOR_PERMISSIONS),
        supplemental_telemetry={"isolation": isolation, "cache_control_note": PROMPT_CACHE_POLICY},
        **figures,
    )


def session_from_capture(
    capture: CursorSessionCapture,
    task: BenchmarkTask,
) -> Layer4SessionResult:
    obs = parse_stream_json(capture.stdout)
    hook_reports = parse_hook_debug(capture.hook_debug)
    hook_last = hook_reports[-1] if hook_reports else None
    token_figures, derived = agent_token_figures(obs)
    figures: Dict[str, MetricFigure] = {}
    figures.update(token_figures)
    figures.update(hook_figures(hook_last, condition=capture.condition))
    figures.update(tool_and_file_figures(obs))

    if capture.files_changed_measured:
        figures["files_changed"] = MetricFigure.exact(
            len(capture.files_changed_paths),
            "snapshot_diff",
            "Paths whose bytes differ from the pre-agent workspace snapshot.",
        )
    else:
        figures["files_changed"] = MetricFigure.unavailable(
            "snapshot_diff",
            "Workspace snapshot diff was not measured for this session.",
        )
    figures["files_changed_via_codex_patch"] = MetricFigure.unavailable(
        "not_reported",
        "Cursor stream-json has no Codex file_change event. Not stored as zero.",
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
            "Milliseconds around the cursor-agent subprocess, including hook time.",
        )

    invalid: List[str] = []
    layout_problems = list((capture.hook_layout or {}).get("problems") or [])
    if not capture.restore_verified:
        invalid.append("snapshot_restore_failed")
    if layout_problems:
        invalid.append("hook_layout_mismatch")
    if capture.prompt != task.prompt:
        invalid.append("prompt_modified")
    if capture.command and capture.command[-1] != task.prompt:
        invalid.append("prompt_modified")
    if "<!-- overhaust-context -->" in (capture.prompt or ""):
        invalid.append("context_pasted_into_prompt")
    if capture.condition == "overhaust":
        if capture.integration_path != INTEGRATION_HOOK:
            invalid.append("overhaust_hook_not_configured")
        if not capture.prompt_file_written:
            invalid.append("overhaust_prompt_file_missing")
        if not hook_reports:
            invalid.append("overhaust_hook_did_not_fire")
        elif hook_last and hook_last.get("error"):
            invalid.append("overhaust_hook_error")
        elif not _context_injected(hook_last):
            invalid.append("overhaust_context_not_injected")
        if capture.store.parseable and capture.store.marker_present is False:
            invalid.append("overhaust_marker_missing_from_store")
    elif capture.condition == "baseline":
        if hook_reports:
            invalid.append("baseline_hook_contamination")
        if capture.store.parseable and capture.store.marker_present:
            invalid.append("baseline_context_marker_in_store")
    if obs.overhaust_mcp_calls:
        invalid.append("overhaust_mcp_tool_called")
    if capture.store.parseable and capture.store.overhaust_tools:
        invalid.append("overhaust_mcp_tool_available")
    if capture.isolation == ISOLATION_MCP:
        evidence = capture.isolation_evidence or {}
        if evidence.get("applied") is not True:
            invalid.append("mcp_toggle_not_applied")
        if evidence.get("disable_timed_out") or evidence.get("disable_exit_code") not in (0,):
            invalid.append("mcp_toggle_disable_failed")
        if evidence.get("overhaust_listed") is not False:
            invalid.append("overhaust_mcp_still_listed")
        if evidence.get("refused_preexisting_slugs"):
            invalid.append("mcp_toggle_preexisting_slug")
        if evidence.get("cleanup_verified") is not True:
            invalid.append("mcp_toggle_cleanup_failed")

    deduped: List[str] = []
    for reason in invalid:
        if reason not in deduped:
            deduped.append(reason)
    invalid = deduped

    launch_error = capture.launch_error
    trust_failure = "workspace trust required" in (capture.stderr or "").lower()
    if invalid:
        outcome = SessionOutcome.INVALID.value
        valid = False
    elif capture.timed_out:
        outcome = SessionOutcome.ERROR.value
        valid = True
        launch_error = launch_error or "cursor-agent exceeded the session timeout"
    elif launch_error and not obs.result_subtype:
        outcome = SessionOutcome.ERROR.value
        valid = True
    elif obs.is_error or (obs.result_subtype and obs.result_subtype != "success"):
        outcome = SessionOutcome.FAILED.value
        valid = True
    elif capture.exit_code not in (0, None) and obs.result_subtype == "success" and not obs.is_error:
        outcome = SessionOutcome.FAILED.value
        valid = True
    elif obs.result_subtype == "success" and not obs.is_error and capture.exit_code in (0, None):
        outcome = SessionOutcome.COMPLETED.value
        valid = True
    elif trust_failure:
        outcome = SessionOutcome.ERROR.value
        valid = True
        launch_error = launch_error or "Workspace Trust Required"
    else:
        outcome = SessionOutcome.ERROR.value
        valid = True
        launch_error = launch_error or (
            "cursor-agent produced no result event."
            + (f" (exit {capture.exit_code})" if capture.exit_code not in (0, None) else "")
        )

    answer = _answer_text(obs)
    correctness = evaluate_answer(task, answer)
    model_reported = obs.model_display_name
    if capture.model_requested:
        model = capture.model_requested
        model_source = "cli_flag"
    elif model_reported:
        model = model_reported
        model_source = "cursor_stream_json.system.init.model"
    else:
        model = None
        model_source = "unavailable"

    duration = {
        "duration_ms": {
            "value": obs.duration_ms,
            "kind": "exact" if obs.duration_ms is not None else "unavailable",
            "source": "cursor_stream_json.result.duration_ms",
        },
        "duration_api_ms": {
            "value": obs.duration_api_ms,
            "kind": "exact" if obs.duration_api_ms is not None else "unavailable",
            "source": "cursor_stream_json.result.duration_api_ms",
        },
    }
    files_kind = "exact" if figures["files_inspected"].is_exact else "unavailable"
    supplemental: Dict[str, Any] = {
        "isolation": capture.isolation,
        "isolation_evidence": dict(capture.isolation_evidence or {}),
        "hook_state": capture.hook_layout,
        "injection_verification": capture.store.verification,
        "store_inspection": capture.store.to_dict(),
        "fixture_hash": capture.snapshot_hash,
        "overhaust_commit": capture.overhaust_commit,
        "fixture_commit": {
            "value": None,
            "kind": "unavailable",
            "note": "The LabKOT fixture is a generated tree, not a git checkout.",
        },
        "derived_usage_component_sum": derived,
        "provider_duration": duration,
        "cursor_session_id": obs.session_id,
        "model_display_name": model_reported,
        "files_inspected_paths": list(obs.read_paths) if files_kind == "exact" else None,
        "files_inspected_kind": files_kind,
        "cache_control_note": PROMPT_CACHE_POLICY,
        "comparability": (
            "Cursor cacheReadTokens is a separate bucket from inputTokens. "
            "Do not compare these figures to Codex."
        ),
        "thinking_events": obs.thinking_events,
        "cost": {"value": None, "kind": "unavailable", "note": "stream-json does not report cost or plan usage."},
    }
    if hook_last:
        supplemental["hook_debug"] = {
            key: hook_last.get(key)
            for key in (
                "fired",
                "error",
                "context_bytes",
                "context_bytes_kind",
                "estimated_context_tokens",
                "estimated_context_tokens_kind",
                "latency_ms",
                "latency_ms_kind",
                "injection_mode",
                "project_id",
                "prompt_hash",
                "prompt_length",
                "harness_session_id",
                "cursor_session_id",
            )
        }
    if capture.stderr:
        supplemental["stderr_preview"] = capture.stderr[-2000:]
    if obs.parse_errors:
        supplemental["stream_parse_errors"] = obs.parse_errors[:20]
    if (
        capture.model_requested
        and model_reported
        and capture.model_requested != model_reported
    ):
        supplemental["model_flag_differs_from_display_name"] = {
            "requested": capture.model_requested,
            "reported": model_reported,
        }

    error = launch_error
    if obs.is_error and obs.result_text and not error:
        error = obs.result_text[:500]
    gaps = telemetry_gaps_for(figures)
    status = primary_metric_status_for(figures)
    raw_source = "cursor_stream_json" if obs.parsed and obs.events else "unavailable"
    permissions = dict(CURSOR_PERMISSIONS)
    permissions["isolation"] = capture.isolation

    return Layer4SessionResult(
        schema_version=SCHEMA_VERSION,
        session_id=capture.session_id,
        agent="cursor",
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
        pair_id=capture.pair_id,
        order_in_pair=capture.order_in_pair,
        condition_order=capture.condition_order,
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
        token_accounting_note=CURSOR_TOKEN_ACCOUNTING,
        error=error,
        answer_text=answer,
        correctness=correctness.correct,
        evidence_score=correctness.evidence_score,
        correctness_detail=correctness.to_dict(),
        integration_path=capture.integration_path,
        hook_command=capture.hook_command,
        hook_fired=bool(hook_reports),
        context_injected=_context_injected(hook_last) if hook_reports else False,
        permissions=permissions,
        command=list(capture.command),
        exit_code=capture.exit_code,
        timed_out=capture.timed_out,
        codex_thread_id=None,
        tool_call_types=dict(obs.tool_call_types),
        tool_invocations=list(obs.tool_invocations),
        files_changed_paths=list(capture.files_changed_paths),
        supplemental_telemetry=supplemental,
        started_at=capture.started_at,
        finished_at=capture.finished_at,
        prompt_sha256=prompt_sha256(capture.prompt),
        **figures,
    )
