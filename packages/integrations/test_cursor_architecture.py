"""Cursor MCP + alwaysApply rule architecture tests."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULE_PATH = ROOT / ".cursor" / "rules" / "overhaust-context.mdc"
TEMPLATE_RULE = (
    ROOT / "integrations" / "templates" / "cursor" / "rules" / "overhaust-context.mdc"
)
HOOKS_PATH = ROOT / ".cursor" / "hooks.json"
TEMPLATE_HOOKS = ROOT / "integrations" / "templates" / "cursor" / "hooks.json"


def test_cursor_rule_exists_and_always_applied():
    assert RULE_PATH.exists()
    text = RULE_PATH.read_text(encoding="utf-8")
    assert "alwaysApply: true" in text
    assert "get_relevant_context" in text
    lowered = text.lower()
    assert "before" in lowered
    assert "glob" in lowered or "grep" in lowered or "explor" in lowered
    assert "unavailable" in lowered or "disconnected" in lowered
    assert "do not block" in lowered
    assert "preferably" in lowered and "root_path" in lowered


def test_cursor_rule_template_matches_installed_intent():
    template = TEMPLATE_RULE.read_text(encoding="utf-8")
    assert "alwaysApply: true" in template
    assert "get_relevant_context" in template
    assert "do not block" in template.lower()
    assert "preferably" in template.lower()
    assert "root_path" in template.lower()


def test_mcp_checkout_warning_helper():
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "scripts"))
    # Import via path load of verify script helpers
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "verify_cursor_integration",
        root / "scripts" / "verify_cursor_integration.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    warnings = mod._mcp_checkout_warnings(
        {"cwd": "/tmp/does-not-exist-overhaust", "env": {}},
        root,
    )
    assert warnings
    assert any("does not exist" in w for w in warnings)

    ok = mod._mcp_checkout_warnings(
        {"cwd": str(root), "env": {"OVERHAUST_ROOT": str(root)}},
        root,
    )
    assert ok == []


def test_cursor_rule_does_not_claim_hook_injection():
    text = RULE_PATH.read_text(encoding="utf-8")
    assert "additionalContext" not in text
    assert "beforeSubmitPrompt" not in text
    assert "user_message" not in text


def test_cursor_hooks_do_not_install_injection_command():
    data = json.loads(HOOKS_PATH.read_text(encoding="utf-8"))
    dumped = json.dumps(data)
    assert "overhaust_user_prompt_hook" not in dumped
    template = json.loads(TEMPLATE_HOOKS.read_text(encoding="utf-8"))
    assert "overhaust_user_prompt_hook" not in json.dumps(template)
    assert "additionalContext" not in dumped
