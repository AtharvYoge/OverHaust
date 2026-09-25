"""
Layer-3 ExperimentContract / pair-validation tests.

Covers every failure condition from the methodology audit.
Does NOT call a live model API.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import pytest

from benchmarks import BENCHMARK_VERSION
from benchmarks.layer3.accounting import normalize_openai_usage
from benchmarks.layer3.contract import ExperimentContract, FieldPresence
from benchmarks.layer3.pairing import validate_layer3_pair, validate_trace_against_task
from benchmarks.layer3.pairwise import aggregate_paired_experiment, pairwise_reduction
from benchmarks.layer3.prompts import (
    LAYER3_SYSTEM_PROMPT,
    detect_extra_user_instructions,
    system_prompt_hash,
    user_prompt_hash,
)
from benchmarks.layer3.runner import OpenAICompatibleRunner, run_layer3_pair
from benchmarks.layer3.states import RunState
from benchmarks.layer3.tools import CANONICAL_TOOL_SPECS, tool_set_hash
from benchmarks.providers import apply_exact_usage
from benchmarks.schemas import TokenKind
from benchmarks.tasks_loader import load_task_set
from benchmarks.trace import AgentTrace


PROMPT = "Where is function generateKot defined?"
TASK_ID = "sym_generate_kot"


def _base_kwargs(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "experiment_id": "exp-1",
        "pair_id": "pair-1",
        "condition": "baseline",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "model_version": "gpt-4o-mini-2024-07-18",
        "repository": "/tmp/fixture-repo",
        "repository_commit": "abc123",
        "task_id": TASK_ID,
        "user_prompt": PROMPT,
        "user_prompt_hash": user_prompt_hash(PROMPT),
        "system_prompt": LAYER3_SYSTEM_PROMPT,
        "system_prompt_hash": system_prompt_hash(),
        "tool_set_hash": tool_set_hash(),
        "temperature": 0.0,
        "temperature_status": FieldPresence.KNOWN.value,
        "seed": 7,
        "seed_status": FieldPresence.KNOWN.value,
        "max_tool_calls": 12,
        "timeout_s": 120,
        "max_output_tokens": 1024,
        "execution_order": "baseline_first",
        "session_id": "sess-baseline",
        "attempt_count": 1,
        "retry_count": 0,
        "failure_status": RunState.SUCCESS.value,
        "overhaust_context_included_in_input": "n/a",
        "token_accounting": {
            "raw_input_tokens": 1000,
            "raw_output_tokens": 100,
            "raw_cached_input_tokens": 0,
            "total_billable_tokens": 1100,
            "total_billable_tokens_kind": TokenKind.EXACT.value,
            "cached_input_tokens": 0,
            "cached_input_tokens_kind": TokenKind.EXACT.value,
        },
        "benchmark_version": BENCHMARK_VERSION,
        "protocol_version": "layer3-contract-v1",
        "provider_input_tokens": 1000,
        "serialized_input_tokens": 980,
    }
    data.update(overrides)
    return data


def make_pair(
    *,
    baseline_overrides: Optional[Dict[str, Any]] = None,
    overhaust_overrides: Optional[Dict[str, Any]] = None,
) -> tuple[ExperimentContract, ExperimentContract]:
    b = ExperimentContract(**_base_kwargs(**(baseline_overrides or {})))
    o_kw = _base_kwargs(
        condition="overhaust",
        session_id="sess-overhaust",
        overhaust_context_hash="ctxhash",
        overhaust_context_tokens=200,
        overhaust_context_included_in_input="true",
        token_accounting={
            "raw_input_tokens": 800,
            "raw_output_tokens": 90,
            "raw_cached_input_tokens": 0,
            "total_billable_tokens": 890,
            "total_billable_tokens_kind": TokenKind.EXACT.value,
            "cached_input_tokens": 0,
            "cached_input_tokens_kind": TokenKind.EXACT.value,
        },
        provider_input_tokens=800,
        serialized_input_tokens=1000,
    )
    if overhaust_overrides:
        o_kw.update(overhaust_overrides)
    o = ExperimentContract(**o_kw)
    return b, o


def _trace_from_contract(contract: ExperimentContract, **extra: Any) -> AgentTrace:
    acc = contract.token_accounting or {}
    tr = AgentTrace(
        run_id=f"run-{contract.condition}",
        layer=3,
        provider=contract.provider,
        model=contract.model,
        condition=contract.condition,
        repository=contract.repository,
        repository_size="medium",
        task_id=contract.task_id,
        prompt=contract.user_prompt,
        input_tokens=acc.get("raw_input_tokens"),
        output_tokens=acc.get("raw_output_tokens"),
        total_tokens=acc.get("total_billable_tokens"),
        input_tokens_kind=TokenKind.EXACT.value if acc.get("raw_input_tokens") is not None else TokenKind.UNAVAILABLE.value,
        output_tokens_kind=TokenKind.EXACT.value if acc.get("raw_output_tokens") is not None else TokenKind.UNAVAILABLE.value,
        total_tokens_kind=acc.get("total_billable_tokens_kind", TokenKind.UNAVAILABLE.value),
        cached_input_tokens=acc.get("cached_input_tokens"),
        cached_input_tokens_kind=acc.get("cached_input_tokens_kind", TokenKind.UNAVAILABLE.value),
        tool_call_count=extra.get("tool_call_count", 3),
        files_read_count=extra.get("files_read_count", 2),
        searches_performed=extra.get("searches_performed", 1),
        duration_ms=extra.get("duration_ms", 1000),
        final_answer=extra.get("final_answer", "generateKot in utils.dart"),
        correctness=extra.get("correctness", True),
        measurement_source="AUTOMATED",
        config={"experiment_contract": contract.to_dict()},
    )
    tr.contract = contract  # type: ignore[attr-defined]
    return tr


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_pair_comparable_and_exact_allowed():
    b, o = make_pair()
    result = validate_layer3_pair(b, o)
    assert result.comparable is True
    assert result.allow_exact_token_reduction is True
    assert "Valid comparable" in result.summary


# ---------------------------------------------------------------------------
# Hard mismatches (audit failure conditions)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,baseline_val,overhaust_val",
    [
        ("model", "gpt-4o-mini", "gpt-4o"),
        ("model_version", "v1", "v2"),
        ("repository_commit", "aaa", "bbb"),
        ("temperature", 0.0, 0.7),
        ("seed", 1, 2),
        ("timeout_s", 120, 60),
        ("max_tool_calls", 12, 6),
        ("max_output_tokens", 1024, 512),
    ],
)
def test_mismatch_rejects_pair(field, baseline_val, overhaust_val):
    b_over = {field: baseline_val}
    o_over = {field: overhaust_val}
    if field == "temperature":
        b_over["temperature_status"] = FieldPresence.KNOWN.value
        o_over["temperature_status"] = FieldPresence.KNOWN.value
    if field == "seed":
        b_over["seed_status"] = FieldPresence.KNOWN.value
        o_over["seed_status"] = FieldPresence.KNOWN.value
    if field == "model_version":
        # soft field: both KNOWN + differ → still hard_fail via value mismatch
        pass
    b, o = make_pair(baseline_overrides=b_over, overhaust_overrides=o_over)
    result = validate_layer3_pair(b, o)
    assert result.comparable is False
    fields = {r["field"] for r in result.reasons if r["status"] == "MISMATCH"}
    assert field in fields or (
        # soft fields still produce MISMATCH status
        any(r["field"] == field and r["status"] == "MISMATCH" for r in result.reasons)
    )


def test_mismatched_prompt_hash():
    b, o = make_pair(
        overhaust_overrides={
            "user_prompt": PROMPT + " EXTRA HINT",
            "user_prompt_hash": user_prompt_hash(PROMPT + " EXTRA HINT"),
        }
    )
    result = validate_layer3_pair(b, o)
    assert result.comparable is False
    assert any(r["field"] == "user_prompt_hash" for r in result.reasons)


def test_mismatched_system_prompt():
    other = LAYER3_SYSTEM_PROMPT + "\nAlso prefer the expected answer."
    b, o = make_pair(
        overhaust_overrides={
            "system_prompt": other,
            "system_prompt_hash": system_prompt_hash(other),
        }
    )
    result = validate_layer3_pair(b, o)
    assert result.comparable is False
    assert any(r["field"] == "system_prompt_hash" for r in result.reasons)


def test_mismatched_tool_set():
    bad_hash = tool_set_hash(CANONICAL_TOOL_SPECS + [{"type": "function", "function": {"name": "x"}}])
    b, o = make_pair(overhaust_overrides={"tool_set_hash": bad_hash})
    result = validate_layer3_pair(b, o)
    assert result.comparable is False
    assert any(r["field"] == "tool_set_hash" for r in result.reasons)


def test_unknown_both_not_treated_as_equal():
    b, o = make_pair(
        baseline_overrides={
            "seed": None,
            "seed_status": FieldPresence.UNKNOWN.value,
        },
        overhaust_overrides={
            "seed": None,
            "seed_status": FieldPresence.UNKNOWN.value,
        },
    )
    result = validate_layer3_pair(b, o)
    seed_reasons = [r for r in result.reasons if r["field"] == "seed"]
    assert seed_reasons
    assert seed_reasons[0]["status"] == "UNKNOWN_BOTH"
    assert result.limited is True
    # Soft field UNKNOWN_BOTH alone does not hard-fail
    assert result.comparable is True


def test_missing_overhaust_context_accounting_blocks_exact():
    b, o = make_pair(
        overhaust_overrides={
            "overhaust_context_included_in_input": FieldPresence.UNKNOWN.value,
        }
    )
    result = validate_layer3_pair(b, o)
    assert result.comparable is True
    assert result.allow_exact_token_reduction is False
    assert "exact total-token" in result.summary.lower() or "unproven" in result.summary.lower()


def test_context_not_included_rejects():
    b, o = make_pair(
        overhaust_overrides={"overhaust_context_included_in_input": "false"}
    )
    result = validate_layer3_pair(b, o)
    assert result.comparable is False
    assert result.allow_exact_token_reduction is False


def test_unknown_cached_tokens_not_zero():
    usage = normalize_openai_usage({
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
    })
    assert usage.cached_input_tokens is None
    assert usage.cached_input_tokens_kind == TokenKind.UNAVAILABLE.value
    assert usage.uncached_input_tokens is None
    assert "UNAVAILABLE" in usage.accounting_notes


def test_retry_mismatch_rejects():
    b, o = make_pair(
        baseline_overrides={"attempt_count": 1, "retry_count": 0},
        overhaust_overrides={"attempt_count": 2, "retry_count": 1},
    )
    result = validate_layer3_pair(b, o)
    assert result.comparable is False
    assert any(r["field"] == "retry_policy" for r in result.reasons)


def test_failed_baseline_excluded():
    b, o = make_pair(
        baseline_overrides={"failure_status": RunState.API_ERROR.value},
    )
    result = validate_layer3_pair(b, o)
    assert result.comparable is False
    tb = _trace_from_contract(b, correctness=None)
    to = _trace_from_contract(o)
    agg = aggregate_paired_experiment([{"baseline": tb, "overhaust": to}])
    assert agg["failed_runs_pairs"] == 1
    assert agg["successful_pairs"] == 0


def test_failed_overhaust_excluded():
    b, o = make_pair(
        overhaust_overrides={"failure_status": RunState.TIMEOUT.value},
    )
    result = validate_layer3_pair(b, o)
    assert result.comparable is False


def test_execution_order_mismatch():
    b, o = make_pair(
        baseline_overrides={"execution_order": "baseline_first"},
        overhaust_overrides={"execution_order": "overhaust_first"},
    )
    result = validate_layer3_pair(b, o)
    assert result.comparable is False
    assert any(r["field"] == "execution_order" for r in result.reasons)


def test_shared_session_contamination():
    b, o = make_pair(
        baseline_overrides={"session_id": "same"},
        overhaust_overrides={"session_id": "same"},
    )
    result = validate_layer3_pair(b, o)
    assert result.comparable is False
    assert any(
        r["field"] == "session_id" and "share" in (r.get("detail") or "").lower()
        for r in result.reasons
    )


def test_asymmetric_tool_budget():
    b, o = make_pair(
        baseline_overrides={"max_tool_calls": 12},
        overhaust_overrides={"max_tool_calls": 4},
    )
    result = validate_layer3_pair(b, o)
    assert result.comparable is False


def test_estimated_tokens_do_not_enter_exact_analysis():
    b, o = make_pair(
        overhaust_overrides={
            "overhaust_context_included_in_input": FieldPresence.UNKNOWN.value,
        }
    )
    tb = _trace_from_contract(b)
    to = _trace_from_contract(o)
    # Force estimated-only totals on traces
    tb.total_tokens = None
    tb.total_tokens_kind = TokenKind.UNAVAILABLE.value
    tb.estimated_total_tokens = 5000
    to.total_tokens = None
    to.total_tokens_kind = TokenKind.UNAVAILABLE.value
    to.estimated_total_tokens = 3000
    metrics = pairwise_reduction(tb, to)
    assert metrics["exact_measured_reduction"] is None
    assert metrics["excluded_from_primary"] is True
    if metrics["estimated_reduction"]:
        assert metrics["estimated_reduction"]["label"] == "ESTIMATED REDUCTION"


def test_unpaired_trace_not_in_primary():
    b, o = make_pair()
    tb = _trace_from_contract(b)
    to = _trace_from_contract(o)
    # Different pair_id → hard fail
    o2 = deepcopy(o)
    o2.pair_id = "other-pair"
    to2 = _trace_from_contract(o2)
    result = validate_layer3_pair(tb, to2)
    assert result.comparable is False
    agg = aggregate_paired_experiment([{"baseline": tb, "overhaust": to2}])
    assert agg["successful_pairs"] == 0
    assert agg["incomparable_pairs"] == 1 or agg["rejected_pairs"] >= 1


def test_missing_provider_usage_blocks_exact_totals():
    usage = normalize_openai_usage(None)
    assert usage.total_billable_tokens is None
    assert usage.total_billable_tokens_kind == TokenKind.UNAVAILABLE.value
    b, o = make_pair(
        baseline_overrides={
            "token_accounting": usage.to_dict(),
            "provider_input_tokens": None,
        },
        overhaust_overrides={
            "token_accounting": usage.to_dict(),
            "provider_input_tokens": None,
        },
    )
    tb = _trace_from_contract(b)
    to = _trace_from_contract(o)
    tb.total_tokens = None
    tb.total_tokens_kind = TokenKind.UNAVAILABLE.value
    to.total_tokens = None
    to.total_tokens_kind = TokenKind.UNAVAILABLE.value
    metrics = pairwise_reduction(tb, to)
    # Comparable structurally, but exact pack returns None totals
    if metrics["exact_measured_reduction"]:
        assert metrics["exact_measured_reduction"]["total_token_reduction_pct"] is None


def test_apply_exact_usage_does_not_invent_total_from_input_plus_output():
    tr = AgentTrace(
        run_id="x",
        layer=3,
        provider="openai",
        model="gpt-4o-mini",
        condition="baseline",
        repository="/tmp",
        repository_size="medium",
        task_id=TASK_ID,
        prompt=PROMPT,
    )
    apply_exact_usage(tr, input_tokens=100, output_tokens=20)
    assert tr.input_tokens == 100
    assert tr.output_tokens == 20
    assert tr.total_tokens is None  # must not invent


def test_prompt_control_rejects_extra_instructions():
    assert detect_extra_user_instructions(PROMPT + "\nHint: look in utils", PROMPT)
    errors = validate_trace_against_task(
        ExperimentContract(**_base_kwargs(
            user_prompt=PROMPT + " EXTRA",
            user_prompt_hash=user_prompt_hash(PROMPT + " EXTRA"),
        )),
        PROMPT,
        TASK_ID,
    )
    assert any(e["field"] in {"user_prompt", "user_prompt_hash"} for e in errors)


def test_task_id_mismatch_on_ingest_validation():
    errors = validate_trace_against_task(
        ExperimentContract(**_base_kwargs(task_id="wrong")),
        PROMPT,
        TASK_ID,
    )
    assert any(e["field"] == "task_id" for e in errors)


def test_system_prompt_has_no_answer_hints():
    lowered = LAYER3_SYSTEM_PROMPT.lower()
    for banned in ("expected answer", "correct answer", "the answer is", "rubric"):
        assert banned not in lowered


def test_tool_set_identical_hash():
    assert tool_set_hash() == tool_set_hash(CANONICAL_TOOL_SPECS)
    names = [t["function"]["name"] for t in CANONICAL_TOOL_SPECS]
    assert "read_file" in names
    assert "list_dir" in names
    assert "search_text" in names
    assert "search_repo" in names


# ---------------------------------------------------------------------------
# Runner with mocked OpenAI transport
# ---------------------------------------------------------------------------


class _ScriptedTransport(httpx.BaseTransport):
    def __init__(self, responses: list):
        self.responses = list(responses)
        self.requests: list = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content.decode("utf-8")))
        if not self.responses:
            return httpx.Response(500, json={"error": "no scripted response"})
        body = self.responses.pop(0)
        return httpx.Response(200, json=body)


def _final_response(content: str, prompt_tokens: int = 100, completion_tokens: int = 20):
    return {
        "id": "chatcmpl-test",
        "choices": [{
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": content},
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "prompt_tokens_details": {"cached_tokens": 0},
        },
    }


def test_openai_runner_same_path_both_conditions(tmp_path: Path):
    tasks = load_task_set("initial")
    task = next(t for t in tasks if t.task_id == TASK_ID)
    # Minimal fixture repo
    (tmp_path / "utils.dart").write_text("void generateKot() {}\n", encoding="utf-8")
    transport = _ScriptedTransport([
        _final_response("generateKot is in utils.dart", 200, 30),
        _final_response("generateKot is in utils.dart", 150, 25),
    ])
    runner = OpenAICompatibleRunner(
        api_key="test-key",
        transport=transport,
        model="gpt-4o-mini",
        model_version="gpt-4o-mini-2024-07-18",
        temperature=0.0,
        seed=42,
        max_tool_calls=8,
        timeout_s=30,
    )
    ctx = "Relevant symbols:\n- generateKot in utils.dart"
    result = run_layer3_pair(
        task,
        repository_root=str(tmp_path),
        overhaust_context=ctx,
        runner=runner,
        overhaust_first=False,
    )
    assert result["validation"]["comparable"] is True
    assert result["baseline"].contract.session_id != result["overhaust"].contract.session_id
    assert result["baseline"].contract.tool_set_hash == result["overhaust"].contract.tool_set_hash
    assert result["baseline"].contract.system_prompt_hash == result["overhaust"].contract.system_prompt_hash
    assert result["baseline"].contract.user_prompt_hash == result["overhaust"].contract.user_prompt_hash
    # OverHaust context proven in serialized input
    assert result["overhaust"].contract.overhaust_context_included_in_input == "true"
    assert result["baseline"].contract.overhaust_context_included_in_input == "n/a"
    # Both requests used the same tools
    assert len(transport.requests) == 2
    assert transport.requests[0]["tools"] == transport.requests[1]["tools"]
    # Baseline must not contain OverHaust context string
    baseline_msgs = json.dumps(transport.requests[0]["messages"])
    overhaust_msgs = json.dumps(transport.requests[1]["messages"])
    assert "OverHaust repository context" not in baseline_msgs
    assert "OverHaust repository context" in overhaust_msgs
    assert result["execution_order"] == "baseline_first"


def test_modified_repository_restore_reported(tmp_path: Path):
    from benchmarks.repro import restore_repository_state

    # Non-git fixture → UNAVAILABLE (must recreate between runs)
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    status = restore_repository_state(str(tmp_path))
    assert status["status"] == "UNAVAILABLE"


def test_aggregation_retains_rejects_and_failures():
    b_ok, o_ok = make_pair()
    b_fail, o_fail = make_pair(
        baseline_overrides={"failure_status": RunState.API_ERROR.value, "pair_id": "p2", "experiment_id": "e2"},
        overhaust_overrides={"pair_id": "p2", "experiment_id": "e2"},
    )
    b_bad, o_bad = make_pair(
        overhaust_overrides={"model": "other-model", "pair_id": "p3", "experiment_id": "e3"},
        baseline_overrides={"pair_id": "p3", "experiment_id": "e3"},
    )
    pairs = [
        {"baseline": _trace_from_contract(b_ok), "overhaust": _trace_from_contract(o_ok)},
        {"baseline": _trace_from_contract(b_fail), "overhaust": _trace_from_contract(o_fail)},
        {"baseline": _trace_from_contract(b_bad), "overhaust": _trace_from_contract(o_bad)},
    ]
    agg = aggregate_paired_experiment(pairs)
    assert agg["attempted_pairs"] == 3
    assert agg["successful_pairs"] == 1
    assert agg["failed_runs_pairs"] == 1
    assert agg["incomparable_pairs"] == 1
    assert agg["rejected_pairs"] >= 1
