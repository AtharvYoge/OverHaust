#!/usr/bin/env python3
"""
CLI entry: python3 -m benchmarks.run ...

Layers:
  1 — synthetic context-size (existing)
  2 — deterministic agent simulation
  3 — live OpenAI pair via --compare, or external traces via --ingest
  4 — IDE session traces via --ingest (same ingest path; set layer in JSON)

Examples:
  python3 -m benchmarks.run --layer 1 --compare --task-set initial --runs 3
  python3 -m benchmarks.run --layer 2 --compare --task-set initial --runs 3 --repo-size medium
  python3 -m benchmarks.run --layer 2 --task-set adversarial --repo-size small --runs 1
  python3 -m benchmarks.run --layer 3 --compare --task sym_generate_kot --runs 1 --repo-size small
  python3 -m benchmarks.run --layer 3 --ingest traces.json --task-set initial
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from benchmarks.experiment import (  # noqa: E402
    run_layer2_benchmark,
    run_layer3_ingest,
    run_layer3_live,
)
from benchmarks.providers import ProviderNotConfiguredError  # noqa: E402
from benchmarks.runners import run_benchmark  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m benchmarks.run",
        description="OverHaust context-efficiency benchmark harness (Layers 1–4)",
    )
    p.add_argument(
        "--layer", type=int, choices=[1, 2, 3, 4], default=1,
        help="Benchmark layer (default: 1). Layer 3 live uses --compare; Layer 4 uses --ingest.",
    )

    g = p.add_mutually_exclusive_group(required=False)
    g.add_argument("--condition", choices=["baseline", "overhaust"])
    g.add_argument("--compare", action="store_true")
    g.add_argument("--ingest", nargs="+", metavar="PATH")

    p.add_argument("--task-set", default="initial")
    p.add_argument("--task", action="append", dest="tasks")
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--model", default=None)
    p.add_argument("--repo-size", choices=["small", "medium", "large"], default="medium")
    p.add_argument("--max-tool-calls", type=int, default=12)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--indexing-cost-tokens", type=float, default=None,
                   help="Measured indexing cost for break-even (optional; do not invent)")
    p.add_argument("--results-dir", type=Path, default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-shuffle", action="store_true")
    p.add_argument("--dry-run", action="store_true",
                   help="Layer 3 only: validate fixture size and restoration without a provider call.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.runs < 1:
        print("--runs must be >= 1", file=sys.stderr)
        return 2

    try:
        if args.layer == 1:
            if not (args.condition or args.compare or args.ingest):
                print("Layer 1 requires --condition, --compare, or --ingest", file=sys.stderr)
                return 2
            report = run_benchmark(
                condition=args.condition,
                compare=args.compare,
                task_set=args.task_set,
                runs=args.runs,
                model=args.model,
                task_ids=args.tasks,
                results_dir=args.results_dir,
                ingest_paths=[Path(p) for p in args.ingest] if args.ingest else None,
            )
        elif args.layer == 2:
            report = run_layer2_benchmark(
                task_set=args.task_set,
                runs=args.runs,
                task_ids=args.tasks,
                repo_size=args.repo_size,
                max_tool_calls=args.max_tool_calls,
                model=args.model,
                seed=args.seed,
                results_dir=args.results_dir,
                shuffle=not args.no_shuffle,
                indexing_cost_tokens=args.indexing_cost_tokens,
            )
        elif args.layer == 3 and args.compare:
            report = run_layer3_live(
                task_set=args.task_set,
                runs=args.runs,
                task_ids=args.tasks,
                repo_size=args.repo_size,
                max_tool_calls=args.max_tool_calls,
                model=args.model,
                seed=args.seed,
                results_dir=args.results_dir,
                dry_run=args.dry_run,
            )
        elif args.layer in (3, 4):
            if not args.ingest:
                print(
                    "Layer 3 live pairs: --compare (needs OPENAI_API_KEY or OVERHAUST_L3_API_KEY). "
                    "Layer 3/4 ingest: --ingest <trace.json>.",
                    file=sys.stderr,
                )
                return 2
            report = run_layer3_ingest(
                [Path(p) for p in args.ingest],
                task_set=args.task_set,
                results_dir=args.results_dir,
                indexing_cost_tokens=args.indexing_cost_tokens,
            )
            report["layer"] = args.layer
        else:
            print(f"Unknown layer {args.layer}", file=sys.stderr)
            return 2
    except ProviderNotConfiguredError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    if report.get("dry_run"):
        probe = report.get("repository_restore_probe") or {}
        print(
            "Layer 3 dry run: "
            f"repo_size={report.get('repo_size')} "
            f"restore={probe.get('status')} verified={probe.get('verified')} "
            f"model={report.get('model')}"
        )
        print(report.get("claim_policy"))
        return 0

    paths = report.get("_output_paths", {})
    print(f"Wrote {paths.get('json')}")
    print(f"Wrote {paths.get('md')}")
    if args.json:
        slim = {k: v for k, v in report.items() if k != "_output_paths"}
        print(json.dumps(slim, indent=2))
    else:
        if args.layer == 1:
            overall = report.get("summary", {}).get("overall_comparison", {})
            ctx = overall.get("context_token_reduction", {})
            print(
                "Layer 1 query-time context tokens (mean): "
                f"baseline={ctx.get('baseline_mean')}  "
                f"overhaust={ctx.get('overhaust_mean')}  "
                f"reduction%={ctx.get('reduction_percent')}"
            )
        elif args.layer == 3 and args.compare:
            agg = report.get("layered_report", {}).get("pair_aggregation", {})
            print(
                "Layer 3 live pairs: "
                f"attempted={agg.get('attempted_pairs')} "
                f"successful={agg.get('successful_pairs')} "
                f"rejected={agg.get('rejected_pairs')} "
                f"failed={agg.get('failed_runs_pairs')} "
                f"incomparable={agg.get('incomparable_pairs')}"
            )
            exact = agg.get("exact_total_token_reduction_pct") or {}
            if agg.get("successful_pairs"):
                print(
                    "EXACT MEASURED REDUCTION total_token_reduction_pct "
                    f"mean={exact.get('mean')} n={exact.get('n')}"
                )
            else:
                print("No EXACT MEASURED REDUCTION (pair did not qualify).")
        else:
            layered = report.get("layered_report", {})
            comp = layered.get("comparison", {}).get("token_reduction", {})
            print(
                f"Layer {args.layer} token reduction median % "
                f"({comp.get('kind')}): {comp.get('reduction_percent_median')}"
            )
            print(f"accuracy_delta: {layered.get('comparison', {}).get('accuracy_delta')}")
            print(f"break-even: {layered.get('break_even', {}).get('token_units', {}).get('status')}")
        print(report.get("claim_policy") or (
            "NOTE: Do not claim product token savings without controlled Layer 3+ data."
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
