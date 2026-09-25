"""
Strict Layer-3 ingest: reject traces that violate the experiment contract / task prompt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from benchmarks.layer3.contract import ExperimentContract
from benchmarks.layer3.pairing import (
    validate_layer3_pair,
    validate_trace_against_task,
)
from benchmarks.layer3.pairwise import aggregate_paired_experiment, pairwise_reduction
from benchmarks.providers import ingest_layer3_trace
from benchmarks.schemas import BenchmarkTask
from benchmarks.tasks_loader import load_task_set
from benchmarks.trace import AgentTrace


class TraceRejected(ValueError):
    """Trace failed contract / task validation and must not be aggregated."""


def attach_contract(trace: AgentTrace, contract: ExperimentContract) -> AgentTrace:
    trace.contract = contract  # type: ignore[attr-defined]
    cfg = dict(trace.config or {})
    cfg["experiment_contract"] = contract.to_dict()
    trace.config = cfg
    return trace


def ingest_strict_trace(
    data: Dict[str, Any],
    *,
    task: BenchmarkTask,
) -> AgentTrace:
    raw_contract = data.get("contract") or data.get("experiment_contract") or (
        (data.get("config") or {}).get("experiment_contract")
    )
    if not raw_contract:
        raise TraceRejected("Layer-3 trace missing experiment_contract")
    contract = ExperimentContract.from_dict(raw_contract)
    errors = validate_trace_against_task(contract, task.prompt, task.task_id)
    if errors:
        raise TraceRejected(f"trace rejected: {errors}")
    # Ensure prompt fields aligned
    if contract.user_prompt.rstrip("\n") != task.prompt.rstrip("\n"):
        raise TraceRejected("user prompt diverges from task definition")
    trace = ingest_layer3_trace(data, task=task)
    return attach_contract(trace, contract)


def load_and_pair_traces(
    paths: Sequence[Path],
    *,
    task_set: str = "initial",
) -> Dict[str, Any]:
    tasks = {t.task_id: t for t in load_task_set(task_set)}
    traces: List[AgentTrace] = []
    rejected_ingest: List[Dict[str, Any]] = []
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        items = payload if isinstance(payload, list) else payload.get("traces", payload.get("runs", [payload]))
        for item in items:
            tid = item.get("task_id") or (item.get("contract") or {}).get("task_id")
            task = tasks.get(tid)
            if not task:
                rejected_ingest.append({"reason": f"unknown task_id {tid}", "item": item.get("run_id")})
                continue
            try:
                traces.append(ingest_strict_trace(item, task=task))
            except TraceRejected as exc:
                rejected_ingest.append({"reason": str(exc), "task_id": tid})

    # Group by pair_id
    by_pair: Dict[str, Dict[str, AgentTrace]] = {}
    unpaired: List[str] = []
    for tr in traces:
        contract = getattr(tr, "contract", None)
        if not contract:
            unpaired.append(tr.run_id)
            continue
        bucket = by_pair.setdefault(contract.pair_id, {})
        bucket[tr.condition] = tr

    pairs = []
    unpaired_traces = list(unpaired)
    for pair_id, conds in by_pair.items():
        if "baseline" in conds and "overhaust" in conds:
            pairs.append({"baseline": conds["baseline"], "overhaust": conds["overhaust"]})
        else:
            unpaired_traces.append(pair_id)

    aggregation = aggregate_paired_experiment(pairs) if pairs else {
        "attempted_pairs": 0,
        "successful_pairs": 0,
        "rejected_pairs": 0,
        "failed_runs_pairs": 0,
        "incomparable_pairs": 0,
        "note": "No complete pairs found.",
    }
    return {
        "traces": [t.to_dict() for t in traces],
        "rejected_ingest": rejected_ingest,
        "unpaired": unpaired_traces,
        "pair_aggregation": aggregation,
        "pair_validations": [
            validate_layer3_pair(p["baseline"], p["overhaust"]).to_dict()
            for p in pairs
        ],
        "pairwise_metrics": [
            pairwise_reduction(p["baseline"], p["overhaust"])
            for p in pairs
        ],
    }
