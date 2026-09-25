"""
Canonical Layer 4 session record.

Every future agent adapter (Cursor, Claude Code, Codex) writes this schema.
Token figures carry an explicit kind. Exact, estimated, and missing values
never share a field, and a missing value is never stored as zero.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class FigureKind(str, Enum):
    EXACT = "exact"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


class SessionOutcome(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    ERROR = "error"
    INVALID = "invalid"


# Agent provider-token fields. These must never be estimated, and OverHaust's
# own context tokens must never be written into them or subtracted from them.
AGENT_TOKEN_FIELDS = (
    "agent_input_tokens",
    "agent_cached_input_tokens",
    "agent_output_tokens",
    "agent_reasoning_output_tokens",
    "agent_cache_write_input_tokens",
    "agent_total_tokens",
)

OVERHAUST_CONTEXT_TOKEN_FIELD = "overhaust_context_tokens"

METRIC_FIELDS = AGENT_TOKEN_FIELDS + (
    OVERHAUST_CONTEXT_TOKEN_FIELD,
    "overhaust_context_bytes",
    "overhaust_retrieval_latency_ms",
    "overhaust_hook_latency_ms",
    "tool_calls",
    "files_inspected",
    "files_changed",
    "files_changed_via_codex_patch",
    "elapsed_ms",
)


def _as_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"metric value must be a number, got {value!r}")
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"metric value must be an integer count, got {value!r}")
        value = int(value)
    return int(value)


@dataclass
class MetricFigure:
    """One measured number plus the only provenance that number is allowed to have."""

    value: Optional[int]
    kind: str
    source: str
    note: str = ""

    def __post_init__(self) -> None:
        kind = FigureKind(self.kind)
        self.kind = kind.value
        if not self.source:
            raise ValueError("metric source is required")
        if kind is FigureKind.UNAVAILABLE:
            if self.value is not None:
                raise ValueError("unavailable metric must have a null value, not zero")
            return
        self.value = _as_int(self.value)
        if self.value < 0:
            raise ValueError("metric value must be >= 0")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "kind": self.kind,
            "source": self.source,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetricFigure":
        if not isinstance(data, dict):
            raise ValueError("metric figure must be an object")
        return cls(
            value=data.get("value"),
            kind=str(data.get("kind") or ""),
            source=str(data.get("source") or ""),
            note=str(data.get("note") or ""),
        )

    @classmethod
    def exact(cls, value: int, source: str, note: str = "") -> "MetricFigure":
        return cls(value, FigureKind.EXACT.value, source, note)

    @classmethod
    def estimated(cls, value: int, source: str, note: str = "") -> "MetricFigure":
        return cls(value, FigureKind.ESTIMATED.value, source, note)

    @classmethod
    def unavailable(cls, source: str, note: str = "") -> "MetricFigure":
        return cls(None, FigureKind.UNAVAILABLE.value, source, note)

    @property
    def is_exact(self) -> bool:
        return self.kind == FigureKind.EXACT.value

    @property
    def is_estimated(self) -> bool:
        return self.kind == FigureKind.ESTIMATED.value

    @property
    def is_unavailable(self) -> bool:
        return self.kind == FigureKind.UNAVAILABLE.value


@dataclass
class Layer4SessionResult:
    """One isolated agent session. Failed and incomplete sessions are retained."""

    schema_version: str
    session_id: str
    agent: str
    agent_version: Optional[str]
    agent_version_source: str
    model: Optional[str]
    model_requested: Optional[str]
    model_reported: Optional[str]
    model_source: str
    condition: str
    task_id: str
    rep: int
    seed: int
    pair_id: str
    order_in_pair: int
    condition_order: str
    execution_order: int
    snapshot_hash: str
    snapshot_hash_before: Optional[str]
    snapshot_hash_after: Optional[str]
    raw_telemetry_source: str
    raw_telemetry_paths: Dict[str, Optional[str]]

    agent_input_tokens: MetricFigure
    agent_cached_input_tokens: MetricFigure
    agent_output_tokens: MetricFigure
    agent_reasoning_output_tokens: MetricFigure
    agent_cache_write_input_tokens: MetricFigure
    agent_total_tokens: MetricFigure
    overhaust_context_tokens: MetricFigure
    overhaust_context_bytes: MetricFigure
    overhaust_retrieval_latency_ms: MetricFigure
    overhaust_hook_latency_ms: MetricFigure
    tool_calls: MetricFigure
    files_inspected: MetricFigure
    files_changed: MetricFigure
    files_changed_via_codex_patch: MetricFigure
    elapsed_ms: MetricFigure

    outcome: str
    valid: bool
    invalid_reasons: List[str] = field(default_factory=list)
    telemetry_gaps: List[str] = field(default_factory=list)
    primary_metric_status: str = "missing"
    token_accounting_note: str = ""
    error: Optional[str] = None
    answer_text: Optional[str] = None
    correctness: Optional[bool] = None
    evidence_score: Optional[float] = None
    correctness_detail: Optional[Dict[str, Any]] = None

    integration_path: str = "none"
    hook_command: Optional[str] = None
    hook_fired: Optional[bool] = None
    context_injected: Optional[bool] = None
    permissions: Dict[str, Any] = field(default_factory=dict)
    command: List[str] = field(default_factory=list)
    exit_code: Optional[int] = None
    timed_out: bool = False
    codex_thread_id: Optional[str] = None
    tool_call_types: Dict[str, int] = field(default_factory=dict)
    tool_invocations: List[Dict[str, Any]] = field(default_factory=list)
    files_changed_paths: List[str] = field(default_factory=list)
    supplemental_telemetry: Dict[str, Any] = field(default_factory=dict)
    telemetry_disagreement: List[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    prompt_sha256: str = ""
    agent_version_warning: Optional[str] = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if self.condition not in {"baseline", "overhaust"}:
            raise ValueError(f"invalid condition: {self.condition}")
        SessionOutcome(self.outcome)
        if self.primary_metric_status not in {"complete", "partial", "missing"}:
            raise ValueError(f"invalid primary_metric_status: {self.primary_metric_status}")
        if self.rep < 0:
            raise ValueError("rep must be >= 0")
        if self.execution_order < 0:
            raise ValueError("execution_order must be >= 0")
        if not self.pair_id:
            raise ValueError("pair_id is required")
        if self.order_in_pair not in (1, 2):
            raise ValueError("order_in_pair must be 1 or 2")
        if self.condition_order not in {"baseline->overhaust", "overhaust->baseline"}:
            raise ValueError(
                "condition_order must be 'baseline->overhaust' or "
                f"'overhaust->baseline', got {self.condition_order!r}"
            )

        for name in METRIC_FIELDS:
            figure = getattr(self, name)
            if not isinstance(figure, MetricFigure):
                raise ValueError(f"{name} must be a MetricFigure")
            if name in AGENT_TOKEN_FIELDS and figure.is_estimated:
                raise ValueError(
                    f"{name} is an agent provider-token field and cannot be estimated. "
                    "Leave it unavailable, or record an exact provider figure."
                )
            if name == OVERHAUST_CONTEXT_TOKEN_FIELD and figure.is_exact:
                source = figure.source.lower()
                if "provider" not in source and "exact" not in source:
                    raise ValueError(
                        "overhaust_context_tokens may be exact only when a provider "
                        "reports that count. Hook TokenEstimator output is estimated."
                    )

        if self.agent_total_tokens.is_exact:
            # A synthesized sum is not a provider total. Callers must label the
            # source with the event that actually reported total_tokens.
            source = self.agent_total_tokens.source
            if "total_tokens" not in source:
                raise ValueError(
                    "agent_total_tokens source must name the provider field that "
                    "reported total_tokens. Do not store input+output as a total."
                )

        gaps = [name for name in METRIC_FIELDS if getattr(self, name).is_unavailable]
        # telemetry_gaps is informational; keep it consistent when we built it.
        # Callers may pass an explicit list. Do not rewrite a caller-supplied
        # list that is a superset, but reject a list that hides an unavailable figure.
        missing_from_list = [name for name in gaps if name not in self.telemetry_gaps]
        if missing_from_list:
            raise ValueError(
                "telemetry_gaps must list every unavailable metric: "
                + ", ".join(missing_from_list)
            )

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        data = asdict(self)
        for name in METRIC_FIELDS:
            data[name] = getattr(self, name).to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Layer4SessionResult":
        if not isinstance(data, dict):
            raise ValueError("session result must be an object")
        payload = dict(data)
        for name in METRIC_FIELDS:
            payload[name] = MetricFigure.from_dict(payload[name])
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in payload.items() if k in known}
        return cls(**filtered)


def primary_metric_status_for(result_tokens: Dict[str, MetricFigure]) -> str:
    """
    Primary metric is the agent's reported input, cached input (when the
    provider reported it), and output. Cached being missing does not discard
    input and output. Nothing here sums those fields into a total.
    """
    input_ok = result_tokens["agent_input_tokens"].is_exact
    output_ok = result_tokens["agent_output_tokens"].is_exact
    cached = result_tokens["agent_cached_input_tokens"]
    if input_ok and output_ok and cached.is_exact:
        return "complete"
    if input_ok and output_ok:
        return "partial"
    return "missing"


def telemetry_gaps_for(figures: Dict[str, MetricFigure]) -> List[str]:
    return [name for name in METRIC_FIELDS if figures[name].is_unavailable]


def unavailable_metrics(note: str, source: str = "not_reported") -> Dict[str, MetricFigure]:
    """Every metric explicitly missing. Used when a session dies before telemetry."""
    return {name: MetricFigure.unavailable(source, note) for name in METRIC_FIELDS}
