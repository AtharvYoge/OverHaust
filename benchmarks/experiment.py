"""
Layer orchestration: run Layer 1 / 2 / ingest Layer 3–4; emit structured reports.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from benchmarks import BENCHMARK_VERSION
from benchmarks.providers import ProviderNotConfiguredError, load_traces, require_provider
from benchmarks.report import build_layered_report, format_report_markdown
from benchmarks.repos import prepare_sized_fixture
from benchmarks.runners import build_report, run_benchmark, write_report
from benchmarks.sim_agent import run_layer2_pair
from benchmarks.tasks_loader import filter_tasks, load_task_set
from benchmarks.trace import AgentTrace


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_layer2_benchmark(
    *,
    task_set: str = "initial",
    runs: int = 1,
    task_ids: Optional[Sequence[str]] = None,
    repo_size: str = "medium",
    max_tool_calls: int = 12,
    model: Optional[str] = None,
    seed: Optional[int] = None,
    results_dir: Optional[Path] = None,
    shuffle: bool = True,
    indexing_cost_tokens: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Execute deterministic agent simulation for baseline + overhaust.

    Randomized run order across (task, condition, rep) when shuffle=True.
    """
    if runs < 1:
        raise ValueError("runs must be >= 1")
    tasks = filter_tasks(load_task_set(task_set), task_ids)
    fixture = prepare_sized_fixture(repo_size)  # type: ignore[arg-type]
    rng = random.Random(seed)

    jobs: List[tuple] = []
    for task in tasks:
        for rep in range(1, runs + 1):
            jobs.append((task, rep))
    if shuffle:
        rng.shuffle(jobs)

    traces: List[AgentTrace] = []
    try:
        for task, rep in jobs:
            # Conditions run as a pair with identical budgets; order of pairs
            # is shuffled. Within a pair we still run baseline then overhaust
            # so OverHaust index state is comparable; condition order can be
            # flipped by seed parity for extra balance.
            pair = run_layer2_pair(
                task,
                fixture=fixture,
                max_tool_calls=max_tool_calls,
                model=model,
                seed=None if seed is None else seed + rep,
            )
            order = ["baseline", "overhaust"]
            if seed is not None and ((seed + rep) % 2):
                order = ["overhaust", "baseline"]
            for cond in order:
                tr = pair[cond]
                tr.config["run_index"] = rep
                traces.append(tr)
    finally:
        fixture.close()

    cats = {t.task_id: t.category for t in tasks}
    layered = build_layered_report(
        traces,
        task_categories=cats,
        indexing_cost_tokens=indexing_cost_tokens,
        layer=2,
    )
    report = {
        "benchmark_version": BENCHMARK_VERSION,
        "layer": 2,
        "task_set": task_set,
        "repository_size": repo_size,
        "model": model or "deterministic-sim-agent",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": seed,
        "max_tool_calls": max_tool_calls,
        "traces": [t.to_dict() for t in traces],
        "layered_report": layered,
        "claim_policy": layered["claim_policy"],
    }

    out_dir = results_dir or (Path(__file__).resolve().parent / "results")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    json_path = out_dir / f"layer2-{stamp}.json"
    md_path = out_dir / f"layer2-{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(format_report_markdown(layered), encoding="utf-8")
    report["_output_paths"] = {"json": str(json_path), "md": str(md_path)}
    return report


