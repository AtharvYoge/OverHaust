"""
Install OverHaust agent hook integrations (Codex, Claude Code, Cursor).
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional


def repo_root() -> Path:
    """OverHaust monorepo root (packages/integrations → packages → root)."""
    return Path(__file__).resolve().parents[2]


def hook_script_path(root: Optional[Path] = None) -> Path:
    base = root or repo_root()
    return base / "scripts" / "integrations" / "overhaust_user_prompt_hook.py"


def hook_command(root: Optional[Path] = None, python: str = "python3") -> str:
    script = hook_script_path(root)
    return f'{python} "{script}"'


def _load_template(rel_path: str, root: Optional[Path] = None) -> str:
    base = root or repo_root()
    path = base / "integrations" / "templates" / rel_path
    return path.read_text(encoding="utf-8")


def _substitute_placeholders(value: Any, root: Path, python: str = "python3") -> Any:
    command = hook_command(root, python)
    repo = str(root)

    if isinstance(value, str):
        return (
            value.replace("{{HOOK_COMMAND}}", command)
            .replace("{{REPO_ROOT}}", repo)
            .replace("{{PYTHON}}", python)
        )
    if isinstance(value, list):
        return [_substitute_placeholders(item, root, python) for item in value]
    if isinstance(value, dict):
        return {k: _substitute_placeholders(v, root, python) for k, v in value.items()}
    return value


def _load_rendered_template(rel_path: str, root: Path, python: str = "python3") -> Dict[str, Any]:
    raw = json.loads(_load_template(rel_path, root))
    rendered = _substitute_placeholders(raw, root, python)
    assert isinstance(rendered, dict)
    return rendered


def _deep_merge_hooks(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """Merge hook event lists without duplicating identical command entries."""
    merged_hooks: Dict[str, Any] = dict(existing.get("hooks", {}))
    for event, groups in incoming.get("hooks", {}).items():
        if event not in merged_hooks:
            merged_hooks[event] = groups
            continue
        existing_groups = merged_hooks[event]
        if not isinstance(existing_groups, list):
            merged_hooks[event] = groups
            continue
        for group in groups:
            cmd = _extract_command(group)
            if cmd and any(_extract_command(g) == cmd for g in existing_groups):
                continue
            existing_groups.append(group)
        merged_hooks[event] = existing_groups
    return merged_hooks


def _extract_command(group: Any) -> Optional[str]:
    if not isinstance(group, dict):
        return None
    if "command" in group:
        return str(group["command"])
    hooks = group.get("hooks")
    if isinstance(hooks, list) and hooks:
        first = hooks[0]
        if isinstance(first, dict):
            return str(first.get("command", "")) or None
    return None


def install_codex(
    target: Optional[str] = None,
    *,
    root: Optional[Path] = None,
    python: str = "python3",
    dry_run: bool = False,
) -> str:
    base = root or repo_root()
    path = os.path.expanduser(target or "~/.codex/hooks.json")
    incoming = _load_rendered_template("codex/hooks.json", base, python)

    existing: Dict[str, Any] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            existing = json.load(fh)

    merged = dict(existing)
    merged["hooks"] = _deep_merge_hooks(existing, incoming)
    if "description" not in merged and incoming.get("description"):
        merged["description"] = incoming["description"]

    if dry_run:
        return path

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2)
        fh.write("\n")
    return path


def install_claude(
    target: Optional[str] = None,
    *,
    root: Optional[Path] = None,
    python: str = "python3",
    project_local: bool = False,
    dry_run: bool = False,
) -> str:
    base = root or repo_root()
    if target:
        path = target
    elif project_local:
        path = str(base / ".claude" / "settings.json")
    else:
        path = os.path.expanduser("~/.claude/settings.json")

    template = _load_rendered_template("claude/settings.json", base, python)
    incoming = template

    existing: Dict[str, Any] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            existing = json.load(fh)

    merged = dict(existing)
    merged["hooks"] = _deep_merge_hooks(existing, incoming)

    if dry_run:
        return path

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2)
        fh.write("\n")
    return path


def _is_overhaust_hook_entry(entry: Any) -> bool:
    cmd = _extract_command(entry) or ""
    return "overhaust_user_prompt_hook" in cmd


def _strip_overhaust_hook_commands(hooks: Dict[str, Any]) -> Dict[str, Any]:
    """Remove OverHaust injection commands; keep unrelated third-party hooks."""
    stripped: Dict[str, Any] = {}
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            stripped[event] = groups
            continue
        filtered = [group for group in groups if not _is_overhaust_hook_entry(group)]
        if filtered:
            stripped[event] = filtered
    return stripped


def install_cursor_hooks(
    target: Optional[str] = None,
    *,
    root: Optional[Path] = None,
    python: str = "python3",
    project_local: bool = True,
    dry_run: bool = False,
) -> str:
    """Write Cursor hooks.json without OverHaust model-injection commands.

    Cursor Agent context comes from MCP get_relevant_context + alwaysApply rules.
    """
    base = root or repo_root()
    if target:
        path = target
    elif project_local:
        path = str(base / ".cursor" / "hooks.json")
    else:
        path = os.path.expanduser("~/.cursor/hooks.json")

    incoming = _load_rendered_template("cursor/hooks.json", base, python)

    existing: Dict[str, Any] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            existing = json.load(fh)

    merged = dict(existing)
    existing_hooks = _strip_overhaust_hook_commands(existing.get("hooks") or {})
    incoming_hooks = incoming.get("hooks") or {}
    combined = dict(existing_hooks)
    for event, groups in incoming_hooks.items():
        if event not in combined:
            combined[event] = groups
    merged["hooks"] = combined
    merged["version"] = incoming.get("version", existing.get("version", 1))
    if incoming.get("description"):
        merged["description"] = incoming["description"]

    if dry_run:
        return path

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2)
        fh.write("\n")
    return path


def install_cursor_mcp(
    target: Optional[str] = None,
    *,
    root: Optional[Path] = None,
    python: str = "python3",
    dry_run: bool = False,
) -> str:
    base = root or repo_root()
    path = os.path.expanduser(target or "~/.cursor/mcp.json")
    incoming = _load_rendered_template("cursor/mcp.json", base, python)

    existing: Dict[str, Any] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            existing = json.load(fh)

    merged = dict(existing)
    servers = dict(existing.get("mcpServers", {}))
    servers["overhaust"] = incoming["mcpServers"]["overhaust"]
    merged["mcpServers"] = servers

    if dry_run:
        return path

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2)
        fh.write("\n")
    return path


def install_cursor_rules(
    target: Optional[str] = None,
    *,
    root: Optional[Path] = None,
    dry_run: bool = False,
) -> str:
    base = root or repo_root()
    if target:
        path = Path(target)
    else:
        path = base / ".cursor" / "rules" / "overhaust-context.mdc"

    src = base / "integrations" / "templates" / "cursor" / "rules" / "overhaust-context.mdc"
    if dry_run:
        return str(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, path)
    return str(path)


def install_continue_mcp(
    target: Optional[str] = None,
    *,
    root: Optional[Path] = None,
    python: str = "python3",
    dry_run: bool = False,
) -> str:
    """Write Continue workspace MCP YAML under .continue/mcpServers/."""
    base = root or repo_root()
    if target:
        path = Path(target)
    else:
        path = base / ".continue" / "mcpServers" / "overhaust.yaml"

    raw = _load_template("continue/mcpServers/overhaust.yaml", base)
    rendered = (
        raw.replace("{{HOOK_COMMAND}}", hook_command(base, python))
        .replace("{{REPO_ROOT}}", str(base))
        .replace("{{PYTHON}}", python)
    )
    if dry_run:
        return str(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered if rendered.endswith("\n") else rendered + "\n", encoding="utf-8")
    return str(path)


def install_continue_rules(
    target: Optional[str] = None,
    *,
    root: Optional[Path] = None,
    dry_run: bool = False,
) -> str:
    """Copy Continue alwaysApply rule into .continue/rules/."""
    base = root or repo_root()
    if target:
        path = Path(target)
    else:
        path = base / ".continue" / "rules" / "overhaust-context.md"
    src = base / "integrations" / "templates" / "continue" / "rules" / "overhaust-context.md"
    if dry_run:
        return str(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, path)
    return str(path)


def uninstall_continue(
    *,
    root: Optional[Path] = None,
    dry_run: bool = False,
) -> List[str]:
    """Remove OverHaust-owned Continue project files only."""
    base = root or repo_root()
    paths = [
        base / ".continue" / "mcpServers" / "overhaust.yaml",
        base / ".continue" / "rules" / "overhaust-context.md",
    ]
    removed: List[str] = []
    for path in paths:
        if not path.exists():
            continue
        removed.append(str(path))
        if not dry_run:
            path.unlink()
    return removed


def cline_hook_script_path(root: Optional[Path] = None) -> Path:
    base = root or repo_root()
    return base / "scripts" / "integrations" / "overhaust_cline_user_prompt_hook.py"


def install_cline_hook(
    target: Optional[str] = None,
    *,
    root: Optional[Path] = None,
    python: str = "python3",
    dry_run: bool = False,
) -> str:
    """Install project-local Cline UserPromptSubmit wrapper (contextModification)."""
    base = root or repo_root()
    if target:
        path = Path(target)
    else:
        path = base / ".clinerules" / "hooks" / "UserPromptSubmit"

    template = _load_template("cline/hooks/UserPromptSubmit", base)
    script = cline_hook_script_path(base)
    rendered = (
        template.replace("{{PYTHON}}", python)
        .replace("{{CLINE_HOOK_SCRIPT}}", str(script))
        .replace("{{REPO_ROOT}}", str(base))
    )
    if dry_run:
        return str(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered if rendered.endswith("\n") else rendered + "\n", encoding="utf-8")
    # Executable bit required by Cline hooks on macOS/Linux
    mode = path.stat().st_mode
    path.chmod(mode | 0o111)
    return str(path)


def uninstall_cline(
    *,
    root: Optional[Path] = None,
    dry_run: bool = False,
) -> List[str]:
    """Remove OverHaust-owned Cline UserPromptSubmit hook if present."""
    base = root or repo_root()
    path = base / ".clinerules" / "hooks" / "UserPromptSubmit"
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    if "overhaust_cline_user_prompt_hook" not in text:
        return []
    if dry_run:
        return [str(path)]
    path.unlink()
    return [str(path)]


def uninstall_codex(
    target: Optional[str] = None,
    *,
    dry_run: bool = False,
) -> Optional[str]:
    """Remove OverHaust UserPromptSubmit entries from Codex hooks.json."""
    path = os.path.expanduser(target or "~/.codex/hooks.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        existing = json.load(fh)
    hooks = existing.get("hooks") or {}
    stripped = _strip_overhaust_hook_commands(hooks if isinstance(hooks, dict) else {})
    if dry_run:
        return path
    existing["hooks"] = stripped
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(existing, fh, indent=2)
        fh.write("\n")
    return path


def uninstall_claude(
    target: Optional[str] = None,
    *,
    dry_run: bool = False,
) -> Optional[str]:
    """Remove OverHaust UserPromptSubmit entries; preserve unrelated hooks."""
    path = os.path.expanduser(target or "~/.claude/settings.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        existing = json.load(fh)
    hooks = existing.get("hooks") or {}
    stripped = _strip_overhaust_hook_commands(hooks if isinstance(hooks, dict) else {})
    if dry_run:
        return path
    existing["hooks"] = stripped
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(existing, fh, indent=2)
        fh.write("\n")
    return path


def install_agent(
    agent: str,
    *,
    root: Optional[Path] = None,
    python: str = "python3",
    dry_run: bool = False,
) -> List[str]:
    """Install integration for one host adapter; returns list of written paths."""
    from packages.integrations.adapters.registry import get_adapter, list_adapters

    if agent == "all":
        written: List[str] = []
        for adapter in list_adapters():
            written.extend(adapter.install(root=root, python=python, dry_run=dry_run))
        return written

    adapter = get_adapter(agent)
    if adapter is None:
        raise ValueError(f"unsupported agent: {agent}")
    return adapter.install(root=root, python=python, dry_run=dry_run)
