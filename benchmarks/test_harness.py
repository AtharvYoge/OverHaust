"""Tests for the isolated context-efficiency benchmark harness."""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest

from benchmarks.evaluate import evaluate_answer
from benchmarks.fixture import prepare_labkot_fixture
from benchmarks.metrics import compare_conditions, pair_reduction
from benchmarks.runners import (
    build_report,
    ingest_run_record,
    run_baseline_condition,
    run_benchmark,
    run_condition_suite,
    run_overhaust_condition,
)
from benchmarks.schemas import (
    BenchmarkTask,
    MeasurementSource,
    RunRecord,
    TokenKind,
    TokenMeasurement,
    aggregate_numeric,
    reduce_percent,
    validate_task_dict,
)
from benchmarks.tasks_loader import load_task_set
from benchmarks.tokens import TokenCounter, assert_kinds_not_mixed


ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = Path(__file__).resolve().parent / "tasks"


# --------------------------------------------------------------------------- #
# 1. task schema validation
# --------------------------------------------------------------------------- #


def test_task_schema_rejects_missing_fields():
    with pytest.raises(ValueError, match="missing required"):
        validate_task_dict({"task_id": "x"})


def test_task_schema_rejects_bad_category():
    good = {
        "task_id": "t",
        "title": "T",
        "prompt": "P",
        "project_id": "p",
        "expected_answer_requirements": ["a"],
        "difficulty": "easy",
        "category": "not_a_real_category",
    }
    with pytest.raises(ValueError, match="category"):
        validate_task_dict(good)


def test_initial_task_set_loads_five_valid_tasks():
    tasks = load_task_set("initial", tasks_dir=TASKS_DIR)
    assert len(tasks) == 5
    ids = {t.task_id for t in tasks}
    assert "sym_generate_kot" in ids
    assert "flow_order_to_kitchen" in ids
    categories = {t.category for t in tasks}
    assert categories == {
        "symbol_lookup",
        "code_flow",
        "cross_file_reasoning",
        "change_impact",
        "architecture",
    }


# --------------------------------------------------------------------------- #
# 2–3. baseline loading + OverHaust context invocation
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def fixture_project():
    fx = prepare_labkot_fixture()
    yield fx
    fx.close()


@pytest.fixture(scope="module")
def initial_tasks():
    return load_task_set("initial", tasks_dir=TASKS_DIR)


def test_baseline_task_loading_and_run(fixture_project, initial_tasks):
    task = next(t for t in initial_tasks if t.task_id == "sym_generate_kot")
    record = run_baseline_condition(task, fixture=fixture_project, run_index=1)
    assert record.condition == "baseline"
    assert record.overhaust_context_used is False
    assert record.measurement_source == MeasurementSource.AUTOMATED.value
    assert record.error is None
    assert record.context_tokens is not None and record.context_tokens > 0
    assert record.context_tokens_kind == TokenKind.ESTIMATED.value
    # Live agent fields remain null in automated mode.
    assert record.input_tokens is None
    assert record.output_tokens is None
    assert record.tool_calls is None


def test_overhaust_context_invocation_uses_existing_seam(fixture_project, initial_tasks):
    task = next(t for t in initial_tasks if t.task_id == "sym_generate_kot")
    record = run_overhaust_condition(task, fixture=fixture_project, run_index=1)
    assert record.condition == "overhaust"
    assert record.overhaust_context_used is True
    assert record.error is None
    assert record.context_tokens is not None
    assert record.overhaust_context_preview is not None
    assert record.overhaust_context_metrics is not None
    assert "files_count" in record.overhaust_context_metrics


# --------------------------------------------------------------------------- #
# 4–5. token counter + exact vs estimated
# --------------------------------------------------------------------------- #


def test_token_counter_labels_estimated():
    counter = TokenCounter(model="gpt-4")
    m = counter.count_text("hello world from OverHaust")
    assert m.value is not None and m.value > 0
    assert m.kind == TokenKind.ESTIMATED
    assert m.source == MeasurementSource.ESTIMATED


def test_exact_vs_estimated_classification():
    est = TokenCounter().count_text("abc")
    exact = TokenCounter.record_exact(42, note="provider")
    assert est.kind == TokenKind.ESTIMATED
    assert exact.kind == TokenKind.EXACT
    assert TokenCounter.classify(est) == "estimated_token_count"
    assert TokenCounter.classify(exact) == "exact_token_count"
    with pytest.raises(ValueError, match="mix"):
        assert_kinds_not_mixed([est, exact])


# --------------------------------------------------------------------------- #
# 6–7. reduction calculation + invalid denominator
# --------------------------------------------------------------------------- #


def test_reduction_percent_formula():
    assert reduce_percent(100, 40) == 60.0
    assert reduce_percent(200, 150) == 25.0


def test_reduction_invalid_denominator_returns_null():
    assert reduce_percent(0, 10) is None
    assert reduce_percent(None, 10) is None
    assert reduce_percent(10, None) is None
    empty = pair_reduction([], [], "total_tokens")
    assert empty["reduction_percent"] is None
    assert empty["baseline_mean"] is None


# --------------------------------------------------------------------------- #
# 8–9. aggregation + repeated runs
# --------------------------------------------------------------------------- #


