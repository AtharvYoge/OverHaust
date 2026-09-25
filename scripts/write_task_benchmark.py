#!/usr/bin/env python3
"""
Phase 15 write-enabled coding task benchmark.

Creates isolated LabKOT copies and runs Codex exec under:
  A) naïve hook — full top-hit file injection
  B) OverHaust hook — compact invoke_context_request injection

Usage:
  python3 scripts/write_task_benchmark.py --project-id labkot
  python3 scripts/write_task_benchmark.py --project-id labkot --skip-agent
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.benchmark.implementation_quality import evaluate_repo  # noqa: E402
from packages.context.benchmark import (  # noqa: E402
    measure_hook_interception,
    measure_overhaust_context,
    run_agent_benchmark,
    simulate_naive_agent_exploration,
)
from packages.integrations.interception import CONTEXT_MARKER  # noqa: E402

LABKOT_PROMPT = (
    "Add support for multiple kitchen printers and route each order "
    "to the appropriate printer."
)

OVERHAUST_HOOK = ROOT / "scripts" / "integrations" / "overhaust_user_prompt_hook.py"
NAIVE_HOOK = ROOT / "scripts" / "integrations" / "naive_user_prompt_hook.py"
CODEX_HOOKS = Path.home() / ".codex" / "hooks.json"


def _labkot_source(project_id: str) -> tuple[str, Optional[str]]:
    from packages.memory.memory_store import get_memory_store
    from services.ingestion.index_store import ProjectIndexStore

    store = get_memory_store()
    root = ProjectIndexStore(store).get_project_root(project_id)
    if not root:
        raise ValueError(f"No root for project {project_id}")
    sha = None
    proc = subprocess.run(
        ["git", "-C", root, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        sha = proc.stdout.strip()
    return root, sha


def _copy_repo(source: str, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    # Avoid --local: LabKOT may live on a different volume than the benchmark dir.
    proc = subprocess.run(
        ["git", "clone", source, str(dest)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git clone failed: {proc.stderr.strip()}")


def _backup_codex_hooks() -> Optional[str]:
    if CODEX_HOOKS.exists():
        return CODEX_HOOKS.read_text(encoding="utf-8")
    return None


def _install_codex_hook(script: Path) -> None:
    payload = {
        "description": "Phase 15 benchmark hook",
        "hooks": {
            "UserPromptSubmit": [{
                "hooks": [{
                    "type": "command",
                    "command": f'python3 "{script}"',
                    "statusMessage": "Context injection",
                }]
            }]
        },
    }
    CODEX_HOOKS.parent.mkdir(parents=True, exist_ok=True)
    CODEX_HOOKS.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _restore_codex_hooks(content: Optional[str]) -> None:
    if content is None:
        if CODEX_HOOKS.exists():
            CODEX_HOOKS.unlink()
    else:
        CODEX_HOOKS.write_text(content, encoding="utf-8")


def _run_codex_agent(
    repo: Path,
    project_id: str,
    *,
    timeout: int = 600,
) -> Dict[str, Any]:
    debug_file = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    debug_path = debug_file.name
    debug_file.close()

    env = os.environ.copy()
    env["OVERHAUST_PROJECT_ID"] = project_id
    env["OVERHAUST_INTEGRATION_DEBUG"] = "1"
    env["OVERHAUST_INTEGRATION_DEBUG_FILE"] = debug_path

    impl_prompt = (
        f"{LABKOT_PROMPT}\n\n"
        "Implement this in the codebase. Add or update tests in "
        "test/kitchen_print_service_test.dart as needed. "
        "Keep changes focused on kitchen printing; do not modify unrelated files."
    )

    cmd = [
        "codex", "exec",
        "--dangerously-bypass-hook-trust",
        "--dangerously-bypass-approvals-and-sandbox",
        "-s", "workspace-write",
        impl_prompt,
    ]

    t0 = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    agent_ms = int((time.perf_counter() - t0) * 1000)

    debug_events: List[Dict[str, Any]] = []
    if os.path.exists(debug_path):
        for line in Path(debug_path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    debug_events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        os.unlink(debug_path)

    hook_event = debug_events[-1] if debug_events else {}
    stderr = proc.stderr or ""
    hook_ran_in_stderr = "hook: UserPromptSubmit" in stderr
    return {
        "exit_code": proc.returncode,
        "agent_ms": agent_ms,
        "hook_fired": bool(debug_events) or hook_ran_in_stderr,
        "context_injected": (
            hook_event.get("context_bytes", 0) > 0 or hook_ran_in_stderr
        ),
        "hook_debug": hook_event,
        "stdout_preview": proc.stdout[:1500],
        "stderr_preview": proc.stderr[:1500],
        "agent_completed": proc.returncode == 0,
    }


def _context_metrics(project_id: str, condition: str, root_path: str) -> Dict[str, Any]:
    if condition == "naive":
        naive = simulate_naive_agent_exploration(project_id, LABKOT_PROMPT)
        return {
            "condition": "naive",
            "estimated_context_tokens": naive["estimated_context_tokens"],
            "files_exposed": naive["files_read"],
            "lines_exposed": naive["approx_source_lines"],
            "bytes_exposed": naive["response_bytes"],
            "context_latency_ms": naive["latency_ms"],
            "paths": naive["paths"],
            "integration": "naive_user_prompt_hook (UserPromptSubmit full files)",
        }
    overhaust = measure_overhaust_context(project_id, LABKOT_PROMPT)
    hook = measure_hook_interception(project_id, LABKOT_PROMPT, root_path=root_path)
    return {
        "condition": "overhaust",
        "estimated_context_tokens": overhaust["estimated_context_tokens"],
        "files_exposed": overhaust["files_read"],
        "lines_exposed": overhaust["approx_source_lines"],
        "bytes_exposed": hook["response_bytes"],
        "context_latency_ms": overhaust["latency_ms"],
        "hook_overhead_ms": hook.get("hook_overhead_ms", 0),
        "paths": overhaust["paths"],
        "integration": "overhaust_user_prompt_hook (UserPromptSubmit → invoke_context_request)",
        "context_marker": CONTEXT_MARKER,
    }


def run_benchmark(
    project_id: str,
    *,
    skip_agent: bool = False,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    source_root, baseline_sha = _labkot_source(project_id)
    run_dir = output_dir or (
        ROOT / "benchmark-runs" / f"phase15-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    naive_repo = run_dir / "naive"
    overhaust_repo = run_dir / "overhaust"
    _copy_repo(source_root, naive_repo)
    _copy_repo(source_root, overhaust_repo)

    (run_dir / "baseline_sha.txt").write_text(baseline_sha or "unknown", encoding="utf-8")

    fair = run_agent_benchmark(project_id, LABKOT_PROMPT)
    hook_backup = _backup_codex_hooks()
    results: Dict[str, Any] = {
        "project_id": project_id,
        "task": LABKOT_PROMPT,
        "baseline_sha": baseline_sha,
        "source_root": source_root,
        "run_dir": str(run_dir),
        "fair_benchmark": {
            "naive_tokens": fair["baseline_fair"]["estimated_context_tokens"],
            "overhaust_tokens": fair["overhaust"]["estimated_context_tokens"],
            "reduction_pct": fair["fair_reduction"]["tokens_vs_naive_full_files_pct"],
        },
        "conditions": {},
    }

    for label, repo, hook_script in (
        ("naive", naive_repo, NAIVE_HOOK),
        ("overhaust", overhaust_repo, OVERHAUST_HOOK),
    ):
        ctx = _context_metrics(project_id, label, str(repo))
        cond: Dict[str, Any] = {"context": ctx, "agent": None, "quality": None}

        if not skip_agent and shutil.which("codex"):
            try:
                _install_codex_hook(hook_script)
                cond["agent"] = _run_codex_agent(repo, project_id)
            finally:
                _restore_codex_hooks(hook_backup)
        elif skip_agent:
            cond["agent"] = {"skipped": True, "reason": "skip_agent flag"}
        else:
            cond["agent"] = {"skipped": True, "reason": "codex CLI not installed"}

        agent_done = bool(cond["agent"] and cond["agent"].get("agent_completed"))
        cond["quality"] = evaluate_repo(
            repo,
            baseline_sha=baseline_sha,
            agent_completed=agent_done,
        ).to_dict()
        results["conditions"][label] = cond

        out_path = run_dir / f"{label}_result.json"
        out_path.write_text(json.dumps(cond, indent=2, default=str), encoding="utf-8")

    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 15 write-task benchmark")
    parser.add_argument("--project-id", default="labkot")
    parser.add_argument("--skip-agent", action="store_true", help="Context metrics only")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    out = Path(args.output_dir) if args.output_dir else None
    report = run_benchmark(args.project_id, skip_agent=args.skip_agent, output_dir=out)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0

    print(f"Run dir: {report['run_dir']}")
    print(f"Baseline SHA: {report['baseline_sha']}")
    print(f"Token reduction (fair): {report['fair_benchmark']['reduction_pct']}%")
    for label in ("naive", "overhaust"):
        c = report["conditions"][label]
        ctx = c["context"]
        q = c["quality"]
        print(f"\n=== {label.upper()} ===")
        print(f"  context tokens~={ctx['estimated_context_tokens']} latency={ctx['context_latency_ms']}ms")
        if c.get("agent"):
            a = c["agent"]
            if a.get("skipped"):
                print(f"  agent: skipped ({a.get('reason')})")
            else:
                print(f"  agent: completed={a.get('agent_completed')} time={a.get('agent_ms')}ms hook={a.get('hook_fired')}")
        if q:
            print(f"  changed_files={q.get('changed_files')}")
            print(f"  tests_passed={q.get('tests_passed')} correct={q.get('correct_implementation')}")
            print(f"  unrelated={q.get('unrelated_changes')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
