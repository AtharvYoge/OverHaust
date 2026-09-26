"""
Map Cursor headless `cursor-agent -p --output-format stream-json` onto Layer 4 figures.

Checked against cursor-agent 2026.09.26-dd393fe (Cursor 3.21.16):

- `result.usage.inputTokens`, `outputTokens`, `cacheReadTokens`, and
  `cacheWriteTokens` are exact when present.
- `cacheReadTokens` is a separate bucket. It is not included in `inputTokens`
  and is not subtracted from it. That is unlike Codex, where cached input is
  a subset of input. Cursor numbers must not be compared to Codex numbers.
- Reasoning tokens are not reported (thinking events carry text only).
- There is no provider total. A sum of exact components is DERIVED and is
  never stored as `agent_total_tokens`.
- A missing usage field stays unavailable. It is not stored as zero.
- Tool calls are `tool_call` events. The kind is the `*ToolCall` key.
  Completed events are counted once; a matching started event is not a
  second call. File paths come only from `readToolCall` args.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from benchmarks.layer4.schema import MetricFigure


SOURCE_USAGE = "cursor_stream_json.result.usage"
SOURCE_NOT_REPORTED = "not_reported"
SOURCE_TOOLS = "cursor_stream_json.tool_call"
SOURCE_READS = "cursor_stream_json.tool_call.readToolCall"
SOURCE_HOOK_TOKENS = "overhaust_hook_debug.estimated_context_tokens"
SOURCE_HOOK_BYTES = "overhaust_hook_debug.context_bytes"
SOURCE_HOOK_LATENCY = "overhaust_hook_debug.latency_ms"

# Names registered by services/mcp_server/server.py. A session that can call
# any of these had the OverHaust MCP available. The treatment is the hook.
OVERHAUST_MCP_TOOL_NAMES = frozenset({
    "create_project",
    "remember",
    "search_memory",
    "search_project_knowledge",
    "build_context",
    "get_project_context",
    "get_relevant_context",
    "trace_code_flow",
    "update_memory",
    "estimate_context",
})

USAGE_FIELDS = (
    ("inputTokens", "agent_input_tokens"),
    ("cacheReadTokens", "agent_cached_input_tokens"),
    ("cacheWriteTokens", "agent_cache_write_input_tokens"),
    ("outputTokens", "agent_output_tokens"),
)

CURSOR_TOKEN_ACCOUNTING = (
    "Cursor stream-json result.usage reports inputTokens, outputTokens, "
    "cacheReadTokens, and cacheWriteTokens as separate fields when the CLI "
    "emits them. cacheReadTokens is not included in inputTokens and is never "
    "subtracted from it. Reasoning tokens are not reported. result.usage has "
    "no total. agent_total_tokens stays unavailable. A sum of the exact "
    "components is stored only as supplemental derived_usage_component_sum "
    "with kind DERIVED and is not a provider total. Missing fields stay null. "
    "OverHaust context tokens are a separate estimated field and are never "
    "subtracted from these figures. Do not compare these numbers to Codex."
)

RETRIEVAL_LATENCY_NOTE = (
    "The sessionStart hook records end-to-end hook wall time. It does not "
    "emit a separate retrieval latency. overhaust_retrieval_latency_ms stays "
    "unavailable rather than substituting hook wall time."
)

HOOK_LATENCY_NOTE = (
    "Exact reading of the sessionStart hook debug latency_ms. This is "
    "end-to-end hook wall time, including the production context seam, not "
    "isolated retrieval latency."
)

# What a live run can record. Dry-run prints this catalog and launches nothing.
TELEMETRY_CATALOG: Tuple[Dict[str, str], ...] = (
    {
        "field": "agent_input_tokens",
        "label": "EXACT|UNAVAILABLE",
        "detail": "EXACT from result.usage.inputTokens when present; otherwise UNAVAILABLE. Never filled with zero.",
    },
    {
        "field": "agent_cached_input_tokens",
        "label": "EXACT|UNAVAILABLE",
        "detail": (
            "EXACT from result.usage.cacheReadTokens when present. This bucket "
            "is not included in inputTokens. Otherwise UNAVAILABLE. Never zero-filled."
        ),
    },
    {
        "field": "agent_cache_write_input_tokens",
        "label": "EXACT|UNAVAILABLE",
        "detail": "EXACT from result.usage.cacheWriteTokens when present; otherwise UNAVAILABLE.",
    },
    {
        "field": "agent_output_tokens",
        "label": "EXACT|UNAVAILABLE",
        "detail": "EXACT from result.usage.outputTokens when present; otherwise UNAVAILABLE.",
    },
    {
        "field": "agent_reasoning_output_tokens",
        "label": "UNAVAILABLE",
        "detail": "UNAVAILABLE. Thinking events carry text only. No reasoning-token count is reported.",
    },
    {
        "field": "agent_total_tokens",
        "label": "UNAVAILABLE",
        "detail": "UNAVAILABLE. Cursor does not report a provider total. Not replaced with a sum.",
    },
    {
        "field": "derived_usage_component_sum",
        "label": "DERIVED",
        "detail": (
            "DERIVED sum of the exact components that were present "
            "(inputTokens + outputTokens + cacheReadTokens + cacheWriteTokens). "
            "Not a provider total. Incomplete when any component is unavailable."
        ),
    },
    {
        "field": "tool_calls",
        "label": "EXACT|UNAVAILABLE",
        "detail": "EXACT count of completed tool_call events, keyed by the *ToolCall name. UNAVAILABLE if the stream was not parsed.",
    },
    {
        "field": "files_inspected",
        "label": "EXACT|UNAVAILABLE",
        "detail": "EXACT unique paths from readToolCall args. UNAVAILABLE if tool events were not parsed. Never inferred from the prompt.",
    },
    {
        "field": "files_changed",
        "label": "EXACT|UNAVAILABLE",
        "detail": "EXACT workspace diff against the pre-agent snapshot. UNAVAILABLE if the snapshot was not measured.",
    },
    {
        "field": "files_changed_via_codex_patch",
        "label": "UNAVAILABLE",
        "detail": "UNAVAILABLE. Cursor does not emit Codex file_change patches.",
    },
    {
        "field": "elapsed_ms",
        "label": "EXACT|UNAVAILABLE",
        "detail": "EXACT harness wall clock around the subprocess.",
    },
    {
        "field": "duration_ms",
        "label": "EXACT|UNAVAILABLE",
        "detail": "EXACT from result.duration_ms when present; otherwise UNAVAILABLE. duration_api_ms is recorded the same way.",
    },
    {
        "field": "overhaust_context_tokens",
        "label": "ESTIMATED|UNAVAILABLE",
        "detail": "ESTIMATED via TokenEstimator on the hook debug record. Not a provider count and not subtracted.",
    },
    {
        "field": "overhaust_context_bytes",
        "label": "EXACT|UNAVAILABLE",
        "detail": "EXACT from hook debug context_bytes.",
    },
    {
        "field": "overhaust_hook_latency_ms",
        "label": "EXACT|UNAVAILABLE",
        "detail": "EXACT hook wall time from hook debug latency_ms.",
    },
    {
        "field": "overhaust_retrieval_latency_ms",
        "label": "UNAVAILABLE",
        "detail": "UNAVAILABLE. Hook wall time is not labeled as retrieval latency.",
    },
    {
        "field": "cost",
        "label": "UNAVAILABLE",
        "detail": "UNAVAILABLE. stream-json does not report cost or plan usage.",
    },
)


@dataclass
class CursorStreamObservation:
    events: List[Dict[str, Any]] = field(default_factory=list)
    parsed: bool = False
    non_json_lines: int = 0
    parse_errors: List[str] = field(default_factory=list)
    session_id: Optional[str] = None
    model_display_name: Optional[str] = None
    permission_mode: Optional[str] = None
    api_key_source: Optional[str] = None
    cwd: Optional[str] = None
    result_text: Optional[str] = None
    result_subtype: Optional[str] = None
    is_error: Optional[bool] = None
    request_id: Optional[str] = None
    duration_ms: Optional[int] = None
    duration_api_ms: Optional[int] = None
    usage: Optional[Dict[str, int]] = None
    usage_present: bool = False
    tool_call_types: Dict[str, int] = field(default_factory=dict)
    tool_invocations: List[Dict[str, Any]] = field(default_factory=list)
    read_paths: List[str] = field(default_factory=list)
    overhaust_mcp_calls: List[str] = field(default_factory=list)
    thinking_events: int = 0
    assistant_texts: List[str] = field(default_factory=list)


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


def _tool_kind(tool_call: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    for key, value in tool_call.items():
        if key.endswith("ToolCall") and isinstance(value, dict):
            return key, value
    return "unknown", {}


def _shrink_arg(value: Any) -> Any:
    if isinstance(value, str) and len(value) > 500:
        return {
            "_truncated": True,
            "length": len(value),
            "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
        }
    if isinstance(value, dict):
        return {str(key): _shrink_arg(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_shrink_arg(item) for item in value[:50]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _read_paths(args: Dict[str, Any]) -> List[str]:
    paths: List[str] = []
    for key in ("path", "filePath", "file_path", "target_file"):
        raw = args.get(key)
        if isinstance(raw, str) and raw.strip():
            paths.append(raw.strip())
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    paths.append(item.strip())
    return paths


def _mcp_identity(kind: str, args: Dict[str, Any]) -> Optional[str]:
    server = ""
    for key in ("server", "serverName", "providerIdentifier"):
        raw = args.get(key)
        if isinstance(raw, str) and raw.strip():
            server = raw.strip()
            break
    tool_name = ""
    for key in ("toolName", "tool", "name", "mcpToolName"):
        raw = args.get(key)
        if isinstance(raw, str) and raw.strip():
            tool_name = raw.strip()
            break
    overhaust_server = server.lower() == "overhaust"
    overhaust_tool = tool_name in OVERHAUST_MCP_TOOL_NAMES
    if kind == "mcpToolCall" and (overhaust_server or overhaust_tool):
        return tool_name or server or "overhaust"
    if overhaust_server or overhaust_tool:
        return tool_name or server or "overhaust"
    return None


def parse_stream_json(text: str) -> CursorStreamObservation:
    events, non_json, errors = parse_jsonl(text)
    obs = CursorStreamObservation(
        events=events,
        parsed=bool(events),
        non_json_lines=non_json,
        parse_errors=errors,
    )
    # Empty output is not evidence of zero tool calls. A real session with
    # zero tools still has a result event, which counts as parsed.
    seen_completed: set[str] = set()
    started_only: Dict[str, Dict[str, Any]] = {}

    for event in events:
        kind = str(event.get("type") or "")
        subtype = str(event.get("subtype") or "")
        session_id = event.get("session_id")
        if isinstance(session_id, str) and session_id:
            obs.session_id = session_id
        if kind == "system" and subtype == "init":
            model = event.get("model")
            if isinstance(model, str) and model.strip():
                obs.model_display_name = model.strip()
            permission = event.get("permissionMode")
            if isinstance(permission, str):
                obs.permission_mode = permission
            api_source = event.get("apiKeySource")
            if isinstance(api_source, str):
                obs.api_key_source = api_source
            cwd = event.get("cwd")
            if isinstance(cwd, str):
                obs.cwd = cwd
        elif kind == "thinking":
            obs.thinking_events += 1
        elif kind == "assistant":
            text_value = _message_text(event.get("message"))
            if text_value:
                obs.assistant_texts.append(text_value)
        elif kind == "tool_call":
            tool_call = event.get("tool_call")
            if not isinstance(tool_call, dict):
                continue
            tool_kind, body = _tool_kind(tool_call)
            args = body.get("args") if isinstance(body.get("args"), dict) else {}
            call_id = str(event.get("call_id") or tool_call.get("toolCallId") or "")
            record = {
                "kind": tool_kind,
                "subtype": subtype or "completed",
                "call_id": call_id,
                "args": _shrink_arg(args),
            }
            if subtype == "started":
                if call_id:
                    started_only[call_id] = record
                else:
                    _record_tool(obs, record)
                continue
            if call_id:
                seen_completed.add(call_id)
                started_only.pop(call_id, None)
            _record_tool(obs, record)
        elif kind == "result":
            obs.result_subtype = subtype or None
            if "is_error" in event:
                obs.is_error = bool(event.get("is_error"))
            result = event.get("result")
            if isinstance(result, str):
                obs.result_text = result
            request_id = event.get("request_id")
            if isinstance(request_id, str):
                obs.request_id = request_id
            obs.duration_ms = _int_or_none(event.get("duration_ms"))
            obs.duration_api_ms = _int_or_none(event.get("duration_api_ms"))
            usage = event.get("usage")
            if isinstance(usage, dict):
                obs.usage_present = True
                found: Dict[str, int] = {}
                for key, _field in USAGE_FIELDS:
                    if key not in usage:
                        continue
                    number = _int_or_none(usage.get(key))
                    if number is None or number < 0:
                        continue
                    found[key] = number
                obs.usage = found

    for record in started_only.values():
        _record_tool(obs, record)
    return obs


def _record_tool(obs: CursorStreamObservation, record: Dict[str, Any]) -> None:
    kind = str(record["kind"])
    obs.tool_call_types[kind] = obs.tool_call_types.get(kind, 0) + 1
    obs.tool_invocations.append(record)
    args = record.get("args") if isinstance(record.get("args"), dict) else {}
    if kind == "readToolCall":
        for path in _read_paths(args):
            if path not in obs.read_paths:
                obs.read_paths.append(path)
    identity = _mcp_identity(kind, args)
    if identity and identity not in obs.overhaust_mcp_calls:
        obs.overhaust_mcp_calls.append(identity)


def _message_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return ""


def _usage_figure(usage: Optional[Dict[str, int]], key: str, *, usage_present: bool) -> MetricFigure:
    if not usage_present or usage is None or key not in usage:
        note = (
            "Cursor result.usage did not include this field. Not stored as zero."
            if usage_present
            else "No Cursor result.usage object. Not stored as zero."
        )
        return MetricFigure.unavailable(SOURCE_NOT_REPORTED, note)
    return MetricFigure.exact(usage[key], f"{SOURCE_USAGE}.{key}")


def agent_token_figures(obs: CursorStreamObservation) -> Tuple[Dict[str, MetricFigure], Dict[str, Any]]:
    usage = obs.usage if obs.usage_present else None
    figures = {
        field_name: _usage_figure(usage, key, usage_present=obs.usage_present)
        for key, field_name in USAGE_FIELDS
    }
    figures["agent_reasoning_output_tokens"] = MetricFigure.unavailable(
        SOURCE_NOT_REPORTED,
        "Cursor stream-json has thinking text only. No reasoning-token count "
        f"is reported ({obs.thinking_events} thinking event(s) were ignored "
        "as a token count).",
    )
    figures["agent_total_tokens"] = MetricFigure.unavailable(
        SOURCE_NOT_REPORTED,
        "Cursor result.usage has no provider total. See supplemental "
        "derived_usage_component_sum, which is DERIVED and is not a provider total.",
    )
    components: Dict[str, Optional[int]] = {}
    present: List[int] = []
    missing: List[str] = []
    for key, field_name in USAGE_FIELDS:
        figure = figures[field_name]
        if figure.is_exact and figure.value is not None:
            components[key] = int(figure.value)
            present.append(int(figure.value))
        else:
            components[key] = None
            missing.append(key)
    complete = bool(present) and not missing
    derived = {
        "kind": "DERIVED",
        "value": sum(present) if complete else None,
        "components": components,
        "included": [key for key, value in components.items() if value is not None],
        "missing": missing,
        "complete": complete,
        "note": (
            "Sum of exact Cursor usage components. cacheReadTokens is added "
            "because it is a separate bucket, not because it is inside inputTokens. "
            "This is not a provider total and must not be compared to Codex totals."
        ),
    }
    if present and missing:
        derived["partial_sum"] = sum(present)
        derived["note"] += (
            " Incomplete because at least one component is unavailable; value is null."
        )
    return figures, derived


def tool_and_file_figures(obs: CursorStreamObservation) -> Dict[str, MetricFigure]:
    if not obs.parsed:
        unavailable = MetricFigure.unavailable(
            SOURCE_NOT_REPORTED,
            "Cursor stream-json was not parsed, so tool calls and read paths "
            "are unavailable. Not stored as zero.",
        )
        return {
            "tool_calls": unavailable,
            "files_inspected": MetricFigure.unavailable(
                SOURCE_READS,
                "Read paths are unavailable because tool events were not parsed. "
                "Not inferred from the prompt.",
            ),
        }
    return {
        "tool_calls": MetricFigure.exact(
            len(obs.tool_invocations),
            SOURCE_TOOLS,
            "Completed tool_call events. A started event with a later completed "
            "event for the same call_id is counted once.",
        ),
        "files_inspected": MetricFigure.exact(
            len(obs.read_paths),
            SOURCE_READS,
            "Unique paths from readToolCall args. Other tool kinds are not treated as file reads.",
        ),
    }


def hook_figures(report: Optional[Dict[str, Any]], *, condition: str) -> Dict[str, MetricFigure]:
    if condition != "overhaust":
        note = "Baseline does not run the OverHaust sessionStart hook. Not stored as zero."
        return {
            "overhaust_context_tokens": MetricFigure.unavailable(SOURCE_NOT_REPORTED, note),
            "overhaust_context_bytes": MetricFigure.unavailable(SOURCE_NOT_REPORTED, note),
            "overhaust_retrieval_latency_ms": MetricFigure.unavailable(SOURCE_NOT_REPORTED, note),
            "overhaust_hook_latency_ms": MetricFigure.unavailable(SOURCE_NOT_REPORTED, note),
        }
    data = report or {}
    tokens = _int_or_none(data.get("estimated_context_tokens")) if data else None
    token_kind = str(data.get("estimated_context_tokens_kind") or "")
    context_bytes = _int_or_none(data.get("context_bytes")) if data else None
    bytes_kind = str(data.get("context_bytes_kind") or "")
    latency = _int_or_none(data.get("latency_ms")) if data else None

    if tokens is None or token_kind == "unavailable":
        token_figure = MetricFigure.unavailable(
            SOURCE_NOT_REPORTED,
            "Hook debug did not report an estimated context token count.",
        )
    else:
        token_figure = MetricFigure.estimated(
            tokens,
            SOURCE_HOOK_TOKENS,
            "TokenEstimator count from the sessionStart hook debug record. "
            "Kind ESTIMATED. Not subtracted from provider tokens.",
        )
    if context_bytes is None or bytes_kind == "unavailable":
        bytes_figure = MetricFigure.unavailable(
            SOURCE_NOT_REPORTED,
            "Hook debug did not report context_bytes.",
        )
    else:
        bytes_figure = MetricFigure.exact(
            context_bytes,
            SOURCE_HOOK_BYTES,
            "Exact UTF-8 byte length of the injected context, from hook debug.",
        )
    if latency is None:
        latency_figure = MetricFigure.unavailable(
            SOURCE_NOT_REPORTED,
            "Hook debug did not report latency_ms.",
        )
    else:
        latency_figure = MetricFigure.exact(latency, SOURCE_HOOK_LATENCY, HOOK_LATENCY_NOTE)
    return {
        "overhaust_context_tokens": token_figure,
        "overhaust_context_bytes": bytes_figure,
        "overhaust_retrieval_latency_ms": MetricFigure.unavailable(
            SOURCE_NOT_REPORTED,
            RETRIEVAL_LATENCY_NOTE,
        ),
        "overhaust_hook_latency_ms": latency_figure,
    }


def parse_hook_debug(text: str) -> List[Dict[str, Any]]:
    events, _, _ = parse_jsonl(text)
    return events
