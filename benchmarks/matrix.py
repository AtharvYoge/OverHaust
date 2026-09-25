"""
Benchmark matrix: category × repository_size cells.

Cells start as unknown; filled only when enough runs exist.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from benchmarks.metrics import pair_reduction
from benchmarks.schemas import RunRecord, aggregate_numeric
from benchmarks.trace import AgentTrace

MATRIX_CATEGORIES = [
    "symbol_lookup",
    "code_flow",
    "architecture",
    "debugging",
    "modification",
    "cross_file_reasoning",
    "change_impact",
]
MATRIX_SIZES = ["small", "medium", "large"]


def empty_matrix() -> Dict[str, Dict[str, Any]]:
    return {
        cat: {
            size: {
                "status": "unknown",
                "n_baseline": 0,
                "n_overhaust": 0,
                "token_reduction_pct_median": None,
                "success_baseline": None,
                "success_overhaust": None,
                "accuracy_delta": None,
            }
            for size in MATRIX_SIZES
        }
        for cat in MATRIX_CATEGORIES
    }


def _success_rate(flags: Sequence[Optional[bool]]) -> Optional[float]:
    known = [f for f in flags if f is not None]
    if not known:
        return None
    return round(sum(1 for f in known if f) / len(known), 4)


def fill_matrix_from_traces(
    traces: Sequence[AgentTrace],
    *,
    task_categories: Dict[str, str],
    min_reps: int = 3,
) -> Dict[str, Dict[str, Any]]:
    """
    Populate matrix cells from Layer 2/3 traces.

    task_categories: task_id → category
    """
    matrix = empty_matrix()
    buckets: Dict[tuple, Dict[str, List[AgentTrace]]] = {}
    for tr in traces:
        cat = task_categories.get(tr.task_id)
        if cat not in matrix:
            continue
        size = tr.repository_size
        if size not in MATRIX_SIZES:
            continue
        key = (cat, size)
        bucket = buckets.setdefault(key, {"baseline": [], "overhaust": []})
        if tr.condition in bucket:
            bucket[tr.condition].append(tr)

    for (cat, size), conds in buckets.items():
        b, o = conds["baseline"], conds["overhaust"]
        cell = matrix[cat][size]
        cell["n_baseline"] = len(b)
        cell["n_overhaust"] = len(o)
        if len(b) < min_reps or len(o) < min_reps:
            cell["status"] = "insufficient_reps"
            continue

        # Prefer exact total_tokens; else estimated_total_tokens (labelled in note).
        def totals(xs: List[AgentTrace]):
            exact = [t.total_tokens for t in xs if t.total_tokens is not None]
            if exact:
                return exact, "exact"
            return [t.estimated_total_tokens for t in xs], "estimated"

        b_vals, b_kind = totals(b)
        o_vals, o_kind = totals(o)
        if b_kind != o_kind:
            cell["status"] = "kind_mismatch"
            cell["note"] = "Refusing to compare exact vs estimated totals."
            continue

        b_agg = aggregate_numeric(b_vals)
        o_agg = aggregate_numeric(o_vals)
        from benchmarks.schemas import reduce_percent
        cell["token_reduction_pct_median"] = reduce_percent(b_agg["median"], o_agg["median"])
        cell["token_kind"] = b_kind
        sb = _success_rate([t.correctness for t in b])
        so = _success_rate([t.correctness for t in o])
        cell["success_baseline"] = sb
        cell["success_overhaust"] = so
        if sb is not None and so is not None:
            cell["accuracy_delta"] = round(so - sb, 4)
        cell["status"] = "measured"
    return matrix


def format_matrix_markdown(matrix: Dict[str, Dict[str, Any]]) -> str:
    header = "| Category | " + " | ".join(s.upper() for s in MATRIX_SIZES) + " |"
    sep = "|---|" + "|".join(["---:"] * len(MATRIX_SIZES)) + "|"
    lines = [
        "# Benchmark matrix",
        "",
        "Cells show median token_reduction_pct (and status). `?` = unknown/insufficient.",
        "",
        header,
        sep,
    ]
    for cat in MATRIX_CATEGORIES:
        cells = []
        for size in MATRIX_SIZES:
            c = matrix[cat][size]
            if c["status"] != "measured" or c["token_reduction_pct_median"] is None:
                cells.append("?")
            else:
                cells.append(f"{c['token_reduction_pct_median']:.1f}%")
        lines.append(f"| {cat} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(
        "A percentage is only meaningful together with success_baseline / "
        "success_overhaust / accuracy_delta in the JSON cell payload."
    )
    return "\n".join(lines) + "\n"