def run_layer3_ingest(
    paths: Sequence[Path],
    *,
    task_set: str = "initial",
    results_dir: Optional[Path] = None,
    indexing_cost_tokens: Optional[float] = None,
) -> Dict[str, Any]:
    """Strict Layer-3 ingest with pair validation (rejects incomparable pairs)."""
    from benchmarks.layer3.ingest import load_and_pair_traces

    paired = load_and_pair_traces(paths, task_set=task_set)

    layered = {
        "pair_aggregation": paired["pair_aggregation"],
        "pair_validations": paired["pair_validations"],
        "pairwise_metrics": paired["pairwise_metrics"],
        "rejected_ingest": paired["rejected_ingest"],
        "unpaired": paired["unpaired"],
        "A_exact_measured_results": {
            "successful_pairs": paired["pair_aggregation"].get("successful_pairs"),
            "exact_total_token_reduction_pct": paired["pair_aggregation"].get(
                "exact_total_token_reduction_pct"
            ),
            "note": (
                "Exact reductions only from SUCCESS + comparable + "
                "allow_exact_token_reduction pairs."
            ),
        },
        "B_estimated_results": {
            "note": "Estimated reductions never labelled as exact savings.",
        },
        "C_unsupported_claims": [
            "Do not claim product token savings until controlled Layer-3 data exists.",
            "Incomparable / failed / rejected pairs must not be aggregated as savings.",
        ],
        "D_limitations": [
            "OpenAI Chat Completions runner; seed support model-dependent.",
            "Cached token reporting may be UNAVAILABLE — never treated as zero.",
        ],
        "E_statistical_uncertainty": paired["pair_aggregation"].get(
            "exact_total_token_reduction_pct"
        ),
        "claim_policy": (
            "No percentage token reduction should be claimed as a product result "
            "until Layer 3+ controlled experimental data exists."
        ),
        "indexing_cost_tokens": indexing_cost_tokens,
    }
    report = {
        "benchmark_version": BENCHMARK_VERSION,
        "layer": 3,
        "task_set": task_set,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "traces": paired["traces"],
        "layered_report": layered,
        "claim_policy": layered["claim_policy"],
    }
    out_dir = results_dir or (Path(__file__).resolve().parent / "results")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    json_path = out_dir / f"layer3-{stamp}.json"
    md_path = out_dir / f"layer3-{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_lines = [
        "# Layer-3 strict ingest report",
        "",
        f"- attempted_pairs: {paired['pair_aggregation'].get('attempted_pairs')}",
        f"- successful_pairs: {paired['pair_aggregation'].get('successful_pairs')}",
        f"- rejected_pairs: {paired['pair_aggregation'].get('rejected_pairs')}",
        f"- failed_runs_pairs: {paired['pair_aggregation'].get('failed_runs_pairs')}",
        f"- incomparable_pairs: {paired['pair_aggregation'].get('incomparable_pairs')}",
        f"- rejected_ingest: {len(paired['rejected_ingest'])}",
        f"- unpaired: {len(paired['unpaired'])}",
        "",
        layered["claim_policy"],
        "",
    ]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    report["_output_paths"] = {"json": str(json_path), "md": str(md_path)}
    return report


