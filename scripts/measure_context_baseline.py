#!/usr/bin/env python3
"""
Baseline comparison: raw search hits vs compact get_relevant_context response.

DEPRECATED for product thesis validation — use scripts/agent_benchmark.py instead.
That script compares OverHaust against naïve agent full-file reads (fair baseline).

This script remains for quick diagnostics and legacy Phase 11 comparisons.

Usage:
  python3 scripts/measure_context_baseline.py --project-id labkot --prompt "..."

Requires a registered, indexed project in the local OverHaust database.
Token counts are tiktoken estimates (not provider billing).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.context.agent_context import invoke_context_request
from packages.context.retrieval import search_project_knowledge
from packages.memory.memory_store import get_memory_store
from packages.tokenization.token_estimator import TokenEstimator

LABKOT_PROMPT = (
    "Add support for multiple kitchen printers and route each order "
    "to the appropriate printer."
)


def _unique_files(results) -> set:
    files = set()
    for row in results:
        meta = row.get("metadata") or {}
        path = meta.get("file_path") or meta.get("source_ref") or ""
        if path:
            files.add(path)
    return files


def _approx_lines_from_results(results) -> int:
    total = 0
    for row in results:
        content = row.get("content") or ""
        if content:
            total += len(content.splitlines())
        else:
            total += 1
    return total


def _reduction_pct(a_value: float, b_value: float) -> Optional[float]:
    if a_value <= 0:
        return None
    return round((1.0 - (b_value / a_value)) * 100.0, 2)


def measure(project_id: str, prompt: str, search_limit: int = 10) -> dict:
    store = get_memory_store()
    estimator = TokenEstimator()

    t0 = time.perf_counter()
    search_results = search_project_knowledge(
        project_id, prompt, memory_store=store, limit=search_limit,
    )
    search_ms = int((time.perf_counter() - t0) * 1000)
    search_json = json.dumps({"results": search_results}, default=str)
    search_bytes = len(search_json.encode("utf-8"))
    search_files = _unique_files(search_results)
    search_lines = _approx_lines_from_results(search_results)
    search_tokens = estimator.estimate_tokens(search_json)

    t1 = time.perf_counter()
    context = invoke_context_request(project_id, prompt, memory_store=store)
    context_ms = int((time.perf_counter() - t1) * 1000)
    context_payload = context.to_dict()
    context_bytes = len(json.dumps(context_payload, default=str).encode("utf-8"))
    context_tokens = estimator.estimate_tokens(context_payload.get("context", ""))

    b = context_payload["metrics"]
    return {
        "project_id": project_id,
        "prompt": prompt,
        "A_raw_search": {
            "files_count": len(search_files),
            "results_count": len(search_results),
            "approx_source_lines": search_lines,
            "response_bytes": search_bytes,
            "estimated_context_tokens": search_tokens,
            "token_estimate_note": "tiktoken estimate on full search JSON",
            "latency_ms": search_ms,
        },
        "B_compact_context": {
            "files_count": b["files_count"],
            "symbols_count": b["symbols_count"],
            "approx_source_lines": b["approx_source_lines"],
            "response_bytes": context_bytes,
            "estimated_context_tokens": context_tokens,
            "token_estimate_note": "tiktoken estimate on context field only",
            "latency_ms": context_ms,
            "code_flow_included": b["code_flow_included"],
            "confidence": context_payload["confidence"],
            "insufficient_evidence": context_payload["insufficient_evidence"],
        },
        "reduction": {
            "response_bytes_ratio": round(
                context_bytes / search_bytes, 4,
            ) if search_bytes else None,
            "files_ratio": round(
                b["files_count"] / max(len(search_files), 1),
                4,
            ),
            "bytes_reduction_pct": _reduction_pct(search_bytes, context_bytes),
            "files_reduction_pct": _reduction_pct(len(search_files), b["files_count"]),
            "lines_reduction_pct": _reduction_pct(search_lines, b["approx_source_lines"]),
            "tokens_reduction_pct": _reduction_pct(search_tokens, context_tokens),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Measure context baseline A vs B")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--prompt", default=LABKOT_PROMPT)
    parser.add_argument("--search-limit", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args()

    report = measure(args.project_id, args.prompt, search_limit=args.search_limit)
    if args.json:
        print(json.dumps(report, indent=2))
        return

    print(f"Project: {report['project_id']}")
    print(f"Prompt:  {report['prompt']}\n")
    print("NOTE: For fair agent baseline, use: python3 scripts/agent_benchmark.py\n")
    a = report["A_raw_search"]
    b = report["B_compact_context"]
    r = report["reduction"]
    print("A) Raw search (limit={}) — unbounded retrieval JSON".format(args.search_limit))
    print(f"   files={a['files_count']} results={a['results_count']} "
          f"lines~={a['approx_source_lines']} bytes={a['response_bytes']} "
          f"tokens~={a['estimated_context_tokens']} ({a['token_estimate_note']}) "
          f"latency={a['latency_ms']}ms")
    print("\nB) Compact get_relevant_context")
    print(f"   files={b['files_count']} symbols={b['symbols_count']} "
          f"lines~={b['approx_source_lines']} bytes={b['response_bytes']} "
          f"tokens~={b['estimated_context_tokens']} ({b['token_estimate_note']}) "
          f"latency={b['latency_ms']}ms flow={b['code_flow_included']} "
          f"confidence={b['confidence']}")
    print("\nEstimated reduction (B vs A)")
    print(f"   bytes:  {r['bytes_reduction_pct']}%")
    print(f"   files:  {r['files_reduction_pct']}%")
    print(f"   lines:  {r['lines_reduction_pct']}%")
    print(f"   tokens: {r['tokens_reduction_pct']}% (estimate on context field vs search JSON)")


if __name__ == "__main__":
    main()
