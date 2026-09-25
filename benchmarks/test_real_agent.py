"""Tests for Layer 2–4 real-agent benchmark infrastructure."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.breakeven import break_even_queries
from benchmarks.evaluate import evaluate_answer, evaluate_rubric
from benchmarks.experiment import run_layer2_benchmark, run_layer3_ingest
from benchmarks.matrix import empty_matrix, fill_matrix_from_traces
from benchmarks.providers import ProviderNotConfiguredError, ingest_layer3_trace, require_provider
from benchmarks.repos import count_source_files, prepare_sized_fixture
from benchmarks.report import build_layered_report
from benchmarks.schemas import AnswerRubric, BenchmarkTask, aggregate_numeric, reduce_percent
from benchmarks.sim_agent import run_layer2_pair, run_simulated_agent
from benchmarks.tasks_loader import load_task_set
from benchmarks.trace import AgentTrace


TASKS = Path(__file__).resolve().parent / "tasks"


@pytest.fixture(scope="module")
def medium_fixture():
    fx = prepare_sized_fixture("medium")
    yield fx
    fx.close()


def test_repo_sizes_differ():
    small = prepare_sized_fixture("small")
    medium = prepare_sized_fixture("medium")
    large = prepare_sized_fixture("large")
    try:
        ns = count_source_files(small.root)
        nm = count_source_files(medium.root)
        nl = count_source_files(large.root)
        assert ns < nm < nl
        assert ns <= 3
        assert nl >= 40
    finally:
        small.close()
        medium.close()
        large.close()


def test_aggregate_has_percentiles_and_ci():
    stats = aggregate_numeric([10, 20, 30, 40, 50])
    assert stats["p25"] is not None and stats["p75"] is not None
    assert stats["ci95_low"] is not None and stats["ci95_high"] is not None
    assert stats["n"] == 5


def test_rubric_defined_before_results():
    tasks = load_task_set("initial", tasks_dir=TASKS)
    for t in tasks:
        r = t.get_rubric()
        assert isinstance(r, AnswerRubric)
        assert r.required_facts or r.required_symbols or r.required_files or r.required_any_of


def test_adversarial_task_set_loads():
    tasks = load_task_set("adversarial", tasks_dir=TASKS)
    assert len(tasks) >= 4
    assert any(t.adversarial for t in tasks)


def test_layer2_baseline_vs_overhaust_comparable(medium_fixture):
    task = next(t for t in load_task_set("initial", tasks_dir=TASKS) if t.task_id == "sym_generate_kot")
    pair = run_layer2_pair(task, fixture=medium_fixture, max_tool_calls=8)
    b, o = pair["baseline"], pair["overhaust"]
    assert b.layer == 2 and o.layer == 2
    assert b.condition == "baseline" and o.condition == "overhaust"
    assert b.tool_call_count is not None and o.tool_call_count is not None
    assert b.estimated_total_tokens is not None
    assert o.estimated_total_tokens is not None
    # Exact provider fields must remain null in Layer 2.
    assert b.total_tokens is None and o.total_tokens is None
    assert b.input_tokens_kind == "unavailable"
    assert o.overhaust_context_tokens is not None
    assert b.overhaust_context_tokens is None
    assert b.correctness is not None and o.correctness is not None
    assert b.reproducibility.get("benchmark_version")


def test_layer2_can_show_negative_savings_on_tiny_repo():
    """Infrastructure must allow negative reductions (tiny repo case)."""
    fx = prepare_sized_fixture("small")
    try:
        task = next(
            t for t in load_task_set("adversarial", tasks_dir=TASKS)
            if t.task_id == "adv_tiny_one_file"
        )
        pair = run_layer2_pair(task, fixture=fx, max_tool_calls=6)
        b_tok = pair["baseline"].estimated_total_tokens
        o_tok = pair["overhaust"].estimated_total_tokens
        assert b_tok is not None and o_tok is not None
        # Do not assert direction — only that reduction % can be computed (incl. negative).
        pct = reduce_percent(b_tok, o_tok)
        assert pct is not None
    finally:
        fx.close()


def test_layer2_experiment_writes_report(tmp_path):
    report = run_layer2_benchmark(
        task_set="initial",
        runs=2,
        task_ids=["sym_generate_kot"],
        repo_size="medium",
        results_dir=tmp_path,
        seed=7,
        shuffle=True,
    )
    assert report["layer"] == 2
    assert len(report["traces"]) == 4  # 2 runs × 2 conditions
    assert Path(report["_output_paths"]["json"]).exists()
    assert Path(report["_output_paths"]["md"]).exists()
    layered = report["layered_report"]
    assert "A_exact_measured_results" in layered
    assert "B_estimated_results" in layered
    assert "C_unsupported_claims" in layered
    assert layered["A_exact_measured_results"]["n_traces_with_exact_totals"] == 0
    assert "No percentage token reduction should be claimed" in layered["claim_policy"]


def test_break_even_insufficient_without_costs():
    r = break_even_queries(
        indexing_cost=None,
        baseline_per_query_cost=100,
        overhaust_per_query_cost=40,
    )
    assert r["status"] == "insufficient_data"
    assert r["break_even_n"] is None


def test_break_even_computes_when_measured():
    r = break_even_queries(
        indexing_cost=300,
        baseline_per_query_cost=100,
        overhaust_per_query_cost=40,
    )
    assert r["status"] == "computed"
    assert r["break_even_n"] == 5  # ceil(300/60)


def test_break_even_never_when_no_savings():
    r = break_even_queries(
        indexing_cost=100,
        baseline_per_query_cost=40,
        overhaust_per_query_cost=50,
    )
    assert r["status"] == "never_breaks_even_at_measured_rates"


def test_layer3_provider_refuses_without_config():
    with pytest.raises(ProviderNotConfiguredError):
        require_provider()


def test_layer3_ingest_rejects_traces_without_contract(tmp_path):
    """Strict ingest must reject legacy traces missing ExperimentContract."""
    payload = {
        "traces": [
            {
                "run_id": "b1",
                "layer": 3,
                "provider": "openai",
                "model": "gpt-test",
                "condition": "baseline",
                "repository": "fixture:labkot_retrieval",
                "repository_size": "medium",
                "task_id": "sym_generate_kot",
                "prompt": "Where is generateKOT defined and what does it return?",
                "input_tokens": 1000,
                "output_tokens": 200,
                "total_tokens": 1200,
                "final_answer": "FOUND: generateKOT",
            },
        ]
    }
    path = tmp_path / "traces.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = run_layer3_ingest([path], task_set="initial", results_dir=tmp_path / "out")
    assert report["layer"] == 3
    layered = report["layered_report"]
    assert len(layered["rejected_ingest"]) >= 1
    assert layered["pair_aggregation"].get("successful_pairs", 0) == 0
    assert "No percentage token reduction should be claimed" in layered["claim_policy"]


def test_layer3_ingest_exact_tokens(tmp_path):
    from benchmarks import BENCHMARK_VERSION
    from benchmarks.layer3.contract import ExperimentContract, FieldPresence
    from benchmarks.layer3.prompts import system_prompt_hash, user_prompt_hash
    from benchmarks.layer3.states import RunState
    from benchmarks.layer3.tools import tool_set_hash
    from benchmarks.schemas import TokenKind

    prompt = "Where is generateKOT defined and what does it return?"
    shared = dict(
        experiment_id="exp-ingest",
        pair_id="pair-ingest",
        provider="openai",
        model="gpt-test",
        model_version="gpt-test",
        repository="fixture:labkot_retrieval",
        repository_commit="commit-1",
        task_id="sym_generate_kot",
        user_prompt=prompt,
        user_prompt_hash=user_prompt_hash(prompt),
        system_prompt_hash=system_prompt_hash(),
        tool_set_hash=tool_set_hash(),
        temperature=0.0,
        temperature_status=FieldPresence.KNOWN.value,
        seed=1,
        seed_status=FieldPresence.KNOWN.value,
        max_tool_calls=12,
        timeout_s=120,
        max_output_tokens=1024,
        execution_order="baseline_first",
        attempt_count=1,
        retry_count=0,
        failure_status=RunState.SUCCESS.value,
        benchmark_version=BENCHMARK_VERSION,
        protocol_version="layer3-contract-v1",
    )
    b_contract = ExperimentContract(
        **shared,
        condition="baseline",
        session_id="sess-b",
        overhaust_context_included_in_input="n/a",
        token_accounting={
            "raw_input_tokens": 1000,
            "raw_output_tokens": 200,
            "total_billable_tokens": 1200,
            "total_billable_tokens_kind": TokenKind.EXACT.value,
            "cached_input_tokens": 100,
            "cached_input_tokens_kind": TokenKind.EXACT.value,
        },
    )
    o_contract = ExperimentContract(
        **shared,
        condition="overhaust",
        session_id="sess-o",
        overhaust_context_hash="ctx",
        overhaust_context_tokens=120,
        overhaust_context_included_in_input="true",
        token_accounting={
            "raw_input_tokens": 700,
            "raw_output_tokens": 180,
            "total_billable_tokens": 880,
            "total_billable_tokens_kind": TokenKind.EXACT.value,
            "cached_input_tokens": 0,
            "cached_input_tokens_kind": TokenKind.EXACT.value,
        },
    )
    payload = {
        "traces": [
            {
                "run_id": "b1",
                "layer": 3,
                "provider": "openai",
                "model": "gpt-test",
                "condition": "baseline",
                "repository": "fixture:labkot_retrieval",
                "repository_size": "medium",
                "task_id": "sym_generate_kot",
                "prompt": prompt,
                "input_tokens": 1000,
                "output_tokens": 200,
                "cached_input_tokens": 100,
                "total_tokens": 1200,
                "final_answer": (
                    "FOUND: generateKOT\nFOUND: kot_generator\nFOUND: orderId\n"
                    "FOUND file: src/kitchen/kot_generator.ts\nFOUND symbol: generateKOT"
                ),
                "duration_ms": 1500,
                "contract": b_contract.to_dict(),
            },
            {
                "run_id": "o1",
                "layer": 3,
                "provider": "openai",
                "model": "gpt-test",
                "condition": "overhaust",
                "repository": "fixture:labkot_retrieval",
                "repository_size": "medium",
                "task_id": "sym_generate_kot",
                "prompt": prompt,
                "input_tokens": 700,
                "output_tokens": 180,
                "total_tokens": 880,
                "final_answer": (
                    "FOUND: generateKOT\nFOUND: kot_generator\nFOUND: orderId\n"
                    "FOUND file: src/kitchen/kot_generator.ts\nFOUND symbol: generateKOT"
                ),
                "duration_ms": 900,
                "overhaust_context_tokens": 120,
                "overhaust_context_tokens_kind": "estimated_token_count",
                "contract": o_contract.to_dict(),
            },
        ]
    }
    path = tmp_path / "traces.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = run_layer3_ingest([path], task_set="initial", results_dir=tmp_path / "out")
    assert report["layer"] == 3
    layered = report["layered_report"]
    assert layered["pair_aggregation"]["successful_pairs"] == 1
    assert layered["pair_validations"][0]["comparable"] is True
    assert layered["pairwise_metrics"][0]["exact_measured_reduction"] is not None
    assert "No percentage token reduction should be claimed" in layered["claim_policy"]


def test_trace_refuses_estimated_in_exact_field():
    tr = AgentTrace(
        run_id="x", layer=3, provider="x", model="m", condition="baseline",
        repository="r", repository_size="small", task_id="t", prompt="p",
        total_tokens=10, total_tokens_kind="estimated_token_count",
    )
    with pytest.raises(ValueError, match="estimated"):
        tr.validate_token_kinds()


def test_matrix_starts_unknown_and_fills():
    m = empty_matrix()
    assert m["symbol_lookup"]["small"]["status"] == "unknown"
    # Build minimal traces
    traces = []
    for cond, total in (("baseline", 100), ("overhaust", 60)):
        for i in range(3):
            traces.append(AgentTrace(
                run_id=f"{cond}{i}", layer=2, provider="sim", model="m",
                condition=cond, repository="r", repository_size="medium",
                task_id="sym_generate_kot", prompt="p",
                estimated_total_tokens=total, correctness=True,
            ))
    filled = fill_matrix_from_traces(
        traces, task_categories={"sym_generate_kot": "symbol_lookup"}, min_reps=3
    )
    cell = filled["symbol_lookup"]["medium"]
    assert cell["status"] == "measured"
    assert cell["token_reduction_pct_median"] == 40.0


def test_control_variables_documented_in_protocol():
    text = (Path(__file__).resolve().parent / "REAL_AGENT_PROTOCOL.md").read_text()
    for needle in (
        "Same model",
        "max tool",
        "Layer 1/2",
        "break-even",
        "No percentage token reduction",
    ):
        assert needle.lower() in text.lower() or needle in text


def test_production_packages_untouched_by_imports():
    """benchmarks may call invoke_context_request but must not be imported by it."""
    root = Path(__file__).resolve().parents[1]
    for rel in ("packages/context", "packages/retrieval", "packages/integrations"):
        for path in (root / rel).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "import benchmarks" not in text
            assert "from benchmarks" not in text
