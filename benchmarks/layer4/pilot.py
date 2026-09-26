"""Codex instrumentation runs.

Default preset is the 8-session pilot. ``--preset full`` is 20 sessions.

    python3 -m benchmarks.layer4.pilot --model <model>
    python3 -m benchmarks.layer4.pilot --preset full --model <model>
"""

from benchmarks.layer4.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
