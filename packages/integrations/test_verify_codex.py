"""Tests for Codex integration verification helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_verify_codex():
    spec = importlib.util.spec_from_file_location(
        "verify_codex_integration",
        ROOT / "scripts" / "verify_codex_integration.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_extract_commands_nested_and_flat():
    mod = _load_verify_codex()
    nested = {
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
            ]
        }
    }
    flat = {
        "hooks": {
            "UserPromptSubmit": [
                {"command": 'python3 "/tmp/overhaust_user_prompt_hook.py"'},
            ]
        }
    }
    assert mod._extract_commands(nested)
    assert mod._extract_commands(flat)
    assert mod._command_mentions_overhaust(mod._extract_commands(nested)[0])


def test_inspect_codex_returns_classification():
    mod = _load_verify_codex()
    report = mod.inspect_codex()
    assert "classification" in report
    assert "intended_path" in report
    assert "fail_open" in report
    assert report["installed"]["hook_script_exists"] is True
