#!/usr/bin/env python3
"""
Phase 14 real-agent integration verification helper.

Checks installed hook configs and optionally runs a Codex exec session
with hook trust bypass to observe whether OverHaust context is injected.

Usage:
  python3 scripts/verify_real_agent_session.py --inspect
  python3 scripts/verify_real_agent_session.py --codex --project-id labkot
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HOOK_SCRIPT = ROOT / "scripts" / "integrations" / "overhaust_user_prompt_hook.py"
LABKOT_PROMPT = (
    "Add support for multiple kitchen printers and route each order "
    "to the appropriate printer."
)
READ_PLAN_PROMPT = (
    "READ-ONLY PLAN TASK: List which files and symbols you would modify to "
    "add support for multiple kitchen printers and route each order to the "
    "appropriate printer. Do NOT edit any files. Reply with a bullet list only."
)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_parse_error": True, "_path": str(path)}


def _find_overhaust_hook(config: Optional[Dict[str, Any]]) -> bool:
    if not config:
        return False
    text = json.dumps(config)
    return "overhaust" in text.lower() or "overhaust_user_prompt_hook" in text


def inspect_integrations() -> Dict[str, Any]:
    home = Path.home()
    repo_cursor_hooks = ROOT / ".cursor" / "hooks.json"
    repo_claude = ROOT / ".claude" / "settings.json"
    repo_rules = ROOT / ".cursor" / "rules" / "overhaust-context.mdc"

    codex_hooks = _read_json(home / ".codex" / "hooks.json")
    cursor_hooks_user = _read_json(home / ".cursor" / "hooks.json")
    cursor_hooks_repo = _read_json(repo_cursor_hooks)
    claude_user = _read_json(home / ".claude" / "settings.json")
    claude_repo = _read_json(repo_claude)
    cursor_mcp = _read_json(home / ".cursor" / "mcp.json")

    return {
        "codex": {
            "cli_installed": shutil.which("codex") is not None,
            "hooks_json": str(home / ".codex" / "hooks.json"),
            "hooks_present": codex_hooks is not None,
            "overhaust_hook_installed": _find_overhaust_hook(codex_hooks),
            "config": codex_hooks,
        },
        "claude_code": {
            "cli_installed": shutil.which("claude") is not None,
            "user_settings": str(home / ".claude" / "settings.json"),
            "repo_settings": str(repo_claude),
            "user_overhaust": _find_overhaust_hook(claude_user),
            "repo_overhaust": _find_overhaust_hook(claude_repo),
        },
        "cursor": {
            "user_hooks": str(home / ".cursor" / "hooks.json"),
            "repo_hooks": str(repo_cursor_hooks),
            "user_overhaust_hook": _find_overhaust_hook(cursor_hooks_user),
            "repo_overhaust_hook": _find_overhaust_hook(cursor_hooks_repo),
            "rules_fallback": repo_rules.exists(),
            "mcp_overhaust": _find_overhaust_hook(cursor_mcp),
            "mcp_config_path": str(home / ".cursor" / "mcp.json"),
        },
        "hook_script_exists": HOOK_SCRIPT.exists(),
        "hook_script": str(HOOK_SCRIPT),
    }


def _labkot_root(project_id: str) -> Optional[str]:
    from packages.memory.memory_store import get_memory_store
    from services.ingestion.index_store import ProjectIndexStore

    store = get_memory_store()
    return ProjectIndexStore(store).get_project_root(project_id)


def verify_codex_session(
    project_id: str,
    *,
    prompt: str = READ_PLAN_PROMPT,
    timeout: int = 180,
) -> Dict[str, Any]:
    if not shutil.which("codex"):
        return {"status": "skipped", "reason": "codex CLI not installed"}

    root = _labkot_root(project_id)
    if not root or not Path(root).exists():
        return {"status": "skipped", "reason": f"project root not found for {project_id}"}

    debug_file = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    debug_path = debug_file.name
    debug_file.close()

    env = os.environ.copy()
    env["OVERHAUST_PROJECT_ID"] = project_id
    env["OVERHAUST_INTEGRATION_DEBUG"] = "1"
    env["OVERHAUST_INTEGRATION_DEBUG_FILE"] = debug_path

    cmd = [
        "codex", "exec",
        "--dangerously-bypass-hook-trust",
        "-s", "read-only",
        prompt,
    ]

    proc = subprocess.run(
        cmd,
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    debug_lines: List[Dict[str, Any]] = []
    if os.path.exists(debug_path):
        for line in Path(debug_path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    debug_lines.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        os.unlink(debug_path)

    hook_fired = len(debug_lines) > 0
    context_injected = any(
        d.get("context_bytes", 0) > 0 and not d.get("error")
        for d in debug_lines
    )
    overhaust_in_output = "overhaust-context" in (proc.stdout + proc.stderr).lower()

    return {
        "status": "completed",
        "project_id": project_id,
        "cwd": root,
        "command": " ".join(cmd[:4]) + " ...",
        "exit_code": proc.returncode,
        "hook_fired": hook_fired,
        "context_injected": context_injected,
        "debug_events": debug_lines,
        "overhaust_marker_in_agent_output": overhaust_in_output,
        "agent_stdout_preview": proc.stdout[:800],
        "agent_stderr_preview": proc.stderr[:800],
        "verified": hook_fired and context_injected,
        "verification_note": (
            "Real-agent verified only if hook fired AND context_bytes > 0 in debug. "
            "Marker in agent stdout is supplementary, not required."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify real agent integrations")
    parser.add_argument("--inspect", action="store_true", help="Inspect hook configs only")
    parser.add_argument("--codex", action="store_true", help="Run Codex exec verification")
    parser.add_argument("--project-id", default="labkot")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report: Dict[str, Any] = {"inspection": inspect_integrations()}

    if args.codex:
        report["codex_session"] = verify_codex_session(args.project_id)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0

    insp = report["inspection"]
    print("=== Integration inspection ===")
    print(f"Codex CLI:     {insp['codex']['cli_installed']}")
    print(f"Codex hook:    {insp['codex']['overhaust_hook_installed']} ({insp['codex']['hooks_json']})")
    print(f"Claude CLI:    {insp['claude_code']['cli_installed']}")
    print(f"Claude hook:   user={insp['claude_code']['user_overhaust']} repo={insp['claude_code']['repo_overhaust']}")
    print(f"Cursor hook:   user={insp['cursor']['user_overhaust_hook']} repo={insp['cursor']['repo_overhaust_hook']}")
    print(f"Cursor MCP OH: {insp['cursor']['mcp_overhaust']}")
    print(f"Cursor rules:  {insp['cursor']['rules_fallback']}")

    if "codex_session" in report:
        s = report["codex_session"]
        print("\n=== Codex session ===")
        print(f"Status:          {s.get('status')}")
        if s.get("status") == "completed":
            print(f"Hook fired:      {s.get('hook_fired')}")
            print(f"Context injected:{s.get('context_injected')}")
            print(f"Verified:        {s.get('verified')}")
            if s.get("debug_events"):
                d = s["debug_events"][-1]
                print(f"Debug: files={d.get('relevant_files')} latency={d.get('latency_ms')}ms")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
