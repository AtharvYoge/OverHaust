"""
Layer 3 — real model / API protocol (provider-neutral).

This module defines the adapter interface and ingestion of EXACT provider
usage. It does NOT call a live API unless a concrete adapter is configured
and credentials are present.

Layer 3 results must never be fabricated. Without a provider, use --ingest.
"""

from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence

from benchmarks.evaluate import evaluate_answer
from benchmarks.repro import collect_reproducibility
from benchmarks.schemas import BenchmarkTask, Condition, MeasurementSource, TokenKind
from benchmarks.tokens import TokenCounter
from benchmarks.trace import AgentTrace, summarize_tool_activity


class ProviderNotConfiguredError(RuntimeError):
    """Raised when Layer 3 is requested but no live provider is available."""


class ModelProvider(ABC):
    """Provider-neutral agent runner with repository tools."""

    name: str = "abstract"

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def run_task(
        self,
        task: BenchmarkTask,
        *,
        condition: str,
        repository_root: str,
        overhaust_context: Optional[str],
        model: str,
        temperature: float,
        max_tool_calls: int,
        timeout_s: int,
    ) -> AgentTrace:
        ...


class NullProvider(ModelProvider):
    """Default: refuses to invent Layer 3 results."""

    name = "null"

    def is_available(self) -> bool:
        return False

    def run_task(self, *args, **kwargs) -> AgentTrace:
        raise ProviderNotConfiguredError(
            "No real-model provider configured. "
            "Use --ingest with provider traces, or implement a ModelProvider."
        )


def apply_exact_usage(
    trace: AgentTrace,
    *,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    cached_input_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
) -> AgentTrace:
    """Stamp EXACT provider-reported token fields (only path for exact counts)."""
    if input_tokens is not None:
        trace.input_tokens = int(input_tokens)
        trace.input_tokens_kind = TokenKind.EXACT.value
    if output_tokens is not None:
        trace.output_tokens = int(output_tokens)
        trace.output_tokens_kind = TokenKind.EXACT.value
    if cached_input_tokens is not None:
        trace.cached_input_tokens = int(cached_input_tokens)
        trace.cached_input_tokens_kind = TokenKind.EXACT.value
    if total_tokens is not None:
        trace.total_tokens = int(total_tokens)
        trace.total_tokens_kind = TokenKind.EXACT.value
    elif (
        trace.input_tokens is not None and trace.output_tokens is not None
        and trace.total_tokens is None
    ):
        # Do NOT invent total when cached semantics are ambiguous.
        # Prefer leaving total UNAVAILABLE over assuming input+output.
        # Callers should supply provider total_tokens when available.
        pass
    trace.measurement_source = MeasurementSource.MANUAL.value
    trace.validate_token_kinds()
    return trace


def ingest_layer3_trace(
    data: Dict[str, Any],
    *,
    task: Optional[BenchmarkTask] = None,
) -> AgentTrace:
    """
    Load an externally produced Layer 3/4 trace.

    Required: task_id, condition, prompt (or task), provider.
    Exact tokens only if explicitly present and kinds say exact / omitted kinds
    default to exact when values come from a MANUAL ingest payload marked as such.
    """
    if "layer" not in data:
        data = {**data, "layer": 3}
    if "run_id" not in data:
        data = {**data, "run_id": str(uuid.uuid4())}
    if "repository_size" not in data:
        data = {**data, "repository_size": "medium"}
    if "repository" not in data:
        data = {**data, "repository": "unknown"}
    if "measurement_source" not in data:
        data = {**data, "measurement_source": MeasurementSource.MANUAL.value}

    # Default missing kinds for provided numeric token fields to EXACT for MANUAL.
    for field, kind_field in (
        ("input_tokens", "input_tokens_kind"),
        ("output_tokens", "output_tokens_kind"),
        ("cached_input_tokens", "cached_input_tokens_kind"),
        ("total_tokens", "total_tokens_kind"),
    ):
        if data.get(field) is not None and kind_field not in data:
            data = {**data, kind_field: TokenKind.EXACT.value}

    trace = AgentTrace.from_dict(data)
    if task is not None and trace.final_answer:
        scored = evaluate_answer(task, trace.final_answer)
        trace.correctness = scored.correct
        trace.evidence_score = scored.evidence_score
        trace.correctness_detail = scored.to_dict()
    if not trace.reproducibility:
        trace.reproducibility = collect_reproducibility(
            model=trace.model, provider=trace.provider,
        )
    # Fill tool summary if only raw tool_calls present.
    if trace.tool_calls and trace.tool_call_count is None:
        activity = summarize_tool_activity(trace.tool_calls)
        trace.tool_call_count = activity["tool_call_count"]
        trace.tool_call_types = activity["tool_call_types"]
        trace.files_opened = activity["files_opened"]
        trace.files_read_count = activity["files_read_count"]
        trace.searches_performed = activity["searches_performed"]
    trace.validate_token_kinds()
    return trace


def load_traces(paths: Sequence[Path], *, tasks: Optional[Dict[str, BenchmarkTask]] = None) -> List[AgentTrace]:
    out: List[AgentTrace] = []
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        items = payload if isinstance(payload, list) else payload.get("traces", payload.get("runs", [payload]))
        for item in items:
            # Support both RunRecord-shaped and AgentTrace-shaped payloads.
            if "layer" not in item and "tool_calls" not in item and "condition" in item:
                # Legacy RunRecord → minimal AgentTrace wrapper.
                item = {
                    "run_id": str(uuid.uuid4()),
                    "layer": 3,
                    "provider": item.get("extras", {}).get("provider", "manual"),
                    "model": item.get("model"),
                    "condition": item["condition"],
                    "repository": item.get("repository") or "unknown",
                    "repository_size": item.get("repository_size") or "medium",
                    "task_id": item["task_id"],
                    "prompt": item.get("prompt") or "",
                    "input_tokens": item.get("input_tokens"),
                    "output_tokens": item.get("output_tokens"),
                    "total_tokens": item.get("total_tokens"),
                    "tool_call_count": item.get("tool_calls"),
                    "files_read_count": item.get("files_inspected"),
                    "duration_ms": item.get("latency_ms"),
                    "final_answer": item.get("answer_text"),
                    "measurement_source": item.get("measurement_source", "MANUAL"),
                }
            task = (tasks or {}).get(item.get("task_id"))
            out.append(ingest_layer3_trace(item, task=task))
    return out


def require_provider(provider: Optional[ModelProvider] = None) -> ModelProvider:
    p = provider or NullProvider()
    if not p.is_available():
        raise ProviderNotConfiguredError(
            f"Provider {p.name!r} is not available. "
            "Configure credentials or ingest external traces."
        )
    return p
