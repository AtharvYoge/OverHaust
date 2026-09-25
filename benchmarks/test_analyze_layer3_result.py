"""Read-only Layer 3 distribution analysis."""

import json

from benchmarks.analyze_layer3_result import analyze_layer3_result


def _pair(task, rep, b_tot, o_tot, b_in, o_in, b_out, o_out, *, status="SUCCESS", error=None):
    pct = round((b_tot - o_tot) / b_tot * 100.0, 4) if status == "SUCCESS" else None
    in_pct = round((b_in - o_in) / b_in * 100.0, 4) if status == "SUCCESS" else None
    out_pct = round((b_out - o_out) / b_out * 100.0, 4) if status == "SUCCESS" else None
    red = None
    if status == "SUCCESS":
        red = {
            "label": "EXACT MEASURED REDUCTION",
            "total_token_reduction_pct": pct,
            "input_token_reduction_pct": in_pct,
            "output_token_change_pct": out_pct,
        }
    def side(condition, total, inp, out, failure):
        return {
            "model": "gpt-4o-mini",
            "repository_size": "small",
            "total_tokens": total,
            "input_tokens": inp,
            "output_tokens": out,
            "total_tokens_kind": "exact_token_count",
            "tool_call_count": 1,
            "correctness": True,
            "error": error if failure != "SUCCESS" else None,
            "config": {
                "experiment_contract": {
                    "condition": condition,
                    "model": "gpt-4o-mini",
                    "model_version": "gpt-4o-mini",
                    "user_prompt_hash": "p",
                    "system_prompt_hash": "s",
                    "tool_set_hash": "t",
                    "repository": "/tmp/repo",
                    "repository_commit": "abc",
                    "max_tool_calls": 4,
                    "timeout_s": 30,
                    "max_output_tokens": 128,
                    "temperature": 0.0,
                    "session_id": f"sess-{condition}",
                    "failure_status": failure,
                    "overhaust_context_included_in_input": "true" if condition == "overhaust" else "n/a",
                    "field_presence": {"model": "KNOWN"},
                }
            },
        }
    b_status = status if status != "SUCCESS" else "SUCCESS"
    return {
        "task_id": task,
        "repetition": rep,
        "pair_id": f"{task}-{rep}",
        "execution_order": "baseline_first",
        "repository_restore": [{"status": "UNAVAILABLE"}],
        "validation": {
            "comparable": status == "SUCCESS",
            "allow_exact_token_reduction": status == "SUCCESS",
        },
        "pairwise_metrics": {"exact_measured_reduction": red},
        "baseline": side("baseline", b_tot, b_in, b_out, b_status),
        "overhaust": side("overhaust", o_tot, o_in, o_out, "SUCCESS"),
    }


def test_analysis_keeps_failed_pair_and_flags_iqr_outlier():
    payload = {
        "mode": "live_openai",
        "task_set": "missing-set",
        "repo_size": "small",
        "model": "gpt-4o-mini",
        "provider": "openai",
        "runs": 1,
        "pairs": [
            _pair("a", 0, 1000, 800, 900, 700, 100, 100),
            _pair("a", 1, 1000, 790, 900, 690, 100, 100),
            _pair("a", 2, 1000, 805, 900, 705, 100, 100),
            _pair("a", 3, 1000, 795, 900, 695, 100, 100),
            _pair("b", 0, 1000, 5000, 900, 4900, 100, 100),
            _pair("c", 0, 4000, 1000, 3800, 800, 200, 200, status="INCOMPLETE", error="max_tool_calls exhausted"),
        ],
    }
    before = json.dumps(payload)
    report = analyze_layer3_result(payload)
    assert json.dumps(payload) == before
    assert report["counts"]["attempted_pairs"] == 6
    assert report["counts"]["primary_exact_pairs"] == 5
    assert report["counts"]["non_primary_pairs"] == 1
    assert report["non_primary_rows"][0]["task_id"] == "c"
    assert report["non_primary_rows"][0]["baseline_status"] == "INCOMPLETE"
    assert report["distribution"]["n"] == 5
    assert any(row["task_id"] == "b" for row in report["outliers"])
    assert report["distribution_outliers_excluded"]["n"] == 4
    assert report["distribution"]["mean"] != report["distribution_outliers_excluded"]["mean"]
    assert report["distribution"]["min"] == min(
        row["total_token_reduction_pct"] for row in report["primary_rows"]
    )
    assert report["contract_audit"]["checks"]["restore_unavailable"] == 6
    assert report["contract_audit"]["checks"]["model_mismatch"] == 0
