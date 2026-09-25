"""
Provider-neutral agent trace schema (Layers 2–4).

Provider-specific payloads may appear under `provider_raw` only.
Required fields stay provider-agnostic so OpenAI/Codex, Anthropic/Claude,
Gemini, etc. can all be represented.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from benchmarks.schemas import Condition, MeasurementSource, TokenKind


VALID_LAYERS = frozenset({1, 2, 3, 4})
VALID_TOOL_TYPES = frozenset({
    "search",
    "grep",
    "read_file",
    "list_dir",
    "glob",
    "other",
})


@dataclass
class TraceMessage:
    role: str  # system | user | assistant | tool
    content: str
    name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TraceToolCall:
    id: str
    tool_type: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    result_preview: str = ""
    result_bytes: int = 0
    duration_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentTrace:
    """
    Normalized record of one agent execution for one task/condition.

    Token fields carry explicit kinds. exact_* are only filled from provider
    telemetry. estimated_* may come from TokenCounter. Never promote estimate→exact.
    """

    run_id: str
    layer: int
    provider: str
    model: Optional[str]
    condition: str
    repository: str
    repository_size: str
    task_id: str
    prompt: str

    messages: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)

    # Exact (provider-reported) — null unless known
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cached_input_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    input_tokens_kind: str = TokenKind.UNAVAILABLE.value
    output_tokens_kind: str = TokenKind.UNAVAILABLE.value
    cached_input_tokens_kind: str = TokenKind.UNAVAILABLE.value
    total_tokens_kind: str = TokenKind.UNAVAILABLE.value

    # Estimated (tokenizer) — always labelled
    estimated_input_tokens: Optional[int] = None
    estimated_output_tokens: Optional[int] = None
    estimated_total_tokens: Optional[int] = None
    estimated_tokens_note: str = ""

    # Tool / exploration counts
    tool_call_count: Optional[int] = None
    tool_call_types: Dict[str, int] = field(default_factory=dict)
    files_opened: List[str] = field(default_factory=list)
    files_read_count: Optional[int] = None
    searches_performed: Optional[int] = None

    # Context accounting
    overhaust_context_tokens: Optional[int] = None
    overhaust_context_tokens_kind: str = TokenKind.UNAVAILABLE.value
    baseline_context_tokens: Optional[int] = None
    baseline_context_tokens_kind: str = TokenKind.UNAVAILABLE.value

    duration_ms: Optional[int] = None
    final_answer: Optional[str] = None
    correctness: Optional[bool] = None
    evidence_score: Optional[float] = None
    correctness_detail: Optional[Dict[str, Any]] = None

    measurement_source: str = MeasurementSource.AUTOMATED.value
    error: Optional[str] = None
    provider_raw: Optional[Dict[str, Any]] = None
    config: Dict[str, Any] = field(default_factory=dict)
    reproducibility: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentTrace":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        if filtered.get("condition") not in {
            Condition.BASELINE.value, Condition.OVERHAUST.value
        }:
            raise ValueError(f"invalid condition: {filtered.get('condition')}")
        if filtered.get("layer") not in VALID_LAYERS:
            raise ValueError(f"invalid layer: {filtered.get('layer')}")
        return cls(**filtered)

    def validate_token_kinds(self) -> None:
        """Refuse silent mixing of exact and estimated in comparative fields."""
        exact_vals = [
            (self.input_tokens, self.input_tokens_kind),
            (self.output_tokens, self.output_tokens_kind),
            (self.total_tokens, self.total_tokens_kind),
        ]
        for value, kind in exact_vals:
            if value is not None and kind == TokenKind.ESTIMATED.value:
                raise ValueError(
                    "Field labelled estimated_token_count must not be stored in "
                    "exact provider fields; use estimated_* fields instead."
                )


def summarize_tool_activity(tool_calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    types: Dict[str, int] = {}
    files: List[str] = []
    searches = 0
    for call in tool_calls:
        t = call.get("tool_type") or "other"
        types[t] = types.get(t, 0) + 1
        if t in {"search", "grep", "glob"}:
            searches += 1
        if t == "read_file":
            path = (call.get("arguments") or {}).get("path")
            if path and path not in files:
                files.append(path)
    return {
        "tool_call_count": len(tool_calls),
        "tool_call_types": types,
        "files_opened": files,
        "files_read_count": len(files),
        "searches_performed": searches,
    }
