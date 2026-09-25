"""Tests for Claude Code integration verification helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_verify_claude():
    spec = importlib.util.spec_from_file_location(
        "verify_claude_integration",
        ROOT / "scripts" / "verify_claude_integration.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_extract_event_commands_nested():
    mod = _load_verify_claude()
    data = {
        "hooks": {
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'python3 "/tmp/overhaust_user_prompt_hook.py"',
                        }
                    ]
                }
            ],
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "rtk hook claude"}],
                }
            ],
        }
    }
    ups = mod._extract_event_commands(data, "UserPromptSubmit")
    pre = mod._extract_event_commands(data, "PreToolUse")
    assert mod._command_mentions_overhaust(ups[0])
    assert pre[0] == "rtk hook claude"


def test_inspect_claude_returns_classification():
    mod = _load_verify_claude()
    report = mod.inspect_claude()
    assert "classification" in report
    assert "intended_path" in report
    assert "fail_open" in report
    assert report["installed"]["hook_script_exists"] is True
