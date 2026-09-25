#!/usr/bin/env python3
"""
OverHaust doctor — host/runtime integration health.

Compatibility shim: equivalent to `scripts/overhaust doctor`.

Examples:
  python3 scripts/overhaust_doctor.py
  python3 scripts/overhaust_doctor.py --json
  python3 scripts/overhaust_doctor.py --adapter codex
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.overhaust_cli import main as cli_main  # noqa: E402


def main() -> int:
    argv = []
    rest = sys.argv[1:]
    i = 0
    while i < len(rest):
        if rest[i] == "--adapter" and i + 1 < len(rest):
            argv += ["--host", rest[i + 1]]
            i += 2
            continue
        argv.append(rest[i])
        i += 1
    return cli_main(["doctor"] + argv)


if __name__ == "__main__":
    raise SystemExit(main())
