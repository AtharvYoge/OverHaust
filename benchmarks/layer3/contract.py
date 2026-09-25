"""
Layer-3 ExperimentContract — every run records known / unknown / unavailable fields.

UNKNOWN must never be silently converted into a default equality value.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from benchmarks import BENCHMARK_VERSION
from benchmarks.layer3.prompts import LAYER3_SYSTEM_PROMPT, system_prompt_hash, user_prompt_hash
from benchmarks.layer3.states import RunState
from benchmarks.layer3.tools import tool_set_hash
from benchmarks.schemas import Condition


class FieldPresence(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


def _presence(value: Any, *, unavailable: bool = False) -> FieldPresence:
    if unavailable:
        return FieldPresence.UNAVAILABLE
    if value is None or value == "" or value == "UNKNOWN":
        return FieldPresence.UNKNOWN
    return FieldPresence.KNOWN


@dataclass
class ExperimentContract:
    """Strict metadata attached to every Layer-3 run."""

    experiment_id: str
    pair_id: str
    condition: str

    provider: str
    model: str
    model_version: Optional[str] = None

    repository: str = ""
    repository_commit: Optional[str] = None

    task_id: str = ""
    user_prompt: str = ""
    user_prompt_hash: str = ""

    system_prompt: str = LAYER3_SYSTEM_PROMPT
    system_prompt_hash: str = ""

    tool_set_hash: str = ""

    temperature: Optional[float] = None
    temperature_status: str = FieldPresence.UNKNOWN.value
    seed: Optional[int] = None
    seed_status: str = FieldPresence.UNKNOWN.value  # KNOWN | UNKNOWN | UNAVAILABLE | UNSUPPORTED

    max_tool_calls: int = 12
    timeout_s: int = 120
    max_output_tokens: Optional[int] = None

    execution_order: str = "UNKNOWN"  # baseline_first | overhaust_first | UNKNOWN
    session_id: str = ""

    attempt_count: int = 1
    retry_count: int = 0
    failure_status: str = RunState.SUCCESS.value

    overhaust_context_hash: Optional[str] = None
    overhaust_context_tokens: Optional[int] = None
    overhaust_context_included_in_input: str = FieldPresence.UNKNOWN.value
    # true | false only when proven; else UNKNOWN

    provider_input_tokens: Optional[int] = None
    serialized_input_tokens: Optional[int] = None

    token_accounting: Dict[str, Any] = field(default_factory=dict)
    benchmark_version: str = BENCHMARK_VERSION
    protocol_version: str = "layer3-contract-v1"

    field_presence: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.system_prompt_hash:
            self.system_prompt_hash = system_prompt_hash(self.system_prompt)
        if self.user_prompt and not self.user_prompt_hash:
            self.user_prompt_hash = user_prompt_hash(self.user_prompt)
        if not self.tool_set_hash:
            self.tool_set_hash = tool_set_hash()
        self.refresh_presence()

    def refresh_presence(self) -> None:
        self.field_presence = {
            "provider": _presence(self.provider).value,
            "model": _presence(self.model).value,
            "model_version": _presence(self.model_version).value,
            "repository": _presence(self.repository).value,
            "repository_commit": _presence(self.repository_commit).value,
            "task_id": _presence(self.task_id).value,
            "user_prompt_hash": _presence(self.user_prompt_hash).value,
            "system_prompt_hash": _presence(self.system_prompt_hash).value,
            "tool_set_hash": _presence(self.tool_set_hash).value,
            "temperature": self.temperature_status,
            "seed": self.seed_status,
            "max_tool_calls": _presence(self.max_tool_calls).value,
            "timeout_s": _presence(self.timeout_s).value,
            "execution_order": _presence(
                None if self.execution_order == "UNKNOWN" else self.execution_order
            ).value,
            "session_id": _presence(self.session_id).value,
            "overhaust_context_included_in_input": self.overhaust_context_included_in_input,
            "benchmark_version": _presence(self.benchmark_version).value,
            "protocol_version": _presence(self.protocol_version).value,
        }

    def to_dict(self) -> Dict[str, Any]:
        self.refresh_presence()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperimentContract":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        if filtered.get("condition") not in {
            Condition.BASELINE.value, Condition.OVERHAUST.value
        }:
            raise ValueError(f"invalid condition: {filtered.get('condition')}")
        return cls(**filtered)

    def is_overhaust(self) -> bool:
        return self.condition == Condition.OVERHAUST.value
