"""
Strict baseline/OverHaust pair validation.

Two UNKNOWN values are NEVER treated as equal.
Returns structured diagnostics — never an opaque exception for mismatches.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from benchmarks.layer3.contract import ExperimentContract, FieldPresence
from benchmarks.layer3.prompts import detect_extra_user_instructions, user_prompt_hash
from benchmarks.layer3.states import RunState
from benchmarks.schemas import Condition

# Must be KNOWN on both sides and equal.
HARD_MATCH_FIELDS = (
    "provider",
    "model",
    "repository",
    "task_id",
    "user_prompt_hash",
    "system_prompt_hash",
    "tool_set_hash",
    "max_tool_calls",
    "timeout_s",
    "max_output_tokens",
    "execution_order",
    "protocol_version",
    "benchmark_version",
)

# Must match when KNOWN; if either side unknown → limited (not hard-fail alone).
# Two UNKNOWN values are NEVER treated as equal (reported as UNKNOWN_BOTH).
SOFT_MATCH_FIELDS = (
    "model_version",
    "repository_commit",
    "temperature",
    "seed",
)


@dataclass
class PairValidationResult:
    comparable: bool
    limited: bool
    reasons: List[Dict[str, Any]] = field(default_factory=list)
    matched_fields: List[str] = field(default_factory=list)
    limits: List[str] = field(default_factory=list)
    baseline_state: Optional[str] = None
    overhaust_state: Optional[str] = None
    allow_exact_token_reduction: bool = False
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _contract_of(trace: Any) -> ExperimentContract:
    if isinstance(trace, ExperimentContract):
        return trace
    if hasattr(trace, "contract") and isinstance(getattr(trace, "contract"), ExperimentContract):
        return trace.contract
    if isinstance(trace, dict):
        raw = trace.get("contract") or trace.get("experiment_contract")
        if raw and "experiment_id" in raw and "pair_id" in raw:
            return ExperimentContract.from_dict(raw)
    raise ValueError("trace does not carry an ExperimentContract")


def _unk(status: str) -> bool:
    return status in {
        FieldPresence.UNKNOWN.value,
        FieldPresence.UNAVAILABLE.value,
        "UNSUPPORTED",
    }


def _field_status(contract: ExperimentContract, name: str) -> str:
    if name == "seed":
        return contract.seed_status
    if name == "temperature":
        return contract.temperature_status
    if name == "max_output_tokens":
        if contract.max_output_tokens is None:
            return FieldPresence.UNKNOWN.value
        return FieldPresence.KNOWN.value
    if name == "execution_order":
        if not contract.execution_order or contract.execution_order == "UNKNOWN":
            return FieldPresence.UNKNOWN.value
        return FieldPresence.KNOWN.value
    contract.refresh_presence()
    return contract.field_presence.get(name, FieldPresence.UNKNOWN.value)


def _field_value(contract: ExperimentContract, name: str) -> Any:
    return getattr(contract, name, None)


def validate_layer3_pair(baseline: Any, overhaust: Any) -> PairValidationResult:
    reasons: List[Dict[str, Any]] = []
    matched: List[str] = []
    limits: List[str] = []
    hard_fail = False

    try:
        b = _contract_of(baseline)
        o = _contract_of(overhaust)
    except ValueError as exc:
        return PairValidationResult(
            comparable=False,
            limited=True,
            reasons=[{
                "field": "contract",
                "baseline": None,
                "overhaust": None,
                "status": "MISMATCH",
                "detail": str(exc),
            }],
            summary="NOT comparable — missing ExperimentContract.",
        )

    if b.condition != Condition.BASELINE.value or o.condition != Condition.OVERHAUST.value:
        hard_fail = True
        reasons.append({
            "field": "condition",
            "baseline": b.condition,
            "overhaust": o.condition,
            "status": "MISMATCH",
            "detail": "Expected baseline contract paired with overhaust contract.",
        })

    for name, bv, ov in (
        ("pair_id", b.pair_id, o.pair_id),
        ("experiment_id", b.experiment_id, o.experiment_id),
    ):
        if bv != ov:
            hard_fail = True
            reasons.append({
                "field": name, "baseline": bv, "overhaust": ov, "status": "MISMATCH",
            })
        else:
            matched.append(name)

    # Session isolation: must be known and different
    if not b.session_id or not o.session_id:
        hard_fail = True
        reasons.append({
            "field": "session_id",
            "baseline": b.session_id,
            "overhaust": o.session_id,
            "status": "UNKNOWN_ONE",
            "detail": "Session isolation not proven.",
        })
    elif b.session_id == o.session_id:
        hard_fail = True
        reasons.append({
            "field": "session_id",
            "baseline": b.session_id,
            "overhaust": o.session_id,
            "status": "MISMATCH",
            "detail": "Baseline and OverHaust must not share session state.",
        })
    else:
        matched.append("session_id")

    def check_field(name: str, *, hard: bool) -> None:
        nonlocal hard_fail
        bv, ov = _field_value(b, name), _field_value(o, name)
        bp, op = _field_status(b, name), _field_status(o, name)
        if _unk(bp) and _unk(op):
            status = "UNKNOWN_BOTH"
            limits.append(f"{name}: both unknown/unavailable — not treated as equal")
            reasons.append({
                "field": name, "baseline": bv, "overhaust": ov, "status": status,
                "detail": "Two unknown/unavailable values are NOT equal.",
            })
            if hard:
                hard_fail = True
            return
        if _unk(bp) or _unk(op):
            status = "UNKNOWN_ONE"
            limits.append(f"{name}: one side unknown/unavailable")
            reasons.append({
                "field": name, "baseline": bv, "overhaust": ov, "status": status,
            })
            if hard:
                hard_fail = True
            return
        if bv != ov:
            hard_fail = True
            reasons.append({
                "field": name, "baseline": bv, "overhaust": ov, "status": "MISMATCH",
            })
        else:
            matched.append(name)

    for name in HARD_MATCH_FIELDS:
        check_field(name, hard=True)
    for name in SOFT_MATCH_FIELDS:
        check_field(name, hard=False)

    if b.retry_count != o.retry_count or b.attempt_count != o.attempt_count:
        hard_fail = True
        reasons.append({
            "field": "retry_policy",
            "baseline": {"attempt": b.attempt_count, "retry": b.retry_count},
            "overhaust": {"attempt": o.attempt_count, "retry": o.retry_count},
            "status": "MISMATCH",
            "detail": "Retry/attempt profiles must match.",
        })
    else:
        matched.append("retry_policy")

    if b.failure_status != RunState.SUCCESS.value or o.failure_status != RunState.SUCCESS.value:
        hard_fail = True
        reasons.append({
            "field": "failure_status",
            "baseline": b.failure_status,
            "overhaust": o.failure_status,
            "status": "MISMATCH",
            "detail": "Only SUCCESS/SUCCESS pairs enter primary analysis.",
        })

    # OverHaust context must be proven in input for exact savings
    allow_exact = True
    incl = o.overhaust_context_included_in_input
    if incl == "true":
        matched.append("overhaust_context_included_in_input")
    elif incl == "false":
        hard_fail = True
        allow_exact = False
        reasons.append({
            "field": "overhaust_context_included_in_input",
            "baseline": "n/a",
            "overhaust": incl,
            "status": "MISMATCH",
            "detail": "OverHaust context was not included in model input.",
        })
    else:
        allow_exact = False
        limits.append(
            "overhaust_context_included_in_input not proven; "
            "exact total-token reduction claims blocked."
        )
        reasons.append({
            "field": "overhaust_context_included_in_input",
            "baseline": "n/a",
            "overhaust": incl,
            "status": "UNKNOWN_ONE",
            "detail": "Must be proven true for exact savings claims.",
        })

    b_acc = b.token_accounting or {}
    o_acc = o.token_accounting or {}
    for side, acc in (("baseline", b_acc), ("overhaust", o_acc)):
        kind = acc.get("cached_input_tokens_kind")
        if kind == "unavailable" or acc.get("cached_input_tokens") is None:
            limits.append(
                f"{side}: cached_input_tokens unavailable (not treated as zero)"
            )

    comparable = not hard_fail
    limited = bool(limits) or any(
        r["status"] in {"UNKNOWN_BOTH", "UNKNOWN_ONE"} for r in reasons
    )
    if not comparable:
        allow_exact = False
        summary = "NOT comparable — must not be aggregated into paired savings."
    elif not allow_exact:
        summary = (
            "Structurally comparable but OverHaust context inclusion unproven — "
            "do NOT claim exact total-token savings."
        )
    elif limited:
        summary = (
            "Valid comparable pair with disclosed limitations "
            "(unknown optional fields / cache reporting)."
        )
    else:
        summary = "Valid comparable baseline/OverHaust pair; exact reduction analysis allowed."

    return PairValidationResult(
        comparable=comparable,
        limited=limited,
        reasons=reasons,
        matched_fields=matched,
        limits=limits,
        baseline_state=b.failure_status,
        overhaust_state=o.failure_status,
        allow_exact_token_reduction=bool(comparable and allow_exact),
        summary=summary,
    )


def validate_trace_against_task(
    contract: ExperimentContract,
    task_prompt: str,
    task_id: str,
) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    if contract.task_id != task_id:
        errors.append({
            "field": "task_id",
            "status": "MISMATCH",
            "baseline": task_id,
            "overhaust": contract.task_id,
            "detail": "task_id must match task definition",
        })
    expected = user_prompt_hash(task_prompt)
    if contract.user_prompt_hash != expected:
        errors.append({
            "field": "user_prompt_hash",
            "status": "MISMATCH",
            "baseline": expected,
            "overhaust": contract.user_prompt_hash,
            "detail": "user prompt must match task definition exactly",
        })
    if detect_extra_user_instructions(contract.user_prompt, task_prompt):
        errors.append({
            "field": "user_prompt",
            "status": "MISMATCH",
            "baseline": task_prompt,
            "overhaust": contract.user_prompt,
            "detail": "extra user-visible instructions detected",
        })
    return errors
