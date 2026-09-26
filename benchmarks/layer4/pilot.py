"""Codex instrumentation runs.

Default preset for Codex is the 8-session pilot. ``--agent cursor`` pilot
is 10 sessions. ``--preset full`` is 20 sessions for either agent.
``--conditions baseline`` keeps only the baseline sessions of that same plan.

    python3 -m benchmarks.layer4.pilot --model <model>
    python3 -m benchmarks.layer4.pilot --preset full --model <model>
    python3 -m benchmarks.layer4.pilot --dry-run --preset full --conditions baseline --model <model>
"""

from benchmarks.layer4.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
