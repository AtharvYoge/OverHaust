#!/usr/bin/env python3
"""
Reproducible agent context benchmark: naïve exploration vs OverHaust.

Usage:
  python3 scripts/agent_benchmark.py --project-id labkot

Requires indexed project in local OverHaust database.
Does NOT run a live autonomous coding agent — simulates the closest measurable baseline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.context.benchmark import run_agent_benchmark

LABKOT_PROMPT = (
    "Add support for multiple kitchen printers and route each order "
    "to the appropriate printer."
)


def main():
    parser = argparse.ArgumentParser(description="Agent context benchmark A vs B")
    parser.add_argument("--project-id", default="labkot")
    parser.add_argument("--prompt", default=LABKOT_PROMPT)
    parser.add_argument("--search-limit", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_agent_benchmark(
        args.project_id,
        args.prompt,
        search_limit=args.search_limit,
    )

    if args.json:
        # Omit full payload from JSON output (large)
        slim = dict(report)
        slim["overhaust"] = {k: v for k, v in report["overhaust"].items() if k != "payload"}
        print(json.dumps(slim, indent=2))
        return

    print(f"Project: {report['project_id']}")
    print(f"Prompt:  {report['prompt']}\n")
    print(report["baseline_recommendation"])
    print()

    naive = report["baseline_fair"]
    oh = report["overhaust"]
    r = report["fair_reduction"]

    print("A) FAIR BASELINE — naïve agent (search + read full top files)")
    print(f"   files_read={naive['files_read']} lines={naive['approx_source_lines']} "
          f"bytes={naive['response_bytes']} tokens~={naive['estimated_context_tokens']} "
          f"latency={naive['latency_ms']}ms")
    print(f"   paths: {', '.join(naive['paths'][:5])}")

    print("\nB) OVERHAUST — get_relevant_context")
    print(f"   files={oh['files_read']} symbols={oh.get('symbols_count', 0)} "
          f"lines={oh['approx_source_lines']} bytes={oh['response_bytes']} "
          f"tokens~={oh['estimated_context_tokens']} latency={oh['latency_ms']}ms "
          f"flow={oh['code_flow_included']}")
    print(f"   paths: {', '.join(oh['paths'][:5])}")

    print("\nFair reduction (OverHaust vs naïve full files)")
    print(f"   tokens: {r['tokens_vs_naive_full_files_pct']}%")
    print(f"   bytes:  {r['bytes_vs_naive_full_files_pct']}%")
    print(f"   lines:  {r['lines_vs_naive_full_files_pct']}%")
    print(f"   files:  {r['files_vs_naive_full_files_pct']}%")
    print(f"   latency overhead: +{r['latency_overhead_ms']}ms")

    hook = report.get("hook_interception")
    if hook:
        print("\nC) HOOK PATH — UserPromptSubmit adapter")
        print(f"   bytes={hook['response_bytes']} tokens~={hook['estimated_context_tokens']} "
              f"latency={hook['latency_ms']}ms engine={hook.get('engine_latency_ms', 0)}ms "
              f"overhead={hook.get('hook_overhead_ms', 0)}ms")
        if hook.get("error"):
            print(f"   error: {hook['error']}")

    legacy = report["baseline_legacy_metadata"]
    print("\n(Legacy metadata-only baseline — NOT recommended for product thesis)")
    print(f"   tokens~={legacy['estimated_context_tokens']} bytes={legacy['response_bytes']}")

    print(f"\n{report['task_success_note']}")


if __name__ == "__main__":
    main()
