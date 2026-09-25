"""
Metric helpers: reductions, aggregations, query-time vs indexing cost.

Percentages return null when the denominator is invalid (None or 0).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from benchmarks.schemas import RunRecord, aggregate_numeric, reduce_percent


def query_time_totals(runs: Sequence[RunRecord]) -> Dict[str, Any]:
    """Aggregate query-time token fields. Indexing cost is excluded."""
    return {
        "total_tokens": aggregate_numeric([r.total_tokens for r in runs]),
        "context_tokens": aggregate_numeric([r.context_tokens for r in runs]),
        "input_tokens": aggregate_numeric([r.input_tokens for r in runs]),
        "output_tokens": aggregate_numeric([r.output_tokens for r in runs]),
        "tool_calls": aggregate_numeric([r.tool_calls for r in runs]),
        "files_inspected": aggregate_numeric([r.files_inspected for r in runs]),
        "latency_ms": aggregate_numeric([r.latency_ms for r in runs]),
        "evidence_score": aggregate_numeric([r.evidence_score for r in runs]),
        "indexing_cost_tokens": aggregate_numeric([r.indexing_cost_tokens for r in runs]),
        "note": (
            "Query-time totals exclude indexing_cost_tokens. "
            "Do not claim amortized savings unless indexing cost and run count "
            "are both measured and documented."
        ),
    }


def pair_reduction(
    baseline_runs: Sequence[RunRecord],
    overhaust_runs: Sequence[RunRecord],
    field: str,
) -> Dict[str, Optional[float]]:
    """
    Compare mean(baseline.field) vs mean(overhaust.field).

    Returns absolute and percent reduction, or nulls when invalid.
    """
    b_vals = [getattr(r, field) for r in baseline_runs]
    o_vals = [getattr(r, field) for r in overhaust_runs]
    b_agg = aggregate_numeric(b_vals)
    o_agg = aggregate_numeric(o_vals)
    b_mean = b_agg["mean"]
    o_mean = o_agg["mean"]
    absolute = None
    if b_mean is not None and o_mean is not None:
        absolute = round(b_mean - o_mean, 4)
    return {
        "baseline_mean": b_mean,
        "overhaust_mean": o_mean,
        "reduction_absolute": absolute,
        "reduction_percent": reduce_percent(b_mean, o_mean),
        "baseline_n": b_agg["n"],
        "overhaust_n": o_agg["n"],
    }


def compare_conditions(
    baseline_runs: Sequence[RunRecord],
    overhaust_runs: Sequence[RunRecord],
) -> Dict[str, Any]:
    """Build the comparison block for a task (or whole suite)."""
    corr = {
        "baseline": _correctness_rate(baseline_runs),
        "overhaust": _correctness_rate(overhaust_runs),
    }
    accuracy_delta = None
    if corr["baseline"]["rate"] is not None and corr["overhaust"]["rate"] is not None:
        accuracy_delta = round(corr["overhaust"]["rate"] - corr["baseline"]["rate"], 4)
    return {
        "token_reduction": pair_reduction(baseline_runs, overhaust_runs, "total_tokens"),
        "input_token_reduction": pair_reduction(baseline_runs, overhaust_runs, "input_tokens"),
        "context_token_reduction": pair_reduction(baseline_runs, overhaust_runs, "context_tokens"),
        "tool_call_reduction": pair_reduction(baseline_runs, overhaust_runs, "tool_calls"),
        "file_inspection_reduction": pair_reduction(baseline_runs, overhaust_runs, "files_inspected"),
        "latency_reduction": pair_reduction(baseline_runs, overhaust_runs, "latency_ms"),
        "correctness": corr,
        "accuracy_delta": accuracy_delta,
        "success_rate": corr,
        "cost_accounting": {
            "query_time_only": True,
            "indexing_included_in_totals": False,
            "amortized_available": False,
            "note": (
                "QUERY-TIME TOKEN REDUCTION only. Indexing/context-generation "
                "cost is reported separately when measured; amortized impact "
                "is not computed until enough information exists."
            ),
        },
    }


def _correctness_rate(runs: Sequence[RunRecord]) -> Dict[str, Optional[float]]:
    known = [r.correctness for r in runs if r.correctness is not None]
    if not known:
        return {"rate": None, "n": 0}
    return {"rate": round(sum(1 for c in known if c) / len(known), 4), "n": len(known)}


def group_by_task(runs: Sequence[RunRecord]) -> Dict[str, Dict[str, List[RunRecord]]]:
    out: Dict[str, Dict[str, List[RunRecord]]] = {}
    for r in runs:
        bucket = out.setdefault(r.task_id, {"baseline": [], "overhaust": []})
        if r.condition in bucket:
            bucket[r.condition].append(r)
    return out
