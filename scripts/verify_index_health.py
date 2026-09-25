#!/usr/bin/env python3
"""Report OverHaust project index health without syncing or changing data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check registered project / index readiness."
    )
    parser.add_argument(
        "--project-id",
        action="append",
        dest="project_ids",
        help="Project id to check (repeatable). Default: all registered projects.",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    from packages.memory.memory_store import get_memory_store
    from services.ingestion.index_store import ProjectIndexStore

    store = get_memory_store()
    index_store = ProjectIndexStore(store)
    if args.project_ids:
        ids = args.project_ids
    else:
        ids = [
            p.get("id") or p.get("project_id")
            for p in store.list_projects()
            if p.get("id") or p.get("project_id")
        ]

    reports = [index_store.index_health(pid) for pid in ids if pid]
    ok = all(r.get("ok") for r in reports) if reports else False

    if args.json:
        print(json.dumps({"ok": ok, "projects": reports}, indent=2))
    else:
        if not reports:
            print("No projects registered.")
            return 1
        for report in reports:
            status = "OK" if report["ok"] else "ISSUES"
            print(
                f"[{status}] {report['project_id']}: "
                f"indexed={report['indexed']} files={report['file_count']} "
                f"extractor_current={report['extractor_current']} "
                f"root_exists={report['root_exists']}"
            )
            if report["issues"]:
                print(f"  issues: {', '.join(report['issues'])}")
            if report.get("root_path"):
                print(f"  root: {report['root_path']}")
        print(
            "Note: context requests do not auto-reindex. "
            "Run scripts/ensure_project_indexed.py when the tree changes."
        )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
