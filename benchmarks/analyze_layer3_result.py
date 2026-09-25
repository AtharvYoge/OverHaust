"""
Read-only distribution analysis for a Layer 3 live result JSON.

Does not modify the source file, scoring, pairing, or production retrieval.
Primary evidence is successful comparable pairs whose exact measured
total-token reduction is present. Failed and incomparable pairs stay in
the report.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from benchmarks.schemas import aggregate_numeric
from benchmarks.tasks_loader import load_task_set


def _contract(trace: Dict[str, Any]) -> Dict[str, Any]:
    return (trace.get("config") or {}).get("experiment_contract") or {}


def _exact_reduction(pair: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    metrics = pair.get("pairwise_metrics") or {}
    red = metrics.get("exact_measured_reduction")
    if not isinstance(red, dict):
        return None
    if red.get("label") != "EXACT MEASURED REDUCTION":
        return None
    if red.get("total_token_reduction_pct") is None:
        return None
    return red


def _is_primary(pair: Dict[str, Any]) -> bool:
    validation = pair.get("validation") or {}
    baseline = _contract(pair.get("baseline") or {})
    overhaust = _contract(pair.get("overhaust") or {})
    if baseline.get("failure_status") != "SUCCESS":
        return False
    if overhaust.get("failure_status") != "SUCCESS":
        return False
    if not validation.get("comparable"):
        return False
    if not validation.get("allow_exact_token_reduction"):
        return False
    return _exact_reduction(pair) is not None


def _task_categories(task_set: Optional[str]) -> Dict[str, str]:
    if not task_set:
        return {}
    try:
        tasks = load_task_set(task_set)
    except Exception:
        return {}
    return {task.task_id: task.category for task in tasks}


def _row(pair: Dict[str, Any], categories: Dict[str, str]) -> Dict[str, Any]:
    baseline = pair.get("baseline") or {}
    overhaust = pair.get("overhaust") or {}
    bc = _contract(baseline)
    oc = _contract(overhaust)
    red = _exact_reduction(pair) or {}
    b_tot = baseline.get("total_tokens")
    o_tot = overhaust.get("total_tokens")
    b_in = baseline.get("input_tokens")
    o_in = overhaust.get("input_tokens")
    b_out = baseline.get("output_tokens")
    o_out = overhaust.get("output_tokens")
    return {
        "task_id": pair.get("task_id"),
        "category": categories.get(pair.get("task_id") or "", ""),
        "repetition": pair.get("repetition"),
        "pair_id": pair.get("pair_id"),
        "execution_order": pair.get("execution_order"),
        "model": baseline.get("model"),
        "repository_size": baseline.get("repository_size"),
        "baseline_total_tokens": b_tot,
        "overhaust_total_tokens": o_tot,
        "absolute_token_difference": (
            None if b_tot is None or o_tot is None else int(b_tot) - int(o_tot)
        ),
        "total_token_reduction_pct": red.get("total_token_reduction_pct"),
        "input_token_reduction_pct": red.get("input_token_reduction_pct"),
        "output_token_change_pct": red.get("output_token_change_pct"),
        "baseline_input_tokens": b_in,
        "overhaust_input_tokens": o_in,
        "baseline_output_tokens": b_out,
        "overhaust_output_tokens": o_out,
        "input_token_difference": (
            None if b_in is None or o_in is None else int(b_in) - int(o_in)
        ),
        "output_token_difference": (
            None if b_out is None or o_out is None else int(b_out) - int(o_out)
        ),
        "baseline_status": bc.get("failure_status"),
        "overhaust_status": oc.get("failure_status"),
        "comparable": (pair.get("validation") or {}).get("comparable"),
        "allow_exact_token_reduction": (pair.get("validation") or {}).get(
            "allow_exact_token_reduction"
        ),
        "primary": _is_primary(pair),
        "baseline_error": baseline.get("error"),
        "overhaust_error": overhaust.get("error"),
        "baseline_correct": baseline.get("correctness"),
        "overhaust_correct": overhaust.get("correctness"),
        "baseline_tool_calls": baseline.get("tool_call_count"),
        "overhaust_tool_calls": overhaust.get("tool_call_count"),
    }


def iqr_fences(values: Sequence[float]) -> Dict[str, Optional[float]]:
    stats = aggregate_numeric(list(values))
    p25 = stats["p25"]
    p75 = stats["p75"]
    if p25 is None or p75 is None:
        return {"p25": None, "p75": None, "iqr": None, "low": None, "high": None}
    iqr = p75 - p25
    return {
        "p25": p25,
        "p75": p75,
        "iqr": round(iqr, 4),
        "low": round(p25 - 1.5 * iqr, 4),
        "high": round(p75 + 1.5 * iqr, 4),
    }


def _bootstrap_mean_ci(
    values: Sequence[float],
    *,
    samples: int = 10000,
    seed: int = 20260924,
) -> Dict[str, Optional[float]]:
    nums = [float(v) for v in values]
    if len(nums) < 2:
        return {"low": None, "high": None, "samples": samples, "seed": seed}
    rng = random.Random(seed)
    n = len(nums)
    means = []
    for _ in range(samples):
        draw = [nums[rng.randrange(n)] for _ in range(n)]
        means.append(sum(draw) / n)
    means.sort()
    lo = means[int(0.025 * (samples - 1))]
    hi = means[int(0.975 * (samples - 1))]
    return {
        "low": round(lo, 4),
        "high": round(hi, 4),
        "samples": samples,
        "seed": seed,
    }


def _permutation_pvalue(
    differences: Sequence[float],
    *,
    samples: int = 10000,
    seed: int = 20260924,
) -> Optional[float]:
    """Two-sided permutation test of mean paired difference == 0."""
    diffs = [float(v) for v in differences]
    n = len(diffs)
    if n < 2:
        return None
    observed = abs(sum(diffs) / n)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(samples):
        signed = [d if rng.randrange(2) else -d for d in diffs]
        if abs(sum(signed) / n) >= observed - 1e-12:
            extreme += 1
    return round((extreme + 1) / (samples + 1), 4)


def _sum(values: Iterable[Optional[float]]) -> Optional[int]:
    nums = [int(v) for v in values if v is not None]
    if not nums:
        return None
    return sum(nums)


def _contract_audit(pairs: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    checks = {
        "model_mismatch": 0,
        "prompt_hash_mismatch": 0,
        "system_prompt_hash_mismatch": 0,
        "tool_set_hash_mismatch": 0,
        "repository_commit_mismatch": 0,
        "repository_mismatch": 0,
        "budget_mismatch": 0,
        "shared_session": 0,
        "overhaust_context_not_proven": 0,
        "inexact_total_tokens": 0,
        "restore_unavailable": 0,
    }
    unknown_fields: Dict[str, int] = {}
    for pair in pairs:
        bc = _contract(pair.get("baseline") or {})
        oc = _contract(pair.get("overhaust") or {})
        if bc.get("model") != oc.get("model") or bc.get("model_version") != oc.get("model_version"):
            checks["model_mismatch"] += 1
        if bc.get("user_prompt_hash") != oc.get("user_prompt_hash"):
            checks["prompt_hash_mismatch"] += 1
        if bc.get("system_prompt_hash") != oc.get("system_prompt_hash"):
            checks["system_prompt_hash_mismatch"] += 1
        if bc.get("tool_set_hash") != oc.get("tool_set_hash"):
            checks["tool_set_hash_mismatch"] += 1
        if bc.get("repository_commit") != oc.get("repository_commit"):
            checks["repository_commit_mismatch"] += 1
        if bc.get("repository") != oc.get("repository"):
            checks["repository_mismatch"] += 1
        if (
            bc.get("max_tool_calls") != oc.get("max_tool_calls")
            or bc.get("timeout_s") != oc.get("timeout_s")
            or bc.get("max_output_tokens") != oc.get("max_output_tokens")
            or bc.get("temperature") != oc.get("temperature")
        ):
            checks["budget_mismatch"] += 1
        if bc.get("session_id") and bc.get("session_id") == oc.get("session_id"):
            checks["shared_session"] += 1
        if oc.get("overhaust_context_included_in_input") != "true":
            checks["overhaust_context_not_proven"] += 1
        btrace = pair.get("baseline") or {}
        otrace = pair.get("overhaust") or {}
        if (
            btrace.get("total_tokens_kind") != "exact_token_count"
            or otrace.get("total_tokens_kind") != "exact_token_count"
        ):
            checks["inexact_total_tokens"] += 1
        restores = pair.get("repository_restore") or []
        if any((item or {}).get("status") == "UNAVAILABLE" for item in restores):
            checks["restore_unavailable"] += 1
        for side, contract in (("baseline", bc), ("overhaust", oc)):
            for name, status in (contract.get("field_presence") or {}).items():
                if status not in {"KNOWN", "true", "n/a"}:
                    key = f"{side}.{name}={status}"
                    unknown_fields[key] = unknown_fields.get(key, 0) + 1
    return {"checks": checks, "non_known_fields": unknown_fields}


def analyze_layer3_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    pairs = list(payload.get("pairs") or [])
    categories = _task_categories(payload.get("task_set"))
    rows = [_row(pair, categories) for pair in pairs]
    primary = [row for row in rows if row["primary"]]
    non_primary = [row for row in rows if not row["primary"]]
    percents = [float(row["total_token_reduction_pct"]) for row in primary]
    fences = iqr_fences(percents)
    outliers = []
    if fences["low"] is not None and fences["high"] is not None:
        for row in primary:
            pct = float(row["total_token_reduction_pct"])
            if pct < fences["low"] or pct > fences["high"]:
                outliers.append(row)
    outlier_ids = {id(row) for row in outliers}
    retained = [row for row in primary if id(row) not in outlier_ids]
    input_delta = _sum(row["input_token_difference"] for row in primary)
    output_delta = _sum(row["output_token_difference"] for row in primary)
    total_delta = _sum(row["absolute_token_difference"] for row in primary)
    by_task: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_task.setdefault(row["task_id"], []).append(row)
    task_summaries = []
    repeated_patterns = []
    for task_id, group in sorted(by_task.items()):
        primary_group = [r for r in group if r["primary"]]
        pcts = [float(r["total_token_reduction_pct"]) for r in primary_group]
        b_toks = [r["baseline_total_tokens"] for r in primary_group]
        o_toks = [r["overhaust_total_tokens"] for r in primary_group]
        diffs = [r["absolute_token_difference"] for r in primary_group]
        patterns = {
            (r["baseline_total_tokens"], r["overhaust_total_tokens"])
            for r in primary_group
        }
        if len(primary_group) > 1 and len(patterns) == 1:
            repeated_patterns.append(task_id)
        task_summaries.append({
            "task_id": task_id,
            "category": group[0]["category"],
            "n": len(primary_group),
            "failure_or_incomplete": sum(1 for r in group if not r["primary"]),
            "reduction_pct": aggregate_numeric(pcts),
            "baseline_total_tokens": aggregate_numeric(b_toks),
            "overhaust_total_tokens": aggregate_numeric(o_toks),
            "absolute_token_difference": aggregate_numeric(diffs),
            "baseline_correct": sum(1 for r in primary_group if r["baseline_correct"] is True),
            "overhaust_correct": sum(1 for r in primary_group if r["overhaust_correct"] is True),
            "both_correct": sum(
                1
                for r in primary_group
                if r["baseline_correct"] is True and r["overhaust_correct"] is True
            ),
            "both_incorrect": sum(
                1
                for r in primary_group
                if r["baseline_correct"] is False and r["overhaust_correct"] is False
            ),
        })
    by_category: Dict[str, List[float]] = {}
    for row in primary:
        by_category.setdefault(row["category"] or "unknown", []).append(
            float(row["total_token_reduction_pct"])
        )
    differences = [
        float(row["absolute_token_difference"])
        for row in primary
        if row["absolute_token_difference"] is not None
    ]
    unique_patterns = {
        (
            row["task_id"],
            row["baseline_total_tokens"],
            row["overhaust_total_tokens"],
        )
        for row in primary
    }
    return {
        "source": {
            "mode": payload.get("mode"),
            "task_set": payload.get("task_set"),
            "repo_size_field": payload.get("repo_size"),
            "model": payload.get("model"),
            "provider": payload.get("provider"),
            "runs": payload.get("runs"),
            "generated_at": payload.get("generated_at"),
            "trace_repository_sizes": sorted({
                (pair.get("baseline") or {}).get("repository_size") for pair in pairs
            }),
        },
        "counts": {
            "attempted_pairs": len(pairs),
            "primary_exact_pairs": len(primary),
            "non_primary_pairs": len(non_primary),
        },
        "primary_rows": primary,
        "non_primary_rows": non_primary,
        "distribution": aggregate_numeric(percents),
        "iqr": fences,
        "outliers": outliers,
        "distribution_outliers_excluded": aggregate_numeric(
            [float(row["total_token_reduction_pct"]) for row in retained]
        ),
        "repeated_identical_tasks": repeated_patterns,
        "outlier_exclusion_label": (
            "Secondary descriptive statistic only. Tukey fences "
            "(below P25-1.5*IQR or above P75+1.5*IQR) on primary "
            "exact total-token reduction percentages. Outliers remain "
            "in the primary distribution."
        ),
        "bootstrap_mean_ci95": _bootstrap_mean_ci(percents),
        "normal_approx_ci95": {
            "low": aggregate_numeric(percents).get("ci95_low"),
            "high": aggregate_numeric(percents).get("ci95_high"),
        },
        "paired_permutation": {
            "statistic": "mean absolute token difference (baseline - overhaust)",
            "mean_difference": None if not differences else round(
                sum(differences) / len(differences), 4
            ),
            "two_sided_p": _permutation_pvalue(differences),
            "assumption": (
                "Treats the recorded pairs as exchangeable. Repeated identical "
                "token counts are not independent draws, so this p-value can "
                "look stronger than the effective sample supports."
            ),
        },
        "unique_token_patterns": len(unique_patterns),
        "by_task": task_summaries,
        "by_category": {
            name: aggregate_numeric(vals) for name, vals in sorted(by_category.items())
        },
        "token_components": {
            "sum_input_token_difference": input_delta,
            "sum_output_token_difference": output_delta,
            "sum_total_token_difference": total_delta,
            "input_share_of_net_reduction": (
                None
                if input_delta is None or total_delta in (None, 0)
                else round(input_delta / total_delta, 4)
            ),
            "output_share_of_net_reduction": (
                None
                if output_delta is None or total_delta in (None, 0)
                else round(output_delta / total_delta, 4)
            ),
            "input_reduction_pct": aggregate_numeric(
                [row["input_token_reduction_pct"] for row in primary]
            ),
            "output_change_pct": aggregate_numeric(
                [row["output_token_change_pct"] for row in primary]
            ),
        },
        "contract_audit": _contract_audit(pairs),
        "claim_boundary": (
            "These figures describe this result file only. They are not a "
            "product-wide token-saving percentage."
        ),
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _stats_line(stats: Dict[str, Any]) -> str:
    return (
        f"n={stats.get('n')} mean={_fmt(stats.get('mean'))} "
        f"median={_fmt(stats.get('median'))} min={_fmt(stats.get('min'))} "
        f"max={_fmt(stats.get('max'))} stdev={_fmt(stats.get('stdev'))} "
        f"p25={_fmt(stats.get('p25'))} p75={_fmt(stats.get('p75'))}"
    )


def format_markdown(report: Dict[str, Any]) -> str:
    src = report["source"]
    dist = report["distribution"]
    lines = [
        "# Layer 3 result distribution",
        "",
        report["claim_boundary"],
        "",
        "## Dataset",
        "",
        f"- mode: {src.get('mode')}",
        f"- task_set: {src.get('task_set')}",
        f"- result repo_size field: {src.get('repo_size_field')}",
        f"- trace repository_size values: {', '.join(str(v) for v in src.get('trace_repository_sizes') or [])}",
        f"- provider/model: {src.get('provider')} / {src.get('model')}",
        f"- repetitions recorded: {src.get('runs')}",
        f"- generated_at: {src.get('generated_at')}",
        f"- attempted pairs: {report['counts']['attempted_pairs']}",
        f"- primary exact pairs: {report['counts']['primary_exact_pairs']}",
        f"- non-primary pairs: {report['counts']['non_primary_pairs']}",
        "",
        "## Overall exact total-token reduction %",
        "",
        _stats_line(dist),
        f"- IQR: {_fmt(report['iqr'].get('iqr'))}",
        f"- Tukey fences: [{_fmt(report['iqr'].get('low'))}, {_fmt(report['iqr'].get('high'))}]",
        f"- unique (task, baseline total, overhaust total) patterns: {report['unique_token_patterns']}",
        "",
        "## Secondary statistic with IQR outliers excluded",
        "",
        report["outlier_exclusion_label"],
        "",
        _stats_line(report["distribution_outliers_excluded"]),
        "",
        "## Per task",
        "",
    ]
    for task in report["by_task"]:
        red = task["reduction_pct"]
        lines.append(
            f"- {task['task_id']} ({task['category']}): n={task['n']} "
            f"mean={_fmt(red.get('mean'))}% median={_fmt(red.get('median'))}% "
            f"min={_fmt(red.get('min'))}% max={_fmt(red.get('max'))}% "
            f"mean baseline tokens={_fmt(task['baseline_total_tokens'].get('mean'))} "
            f"mean OverHaust tokens={_fmt(task['overhaust_total_tokens'].get('mean'))} "
            f"mean absolute difference={_fmt(task['absolute_token_difference'].get('mean'))} "
            f"baseline_correct={task['baseline_correct']}/{task['n']} "
            f"overhaust_correct={task['overhaust_correct']}/{task['n']} "
            f"both_correct={task['both_correct']}/{task['n']} "
            f"both_incorrect={task['both_incorrect']}/{task['n']} "
            f"failure_or_incomplete={task['failure_or_incomplete']}"
        )
    if report.get("repeated_identical_tasks"):
        lines.append(
            "- identical token counts across repetitions (protocol replicates, "
            f"not independent samples): {', '.join(report['repeated_identical_tasks'])}"
        )
    lines.extend(["", "## Outliers", ""])
    if not report["outliers"]:
        lines.append("- none under the Tukey fence rule")
    for row in report["outliers"]:
        lines.append(
            f"- {row['task_id']} rep={row['repetition']}: "
            f"baseline={row['baseline_total_tokens']} "
            f"overhaust={row['overhaust_total_tokens']} "
            f"reduction={_fmt(row['total_token_reduction_pct'])}%"
        )
    comp = report["token_components"]
    lines.extend([
        "",
        "## Token components (primary pairs)",
        "",
        f"- sum input difference (baseline - overhaust): {comp['sum_input_token_difference']}",
        f"- sum output difference (baseline - overhaust): {comp['sum_output_token_difference']}",
        f"- sum total difference: {comp['sum_total_token_difference']}",
        f"- input share of net total difference: {comp['input_share_of_net_reduction']}",
        f"- output share of net total difference: {comp['output_share_of_net_reduction']}",
        f"- input reduction %: {_stats_line(comp['input_reduction_pct'])}",
        f"- output change % (positive means OverHaust used fewer output tokens): {_stats_line(comp['output_change_pct'])}",
        "",
        "## Non-primary pairs",
        "",
    ])
    if not report["non_primary_rows"]:
        lines.append("- none")
    for row in report["non_primary_rows"]:
        lines.append(
            f"- {row['task_id']} rep={row['repetition']}: "
            f"baseline={row['baseline_status']} overhaust={row['overhaust_status']} "
            f"comparable={row['comparable']} error={row['baseline_error'] or row['overhaust_error']}"
        )
    audit = report["contract_audit"]["checks"]
    lines.extend(["", "## Contract audit (all attempted pairs)", ""])
    for name, count in audit.items():
        lines.append(f"- {name}: {count}")
    unknown = report["contract_audit"]["non_known_fields"]
    if unknown:
        lines.append("- field_presence values other than KNOWN/true/n/a:")
        for key, count in sorted(unknown.items()):
            lines.append(f"  - {key}: {count}")
    else:
        lines.append("- field_presence values other than KNOWN/true/n/a: none")
    lines.extend([
        "",
        "## Uncertainty",
        "",
        f"- normal-approximation 95% CI of the mean: "
        f"[{_fmt(report['normal_approx_ci95']['low'])}, {_fmt(report['normal_approx_ci95']['high'])}]",
        f"- bootstrap 95% CI of the mean (seed {report['bootstrap_mean_ci95']['seed']}, "
        f"{report['bootstrap_mean_ci95']['samples']} resamples): "
        f"[{_fmt(report['bootstrap_mean_ci95']['low'])}, {_fmt(report['bootstrap_mean_ci95']['high'])}]",
        f"- paired permutation two-sided p for mean token difference: "
        f"{report['paired_permutation']['two_sided_p']}",
        f"- {report['paired_permutation']['assumption']}",
        "",
    ])
    return "\n".join(lines)


def load_result(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m benchmarks.analyze_layer3_result",
        description="Read-only Layer 3 pair distribution analysis.",
    )
    parser.add_argument("result_json", type=Path)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--md-out", type=Path, default=None)
    args = parser.parse_args(argv)
    payload = load_result(args.result_json)
    report = analyze_layer3_result(payload)
    text = format_markdown(report)
    print(text)
    if args.json_out:
        # Drop bulky row lists from the optional JSON only when writing a
        # summary; keep them so the artifact remains reproducible.
        args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.md_out:
        args.md_out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
