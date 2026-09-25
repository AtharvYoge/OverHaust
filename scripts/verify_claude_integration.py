#!/usr/bin/env python3
"""
Inspect Claude Code OverHaust UserPromptSubmit integration.

Claude Code injects model-visible context via hookSpecificOutput.additionalContext
(same shared hook path as Codex). This script verifies static configuration and
can smoke-test the hook locally without driving the Claude Code UI.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.integrations.install import hook_script_path  # noqa: E402

HOOK_SCRIPT = hook_script_path(ROOT)
RTK_MARKER = "rtk hook claude"


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_parse_error": True}


def _extract_event_commands(
    hooks_data: Optional[Dict[str, Any]],
    event: str,
) -> List[str]:
    if not hooks_data or not isinstance(hooks_data, dict):
        return []
    hooks = hooks_data.get("hooks") or {}
    groups = hooks.get(event) or []
    commands: List[str] = []
    if not isinstance(groups, list):
        return commands
    for group in groups:
        if not isinstance(group, dict):
            continue
        nested = group.get("hooks")
        if isinstance(nested, list):
            for entry in nested:
                if isinstance(entry, dict) and entry.get("command"):
                    commands.append(str(entry["command"]))
        elif group.get("command"):
            commands.append(str(group["command"]))
    return commands


def _command_mentions_overhaust(command: str) -> bool:
    return "overhaust_user_prompt_hook" in command


def _script_path_from_command(command: str) -> Optional[Path]:
    match = re.search(r'"([^"]*overhaust_user_prompt_hook\.py)"', command)
    if match:
        return Path(match.group(1))
    match = re.search(r"(\S*overhaust_user_prompt_hook\.py)", command)
    if match:
        return Path(match.group(1))
    return None


def inspect_claude() -> Dict[str, Any]:
    home = Path.home()
    settings_path = home / ".claude" / "settings.json"
    settings = _read_json(settings_path)
    ups_commands = _extract_event_commands(settings, "UserPromptSubmit")
    pretool_commands = _extract_event_commands(settings, "PreToolUse")
    overhaust_commands = [c for c in ups_commands if _command_mentions_overhaust(c)]
    script_paths = [p for p in (_script_path_from_command(c) for c in overhaust_commands) if p]

    warnings: List[str] = []
    for path in script_paths:
        if not path.exists():
            warnings.append(
                f"WARNING: Claude hook script missing: {path}. "
                "Re-run: python3 scripts/install_agent_integration.py --agent claude"
            )
        else:
            try:
                resolved = path.resolve()
                expected = HOOK_SCRIPT.resolve()
                if resolved != expected:
                    warnings.append(
                        f"WARNING: Claude hook script is {resolved}, expected {expected} "
                        "for this checkout. Re-run install from this repository if unintended."
                    )
            except OSError:
                warnings.append(f"WARNING: cannot resolve Claude hook script path: {path}")

    rtk_present = any(RTK_MARKER in c for c in pretool_commands)
    dumped = json.dumps(settings or {})
    rtk_intact = RTK_MARKER in dumped

    if settings is None:
        classification = "NOT INSTALLED"
        reason = "No ~/.claude/settings.json found."
    elif settings.get("_parse_error"):
        classification = "INVALID"
        reason = "~/.claude/settings.json is not valid JSON."
    elif overhaust_commands:
        classification = "USERPROMPTSUBMIT HOOK"
        reason = (
            "Claude Code UserPromptSubmit is configured to run the OverHaust hook, "
            "which calls invoke_context_request and emits additionalContext."
        )
    else:
        classification = "SETTINGS WITHOUT OVERHAUST"
        reason = (
            "~/.claude/settings.json exists but no OverHaust UserPromptSubmit "
            "command was found."
        )

    indexed = False
    index_file_count = 0
    index_error = ""
    try:
        from packages.memory.memory_store import get_memory_store
        from services.ingestion.index_store import ProjectIndexStore

        store = get_memory_store()
        index = ProjectIndexStore(store).load_index("overhaust")
        if index is not None:
            indexed = True
            index_file_count = len(index.files)
    except Exception as exc:  # pragma: no cover
        index_error = str(exc)

    return {
        "classification": classification,
        "reason": reason,
        "warnings": warnings,
        "intended_path": (
            "UserPromptSubmit → overhaust_user_prompt_hook.py → "
            "invoke_context_request → hookSpecificOutput.additionalContext"
        ),
        "fail_open": (
            "On OverHaust errors the hook returns empty additionalContext and exit 0 "
            "so Claude Code continues normally."
        ),
        "installed": {
            "settings_json": str(settings_path),
            "settings_present": settings is not None and not settings.get("_parse_error"),
            "user_prompt_submit_commands": ups_commands,
            "overhaust_commands": overhaust_commands,
            "pretool_use_commands": pretool_commands,
            "rtk_pretool_present": rtk_present,
            "rtk_marker_intact": rtk_intact,
            "overhaust_user_prompt_submit_count": len(overhaust_commands),
            "hook_script_expected": str(HOOK_SCRIPT),
            "hook_script_exists": HOOK_SCRIPT.exists(),
            "overhaust_indexed": indexed,
            "overhaust_index_file_count": index_file_count,
            "overhaust_index_error": index_error,
        },
        "installer": {
            "command": "python3 scripts/install_agent_integration.py --agent claude",
            "post_install": [
                "python3 scripts/ensure_overhaust_indexed.py  # or index your target project",
                "python3 scripts/verify_claude_integration.py --smoke",
                "Start Claude Code in the indexed repository",
            ],
        },
        "model_visible_claim": (
            "Tests and Claude hook schema establish that additionalContext is emitted. "
            "This harness does not prove a live Claude Code UI session consumed it."
        ),
    }


def smoke_hook_local() -> Dict[str, Any]:
    """Safe local hook invocation using a temporary indexed fixture (not Claude UI)."""
    from packages.integrations.interception import CONTEXT_MARKER
    from packages.memory.memory_store import MemoryStore
    from packages.retrieval.test_fixtures import make_kot_tree
    from services.ingestion.index_store import ProjectIndexStore

    tmpdir = tempfile.mkdtemp()
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()
    try:
        root = Path(tmpdir)
        make_kot_tree(root)
        store = MemoryStore(db.name)
        store.add_project("claude-verify", "ClaudeVerify", "", str(root))
        ProjectIndexStore(store).sync_project("claude-verify", str(root))

        env = os.environ.copy()
        env["OVERHAUST_DB_PATH"] = db.name
        proc = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=json.dumps({
                "prompt": "Where is the KOT generated?",
                "cwd": str(root),
                "hook_event_name": "UserPromptSubmit",
            }),
            text=True,
            capture_output=True,
            cwd=str(ROOT),
            env=env,
            timeout=60,
        )
        if proc.returncode != 0:
            return {"ok": False, "error": proc.stderr or "non-zero exit"}
        out = json.loads(proc.stdout)
        ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
        return {
            "ok": True,
            "has_marker": CONTEXT_MARKER in ctx,
            "context_bytes": len(ctx.encode("utf-8")),
            "stdout_keys": list(out.keys()),
        }
    finally:
        if os.path.exists(db.name):
            os.unlink(db.name)


def smoke_fail_open() -> Dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps({
            "prompt": "hello",
            "cwd": "/no/such/overhaust/project",
            "hook_event_name": "UserPromptSubmit",
        }),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        timeout=60,
    )
    out = json.loads(proc.stdout) if proc.stdout.strip() else {}
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext")
    return {
        "ok": proc.returncode == 0 and ctx == "",
        "returncode": proc.returncode,
        "additional_context_empty": ctx == "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Claude Code OverHaust integration")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run local hook smoke tests (no Claude Code UI)",
    )
    args = parser.parse_args()

    report = inspect_claude()
    if args.smoke:
        report["smoke"] = {
            "local_hook": smoke_hook_local(),
            "fail_open": smoke_fail_open(),
        }

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"Classification: {report['classification']}")
    print(f"Reason: {report['reason']}")
    print(f"Intended path: {report['intended_path']}")
    print(f"Fail-open: {report['fail_open']}")
    print(f"Model-visible claim: {report['model_visible_claim']}")
    installed = report["installed"]
    print(f"RTK PreToolUse preserved: {installed['rtk_pretool_present']}")
    print(f"OverHaust UserPromptSubmit count: {installed['overhaust_user_prompt_submit_count']}")
    for warning in report.get("warnings") or []:
        print(warning, file=sys.stderr)
    if args.smoke:
        smoke = report["smoke"]
        print(f"Smoke local hook: {smoke['local_hook']}")
        print(f"Smoke fail-open:  {smoke['fail_open']}")
        if not smoke["local_hook"].get("ok") or not smoke["fail_open"].get("ok"):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
