#!/usr/bin/env python3
"""
OverHaust unified CLI.

  overhaust doctor        host integration diagnostics (composed via the manager)
  overhaust status        core health + projects + connected hosts
  overhaust integrations  list adapters and their lifecycle state
  overhaust connect       install OverHaust into detected hosts (adapter.install)
  overhaust disconnect    remove OverHaust-owned host config (adapter.uninstall)

The CLI never touches host configuration itself; every host-specific
action is delegated to the adapter registry via IntegrationManager.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.integrations.doctor import format_doctor_report, run_doctor  # noqa: E402
from packages.integrations.host import IntegrationState  # noqa: E402
from packages.integrations.manager import (  # noqa: E402
    IntegrationManager,
    format_connect,
    format_disconnect,
    format_integrations,
    format_status,
)


def _emit(obj, as_json: bool, text: str) -> None:
    if as_json:
        print(json.dumps(obj, indent=2))
    else:
        print(text, end="")


def _confirm(question: str, *, assume_yes: bool, stdin=None) -> bool:
    if assume_yes:
        return True
    stream = stdin or sys.stdin
    if not stream.isatty():
        return False
    answer = input(f"{question} [Y/n] ").strip().lower()
    return answer in {"", "y", "yes"}


def cmd_doctor(args, mgr: IntegrationManager) -> int:
    report = run_doctor(args.adapters, manager=mgr)
    _emit(report.to_dict(), args.json, format_doctor_report(report))
    return 1 if report.result in {"ACTION_REQUIRED", "UNSUPPORTED"} else 0


def cmd_status(args, mgr: IntegrationManager) -> int:
    report = mgr.status(args.adapters)
    _emit(report.to_dict(), args.json, format_status(report))
    return 0


def cmd_integrations(args, mgr: IntegrationManager) -> int:
    records = mgr.discover(args.adapters)
    _emit([r.to_dict() for r in records], args.json, format_integrations(records, verbose=args.verbose))
    return 0


def cmd_connect(args, mgr: IntegrationManager) -> int:
    records = mgr.discover()
    if not args.json:
        print(format_integrations(records), end="")

    if args.adapters:
        targets: Optional[List[str]] = list(args.adapters)
    else:
        detected = [r.adapter_id for r in records if r.detected]
        if not detected:
            if not args.json:
                print("\nNo AI environments detected. Nothing to connect.")
                print("Use --host <adapter-id> to force a specific host.")
            else:
                print(json.dumps({"connected": [], "reason": "no hosts detected"}))
            return 0
        if not args.json and not _confirm("\nConnect all detected environments?", assume_yes=args.yes):
            print("Aborted.")
            return 2
        targets = detected

    outcomes = mgr.connect(
        targets,
        root=ROOT,
        python=args.python,
        dry_run=args.dry_run,
        only_detected=False,
    )
    _emit([o.to_dict() for o in outcomes], args.json, format_connect(outcomes))
    bad = any(o.error for o in outcomes)
    return 1 if bad else 0


def cmd_disconnect(args, mgr: IntegrationManager) -> int:
    targets: Optional[Sequence[str]] = args.adapters or None
    if targets is None and not args.json and not _confirm(
        "Remove OverHaust configuration from all hosts?", assume_yes=args.yes
    ):
        print("Aborted.")
        return 2
    outcomes = mgr.disconnect(targets, dry_run=args.dry_run)
    _emit([o.to_dict() for o in outcomes], args.json, format_disconnect(outcomes))
    return 1 if any(o.error for o in outcomes) else 0


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--host", action="append", dest="adapters", metavar="ADAPTER_ID",
        help="limit to adapter id (repeatable), e.g. cursor, codex, claude, continue, cline",
    )
    parser.add_argument("--probe-emission", action="store_true",
                        help="run local hook emission probes (does not prove model consumption)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="overhaust", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, help_: str, fn):
        p = sub.add_parser(name, help=help_)
        _common(p)
        p.set_defaults(fn=fn)
        return p

    add("doctor", "integration diagnostics", cmd_doctor)
    add("status", "core + projects + hosts", cmd_status)

    p_int = add("integrations", "list adapters and state", cmd_integrations)
    p_int.add_argument("-v", "--verbose", action="store_true")

    p_con = add("connect", "connect detected hosts", cmd_connect)
    p_con.add_argument("-y", "--yes", action="store_true", help="do not prompt")
    p_con.add_argument("--dry-run", action="store_true")
    p_con.add_argument("--python", default="python3")

    p_dis = add("disconnect", "remove OverHaust-owned host config", cmd_disconnect)
    p_dis.add_argument("-y", "--yes", action="store_true", help="do not prompt")
    p_dis.add_argument("--dry-run", action="store_true")

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    mgr = IntegrationManager(probe_emission=args.probe_emission)
    return args.fn(args, mgr)


if __name__ == "__main__":
    raise SystemExit(main())
