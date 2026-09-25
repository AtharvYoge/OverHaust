#!/usr/bin/env python3
"""Register and index any repository for OverHaust multi-repo use."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register a project and run incremental (or full) index sync."
    )
    parser.add_argument("--project-id", required=True, help="Stable OverHaust project id")
    parser.add_argument(
        "--root",
        required=True,
        help="Absolute or relative path to the repository root",
    )
    parser.add_argument("--name", default="", help="Human-readable name (optional)")
    parser.add_argument("--description", default="", help="Optional description")
    parser.add_argument(
        "--force-full",
        action="store_true",
        help="Force a full reindex instead of incremental sync",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON result",
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"Root path is not a directory: {root}", file=sys.stderr)
        return 1

    from services.ingestion.project_lifecycle import ensure_project_indexed

    try:
        result = ensure_project_indexed(
            args.project_id,
            str(root),
            name=args.name or None,
            description=args.description,
            force_full=args.force_full,
        )
    except ValueError as exc:
        print(f"Registration failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"Indexed {result['project_id']}: mode={result['mode']} "
            f"files={result['file_count']} root={result['root_path']}"
        )
        if result.get("resolved_project_id") != result["project_id"]:
            print(
                f"Warning: resolve_project_id returned "
                f"{result.get('resolved_project_id')!r}",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
