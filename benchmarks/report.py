"""
Structured experiment report: Exact / Estimated / Unsupported / Limitations / Uncertainty.

Never emits a product token-savings claim without underlying measured data.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from benchmarks.breakeven import break_even_from_traces
from benchmarks.matrix import fill_matrix_from_traces, format_matrix_markdown
from benchmarks.metrics import pair_reduction
from benchmarks.schemas import aggregate_numeric, reduce_percent
from benchmarks.trace import AgentTrace


CLAIM_BAN = (
    "No percentage token reduction should be claimed as a product result "
    "until Layer 3+ controlled experimental data exists with adequate "
    "repetitions, matched correctness, and documented cost accounting."
)


def _totals(traces: Sequence[AgentTrace], prefer_exact: bool = True):
    if prefer_exact:
        exact = [t.total_tokens for t in traces if t.total_tokens is not None]
        if exact:
            return exact, "exact_token_count"
    est = [t.estimated_total_tokens for t in traces if t.estimated_total_tokens is not None]
    return est, "estimated_token_count"


def _field(traces: Sequence[AgentTrace], name: str) -> List[Optional[float]]:
    return [getattr(t, name) for t in traces]


def compare_trace_sets(
    baseline: Sequence[AgentTrace],
    overhaust: Sequence[AgentTrace],
) -> Dict[str, Any]:
    b_tot, b_kind = _totals(baseline)
    o_tot, o_kind = _totals(overhaust)
    kind_ok = b_kind == o_kind and bool(b_tot) and bool(o_tot)

    def red(b_vals, o_vals):
        ba, oa = aggregate_numeric(b_vals), aggregate_numeric(o_vals)
        return {
            "baseline": ba,
            "overhaust": oa,
            "reduction_percent_mean": reduce_percent(ba["mean"], oa["mean"]),
            "reduction_percent_median": reduce_percent(ba["median"], oa["median"]),
        }

    token_block = {
        "kind": b_kind if kind_ok else "uncomparable",
        "comparable": kind_ok,
        **(red(b_tot, o_tot) if kind_ok else {
            "baseline": aggregate_numeric(b_tot),
            "overhaust": aggregate_numeric(o_tot),
            "reduction_percent_mean": None,
            "reduction_percent_median": None,
            "note": "Refusing comparison across mismatched or empty token kinds.",
        }),
    }

    def rate(xs: Sequence[AgentTrace]) -> Dict[str, Optional[float]]:
        known = [t.correctness for t in xs if t.correctness is not None]
        if not known:
            return {"rate": None, "n": 0}
        return {"rate": round(sum(1 for c in known if c) / len(known), 4), "n": len(known)}

    sb, so = rate(baseline), rate(overhaust)
    accuracy_delta = None
    if sb["rate"] is not None and so["rate"] is not None:
        accuracy_delta = round(so["rate"] - sb["rate"], 4)

    return {
        "token_reduction": token_block,
        "input_token_reduction": {
            "exact": red(
                [t.input_tokens for t in baseline],
                [t.input_tokens for t in overhaust],
            ),
            "estimated": red(
                [t.estimated_input_tokens for t in baseline],
                [t.estimated_input_tokens for t in overhaust],
            ),
        },
        "tool_call_reduction": red(
            _field(baseline, "tool_call_count"),
            _field(overhaust, "tool_call_count"),
        ),
        "file_read_reduction": red(
            _field(baseline, "files_read_count"),
            _field(overhaust, "files_read_count"),
        ),
        "search_reduction": red(
            _field(baseline, "searches_performed"),
            _field(overhaust, "searches_performed"),
        ),
        "latency_reduction": red(
            _field(baseline, "duration_ms"),
            _field(overhaust, "duration_ms"),
        ),
        "success_rate": {"baseline": sb, "overhaust": so},
        "accuracy_delta": accuracy_delta,
        "efficiency_with_correctness": {
            "token_savings_median_pct": token_block.get("reduction_percent_median"),
            "accuracy_delta": accuracy_delta,
            "meaningful": bool(
                kind_ok
                and accuracy_delta is not None
                and accuracy_delta >= -0.05  # allow tiny noise; document threshold
            ),
            "note": (
                "Token savings are only marked meaningful when token kinds match "
                "and accuracy_delta is measured and not materially negative "
                "(threshold: -5 percentage points). This is a reporting gate, "
                "not a product claim."
            ),
        },
    }


def build_layered_report(
    traces: Sequence[AgentTrace],
    *,
    task_categories: Optional[Dict[str, str]] = None,
    indexing_cost_tokens: Optional[float] = None,
    layer: int = 2,
    usd_per_1k_tokens: Optional[float] = None,
) -> Dict[str, Any]:
    baseline = [t for t in traces if t.condition == "baseline"]
    overhaust = [t for t in traces if t.condition == "overhaust"]
    comparison = compare_trace_sets(baseline, overhaust)

    b_mean = comparison["token_reduction"].get("baseline", {}).get("mean")
    o_mean = comparison["token_reduction"].get("overhaust", {}).get("mean")
    # Prefer exact means for break-even when available.
    be = break_even_from_traces(
        indexing_cost_tokens=indexing_cost_tokens,
        baseline_total_tokens_mean=b_mean,
        overhaust_total_tokens_mean=o_mean,
        usd_per_1k_tokens=usd_per_1k_tokens,
    )

    matrix = fill_matrix_from_traces(
        traces, task_categories=task_categories or {}, min_reps=1
    )

    exact_runs = [
        t for t in traces
        if t.total_tokens is not None and t.total_tokens_kind == "exact_token_count"
    ]
    estimated_runs = [
        t for t in traces
        if t.estimated_total_tokens is not None and t.total_tokens is None
    ]

    return {
        "A_exact_measured_results": {
            "n_traces_with_exact_totals": len(exact_runs),
            "comparison_if_exact": (
                compare_trace_sets(
                    [t for t in baseline if t.total_tokens is not None],
                    [t for t in overhaust if t.total_tokens is not None],
                )
                if exact_runs else None
            ),
            "note": "Populated only from provider-reported exact_token_count fields.",
        },
        "B_estimated_results": {
            "n_traces_with_estimated_totals_only": len(estimated_runs),
            "comparison": comparison,
            "note": (
                "Includes Layer 2 simulation and any estimated_* fields. "
                "Not interchangeable with exact provider metrics."
            ),
        },
        "C_unsupported_claims": [
            CLAIM_BAN,
            "Layer 2 results do not prove Layer 3 or Layer 4.",
            "Query-time reductions exclude indexing cost unless break-even is computed with measured indexing_cost.",
        ],
        "D_limitations": [
            f"Report layer focus: {layer}",
            "Deterministic rubrics only (no LLM judge).",
            "Simulator search is substring-based, not embedding retrieval.",
            "Live IDE observability (Layer 4) requires manual/external traces.",
        ],
        "E_statistical_uncertainty": {
            "baseline_n": len(baseline),
            "overhaust_n": len(overhaust),
            "token_stats": comparison["token_reduction"],
            "ci_note": (
                "ci95_* uses normal approximation; unreliable for small n. "
                "Prefer median + p25/p75."
            ),
        },
        "break_even": be,
        "matrix": matrix,
        "matrix_markdown": format_matrix_markdown(matrix),
        "comparison": comparison,
        "claim_policy": CLAIM_BAN,
    }


def format_report_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# OverHaust real-agent benchmark report",
        "",
        "## A. Exact measured results",
        "",
        f"- traces with exact totals: "
        f"{report['A_exact_measured_results']['n_traces_with_exact_totals']}",
        f"- {report['A_exact_measured_results']['note']}",
        "",
        "## B. Estimated results",
        "",
        f"- estimated-only traces: "
        f"{report['B_estimated_results']['n_traces_with_estimated_totals_only']}",
    ]
    comp = report["comparison"]["token_reduction"]
    lines.append(
        f"- token reduction median % ({comp.get('kind')}): "
        f"{comp.get('reduction_percent_median')}"
    )
    lines.append(
        f"- accuracy_delta: {report['comparison'].get('accuracy_delta')}"
    )
    lines.extend(["", "## C. Unsupported claims", ""])
    for c in report["C_unsupported_claims"]:
        lines.append(f"- {c}")
    lines.extend(["", "## D. Limitations", ""])
    for c in report["D_limitations"]:
        lines.append(f"- {c}")
    lines.extend(["", "## E. Statistical uncertainty", ""])
    eu = report["E_statistical_uncertainty"]
    lines.append(f"- baseline_n={eu['baseline_n']} overhaust_n={eu['overhaust_n']}")
    lines.append(f"- {eu['ci_note']}")
    lines.extend(["", "## Break-even", ""])
    lines.append(f"- token: {report['break_even']['token_units'].get('status')} "
                 f"n={report['break_even']['token_units'].get('break_even_n')}")
    lines.append(f"- {report['break_even']['token_units'].get('note')}")
    lines.extend(["", report.get("matrix_markdown", "")])
    lines.extend(["", "## Policy", "", report.get("claim_policy", ""), ""])
    return "\n".join(lines)
