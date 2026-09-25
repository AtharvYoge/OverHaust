"""Tests for agent integration installer."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from packages.integrations.install import (
    hook_command,
    hook_script_path,
    install_agent,
    install_codex,
    install_claude,
    install_continue_mcp,
    install_continue_rules,
    install_cursor_hooks,
    install_cursor_mcp,
    install_cursor_rules,
)


@pytest.fixture
def temp_root(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    script = repo / "scripts" / "integrations"
    script.mkdir(parents=True)
    (script / "overhaust_user_prompt_hook.py").write_text("# stub\n", encoding="utf-8")
    templates = repo / "integrations" / "templates"

    (templates / "codex").mkdir(parents=True)
    (templates / "claude").mkdir(parents=True)
    (templates / "cursor" / "rules").mkdir(parents=True)

    (templates / "codex" / "hooks.json").write_text(
        json.dumps({
            "description": "test",
            "hooks": {
                "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "{{HOOK_COMMAND}}"}]}]
            },
        }),
        encoding="utf-8",
    )
    (templates / "claude" / "settings.json").write_text(
        json.dumps({
            "hooks": {
                "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "{{HOOK_COMMAND}}"}]}]
            },
        }),
        encoding="utf-8",
    )
    (templates / "cursor" / "hooks.json").write_text(
        json.dumps({
            "version": 1,
            "description": "Cursor uses MCP + rules, not hook injection.",
            "hooks": {},
        }),
        encoding="utf-8",
    )
    (templates / "cursor" / "mcp.json").write_text(
        json.dumps({
            "mcpServers": {
                "overhaust": {
                    "command": "{{PYTHON}}",
                    "args": ["-m", "services.mcp_server.server"],
                    "cwd": "{{REPO_ROOT}}",
                    "env": {
                        "PYTHONPATH": "{{REPO_ROOT}}",
                        "OVERHAUST_ROOT": "{{REPO_ROOT}}",
                    },
                }
            }
        }),
        encoding="utf-8",
    )
    (templates / "cursor" / "rules" / "overhaust-context.mdc").write_text(
        "---\nalwaysApply: true\n---\ncall get_relevant_context first\n",
        encoding="utf-8",
    )
    (templates / "continue" / "mcpServers").mkdir(parents=True)
    (templates / "continue" / "rules").mkdir(parents=True)
    (templates / "continue" / "mcpServers" / "overhaust.yaml").write_text(
        "name: OverHaust MCP\nversion: 0.0.1\nschema: v1\n"
        "mcpServers:\n  - name: overhaust\n    command: \"{{PYTHON}}\"\n"
        "    args: [\"-m\", \"services.mcp_server.server\"]\n"
        "    cwd: \"{{REPO_ROOT}}\"\n"
        "    env:\n      PYTHONPATH: \"{{REPO_ROOT}}\"\n"
        "      OVERHAUST_ROOT: \"{{REPO_ROOT}}\"\n",
        encoding="utf-8",
    )
    (templates / "continue" / "rules" / "overhaust-context.md").write_text(
        "---\nname: OverHaust\nalwaysApply: true\n---\n"
        "call get_relevant_context first\n",
        encoding="utf-8",
    )
    (templates / "cline" / "hooks").mkdir(parents=True)
    (templates / "cline" / "hooks" / "UserPromptSubmit").write_text(
        "#!/usr/bin/env bash\nexec {{PYTHON}} \"{{CLINE_HOOK_SCRIPT}}\"\n",
        encoding="utf-8",
    )
    cline_script = repo / "scripts" / "integrations" / "overhaust_cline_user_prompt_hook.py"
    if not cline_script.exists():
        cline_script.write_text("# stub\n", encoding="utf-8")
    return repo


def test_hook_command_uses_absolute_path(temp_root):
    cmd = hook_command(temp_root)
    assert str(hook_script_path(temp_root)) in cmd


def test_repo_root_points_at_monorepo():
    from packages.integrations.install import repo_root

    root = repo_root()
    assert (root / "packages" / "integrations" / "install.py").is_file()
    assert (root / "integrations" / "templates" / "cursor" / "mcp.json").is_file()
    assert (root / "services" / "mcp_server" / "server.py").is_file()
    assert root.name != "packages"


def test_install_codex_writes_hooks(temp_root):
    target = temp_root / "hooks.json"
    path = install_codex(str(target), root=temp_root)
    assert path == str(target)
    data = json.loads(target.read_text())
    assert "UserPromptSubmit" in data["hooks"]


def test_install_claude_merge_safe(temp_root):
    target = temp_root / "settings.json"
    target.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    install_claude(str(target), root=temp_root)
    data = json.loads(target.read_text())
    assert data["theme"] == "dark"
    assert "UserPromptSubmit" in data["hooks"]


def test_install_claude_preserves_pretooluse_and_avoids_duplicates(temp_root):
    target = temp_root / "settings.json"
    target.write_text(json.dumps({
        "theme": "dark",
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": "rtk hook claude"},
                    ],
                }
            ]
        },
    }), encoding="utf-8")
    install_claude(str(target), root=temp_root)
    install_claude(str(target), root=temp_root)  # second install must not duplicate
    data = json.loads(target.read_text())
    assert data["theme"] == "dark"
    pre = data["hooks"]["PreToolUse"]
    assert pre[0]["matcher"] == "Bash"
    assert pre[0]["hooks"][0]["command"] == "rtk hook claude"
    ups = data["hooks"]["UserPromptSubmit"]
    assert len(ups) == 1
    cmd = ups[0]["hooks"][0]["command"]
    assert "overhaust_user_prompt_hook.py" in cmd
    assert str(temp_root) in cmd


def test_install_cursor_bundle(temp_root):
    install_cursor_hooks(root=temp_root)
    install_cursor_mcp(str(temp_root / ".cursor" / "mcp.json"), root=temp_root)
    install_cursor_rules(root=temp_root)
    hooks = json.loads((temp_root / ".cursor" / "hooks.json").read_text())
    dumped = json.dumps(hooks)
    assert "overhaust_user_prompt_hook" not in dumped
    assert "additionalContext" not in dumped
    mcp = json.loads((temp_root / ".cursor" / "mcp.json").read_text())
    assert "overhaust" in mcp["mcpServers"]
    env = mcp["mcpServers"]["overhaust"].get("env") or {}
    assert env.get("OVERHAUST_ROOT") == str(temp_root)
    assert env.get("PYTHONPATH") == str(temp_root)
    rule = (temp_root / ".cursor" / "rules" / "overhaust-context.mdc").read_text()
    assert "alwaysApply: true" in rule
    assert "get_relevant_context" in rule


def test_install_cursor_strips_legacy_injection_hook(temp_root):
    target = temp_root / ".cursor" / "hooks.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({
        "version": 1,
        "hooks": {
            "beforeSubmitPrompt": [
                {"command": 'python3 "/tmp/overhaust_user_prompt_hook.py"', "timeout": 30},
                {"command": "echo keep-me", "timeout": 5},
            ]
        },
    }), encoding="utf-8")
    install_cursor_hooks(str(target), root=temp_root)
    data = json.loads(target.read_text())
    dumped = json.dumps(data)
    assert "overhaust_user_prompt_hook" not in dumped
    assert "echo keep-me" in dumped


def test_install_continue_bundle(temp_root):
    mcp_path = install_continue_mcp(root=temp_root)
    rule_path = install_continue_rules(root=temp_root)
    assert Path(mcp_path).exists()
    text = Path(mcp_path).read_text(encoding="utf-8")
    assert "overhaust" in text
    assert str(temp_root) in text
    assert "services.mcp_server.server" in text
    rule = Path(rule_path).read_text(encoding="utf-8")
    assert "alwaysApply: true" in rule
    assert "get_relevant_context" in rule


def test_install_dry_run_no_write(temp_root):
    target = temp_root / "codex.json"
    install_codex(str(target), root=temp_root, dry_run=True)
    assert not target.exists()
