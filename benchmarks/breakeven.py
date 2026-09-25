"""
Break-even analysis scaffolding.

Computes how many queries are required for OverHaust to break even given:

  one_time_indexing_cost
  + N * (per_query_overhaust_cost + agent_token_cost_overhaust)
  vs
  N * agent_token_cost_baseline

All inputs may be null. The framework returns null rather than inventing values.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def break_even_queries(
    *,
    indexing_cost: Optional[float],
    baseline_per_query_cost: Optional[float],
    overhaust_per_query_cost: Optional[float],
) -> Dict[str, Any]:
    """
    Solve for smallest N >= 1 such that:

      indexing + N * overhaust <= N * baseline

    i.e. N >= indexing / (baseline - overhaust) when baseline > overhaust.
    Costs may be tokens or dollars — units must match; reported as-is.
    """
    result: Dict[str, Any] = {
        "indexing_cost": indexing_cost,
        "baseline_per_query_cost": baseline_per_query_cost,
        "overhaust_per_query_cost": overhaust_per_query_cost,
        "break_even_n": None,
        "savings_per_query": None,
        "status": "insufficient_data",
        "note": (
            "Break-even is not reported until indexing_cost and both per-query "
            "costs are measured. Do not invent values."
        ),
    }
    if (
        indexing_cost is None
        or baseline_per_query_cost is None
        or overhaust_per_query_cost is None
    ):
        return result

    savings = baseline_per_query_cost - overhaust_per_query_cost
    result["savings_per_query"] = round(savings, 4)
    if savings <= 0:
        result["status"] = "never_breaks_even_at_measured_rates"
        result["note"] = (
            "Per-query OverHaust cost is not lower than baseline at measured "
            "rates; indexing cost cannot be amortized under these numbers."
        )
        return result
    if indexing_cost <= 0:
        result["break_even_n"] = 1
        result["status"] = "immediate"
        result["note"] = "No positive indexing cost recorded; break-even at first query."
        return result

    import math
    n = math.ceil(indexing_cost / savings)
    result["break_even_n"] = int(n)
    result["status"] = "computed"
    result["note"] = (
        f"At measured rates, break-even after {n} queries "
        f"(indexing={indexing_cost}, savings/query={savings})."
    )
    return result


def break_even_from_traces(
    *,
    indexing_cost_tokens: Optional[float],
    baseline_total_tokens_mean: Optional[float],
    overhaust_total_tokens_mean: Optional[float],
    # Optional dollar rates — if any missing, dollar break-even stays null.
    usd_per_1k_tokens: Optional[float] = None,
) -> Dict[str, Any]:
    token = break_even_queries(
        indexing_cost=indexing_cost_tokens,
        baseline_per_query_cost=baseline_total_tokens_mean,
        overhaust_per_query_cost=overhaust_total_tokens_mean,
    )
    dollar: Dict[str, Any] = {
        "status": "insufficient_data",
        "break_even_n": None,
        "note": "Provide usd_per_1k_tokens plus measured token costs to compute.",
    }
    if usd_per_1k_tokens is not None and all(
        v is not None
        for v in (indexing_cost_tokens, baseline_total_tokens_mean, overhaust_total_tokens_mean)
    ):
        scale = usd_per_1k_tokens / 1000.0
        dollar = break_even_queries(
            indexing_cost=(indexing_cost_tokens or 0) * scale,
            baseline_per_query_cost=(baseline_total_tokens_mean or 0) * scale,
            overhaust_per_query_cost=(overhaust_total_tokens_mean or 0) * scale,
        )
    return {"token_units": token, "dollar_units": dollar}
