#!/usr/bin/env python3
"""Ensure this OverHaust repository is registered and indexed as project_id=overhaust."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROJECT_ID = "overhaust"
PROJECT_NAME = "OverHaust"


def ensure_overhaust_indexed(root: Path | None = None) -> dict:
    """Register and incrementally sync the OverHaust repo. Does not run on MCP requests."""
    from services.ingestion.project_lifecycle import ensure_project_indexed

    repo = (root or ROOT).resolve()
    return ensure_project_indexed(
        PROJECT_ID,
        str(repo),
        name=PROJECT_NAME,
        description="OverHaust monorepo",
    )


def main() -> int:
    result = ensure_overhaust_indexed()
    print(
        f"Indexed {result['project_id']}: mode={result['mode']} "
        f"files={result['file_count']} root={result['root_path']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
