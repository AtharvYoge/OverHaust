"""CLI for the Layer 4 Codex pilot."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from benchmarks.layer4.matrix import PILOT_SEED
from benchmarks.layer4.runner import PreflightError, RunConfig, run_pilot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m benchmarks.layer4.pilot",
        description=(
            "Run the Layer 4 Codex instrumentation pilot "
            "(8 isolated sessions). This does not report a product result."
        ),
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("LAYER4_CODEX_MODEL") or None,
        help=(
            "Model passed to every session as `codex exec --model`. "
            "Required for a comparable pilot. Defaults to LAYER4_CODEX_MODEL."
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
        help="Write the 8-session plan and fixture hash. Do not launch Codex.",
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
        print(
            "Model was not pinned. Pass --model so both conditions use the same model.",
            file=sys.stderr,
        )
    return 0
