"""
Pairwise Layer-3 metrics — only for SUCCESS + comparable + exact-allowed pairs.

Terminology:
  EXACT MEASURED REDUCTION  — provider exact totals on both sides
  ESTIMATED REDUCTION       — estimated_* fields only (never called "savings")
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from benchmarks.layer3.pairing import PairValidationResult, validate_layer3_pair
from benchmarks.layer3.states import RunState
from benchmarks.schemas import aggregate_numeric, reduce_percent
from benchmarks.trace import AgentTrace


def _usage_total(trace: AgentTrace, *, exact: bool) -> Optional[int]:
    contract = getattr(trace, "contract", None)
    if contract and getattr(contract, "token_accounting", None):
        acc = contract.token_accounting
        if exact:
            if acc.get("total_billable_tokens_kind") == "exact_token_count":
                return acc.get("total_billable_tokens")
            if trace.total_tokens is not None and trace.total_tokens_kind == "exact_token_count":
                return trace.total_tokens
            return None
        return acc.get("total_billable_tokens") or trace.estimated_total_tokens
    if exact:
        if trace.total_tokens is not None and trace.total_tokens_kind == "exact_token_count":
            return trace.total_tokens
        return None
    return trace.estimated_total_tokens


def _input_total(trace: AgentTrace, *, exact: bool) -> Optional[int]:
    contract = getattr(trace, "contract", None)
    if exact:
        if trace.input_tokens is not None and trace.input_tokens_kind == "exact_token_count":
            return trace.input_tokens
        if contract and contract.token_accounting:
            raw = contract.token_accounting.get("raw_input_tokens")
            if raw is not None:
                return raw
        return None
    return trace.estimated_input_tokens


def pairwise_reduction(
    baseline: AgentTrace,
    overhaust: AgentTrace,
    validation: Optional[PairValidationResult] = None,
) -> Dict[str, Any]:
    validation = validation or validate_layer3_pair(baseline, overhaust)
    out: Dict[str, Any] = {
        "pair_id": getattr(getattr(baseline, "contract", None), "pair_id", None),
        "validation": validation.to_dict(),
        "exact_measured_reduction": None,
        "estimated_reduction": None,
        "baseline_correct": baseline.correctness,
        "overhaust_correct": overhaust.correctness,
        "accuracy_delta": None,
        "excluded_from_primary": not (
            validation.comparable and validation.allow_exact_token_reduction
        ),
    }
    if baseline.correctness is not None and overhaust.correctness is not None:
        out["accuracy_delta"] = int(overhaust.correctness) - int(baseline.correctness)

    def pack(exact: bool) -> Optional[Dict[str, Any]]:
        if exact and not validation.allow_exact_token_reduction:
            return None
        if not validation.comparable and exact:
            return None
        b_tot = _usage_total(baseline, exact=exact)
        o_tot = _usage_total(overhaust, exact=exact)
        b_in = _input_total(baseline, exact=exact)
        o_in = _input_total(overhaust, exact=exact)
        label = "EXACT MEASURED REDUCTION" if exact else "ESTIMATED REDUCTION"
        return {
            "label": label,
            "total_token_reduction_pct": reduce_percent(b_tot, o_tot),
            "input_token_reduction_pct": reduce_percent(b_in, o_in),
            "output_token_change_pct": reduce_percent(
                baseline.output_tokens if exact else baseline.estimated_output_tokens,
                overhaust.output_tokens if exact else overhaust.estimated_output_tokens,
            ),
            "tool_call_reduction_pct": reduce_percent(
                baseline.tool_call_count, overhaust.tool_call_count
            ),
            "file_read_reduction_pct": reduce_percent(
                baseline.files_read_count, overhaust.files_read_count
            ),
            "search_reduction_pct": reduce_percent(
                baseline.searches_performed, overhaust.searches_performed
            ),
            "latency_change_pct": reduce_percent(baseline.duration_ms, overhaust.duration_ms),
            "baseline_total": b_tot,
            "overhaust_total": o_tot,
        }

    out["exact_measured_reduction"] = pack(True)
    out["estimated_reduction"] = pack(False)
    return out


def aggregate_paired_experiment(
    pairs: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    pairs: list of {baseline, overhaust} AgentTrace dicts or objects.
    """
    attempted = len(pairs)
    successful: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    incomparable: List[Dict[str, Any]] = []

    reductions: List[Optional[float]] = []
    accuracy_deltas: List[Optional[float]] = []

    for item in pairs:
        b = item["baseline"]
        o = item["overhaust"]
        if isinstance(b, dict):
            # Expect enriched traces with contract already attached via wrapper
            raise TypeError("aggregate_paired_experiment expects AgentTrace objects")
        val = validate_layer3_pair(b, o)
        metrics = pairwise_reduction(b, o, val)
        b_state = getattr(getattr(b, "contract", None), "failure_status", None)
        o_state = getattr(getattr(o, "contract", None), "failure_status", None)
        if b_state != RunState.SUCCESS.value or o_state != RunState.SUCCESS.value:
            failed.append(metrics)
            continue
        if not val.comparable:
            incomparable.append(metrics)
            rejected.append(metrics)
            continue
        if not val.allow_exact_token_reduction:
            rejected.append(metrics)
            # Still track estimated separately but not primary exact
            continue
        successful.append(metrics)
        red = (metrics.get("exact_measured_reduction") or {}).get("total_token_reduction_pct")
        reductions.append(red)
        accuracy_deltas.append(metrics.get("accuracy_delta"))

    return {
        "attempted_pairs": attempted,
        "successful_pairs": len(successful),
        "rejected_pairs": len(rejected),
        "failed_runs_pairs": len(failed),
        "incomparable_pairs": len(incomparable),
        "exact_total_token_reduction_pct": aggregate_numeric(reductions),
        "accuracy_delta": aggregate_numeric(accuracy_deltas),
        "successful_pair_metrics": successful,
        "rejected_pair_metrics": rejected,
        "failed_pair_metrics": failed,
        "incomparable_pair_metrics": incomparable,
        "note": (
            "Primary exact reductions only include SUCCESS+comparable+"
            "allow_exact_token_reduction pairs. Failures and rejects are retained."
        ),
    }