def run_layer3_live(
    *,
    task_set: str = "initial",
    runs: int = 1,
    task_ids: Optional[Sequence[str]] = None,
    repo_size: str = "small",
    max_tool_calls: int = 12,
    model: Optional[str] = None,
    seed: Optional[int] = None,
    temperature: float = 0.0,
    timeout_s: int = 120,
    results_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    One controlled OpenAI pair per task repetition.

    Uses the existing OpenAICompatibleRunner for both conditions.
    OverHaust context comes from unmodified invoke_context_request().
    Baseline receives that context only as absence (None).
    """
    from packages.context.agent_context import invoke_context_request

    from benchmarks.layer3.pairwise import aggregate_paired_experiment
    from benchmarks.layer3.readiness import validate_layer3_live_ready
    from benchmarks.layer3.runner import OpenAICompatibleRunner, run_layer3_pair
    from benchmarks.layer3.tools import tool_set_hash
    from benchmarks.repos import prepare_sized_fixture
    from benchmarks.repro import capture_repository_snapshot, isolate_repository

    if runs < 1:
        raise ValueError("runs must be >= 1")

    runner = OpenAICompatibleRunner(
        model=model or "gpt-4o-mini",
        temperature=temperature,
        seed=seed,
        max_tool_calls=max_tool_calls,
        timeout_s=timeout_s,
    )
    tasks = filter_tasks(load_task_set(task_set), task_ids)
    if not tasks:
        raise ValueError("no tasks selected")

    fixture = prepare_sized_fixture(repo_size)  # type: ignore[arg-type]
    fixture_size = getattr(fixture, "repository_size", None)
    pair_payloads: List[Dict[str, Any]] = []
    pair_objects: List[Dict[str, Any]] = []
    try:
        snapshot = capture_repository_snapshot(str(fixture.root))
        restore_probe = isolate_repository(str(fixture.root), snapshot)
        readiness = validate_layer3_live_ready(
            model=runner.model,
            tasks=tasks,
            requested_repo_size=repo_size,
            fixture_repository_size=fixture_size,
            restore_status=restore_probe,
            tool_set_hash_value=tool_set_hash(),
            temperature=runner.temperature,
            max_tool_calls=runner.max_tool_calls,
            timeout_s=runner.timeout_s,
            max_output_tokens=runner.max_output_tokens,
        )
        repetition_policy = {
            "temperature": runner.temperature,
            "seed": runner.seed,
            "seed_status": "KNOWN" if runner.seed is not None else "UNSUPPORTED",
            "same_configuration_both_conditions": True,
            "session_isolation": "fresh session_id per condition",
            "limitation": (
                "Temperature defaults to 0 and both conditions share one runner. "
                "Identical provider token counts across repetitions are legitimate "
                "deterministic behavior, not independent random samples. "
                "No token noise is added."
            ),
        }
        if dry_run:
            return {
                "benchmark_version": BENCHMARK_VERSION,
                "layer": 3,
                "mode": "dry_run",
                "dry_run": True,
                "task_set": task_set,
                "repo_size": fixture_size,
                "fixture_repository_size": fixture_size,
                "model": runner.model,
                "provider": runner.name,
                "runs": runs,
                "readiness": readiness,
                "repository_restore_probe": {
                    k: v for k, v in restore_probe.items() if k != "files"
                },
                "repetition_policy": repetition_policy,
                "pairs": [],
                "claim_policy": (
                    "Dry run only. No provider call and no token reduction was measured."
                ),
            }
        if not runner.is_available():
            raise ProviderNotConfiguredError(
                "Live Layer 3 needs OPENAI_API_KEY or OVERHAUST_L3_API_KEY. "
                "No token counts were invented."
            )
        rng = random.Random(seed)
        for task in tasks:
            response = invoke_context_request(
                fixture.project_id,
                task.prompt,
                memory_store=fixture.memory_store,
            )
            context = response.context or ""
            for rep in range(runs):
                overhaust_first = bool(rng.randrange(2))
                result = run_layer3_pair(
                    task,
                    repository_root=str(fixture.root),
                    overhaust_context=context,
                    runner=runner,
                    overhaust_first=overhaust_first,
                    repository_size=fixture_size,
                )
                if not result.get("isolation_proven"):
                    from benchmarks.layer3.readiness import ExperimentIntegrityError
                    raise ExperimentIntegrityError(
                        "repository restoration could not be proven; pair not aggregated"
                    )
                pair_objects.append({
                    "baseline": result["baseline"],
                    "overhaust": result["overhaust"],
                })
                pair_payloads.append({
                    "experiment_id": result["experiment_id"],
                    "pair_id": result["pair_id"],
                    "task_id": task.task_id,
                    "repetition": rep,
                    "execution_order": result["execution_order"],
                    "repository_restore": result["repository_restore"],
                    "validation": result["validation"],
                    "pairwise_metrics": result["pairwise_metrics"],
                    "baseline": result["baseline"].to_dict(),
                    "overhaust": result["overhaust"].to_dict(),
                })
    finally:
        fixture.close()

    aggregation = aggregate_paired_experiment(pair_objects)
    report = {
        "benchmark_version": BENCHMARK_VERSION,
        "layer": 3,
        "mode": "live_openai",
        "task_set": task_set,
        "repo_size": fixture_size,
        "fixture_repository_size": fixture_size,
        "readiness": readiness,
        "repository_restore_probe": {
            k: v for k, v in restore_probe.items() if k != "files"
        },
        "repetition_policy": repetition_policy,
        "model": runner.model,
        "provider": runner.name,
        "runs": runs,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pairs": pair_payloads,
        "layered_report": {
            "pair_aggregation": {
                k: v for k, v in aggregation.items()
                if k not in {
                    "successful_pair_metrics",
                    "rejected_pair_metrics",
                    "failed_pair_metrics",
                    "incomparable_pair_metrics",
                }
            },
            "claim_policy": (
                "EXACT MEASURED REDUCTION only when both runs succeed, "
                "validate_layer3_pair is comparable, OverHaust context inclusion "
                "is proven, and provider totals exist on both sides."
            ),
        },
        "claim_policy": (
            "Do not report a token-saving percentage unless the pair is an "
            "EXACT MEASURED REDUCTION under the Layer 3 contract."
        ),
    }
    out_dir = results_dir or (Path(__file__).resolve().parent / "results")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    json_path = out_dir / f"layer3-live-{stamp}.json"
    md_path = out_dir / f"layer3-live-{stamp}.md"
    lines = [
        "# Layer-3 live pair",
        "",
        f"- provider: {runner.name}",
        f"- model: {runner.model}",
        f"- pairs: {len(pair_payloads)}",
        f"- successful_pairs: {aggregation.get('successful_pairs')}",
        f"- rejected_pairs: {aggregation.get('rejected_pairs')}",
        f"- failed_runs_pairs: {aggregation.get('failed_runs_pairs')}",
        f"- incomparable_pairs: {aggregation.get('incomparable_pairs')}",
        "",
        report["claim_policy"],
        "",
        "Token reduction below is reported with answer correctness. "
        "Primary means keep every successful comparable pair, including negative reductions.",
        "",
    ]
    from benchmarks.analyze_layer3_result import analyze_layer3_result
    analysis = analyze_layer3_result(report)
    report["per_task"] = analysis["by_task"]
    for task in analysis["by_task"]:
        red = task["reduction_pct"]
        lines.append(
            f"- {task['task_id']} ({task['category']}): "
            f"n={task['n']} "
            f"baseline_tokens_mean={red and task['baseline_total_tokens'].get('mean')} "
            f"overhaust_tokens_mean={task['overhaust_total_tokens'].get('mean')} "
            f"exact_reduction_mean={red.get('mean')} "
            f"baseline_correct={task['baseline_correct']}/{task['n']} "
            f"overhaust_correct={task['overhaust_correct']}/{task['n']} "
            f"both_correct={task['both_correct']}/{task['n']} "
            f"failure_or_incomplete={task['failure_or_incomplete']}"
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    report["_output_paths"] = {"json": str(json_path), "md": str(md_path)}
    return report
