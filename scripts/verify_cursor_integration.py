#!/usr/bin/env python3
"""
Inspect Cursor OverHaust integration.

Cursor's intended architecture is MCP get_relevant_context + alwaysApply rule.
beforeSubmitPrompt is not a model-injection path.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.integrations.install import install_agent  # noqa: E402


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_parse_error": True}


def _has_overhaust(text: str) -> bool:
    lower = text.lower()
    return "overhaust" in lower or "overhaust_user_prompt_hook" in lower


def _has_injection_hook(data: Optional[Dict[str, Any]]) -> bool:
    text = json.dumps(data or {})
    return "overhaust_user_prompt_hook" in text and "beforeSubmitPrompt" in text


def _rule_always_apply(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    return "alwaysApply: true" in text and "get_relevant_context" in text


def _normalize_path(path: str) -> str:
    try:
        return str(Path(path).expanduser().resolve())
    except OSError:
        return (path or "").strip()


def _mcp_checkout_warnings(mcp_server: Dict[str, Any], expected_root: Path) -> list[str]:
    """Non-fatal warnings when ~/.cursor/mcp.json points at another checkout."""
    warnings: list[str] = []
    expected = _normalize_path(str(expected_root))
    cwd = (mcp_server.get("cwd") or "").strip()
    env = mcp_server.get("env") or {}
    overhaust_root = (env.get("OVERHAUST_ROOT") or env.get("OVERHAUST_REPO_ROOT") or "").strip()

    for label, raw in (("cwd", cwd), ("OVERHAUST_ROOT", overhaust_root)):
        if not raw:
            continue
        resolved = _normalize_path(raw)
        if not Path(resolved).exists():
            warnings.append(
                f"WARNING: MCP {label} path does not exist: {raw!r}. "
                "Re-run: python3 scripts/install_agent_integration.py --agent cursor"
            )
        elif resolved != expected:
            warnings.append(
                f"WARNING: MCP {label} points to {resolved!r}, but this repository is "
                f"{expected!r}. Re-run install from this checkout if that is unintended."
            )
    return warnings


def inspect_cursor(labkot_copy: Optional[Path] = None) -> Dict[str, Any]:
    home = Path.home()
    repo_hooks = ROOT / ".cursor" / "hooks.json"
    repo_rules = ROOT / ".cursor" / "rules" / "overhaust-context.mdc"
    labkot_hooks = (labkot_copy / ".cursor" / "hooks.json") if labkot_copy else None
    labkot_rules = (labkot_copy / ".cursor" / "rules" / "overhaust-context.mdc") if labkot_copy else None

    user_hooks = _read_json(home / ".cursor" / "hooks.json")
    user_mcp = _read_json(home / ".cursor" / "mcp.json")
    repo_hooks_data = _read_json(repo_hooks)
    labkot_hooks_data = _read_json(labkot_hooks) if labkot_hooks else None

    injection_hook_present = any([
        _has_injection_hook(user_hooks),
        _has_injection_hook(repo_hooks_data),
        _has_injection_hook(labkot_hooks_data),
    ])
    mcp_configured = _has_overhaust(json.dumps(user_mcp or {}))
    rules_always = _rule_always_apply(repo_rules) or (
        _rule_always_apply(labkot_rules) if labkot_rules else False
    )
    rule_has_fallback = False
    rule_prefers_root_path = False
    if repo_rules.exists():
        rule_text = repo_rules.read_text(encoding="utf-8")
        lowered = rule_text.lower()
        rule_has_fallback = "unavailable" in lowered or "do not block" in lowered
        rule_prefers_root_path = "root_path" in lowered and "preferably" in lowered

    mcp_server = ((user_mcp or {}).get("mcpServers") or {}).get("overhaust") or {}
    mcp_env = mcp_server.get("env") or {}
    mcp_has_overhaust_root = bool(mcp_env.get("OVERHAUST_ROOT") or mcp_env.get("OVERHAUST_REPO_ROOT"))
    warnings = _mcp_checkout_warnings(mcp_server, ROOT) if mcp_configured else []

    indexed = False
    index_file_count = 0
    try:
        from packages.memory.memory_store import get_memory_store
        from services.ingestion.index_store import ProjectIndexStore

        store = get_memory_store()
        index = ProjectIndexStore(store).load_index("overhaust")
        if index is not None:
            indexed = True
            index_file_count = len(index.files)
    except Exception as exc:  # pragma: no cover - diagnostics only
        index_error = str(exc)
    else:
        index_error = ""

    if mcp_configured and rules_always:
        classification = "MCP + ALWAYS-APPLY RULE"
        reason = (
            "Cursor Agent is instructed to call get_relevant_context before "
            "repository exploration. beforeSubmitPrompt is not used for model injection."
        )
    elif mcp_configured:
        classification = "MCP ONLY"
        reason = "MCP is configured but the alwaysApply rule is missing or disabled."
    elif rules_always:
        classification = "RULES-BASED"
        reason = "alwaysApply rule present but OverHaust MCP server is not in ~/.cursor/mcp.json."
    else:
        classification = "NOT AVAILABLE"
        reason = "No Cursor MCP or alwaysApply OverHaust rule installed."

    return {
        "classification": classification,
        "reason": reason,
        "warnings": warnings,
        "templates": {
            "hooks": str(ROOT / "integrations" / "templates" / "cursor" / "hooks.json"),
            "mcp": str(ROOT / "integrations" / "templates" / "cursor" / "mcp.json"),
            "rules": str(ROOT / "integrations" / "templates" / "cursor" / "rules" / "overhaust-context.mdc"),
        },
        "installed": {
            "user_hooks": str(home / ".cursor" / "hooks.json"),
            "injection_hook_present": injection_hook_present,
            "user_mcp_overhaust": mcp_configured,
            "user_mcp_has_overhaust_root": mcp_has_overhaust_root,
            "user_mcp_cwd": mcp_server.get("cwd"),
            "repo_rules": repo_rules.exists(),
            "repo_rules_always_apply": _rule_always_apply(repo_rules),
            "repo_rules_graceful_fallback": rule_has_fallback,
            "repo_rules_prefers_root_path": rule_prefers_root_path,
            "labkot_copy_rules": labkot_rules.exists() if labkot_rules else False,
            "overhaust_indexed": indexed,
            "overhaust_index_file_count": index_file_count,
            "overhaust_index_error": index_error,
        },
        "installer": {
            "command": "python3 scripts/install_agent_integration.py --agent cursor",
            "writes": [
                "<repo>/.cursor/hooks.json (no OverHaust injection commands)",
                "~/.cursor/mcp.json (merge overhaust server + OVERHAUST_ROOT)",
                "<repo>/.cursor/rules/overhaust-context.mdc (alwaysApply)",
            ],
            "post_install": [
                "python3 scripts/ensure_overhaust_indexed.py",
                "python3 scripts/verify_cursor_integration.py",
            ],
        },
        "cursor_hook_event": "beforeSubmitPrompt",
        "documented_limitation": (
            "Cursor beforeSubmitPrompt schema supports continue/user_message; "
            "additionalContext is not a supported Cursor Agent injection field. "
            "Merged hook responses do not prove the model saw OverHaust context."
        ),
        "intended_path": (
            "alwaysApply rule → MCP get_relevant_context → compact context → gap-only exploration"
        ),
        "real_session_testable": False,
        "real_session_blocker": (
            "Cursor Agent chat cannot be driven programmatically from this harness; "
            "requires a manual user session in Cursor IDE to count Glob/Grep/Read calls."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Cursor OverHaust integration")
    parser.add_argument("--install-labkot-copy", default="", help="Install cursor integration into LabKOT copy")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    labkot_copy = Path(args.install_labkot_copy) if args.install_labkot_copy else None
    if labkot_copy:
        install_agent("cursor", root=ROOT, dry_run=False)
        from packages.integrations.install import (
            install_cursor_hooks,
            install_cursor_rules,
        )

        install_cursor_hooks(target=str(labkot_copy / ".cursor" / "hooks.json"), root=ROOT)
        install_cursor_rules(target=str(labkot_copy / ".cursor" / "rules" / "overhaust-context.mdc"), root=ROOT)

    report = inspect_cursor(labkot_copy)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"Classification: {report['classification']}")
    print(f"Reason: {report['reason']}")
    print(f"Intended path: {report['intended_path']}")
    print(f"Real session testable: {report['real_session_testable']}")
    print(f"Blocker: {report['real_session_blocker']}")
    for warning in report.get("warnings") or []:
        print(warning, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
