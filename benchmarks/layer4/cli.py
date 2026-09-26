"""CLI for the Layer 4 Codex pilot."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from benchmarks.layer4.matrix import FULL_NAME, PILOT_CONDITIONS, PILOT_NAME, PILOT_SEED
from benchmarks.layer4.runner import PreflightError, RunConfig, run_pilot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m benchmarks.layer4.pilot",
        description=(
            "Run a Layer 4 Codex instrumentation preset. "
            "pilot (default) is 8 isolated sessions; full is 20. "
            "This does not report a product result."
        ),
    )
    parser.add_argument(
        "--preset",
        choices=(PILOT_NAME, FULL_NAME),
        default=PILOT_NAME,
        help=(
            "pilot: sym_generate_kot and arch_kitchen_hardware × "
            "baseline/overhaust × 2 reps (8 sessions, default). "
            "full: all 5 Layer 3 tasks × baseline/overhaust × 2 reps "
            "(20 sessions)."
        ),
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("LAYER4_CODEX_MODEL") or None,
        help=(
            "Model passed to every session as `codex exec --model`. "
            "Required for a comparable run. Defaults to LAYER4_CODEX_MODEL."
        ),
    )
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=None,
        metavar="CONDITION",
        help=(
            "Conditions to run. Default is both baseline and overhaust "
            f"({', '.join(PILOT_CONDITIONS)}). "
            "Pass one name to run only that condition, for example "
            "--conditions baseline. A single condition uses the same "
            "pair-counterbalanced plan, seed, fixture, prompts, and timeout, "
            "and keeps that condition's sessions in their original relative order."
        ),
    )
    parser.add_argument("--seed", type=int, default=PILOT_SEED)
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Per-session timeout in seconds (default 600).",
    )
    parser.add_argument("--results-dir", type=Path, default=None)
    parser.add_argument("--codex-bin", default=os.environ.get("CODEX_BIN") or None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write the session plan and fixture hash. Do not launch Codex.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.timeout < 1:
        print("--timeout must be >= 1", file=sys.stderr)
        return 2
    config = RunConfig(
        model=args.model,
        seed=args.seed,
        timeout_s=args.timeout,
        results_dir=args.results_dir,
        dry_run=args.dry_run,
        codex_bin=args.codex_bin,
        preset=args.preset,
        conditions=args.conditions,
    )
    try:
        report = run_pilot(config)
    except PreflightError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    paths = report.get("_output_paths") or {}
    print(f"Wrote {paths.get('json')}")
    print(f"Wrote {paths.get('md')}")
    if report["mode"] == "dry_run":
        print(
            "Dry run only: planned "
            f"{report['planned_session_count']} sessions, launched 0."
        )
        return 0
    summary = report.get("summary") or {}
    print(
        "Recorded "
        f"{report['recorded_session_count']} sessions "
        f"(dropped {report['dropped_session_count']}). "
        f"outcomes={summary.get('outcomes')}"
    )
    if not report.get("model_pinned"):
        conditions = report.get("conditions") or []
        if len(conditions) == 1:
            print(
                "Model was not pinned. Pass --model so this condition uses a pinned model.",
                file=sys.stderr,
            )
        else:
            print(
                "Model was not pinned. Pass --model so both conditions use the same model.",
                file=sys.stderr,
            )
    return 0
