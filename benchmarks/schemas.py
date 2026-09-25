"""
Machine-readable schemas for the context-efficiency benchmark.

Tasks and run records are plain dicts / dataclasses with validation —
no dependency on packages.context internals beyond invoke_context_request.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence


class Condition(str, Enum):
    BASELINE = "baseline"
    OVERHAUST = "overhaust"


class MeasurementSource(str, Enum):
    """How a field was obtained. Never silently mix these."""

    AUTOMATED = "AUTOMATED"
    MANUAL = "MANUAL"
    ESTIMATED = "ESTIMATED"
    NULL = "NULL"


class TokenKind(str, Enum):
    EXACT = "exact_token_count"
    ESTIMATED = "estimated_token_count"
    UNAVAILABLE = "unavailable"


REQUIRED_TASK_FIELDS = (
    "task_id",
    "title",
    "prompt",
    "project_id",
    "expected_answer_requirements",
    "difficulty",
    "category",
)

VALID_CATEGORIES = frozenset({
    "symbol_lookup",
    "code_flow",
    "architecture",
    "cross_file_reasoning",
    "change_impact",
    "debugging",
    "modification",
    "multi_step",
    "adversarial_tiny",
    "adversarial_one_file",
    "adversarial_ambiguous",
    "adversarial_unrelated",
    "adversarial_missing",
    "adversarial_stale",
    "adversarial_broad",
})

VALID_REPO_SIZES = frozenset({"small", "medium", "large"})


@dataclass
class AnswerRubric:
    """
    Deterministic correctness rubric defined BEFORE results are collected.

    required_facts: all must appear for correct=True
    required_any_of: at least one member per group must appear (OR groups)
    required_files / required_symbols: scored for evidence
    forbidden_claims: if present, correctness fails (hallucination guard)
    """

    required_facts: List[str] = field(default_factory=list)
    required_any_of: List[List[str]] = field(default_factory=list)
    required_files: List[str] = field(default_factory=list)
    required_symbols: List[str] = field(default_factory=list)
    forbidden_claims: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "AnswerRubric":
        if not data:
            return cls()
        return cls(
            required_facts=list(data.get("required_facts") or []),
            required_any_of=[list(g) for g in (data.get("required_any_of") or [])],
            required_files=list(data.get("required_files") or []),
            required_symbols=list(data.get("required_symbols") or []),
            forbidden_claims=list(data.get("forbidden_claims") or []),
            notes=data.get("notes") or "",
        )


@dataclass
class BenchmarkTask:
    task_id: str
    title: str
    prompt: str
    project_id: str
    expected_answer_requirements: List[str]
    difficulty: str
    category: str
    expected_symbols: List[str] = field(default_factory=list)
    expected_files: List[str] = field(default_factory=list)
    fixture: str = "labkot_retrieval"
    repository: str = "fixture:labkot_retrieval"
    repository_size: str = "medium"
    rubric: Optional[Dict[str, Any]] = None
    adversarial: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def get_rubric(self) -> AnswerRubric:
        if self.rubric:
            return AnswerRubric.from_dict(self.rubric)
        return AnswerRubric(
            required_facts=list(self.expected_answer_requirements),
            required_files=list(self.expected_files),
            required_symbols=list(self.expected_symbols),
            notes="Derived from legacy expected_* fields.",
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BenchmarkTask":
        validate_task_dict(data)
        size = data.get("repository_size") or "medium"
        if size not in VALID_REPO_SIZES:
            raise ValueError(f"repository_size must be one of {sorted(VALID_REPO_SIZES)}")
        return cls(
            task_id=data["task_id"],
            title=data["title"],
            prompt=data["prompt"],
            project_id=data["project_id"],
            expected_answer_requirements=list(data["expected_answer_requirements"]),
            difficulty=data["difficulty"],
            category=data["category"],
            expected_symbols=list(data.get("expected_symbols") or []),
            expected_files=list(data.get("expected_files") or []),
            fixture=data.get("fixture") or "labkot_retrieval",
            repository=data.get("repository") or "fixture:labkot_retrieval",
            repository_size=size,
            rubric=data.get("rubric"),
            adversarial=bool(data.get("adversarial", False)),
            notes=data.get("notes") or "",
        )


def validate_task_dict(data: Dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValueError("task must be a dict")
    missing = [f for f in REQUIRED_TASK_FIELDS if f not in data or data[f] in (None, "")]
    if missing:
        raise ValueError(f"task missing required fields: {missing}")
    if not isinstance(data["expected_answer_requirements"], list):
        raise ValueError("expected_answer_requirements must be a list")
    if not data["expected_answer_requirements"]:
        raise ValueError("expected_answer_requirements must be non-empty")
    if data["category"] not in VALID_CATEGORIES:
        raise ValueError(
            f"category {data['category']!r} not in {sorted(VALID_CATEGORIES)}"
        )


@dataclass
class TokenMeasurement:
    """A token count with an explicit provenance label."""

    value: Optional[int]
    kind: TokenKind
    source: MeasurementSource
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "kind": self.kind.value,
            "source": self.source.value,
            "note": self.note,
        }

    @classmethod
    def unavailable(cls, note: str = "") -> "TokenMeasurement":
        return cls(None, TokenKind.UNAVAILABLE, MeasurementSource.NULL, note)

    @classmethod
    def estimated(cls, value: int, *, source: MeasurementSource = MeasurementSource.ESTIMATED,
                  note: str = "") -> "TokenMeasurement":
        return cls(value, TokenKind.ESTIMATED, source, note)

    @classmethod
    def exact(cls, value: int, *, source: MeasurementSource = MeasurementSource.MANUAL,
              note: str = "") -> "TokenMeasurement":
        return cls(value, TokenKind.EXACT, source, note)


@dataclass
class CorrectnessResult:
    correct: Optional[bool]
    required_facts_found: List[str] = field(default_factory=list)
    required_facts_missing: List[str] = field(default_factory=list)
    expected_files_found: List[str] = field(default_factory=list)
    expected_files_missing: List[str] = field(default_factory=list)
    expected_symbols_found: List[str] = field(default_factory=list)
    expected_symbols_missing: List[str] = field(default_factory=list)
    evidence_score: Optional[float] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RunRecord:
    """One execution of one task under one condition."""

    task_id: str
    condition: str
    timestamp: str
    model: Optional[str] = None
    repository: Optional[str] = None
    project_id: Optional[str] = None
    run_index: int = 1

    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    context_tokens: Optional[int] = None

    input_tokens_kind: str = TokenKind.UNAVAILABLE.value
    output_tokens_kind: str = TokenKind.UNAVAILABLE.value
    total_tokens_kind: str = TokenKind.UNAVAILABLE.value
    context_tokens_kind: str = TokenKind.UNAVAILABLE.value

    tool_calls: Optional[int] = None
    files_inspected: Optional[int] = None
    latency_ms: Optional[int] = None

    answer_text: Optional[str] = None
    correctness: Optional[bool] = None
    evidence_score: Optional[float] = None
    correctness_detail: Optional[Dict[str, Any]] = None

    overhaust_context_used: Optional[bool] = None
    overhaust_context_preview: Optional[str] = None
    overhaust_context_metrics: Optional[Dict[str, Any]] = None

    measurement_source: str = MeasurementSource.AUTOMATED.value
    indexing_cost_tokens: Optional[int] = None
    indexing_cost_note: str = (
        "Indexing cost is NOT included in query-time totals. "
        "Report separately; do not amortize unless enough runs exist."
    )
    error: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunRecord":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        if "condition" in filtered and filtered["condition"] not in {
            Condition.BASELINE.value, Condition.OVERHAUST.value
        }:
            raise ValueError(f"invalid condition: {filtered['condition']}")
        return cls(**filtered)


def reduce_percent(baseline: Optional[float], treatment: Optional[float]) -> Optional[float]:
    """(baseline - treatment) / baseline * 100, or None if denominator invalid."""
    if baseline is None or treatment is None:
        return None
    if baseline == 0:
        return None
    return round((baseline - treatment) / baseline * 100.0, 4)


def _percentile(sorted_vals: Sequence[float], p: float) -> float:
    """Linear-interpolation percentile; sorted_vals must be non-empty."""
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return float(sorted_vals[f])
    return float(sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f))


def aggregate_numeric(values: Sequence[Optional[float]]) -> Dict[str, Optional[float]]:
    """mean / median / p25 / p75 / min / max / stdev / CI95 over non-null values."""
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return {
            "mean": None, "median": None, "p25": None, "p75": None,
            "min": None, "max": None, "stdev": None,
            "ci95_low": None, "ci95_high": None, "n": 0,
        }
    nums_sorted = sorted(nums)
    n = len(nums_sorted)
    mean = sum(nums_sorted) / n
    mid = n // 2
    median = nums_sorted[mid] if n % 2 else (nums_sorted[mid - 1] + nums_sorted[mid]) / 2.0
    if n == 1:
        stdev = 0.0
    else:
        var = sum((x - mean) ** 2 for x in nums_sorted) / (n - 1)
        stdev = var ** 0.5
    # Approximate 95% CI via normal approximation; null when n < 2.
    if n >= 2 and stdev is not None:
        se = stdev / (n ** 0.5)
        ci_low = mean - 1.96 * se
        ci_high = mean + 1.96 * se
    else:
        ci_low = ci_high = None
    return {
        "mean": round(mean, 4),
        "median": round(median, 4),
        "p25": round(_percentile(nums_sorted, 25), 4),
        "p75": round(_percentile(nums_sorted, 75), 4),
        "min": round(nums_sorted[0], 4),
        "max": round(nums_sorted[-1], 4),
        "stdev": round(stdev, 4),
        "ci95_low": None if ci_low is None else round(ci_low, 4),
        "ci95_high": None if ci_high is None else round(ci_high, 4),
        "n": n,
    }