def test_aggregate_numeric_stats():
    stats = aggregate_numeric([10, 20, 30, None])
    assert stats["n"] == 3
    assert stats["mean"] == 20.0
    assert stats["median"] == 20.0
    assert stats["min"] == 10.0
    assert stats["max"] == 30.0
    assert stats["stdev"] is not None


def test_repeated_runs_retained_individually(fixture_project, initial_tasks):
    tasks = [t for t in initial_tasks if t.task_id == "sym_generate_kot"]
    records = run_condition_suite(
        "overhaust", tasks, runs=3, fixture=fixture_project
    )
    assert len(records) == 3
    assert {r.run_index for r in records} == {1, 2, 3}
    report = build_report(records)
    # Individual runs preserved — not only averages.
    assert len(report["runs"]) == 3
    agg = report["summary"]["per_task"]["sym_generate_kot"]["overhaust"]["context_tokens"]
    assert agg["n"] == 3


# --------------------------------------------------------------------------- #
# 10–11. JSON serialization + comparison output
# --------------------------------------------------------------------------- #


def test_json_result_serialization_and_compare(tmp_path, initial_tasks):
    report = run_benchmark(
        compare=True,
        task_set="initial",
        runs=1,
        task_ids=["sym_generate_kot"],
        results_dir=tmp_path,
    )
    json_path = Path(report["_output_paths"]["json"])
    md_path = Path(report["_output_paths"]["md"])
    assert json_path.exists() and md_path.exists()
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["benchmark_version"]
    assert len(loaded["runs"]) == 2  # baseline + overhaust
    conditions = {r["condition"] for r in loaded["runs"]}
    assert conditions == {"baseline", "overhaust"}
    cmp_ = loaded["summary"]["overall_comparison"]
    assert "context_token_reduction" in cmp_
    assert "cost_accounting" in cmp_
    assert cmp_["cost_accounting"]["indexing_included_in_totals"] is False
    assert "QUERY-TIME" in cmp_["cost_accounting"]["note"]
    md = md_path.read_text(encoding="utf-8")
    assert "sym_generate_kot" in md
    assert "null" in md or "Reduction" in md


def test_manual_ingest_does_not_invent_tokens(tmp_path, initial_tasks):
    task = next(t for t in initial_tasks if t.task_id == "sym_generate_kot")
    manual = {
        "task_id": task.task_id,
        "condition": "baseline",
        "timestamp": "2026-01-01T00:00:00Z",
        "model": "external-agent",
        "answer_text": (
            "generateKOT is defined in kot_generator and returns an object "
            "with orderId and items."
        ),
        "input_tokens": 1200,
        "output_tokens": 200,
        "total_tokens": 1400,
        "input_tokens_kind": TokenKind.EXACT.value,
        "output_tokens_kind": TokenKind.EXACT.value,
        "total_tokens_kind": TokenKind.EXACT.value,
        "tool_calls": 7,
        "files_inspected": 4,
        "measurement_source": MeasurementSource.MANUAL.value,
    }
    path = tmp_path / "manual.json"
    path.write_text(json.dumps({"runs": [manual]}), encoding="utf-8")
    report = run_benchmark(
        task_set="initial",
        ingest_paths=[path],
        task_ids=[task.task_id],
        results_dir=tmp_path / "out",
    )
    run = report["runs"][0]
    assert run["measurement_source"] == "MANUAL"
    assert run["total_tokens"] == 1400
    assert run["total_tokens_kind"] == "exact_token_count"
    assert run["correctness"] is True


# --------------------------------------------------------------------------- #
# 12. deterministic correctness
# --------------------------------------------------------------------------- #


def test_deterministic_correctness_checks(initial_tasks):
    task = next(t for t in initial_tasks if t.task_id == "sym_generate_kot")
    good = evaluate_answer(
        task,
        "generateKOT lives in kot_generator.ts and returns { orderId, items, printedAt }.",
    )
    assert good.correct is True
    assert "generateKOT" in good.required_facts_found
    assert good.evidence_score is not None and good.evidence_score > 0

    bad = evaluate_answer(task, "I have no idea.")
    assert bad.correct is False
    assert bad.required_facts_missing

    none = evaluate_answer(task, None)
    assert none.correct is None


# --------------------------------------------------------------------------- #
# 13. no modification of production context configuration
# --------------------------------------------------------------------------- #


def test_harness_does_not_alter_production_context_config():
    """
    The runners module must call invoke_context_request without overriding
    max_files / max_symbols / max_evidence / include_code_flow.
    """
    import benchmarks.runners as runners_mod

    src = inspect.getsource(runners_mod.run_overhaust_condition)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name == "invoke_context_request":
                kw = {k.arg for k in node.keywords if k.arg}
                # Allowed: project_id (positional), prompt, memory_store only.
                forbidden = {"max_files", "max_symbols", "max_evidence",
                             "include_code_flow", "max_prompt_length"}
                assert not (kw & forbidden), f"must not override budgets: {kw}"


def test_benchmark_package_does_not_import_into_context_engine():
    """Production context modules must not import the benchmarks package."""
    context_dir = ROOT / "packages" / "context"
    for path in context_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "import benchmarks" not in text
        assert "from benchmarks" not in text
