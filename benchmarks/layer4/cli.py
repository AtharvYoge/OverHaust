"""CLI for Layer 4 instrumentation (Codex, and Cursor via --agent cursor)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from benchmarks.layer4.matrix import FULL_NAME, PILOT_CONDITIONS, PILOT_NAME, PILOT_SEED
from benchmarks.layer4.runner import PreflightError, RunConfig, run_pilot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m benchmarks.layer4.pilot",
        description=(
            "Run a Layer 4 instrumentation preset. "
            "Codex pilot (default) is 8 isolated sessions; Codex full is 20. "
            "Cursor pilot is 10 sessions (5 tasks × 2 conditions × 1 rep); "
            "Cursor full is 20 (5 × 2 × 2). "
            "This does not report a product result."
        ),
    )
    parser.add_argument(
        "--agent",
        choices=("codex", "cursor"),
        default="codex",
        help="Agent adapter. Default codex. cursor uses cursor-agent.",
    )
    parser.add_argument(
        "--preset",
        choices=(PILOT_NAME, FULL_NAME),
        default=PILOT_NAME,
        help=(
            "pilot (default): Codex is sym_generate_kot and "
            "arch_kitchen_hardware × baseline/overhaust × 2 reps (8 sessions). "
            "Cursor is all 5 tasks × baseline/overhaust × 1 rep (10 sessions). "
            "full: Codex and Cursor are all 5 tasks × baseline/overhaust × "
            "2 reps (20 sessions)."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Model passed to every session. Codex forwards it as "
            "`codex exec --model` and defaults to LAYER4_CODEX_MODEL. "
            "Cursor forwards it as `cursor-agent --model` and defaults to "
            "gpt-5.5-medium (or LAYER4_CURSOR_MODEL)."
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
        "--cursor-bin",
        default=os.environ.get("CURSOR_BIN") or None,
        help="cursor-agent binary. Default: CURSOR_BIN or PATH. Cursor only.",
    )
    parser.add_argument(
        "--isolation",
        choices=("isolated-home", "mcp-toggle"),
        default=None,
        help=(
            "Cursor isolation strategy. Default for --agent cursor is "
            "isolated-home. isolated-home uses a temp HOME and CURSOR_API_KEY. "
            "mcp-toggle runs `cursor-agent mcp disable overhaust` with cwd set "
            "to each session workspace, then deletes only the "
            "~/.cursor/projects slug that command created. "
            "`mcp list` and `mcp disable` start MCP servers."
        ),
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help=(
            "Cursor only. Check the CLI, auth, model list, and the selected "
            "--isolation strategy. Does not start a model session. Does not "
            "run from the user home or a project directory. isolated-home "
            "does not call mcp disable."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write the session plan and fixture hash. Do not launch an agent.",
    )
    return parser


def _reject_cursor_flags_on_codex(args: argparse.Namespace) -> str | None:
    if args.cursor_bin:
        return "--cursor-bin is only valid with --agent cursor"
    if args.isolation:
        return "--isolation is only valid with --agent cursor"
    if args.preflight:
        return "--preflight is only valid with --agent cursor"
    return None


def _main_cursor(args: argparse.Namespace) -> int:
    from benchmarks.layer4.cursor_condition import CURSOR_DEFAULT_MODEL, ISOLATION_HOME
    from benchmarks.layer4.cursor_runner import (
        CursorRunConfig,
        default_cursor_command_runner,
        format_cursor_dry_run,
        run_cursor,
        run_cursor_preflight,
    )

    model = args.model or os.environ.get("LAYER4_CURSOR_MODEL") or CURSOR_DEFAULT_MODEL
    isolation = args.isolation or ISOLATION_HOME
    if args.preflight:
        import shutil

        binary = args.cursor_bin or shutil.which("cursor-agent") or ""
        try:
            preflight = run_cursor_preflight(
                binary=binary,
                env=dict(os.environ),
                isolation=isolation,
                model=model,
                state_home=Path.home(),
                runner=default_cursor_command_runner,
            )
        except PreflightError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(preflight, indent=2))
        return 0 if preflight.get("selected_usable") else 2

    config = CursorRunConfig(
        model=model,
        seed=args.seed,
        timeout_s=args.timeout,
        results_dir=args.results_dir,
        dry_run=args.dry_run,
        cursor_bin=args.cursor_bin,
        isolation=isolation,
        preset=args.preset,
        conditions=args.conditions,
    )
    try:
        report = run_cursor(config)
    except PreflightError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    paths = report.get("_output_paths") or {}
    print(f"Wrote {paths.get('json')}")
    print(f"Wrote {paths.get('md')}")
    if report["mode"] == "dry_run":
        print(format_cursor_dry_run(report))
        print(
            "Dry run only: planned "
            f"{report['planned_session_count']} sessions, launched 0."
        )
        return 0
    print(
        "Recorded "
        f"{report['recorded_session_count']} sessions "
        f"(dropped {report['dropped_session_count']})."
    )
    restore = report.get("state_restore") or {}
    mcp_cleanup = report.get("mcp_cleanup") or {}
    if restore and not (restore.get("model_keys_restored") and restore.get("files_restored")):
        print("cli-config restore did not verify.", file=sys.stderr)
        return 2
    if mcp_cleanup and not mcp_cleanup.get("cleanup_verified", True):
        print("mcp-disabled.json cleanup did not verify.", file=sys.stderr)
        return 2
    if report.get("stopped_early"):
        print(report.get("stop_reason") or "Stopped: OverHaust MCP tool present.", file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.timeout < 1:
        print("--timeout must be >= 1", file=sys.stderr)
        return 2
    if args.agent == "cursor":
        return _main_cursor(args)
    rejected = _reject_cursor_flags_on_codex(args)
    if rejected:
        print(rejected, file=sys.stderr)
        return 2
    model = args.model or os.environ.get("LAYER4_CODEX_MODEL") or None
    config = RunConfig(
        model=model,
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
