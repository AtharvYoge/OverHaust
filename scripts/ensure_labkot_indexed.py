#!/usr/bin/env python3
"""Ensure LabKOT is registered and indexed in the local OverHaust database."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LABKOT_ROOT = Path("/Volumes/Atharv Work/LabKOT/restaurant_pos")
PROJECT_ID = "labkot"
PROJECT_NAME = "LabKOT"


def main() -> int:
    if not LABKOT_ROOT.is_dir():
        print(f"LabKOT path not found: {LABKOT_ROOT}")
        return 1

    from services.ingestion.project_lifecycle import ensure_project_indexed

    try:
        result = ensure_project_indexed(
            PROJECT_ID,
            str(LABKOT_ROOT),
            name=PROJECT_NAME,
            description="LabKOT restaurant POS",
        )
    except ValueError as exc:
        print(f"Registration failed: {exc}")
        return 2

    print(
        f"Indexed {result['project_id']}: mode={result['mode']} "
        f"files={result['file_count']} root={result['root_path']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
