"""
Map Codex CLI 0.146.0 telemetry onto Layer 4 metric figures.

Checked against openai/codex tag rust-v0.146.0:

- `codex exec --json` writes JSONL `ThreadEvent`s
  (`codex-rs/exec/src/exec_events.rs`). `turn.completed.usage` has
  input_tokens, cached_input_tokens, cache_write_input_tokens, output_tokens,
  and reasoning_output_tokens. It has no total_tokens field.
- Those usage numbers are the thread's cumulative `ThreadTokenUsage.total`,
  not the latest request. The last `turn.completed` is the session total.
- Item types that count as tool calls: command_execution, mcp_tool_call,
  collab_tool_call, web_search. There is no structured file-read item.
- Session rollouts under `$CODEX_HOME/sessions/**/*.jsonl` may also contain
  `event_msg` / `token_count` with `total_token_usage` and `last_token_usage`.
  `last_token_usage` is one API call. It is stored as supplemental telemetry
  and is never copied into the session totals.

OverHaust context tokens come only from the hook debug record
(`estimated_context_tokens`, a TokenEstimator count). They are not subtracted
from the agent figures.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from benchmarks.layer4.schema import MetricFigure


SOURCE_EXEC_USAGE = "codex_exec_jsonl.turn.completed.usage"
SOURCE_ROLLOUT_TOTAL = "codex_session_rollout.token_count.total_token_usage"
SOURCE_NOT_REPORTED = "not_reported"
SOURCE_HOOK_TOKENS = "overhaust_hook_debug.estimated_context_tokens"
SOURCE_HOOK_BYTES = "overhaust_hook_debug.context_bytes"
SOURCE_HOOK_LATENCY = "overhaust_hook_debug.latency_ms"
SOURCE_RETRIEVAL = "overhaust_hook_debug"
SOURCE_TOOLS = "codex_exec_jsonl.item.completed"
SOURCE_PATCH = "codex_exec_jsonl.item.completed.file_change"
SOURCE_FILES_INSPECTED = "codex_exec_jsonl"

TOOL_ITEM_TYPES = frozenset({
    "command_execution",
    "mcp_tool_call",
    "collab_tool_call",
    "web_search",
})

USAGE_COMPONENT_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "cache_write_input_tokens",
)

CODEX_USAGE_ACCOUNTING = (
    "Codex CLI 0.146.0 `codex exec --json` turn.completed.usage reports "
    "cumulative thread totals (ThreadTokenUsage.total): input_tokens, "
    "cached_input_tokens, cache_write_input_tokens, output_tokens, and "
    "reasoning_output_tokens. cached_input_tokens is a subset of input_tokens, "
    "not an additional bucket, and is never subtracted from input_tokens. "
    "reasoning_output_tokens is stored separately and is not subtracted from "
    "output_tokens. The exec usage object has no total_tokens field, so "
    "agent_total_tokens stays unavailable unless a session rollout "
    "token_count event reports total_tokens. The harness never fills that "
    "gap with input+output or input+cached+output. "
    "OverHaust context tokens are recorded on their own fields and are never "
    "subtracted from the agent figures or mixed into cache analysis."
)

FILES_INSPECTED_NOTE = (
    "Codex CLI 0.146.0 exec JSONL has no file-read item. File reads are "
    "embedded in command_execution shell strings, which are not a structured "
    "file list. The count is unavailable rather than parsed out of shell text."
)

RETRIEVAL_LATENCY_NOTE = (
    "Pure OverHaust retrieval latency is not separately emitted. With "
    "OVERHAUST_INTEGRATION_DEBUG=1 the hook debug latency_ms is end-to-end "
    "hook wall time (interception.py overwrites response.metrics.latency_ms "
    "after the optional naïve probe). That wall time is stored on "
    "overhaust_hook_latency_ms. Retrieval latency is left unavailable rather "
    "than substituting the hook wall time."
)

HOOK_LATENCY_NOTE = (
    "Exact reading of overhaust hook debug latency_ms. When "
    "OVERHAUST_INTEGRATION_DEBUG=1 this is end-to-end hook wall time, "
    "including the naïve token probe, not isolated retrieval latency."
)


@dataclass
class ExecObservation:
    events: List[Dict[str, Any]] = field(default_factory=list)
    non_json_lines: int = 0
    thread_id: Optional[str] = None
    turn_completed: int = 0
    turn_failed: int = 0
    failure_message: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    agent_messages: List[str] = field(default_factory=list)
    tool_call_types: Dict[str, int] = field(default_factory=dict)
    tool_invocations: List[Dict[str, Any]] = field(default_factory=list)
    patch_paths: List[str] = field(default_factory=list)
    parse_errors: List[str] = field(default_factory=list)


@dataclass
class RolloutObservation:
    events: List[Dict[str, Any]] = field(default_factory=list)
    model: Optional[str] = None
    cli_version: Optional[str] = None
    total_usage: Optional[Dict[str, int]] = None
    last_usage: Optional[Dict[str, int]] = None


@dataclass
class HookObservation:
    reports: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def fired(self) -> bool:
        return bool(self.reports)

    @property
    def last(self) -> Optional[Dict[str, Any]]:
        return self.reports[-1] if self.reports else None


def parse_jsonl(text: str) -> Tuple[List[Dict[str, Any]], int, List[str]]:
    events: List[Dict[str, Any]] = []
    non_json = 0
    errors: List[str] = []
    for line_no, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            non_json += 1
            errors.append(f"line {line_no}: {exc.msg}")
            continue
        if isinstance(item, dict):
            events.append(item)
        else:
            non_json += 1
            errors.append(f"line {line_no}: expected a JSON object")
    return events, non_json, errors


def _item_type(item: Dict[str, Any]) -> str:
    return str(item.get("type") or item.get("item_type") or "")


def _int_or_none(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return None


def _usage_dict(raw: Any) -> Optional[Dict[str, int]]:
    if not isinstance(raw, dict):
        return None
    found: Dict[str, int] = {}
    for key in USAGE_COMPONENT_KEYS + ("total_tokens",):
        if key not in raw:
            continue
        number = _int_or_none(raw.get(key))
        if number is None:
            continue
        found[key] = number
    return found or None


def parse_exec_jsonl(text: str) -> ExecObservation:
    events, non_json, errors = parse_jsonl(text)
    obs = ExecObservation(events=events, non_json_lines=non_json, parse_errors=errors)
    last_usage: Optional[Dict[str, int]] = None
    for event in events:
        kind = str(event.get("type") or "")
        if kind == "thread.started":
            thread_id = event.get("thread_id")
            if isinstance(thread_id, str) and thread_id:
                obs.thread_id = thread_id
        elif kind == "turn.completed":
            obs.turn_completed += 1
            usage = _usage_dict(event.get("usage"))
            if usage is not None:
                last_usage = usage
        elif kind == "turn.failed":
            obs.turn_failed += 1
            err = event.get("error")
            message = ""
            if isinstance(err, dict):
                message = str(err.get("message") or "")
            elif err:
                message = str(err)
            obs.failure_message = message or obs.failure_message
        elif kind in {"item.completed", "item.started", "item.updated"}:
            if kind != "item.completed":
                continue
            item = event.get("item")
            if not isinstance(item, dict):
                continue
            item_type = _item_type(item)
            if item_type == "agent_message":
                text_value = item.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    obs.agent_messages.append(text_value)
            elif item_type == "file_change":
                changes = item.get("changes") or []
                if isinstance(changes, list):
                    for change in changes:
                        if isinstance(change, dict) and change.get("path"):
                            obs.patch_paths.append(str(change["path"]))
            elif item_type in TOOL_ITEM_TYPES:
                obs.tool_call_types[item_type] = obs.tool_call_types.get(item_type, 0) + 1
                obs.tool_invocations.append(_tool_invocation(item_type, item))
    obs.usage = last_usage
    return obs


def _tool_invocation(item_type: str, item: Dict[str, Any]) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "type": item_type,
        "id": item.get("id"),
        "status": item.get("status"),
    }
    if item_type == "command_execution":
        record["command"] = item.get("command")
        output = item.get("aggregated_output")
        if isinstance(output, str) and len(output) > 500:
            record["aggregated_output_preview"] = output[:500]
            record["aggregated_output_truncated"] = True
        else:
            record["aggregated_output_preview"] = output
            record["aggregated_output_truncated"] = False
        record["exit_code"] = item.get("exit_code")
    elif item_type == "mcp_tool_call":
        record["server"] = item.get("server")
        record["tool"] = item.get("tool")
    elif item_type == "web_search":
        record["query"] = item.get("query")
    elif item_type == "collab_tool_call":
        record["tool"] = item.get("tool")
    return record


def parse_rollout_jsonl(text: str) -> RolloutObservation:
    events, _, _ = parse_jsonl(text)
    obs = RolloutObservation(events=events)
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        kind = str(event.get("type") or "")
        if kind == "session_meta":
            version = payload.get("cli_version")
            if isinstance(version, str) and version.strip():
                obs.cli_version = version.strip()
        model = payload.get("model") if isinstance(payload, dict) else None
        if isinstance(model, str) and model.strip():
            obs.model = model.strip()
        info = payload.get("info") if isinstance(payload, dict) else None
        token_type = payload.get("type") if isinstance(payload, dict) else None
        if kind == "event_msg" and token_type == "token_count" and isinstance(info, dict):
            total = _usage_dict(info.get("total_token_usage"))
            last = _usage_dict(info.get("last_token_usage"))
            if total is not None:
                obs.total_usage = total
            if last is not None:
                obs.last_usage = last
    return obs


def parse_hook_debug(text: str) -> HookObservation:
    events, _, _ = parse_jsonl(text)
    return HookObservation(reports=events)


def _component(
    usage: Optional[Dict[str, int]],
    key: str,
    source: str,
    *,
    absent_note: str,
) -> MetricFigure:
    if usage is None or key not in usage:
        return MetricFigure.unavailable(SOURCE_NOT_REPORTED, absent_note)
    value = usage[key]
    if value < 0:
        return MetricFigure.unavailable(
            SOURCE_NOT_REPORTED,
            f"Codex reported {key}={value}, which is not a usable count.",
        )
    return MetricFigure.exact(value, f"{source}.{key}")


def agent_token_figures(
    exec_obs: ExecObservation,
    rollout: Optional[RolloutObservation],
) -> Tuple[Dict[str, MetricFigure], List[str], Dict[str, Any]]:
    """
    Prefer exec JSONL usage. Fall back to rollout total_token_usage only when
    exec usage is absent. Never read last_token_usage into the session totals.
    """
    rollout_usage = rollout.total_usage if rollout else None
    disagreement: List[str] = []
    source = SOURCE_EXEC_USAGE
    usage = exec_obs.usage
    if usage is None and rollout_usage is not None:
        usage = rollout_usage
        source = SOURCE_ROLLOUT_TOTAL
    elif usage is not None and rollout_usage is not None:
        for key in USAGE_COMPONENT_KEYS:
            if key in usage and key in rollout_usage and usage[key] != rollout_usage[key]:
                disagreement.append(key)

    absent = (
        "Codex did not report this field. Not stored as zero."
        if usage is not None
        else "No Codex usage object on turn.completed or session rollout."
    )
    figures = {
        "agent_input_tokens": _component(usage, "input_tokens", source, absent_note=absent),
        "agent_cached_input_tokens": _component(
            usage, "cached_input_tokens", source, absent_note=absent
        ),
        "agent_output_tokens": _component(usage, "output_tokens", source, absent_note=absent),
        "agent_reasoning_output_tokens": _component(
            usage, "reasoning_output_tokens", source, absent_note=absent
        ),
        "agent_cache_write_input_tokens": _component(
            usage, "cache_write_input_tokens", source, absent_note=absent
        ),
    }

    total_note = (
        "Codex exec JSON usage has no total_tokens field. "
        "input_tokens and output_tokens are not summed, and cached input is "
        "not added on top of input."
    )
    total = MetricFigure.unavailable(SOURCE_NOT_REPORTED, total_note)
    if usage is not None and "total_tokens" in usage and usage["total_tokens"] >= 0:
        total = MetricFigure.exact(
            usage["total_tokens"],
            f"{source}.total_tokens",
            "Provider-reported total_tokens. Not computed by the harness.",
        )
    elif (
        rollout_usage is not None
        and "total_tokens" in rollout_usage
        and not disagreement
        and (exec_obs.usage is None or source == SOURCE_EXEC_USAGE)
    ):
        # Components agree (or exec usage was absent and rollout is the source).
        # When exec usage exists, require the shared components to match before
        # accepting the rollout total that sits on the same object.
        components_ok = True
        if exec_obs.usage is not None:
            for key in ("input_tokens", "output_tokens", "cached_input_tokens"):
                if (
                    key in exec_obs.usage
                    and key in rollout_usage
                    and exec_obs.usage[key] != rollout_usage[key]
                ):
                    components_ok = False
        if components_ok and rollout_usage["total_tokens"] >= 0:
            total = MetricFigure.exact(
                rollout_usage["total_tokens"],
                f"{SOURCE_ROLLOUT_TOTAL}.total_tokens",
                "Provider-reported total_tokens from the session rollout. "
                "Not computed by the harness.",
            )
    figures["agent_total_tokens"] = total

    supplemental: Dict[str, Any] = {}
    if rollout_usage is not None:
        supplemental["rollout_total_token_usage"] = rollout_usage
        supplemental["rollout_total_token_usage_source"] = SOURCE_ROLLOUT_TOTAL
    if rollout and rollout.last_usage is not None:
        supplemental["rollout_last_token_usage"] = rollout.last_usage
        supplemental["rollout_last_token_usage_note"] = (
            "last_token_usage is the most recent model request, not the "
            "session total. It is not copied into agent_* token fields."
        )
    return figures, disagreement, supplemental


def overhaust_figures(
    hook: HookObservation,
    *,
    condition: str,
) -> Dict[str, MetricFigure]:
    if condition != "overhaust":
        note = "Baseline does not run the OverHaust hook. Not stored as zero."
        return {
            "overhaust_context_tokens": MetricFigure.unavailable(SOURCE_NOT_REPORTED, note),
            "overhaust_context_bytes": MetricFigure.unavailable(SOURCE_NOT_REPORTED, note),
            "overhaust_retrieval_latency_ms": MetricFigure.unavailable(
                SOURCE_NOT_REPORTED, note
            ),
            "overhaust_hook_latency_ms": MetricFigure.unavailable(SOURCE_NOT_REPORTED, note),
        }

    report = hook.last or {}
    tokens = _int_or_none(report.get("estimated_context_tokens")) if hook.fired else None
    context_bytes = _int_or_none(report.get("context_bytes")) if hook.fired else None
    latency = _int_or_none(report.get("latency_ms")) if hook.fired else None

    if tokens is None:
        token_figure = MetricFigure.unavailable(
            SOURCE_NOT_REPORTED,
            "Hook debug did not report estimated_context_tokens.",
        )
    else:
        token_figure = MetricFigure.estimated(
            tokens,
            SOURCE_HOOK_TOKENS,
            "TokenEstimator count from the OverHaust hook debug record. "
            "Not a provider token count and not subtracted from agent tokens.",
        )

    if context_bytes is None:
        bytes_figure = MetricFigure.unavailable(
            SOURCE_NOT_REPORTED,
            "Hook debug did not report context_bytes.",
        )
    else:
        bytes_figure = MetricFigure.exact(context_bytes, SOURCE_HOOK_BYTES)

    if latency is None:
        hook_latency = MetricFigure.unavailable(
            SOURCE_NOT_REPORTED,
            "Hook debug did not report latency_ms.",
        )
    else:
        hook_latency = MetricFigure.exact(latency, SOURCE_HOOK_LATENCY, HOOK_LATENCY_NOTE)

    return {
        "overhaust_context_tokens": token_figure,
        "overhaust_context_bytes": bytes_figure,
        "overhaust_retrieval_latency_ms": MetricFigure.unavailable(
            SOURCE_RETRIEVAL, RETRIEVAL_LATENCY_NOTE
        ),
        "overhaust_hook_latency_ms": hook_latency,
    }


def tool_and_file_figures(exec_obs: ExecObservation) -> Dict[str, MetricFigure]:
    if not exec_obs.events:
        return {
            "tool_calls": MetricFigure.unavailable(
                SOURCE_NOT_REPORTED, "No exec JSONL events were captured."
            ),
            "files_inspected": MetricFigure.unavailable(
                SOURCE_FILES_INSPECTED, FILES_INSPECTED_NOTE
            ),
            "files_changed_via_codex_patch": MetricFigure.unavailable(
                SOURCE_NOT_REPORTED, "No exec JSONL events were captured."
            ),
        }
    tool_count = sum(exec_obs.tool_call_types.values())
    return {
        "tool_calls": MetricFigure.exact(
            tool_count,
            SOURCE_TOOLS,
            "Count of completed command_execution, mcp_tool_call, "
            "collab_tool_call, and web_search items. Reasoning, todo, and "
            "agent_message items are not tool calls.",
        ),
        "files_inspected": MetricFigure.unavailable(
            SOURCE_FILES_INSPECTED, FILES_INSPECTED_NOTE
        ),
        "files_changed_via_codex_patch": MetricFigure.exact(
            len(exec_obs.patch_paths),
            SOURCE_PATCH,
            "Count of paths on completed file_change items. Shell redirects "
            "are not included; files_changed is the workspace snapshot diff.",
        ),
    }


def iter_rollout_files(codex_home: Any) -> Iterable[Any]:
    """Newest-last session rollout JSONL files under an isolated CODEX_HOME."""
    root = codex_home / "sessions"
    if not root.is_dir():
        return []
    files = [path for path in root.rglob("*.jsonl") if path.is_file()]
    return sorted(files, key=lambda path: (path.stat().st_mtime, str(path)))
