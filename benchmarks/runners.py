"""
Condition runners for the context-efficiency benchmark.

AUTOMATED mode measures context-size proxies only:
  - baseline: packages.context.benchmark.simulate_naive_agent_exploration
  - overhaust: packages.context.agent_context.invoke_context_request

These are NOT live Cursor/Codex sessions. Agent input/output tokens,
tool_calls from a real model, and answer correctness require MANUAL
ingestion via ingest_run_record().

The harness never changes invoke_context_request behaviour or budgets.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from benchmarks import BENCHMARK_VERSION
from benchmarks.evaluate import evaluate_answer
from benchmarks.fixture import FixtureProject, prepare_labkot_fixture
from benchmarks.metrics import compare_conditions, group_by_task, query_time_totals
from benchmarks.schemas import (
    BenchmarkTask,
    Condition,
    MeasurementSource,
    RunRecord,
    TokenKind,
)
from benchmarks.tasks_loader import filter_tasks, load_task_set
from benchmarks.tokens import TokenCounter


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_overhaust_condition(
    task: BenchmarkTask,
    *,
    fixture: FixtureProject,
    run_index: int = 1,
    model: Optional[str] = None,
    counter: Optional[TokenCounter] = None,
) -> RunRecord:
    """Invoke existing invoke_context_request(); record returned context size."""
    from packages.context.agent_context import invoke_context_request

    counter = counter or TokenCounter(model=model)
    error = None
    context_text = ""
    metrics: Dict[str, Any] = {}
    latency_ms = None
    files_inspected = None
    try:
        response = invoke_context_request(
            fixture.project_id,
            task.prompt,
            memory_store=fixture.memory_store,
        )
        context_text = response.context or ""
        metrics = response.metrics.to_dict() if hasattr(response.metrics, "to_dict") else {
            "files_count": response.metrics.files_count,
            "symbols_count": response.metrics.symbols_count,
            "approx_source_lines": response.metrics.approx_source_lines,
            "response_bytes": response.metrics.response_bytes,
            "latency_ms": response.metrics.latency_ms,
            "code_flow_included": response.metrics.code_flow_included,
        }
        # Prefer engine-reported latency; fall back to None rather than inventing.
        latency_ms = metrics.get("latency_ms")
        files_inspected = metrics.get("files_count")
    except Exception as exc:
        error = str(exc)

    ctx_tokens = counter.count_context(context_text) if context_text else counter.count_context("")
    # Automated path: total_tokens = context_tokens only (query-time context size).
    # input/output from a live model remain null.
    return RunRecord(
        task_id=task.task_id,
        condition=Condition.OVERHAUST.value,
        timestamp=_now(),
        model=model,
        repository=task.repository,
        project_id=fixture.project_id,
        run_index=run_index,
        input_tokens=None,
        output_tokens=None,
        total_tokens=ctx_tokens.value,
        context_tokens=ctx_tokens.value,
        input_tokens_kind=TokenKind.UNAVAILABLE.value,
        output_tokens_kind=TokenKind.UNAVAILABLE.value,
        total_tokens_kind=ctx_tokens.kind.value,
        context_tokens_kind=ctx_tokens.kind.value,
        tool_calls=None,
        files_inspected=files_inspected,
        latency_ms=latency_ms,
        answer_text=None,
        correctness=None,
        evidence_score=None,
        overhaust_context_used=True,
        overhaust_context_preview=(context_text[:500] if context_text else None),
        overhaust_context_metrics=metrics or None,
        measurement_source=MeasurementSource.AUTOMATED.value,
        indexing_cost_tokens=None,
        error=error,
        extras={
            "token_notes": {
                "total": ctx_tokens.note,
                "context": ctx_tokens.note,
            },
            "mode": "automated_context_size",
            "disclaimer": (
                "AUTOMATED OverHaust condition measures query-time context size "
                "from invoke_context_request(). It is not a live agent session."
            ),
        },
    )


def run_baseline_condition(
    task: BenchmarkTask,
    *,
    fixture: FixtureProject,
    run_index: int = 1,
    model: Optional[str] = None,
    counter: Optional[TokenCounter] = None,
    search_limit: int = 10,
) -> RunRecord:
    """
    Automated baseline: simulate naïve search + full-file reads.

    Reuses packages.context.benchmark.simulate_naive_agent_exploration.
    Does NOT run a live agent. tool_calls remain null.
    """
    from packages.context.benchmark import simulate_naive_agent_exploration

    counter = counter or TokenCounter(model=model)
    error = None
    files_inspected = None
    latency_ms = None
    context_tokens = None
    token_kind = TokenKind.UNAVAILABLE.value
    token_note = ""
    paths: List[str] = []
    try:
        naive = simulate_naive_agent_exploration(
            fixture.project_id,
            task.prompt,
            memory_store=fixture.memory_store,
            search_limit=search_limit,
        )
        files_inspected = naive.get("files_inspected")
        latency_ms = naive.get("latency_ms")
        paths = list(naive.get("paths") or [])
        # Prefer re-counting with our labelled TokenCounter for consistency.
        # simulate_naive returns estimated_context_tokens via TokenEstimator;
        # we re-estimate from paths by reading the same files when possible.
        from packages.context.benchmark import _read_full_file

        parts = []
        for path in paths:
            content = _read_full_file(str(fixture.root), path)
            if content:
                parts.append(f"// FILE: {path}\n{content}")
        combined = "\n\n".join(parts)
        measured = counter.count_context(combined)
        context_tokens = measured.value
        token_kind = measured.kind.value
        token_note = measured.note
    except Exception as exc:
        error = str(exc)

    return RunRecord(
        task_id=task.task_id,
        condition=Condition.BASELINE.value,
        timestamp=_now(),
        model=model,
        repository=task.repository,
        project_id=fixture.project_id,
        run_index=run_index,
        input_tokens=None,
        output_tokens=None,
        total_tokens=context_tokens,
        context_tokens=context_tokens,
        input_tokens_kind=TokenKind.UNAVAILABLE.value,
        output_tokens_kind=TokenKind.UNAVAILABLE.value,
        total_tokens_kind=token_kind,
        context_tokens_kind=token_kind,
        tool_calls=None,
        files_inspected=files_inspected,
        latency_ms=latency_ms,
        answer_text=None,
        correctness=None,
        evidence_score=None,
        overhaust_context_used=False,
        measurement_source=MeasurementSource.AUTOMATED.value,
        indexing_cost_tokens=None,
        error=error,
        extras={
            "token_notes": {"total": token_note, "context": token_note},
            "paths": paths,
            "mode": "automated_naive_exploration",
            "disclaimer": (
                "AUTOMATED baseline measures context size of simulated naïve "
                "search+full-file reads. It is not a live agent session; "
                "tool_calls/input_tokens/output_tokens remain null."
            ),
        },
    )


def ingest_run_record(data: Dict[str, Any], *, task: Optional[BenchmarkTask] = None) -> RunRecord:
    """
    Accept an externally produced run record (MANUAL agent telemetry).

    Required keys: task_id, condition, timestamp.
    Optional: answer_text triggers deterministic correctness if task is given.
    """
    if "measurement_source" not in data:
        data = {**data, "measurement_source": MeasurementSource.MANUAL.value}
    record = RunRecord.from_dict(data)
    if task is not None and record.answer_text:
        result = evaluate_answer(task, record.answer_text)
        record.correctness = result.correct
        record.evidence_score = result.evidence_score
        record.correctness_detail = result.to_dict()
    return record


def run_condition_suite(
    condition: str,
    tasks: Sequence[BenchmarkTask],
    *,
    runs: int = 1,
    model: Optional[str] = None,
    fixture: Optional[FixtureProject] = None,
) -> List[RunRecord]:
    if runs < 1:
        raise ValueError("--runs must be >= 1")
    if condition not in {Condition.BASELINE.value, Condition.OVERHAUST.value}:
        raise ValueError(f"unknown condition: {condition}")

    owns_fixture = fixture is None
    fixture = fixture or prepare_labkot_fixture()
    counter = TokenCounter(model=model)
    records: List[RunRecord] = []
    try:
        for task in tasks:
            for i in range(1, runs + 1):
                if condition == Condition.BASELINE.value:
                    records.append(
                        run_baseline_condition(
                            task, fixture=fixture, run_index=i, model=model, counter=counter
                        )
                    )
                else:
                    records.append(
                        run_overhaust_condition(
                            task, fixture=fixture, run_index=i, model=model, counter=counter
                        )
                    )
    finally:
        if owns_fixture:
            fixture.close()
    return records


def build_report(
    records: Sequence[RunRecord],
    *,
    model: Optional[str] = None,
    repository: str = "fixture:labkot_retrieval",
    task_set: str = "initial",
) -> Dict[str, Any]:
    by_task = group_by_task(records)
    per_task = {}
    for task_id, conds in by_task.items():
        per_task[task_id] = {
            "baseline": query_time_totals(conds["baseline"]),
            "overhaust": query_time_totals(conds["overhaust"]),
            "comparison": compare_conditions(conds["baseline"], conds["overhaust"]),
        }
    all_b = [r for r in records if r.condition == Condition.BASELINE.value]
    all_o = [r for r in records if r.condition == Condition.OVERHAUST.value]
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "task_set": task_set,
        "repository": repository,
        "model": model,
        "generated_at": _now(),
        "runs": [r.to_dict() for r in records],
        "summary": {
            "run_count": len(records),
            "baseline_run_count": len(all_b),
            "overhaust_run_count": len(all_o),
            "per_task": per_task,
            "overall_comparison": compare_conditions(all_b, all_o),
            "claims_policy": (
                "No percentage token reduction should be claimed until the "
                "benchmark has produced reproducible measurements. "
                "Automated context-size reductions are QUERY-TIME only and "
                "exclude indexing cost."
            ),
        },
    }


def format_markdown_summary(report: Dict[str, Any]) -> str:
    lines = [
        f"# OverHaust context-efficiency benchmark",
        "",
        f"- version: `{report.get('benchmark_version')}`",
        f"- task_set: `{report.get('task_set')}`",
        f"- repository: `{report.get('repository')}`",
        f"- model: `{report.get('model') or 'n/a'}`",
        f"- generated_at: `{report.get('generated_at')}`",
        "",
        "> No percentage token reduction should be claimed until reproducible "
        "measurements exist. Values below are QUERY-TIME context-size metrics "
        "unless a run's measurement_source is MANUAL.",
        "",
        "| Task | Baseline context tokens (mean) | OverHaust context tokens (mean) | Reduction % | "
        "Baseline files | OverHaust files | Baseline tool calls | OverHaust tool calls | "
        "Correctness (B/O) | Evidence (B/O) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    per_task = report.get("summary", {}).get("per_task", {})
    for task_id, block in sorted(per_task.items()):
        b = block["baseline"]
        o = block["overhaust"]
        c = block["comparison"]
        lines.append(
            "| {task} | {bt} | {ot} | {rp} | {bf} | {of} | {btc} | {otc} | {corr} | {ev} |".format(
                task=task_id,
                bt=_fmt(b["context_tokens"]["mean"]),
                ot=_fmt(o["context_tokens"]["mean"]),
                rp=_fmt(c["context_token_reduction"]["reduction_percent"]),
                bf=_fmt(b["files_inspected"]["mean"]),
                of=_fmt(o["files_inspected"]["mean"]),
                btc=_fmt(b["tool_calls"]["mean"]),
                otc=_fmt(o["tool_calls"]["mean"]),
                corr=f"{_fmt(c['correctness']['baseline']['rate'])}/{_fmt(c['correctness']['overhaust']['rate'])}",
                ev=f"{_fmt(b['evidence_score']['mean'])}/{_fmt(o['evidence_score']['mean'])}",
            )
        )
    lines.extend([
        "",
        "## Cost accounting",
        "",
        report.get("summary", {}).get("overall_comparison", {}).get("cost_accounting", {}).get("note", ""),
        "",
        "## Policy",
        "",
        report.get("summary", {}).get("claims_policy", ""),
        "",
    ])
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def write_report(report: Dict[str, Any], results_dir: Path) -> Dict[str, Path]:
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    json_path = results_dir / f"run-{stamp}.json"
    md_path = results_dir / f"run-{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(format_markdown_summary(report), encoding="utf-8")
    return {"json": json_path, "md": md_path}


def run_benchmark(
    *,
    condition: Optional[str] = None,
    compare: bool = False,
    task_set: str = "initial",
    runs: int = 1,
    model: Optional[str] = None,
    task_ids: Optional[Sequence[str]] = None,
    results_dir: Optional[Path] = None,
    ingest_paths: Optional[Sequence[Path]] = None,
) -> Dict[str, Any]:
    """
    Top-level entry used by the CLI.

    If ingest_paths is set, loads MANUAL records instead of running automated
    conditions (still validates/aggregates consistently).
    """
    tasks = filter_tasks(load_task_set(task_set), task_ids)
    records: List[RunRecord] = []

    if ingest_paths:
        by_id = {t.task_id: t for t in tasks}
        for path in ingest_paths:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            items = payload if isinstance(payload, list) else payload.get("runs", [payload])
            for item in items:
                task = by_id.get(item.get("task_id"))
                records.append(ingest_run_record(item, task=task))
    else:
        conditions = []
        if compare:
            conditions = [Condition.BASELINE.value, Condition.OVERHAUST.value]
        elif condition:
            conditions = [condition]
        else:
            raise ValueError("Specify --condition or --compare (or --ingest)")

        fixture = prepare_labkot_fixture()
        try:
            for cond in conditions:
                records.extend(
                    run_condition_suite(
                        cond, tasks, runs=runs, model=model, fixture=fixture
                    )
                )
        finally:
            fixture.close()

    report = build_report(records, model=model, task_set=task_set)
    out_dir = results_dir or (Path(__file__).resolve().parent / "results")
    paths = write_report(report, out_dir)
    report["_output_paths"] = {k: str(v) for k, v in paths.items()}
    return report
