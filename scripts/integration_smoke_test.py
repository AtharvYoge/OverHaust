#!/usr/bin/env python3
"""
End-to-end smoke test: prompt → hook → invoke_context_request → agent output.

Usage:
  python3 scripts/integration_smoke_test.py
  python3 scripts/integration_smoke_test.py --benchmark --project-id labkot
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.integrations.interception import CONTEXT_MARKER  # noqa: E402
from packages.integrations.hook_io import parse_hook_input  # noqa: E402
from packages.integrations.interception import run_user_prompt_interception  # noqa: E402
from packages.memory.memory_store import MemoryStore  # noqa: E402
from packages.retrieval.test_fixtures import make_kot_tree  # noqa: E402
from services.ingestion.index_store import ProjectIndexStore  # noqa: E402

HOOK_SCRIPT = ROOT / "scripts" / "integrations" / "overhaust_user_prompt_hook.py"
PROMPT = "Add support for multiple kitchen printers and route each order to the appropriate printer."


def _setup_fixture_db() -> tuple[str, str]:
    tmpdir = tempfile.mkdtemp()
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()
    root = Path(tmpdir)
    make_kot_tree(root)
    store = MemoryStore(db.name)
    store.add_project("smoke-p", "Smoke", "", str(root))
    ProjectIndexStore(store).sync_project("smoke-p", str(root))
    return str(root), db.name


def smoke_in_process(root: str, db_path: str) -> dict:
    os.environ["OVERHAUST_DB_PATH"] = db_path
    os.environ["OVERHAUST_INTEGRATION_DEBUG"] = "1"
    store = MemoryStore(db_path)
    hook_input = parse_hook_input(json.dumps({"prompt": PROMPT, "cwd": root}))
    result = run_user_prompt_interception(hook_input, memory_store=store)
    assert CONTEXT_MARKER in result.additional_context, "missing context marker"
    assert result.project_id == "smoke-p"
    assert result.debug.relevant_files
    return {
        "project_id": result.project_id,
        "context_bytes": result.debug.context_bytes,
        "latency_ms": result.debug.latency_ms,
        "files": result.debug.relevant_files,
        "symbols": result.debug.relevant_symbols,
        "reduction_pct": result.debug.reduction_pct,
    }


def smoke_subprocess(root: str, db_path: str) -> dict:
    env = os.environ.copy()
    env["OVERHAUST_DB_PATH"] = db_path
    env["OVERHAUST_INTEGRATION_DEBUG"] = "1"
    proc = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps({"prompt": PROMPT, "cwd": root}),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        env=env,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"hook failed: {proc.stderr}")
    out = json.loads(proc.stdout)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    if CONTEXT_MARKER not in ctx:
        raise AssertionError("subprocess hook missing context marker")
    debug = json.loads(proc.stderr.strip().splitlines()[-1])
    return {"subprocess": True, "debug": debug}


def run_labkot_benchmark() -> dict | None:
    try:
        from packages.context.benchmark import run_agent_benchmark

        return run_agent_benchmark("labkot", PROMPT)
    except Exception as exc:
        return {"error": str(exc), "note": "LabKOT not indexed in this environment"}


def main() -> int:
    parser = argparse.ArgumentParser(description="OverHaust integration smoke test")
    parser.add_argument("--benchmark", action="store_true", help="Also run LabKOT benchmark if indexed")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root, db_path = _setup_fixture_db()
    try:
        in_proc = smoke_in_process(root, db_path)
        sub_proc = smoke_subprocess(root, db_path)
        report = {
            "status": "PASS",
            "in_process": in_proc,
            "subprocess_hook": sub_proc,
        }
        if args.benchmark:
            report["benchmark"] = run_labkot_benchmark()

        if args.json:
            print(json.dumps(report, indent=2, default=str))
        else:
            print("Integration smoke test: PASS")
            print(f"  project_id={in_proc['project_id']}")
            print(f"  context_bytes={in_proc['context_bytes']} latency_ms={in_proc['latency_ms']}")
            print(f"  files={', '.join(in_proc['files'][:3])}")
            if in_proc.get("reduction_pct") is not None:
                print(f"  debug reduction_pct={in_proc['reduction_pct']}%")
            print("  subprocess hook: PASS")
            if args.benchmark and report.get("benchmark"):
                b = report["benchmark"]
                if "error" not in b:
                    r = b["fair_reduction"]
                    print(f"\nLabKOT benchmark tokens reduction: {r['tokens_vs_naive_full_files_pct']}%")
                else:
                    print(f"\nLabKOT benchmark skipped: {b.get('note', b['error'])}")
        return 0
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    raise SystemExit(main())
