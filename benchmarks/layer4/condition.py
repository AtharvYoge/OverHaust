"""
Toggle the OverHaust condition for Codex through the existing hook path.

Baseline and OverHaust sessions get the same argv, sandbox, and environment
except for `$CODEX_HOME/hooks.json`. The OverHaust home installs the repo's
Codex UserPromptSubmit template (`packages.integrations.install.install_codex`).
The task prompt is passed through unchanged. Context is not pasted into it.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from packages.integrations.install import install_codex


INTEGRATION_NONE = "none"
INTEGRATION_HOOK = "codex_user_prompt_submit_hook"

# Identical for both conditions. `--dangerously-bypass-hook-trust` is a no-op
# when no hooks are installed, and it is required for an unattended OverHaust
# hook (Codex otherwise waits on hook trust). Keeping it on both sides means
# the permission set does not differ.
CODEX_EXEC_PERMISSIONS = {
    "sandbox": "workspace-write",
    "dangerously_bypass_hook_trust": True,
    "dangerously_bypass_approvals_and_sandbox": False,
    "skip_git_repo_check": True,
    "ignore_user_config": True,
    "ephemeral": False,
    "resume": False,
    "color": "never",
    "json": True,
}


@dataclass
class CodexHome:
    path: Path
    hooks_path: Optional[Path]
    hook_command: Optional[str]
    integration_path: str
    auth_mode: str


def user_codex_home() -> Path:
    raw = os.environ.get("CODEX_HOME", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".codex"


def detect_auth_mode(env: Optional[Dict[str, str]] = None, home: Optional[Path] = None) -> str:
    """
    api_key    — OPENAI_API_KEY or CODEX_API_KEY is set
    codex_login — ~/.codex/auth.json (or $CODEX_HOME/auth.json) exists
    missing    — neither
    """
    current = env if env is not None else os.environ
    if (current.get("CODEX_API_KEY") or "").strip() or (current.get("OPENAI_API_KEY") or "").strip():
        return "api_key"
    auth_home = home if home is not None else user_codex_home()
    if (auth_home / "auth.json").is_file():
        return "codex_login"
    return "missing"


def _hook_command_from(hooks_path: Path) -> Optional[str]:
    import json

    try:
        data = json.loads(hooks_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    groups = ((data.get("hooks") or {}).get("UserPromptSubmit")) or []
    if not isinstance(groups, list):
        return None
    for group in groups:
        if not isinstance(group, dict):
            continue
        nested = group.get("hooks")
        if isinstance(nested, list):
            for entry in nested:
                if isinstance(entry, dict) and entry.get("command"):
                    return str(entry["command"])
        elif group.get("command"):
            return str(group["command"])
    return None


def prepare_codex_home(
    home: Path,
    *,
    condition: str,
    repo_root: Path,
    auth_mode: str,
    auth_source: Optional[Path] = None,
    python: str = "python3",
) -> CodexHome:
    """
    Create a fresh Codex home.

    The directory must exist before `codex exec` (CODEX_HOME is not created
    by the CLI). Sessions, logs, and user hooks are not copied in.
    """
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True)

    hook_command: Optional[str] = None
    hooks_path: Optional[Path] = None
    if condition == "overhaust":
        hooks_path = home / "hooks.json"
        install_codex(target=str(hooks_path), root=repo_root, python=python)
        hook_command = _hook_command_from(hooks_path)
        integration = INTEGRATION_HOOK
    elif condition == "baseline":
        integration = INTEGRATION_NONE
    else:
        raise ValueError(f"invalid condition: {condition}")

    if auth_mode == "codex_login":
        source = auth_source or (user_codex_home() / "auth.json")
        if source.is_file():
            dest = home / "auth.json"
            shutil.copyfile(source, dest)
            try:
                os.chmod(dest, 0o600)
            except OSError:
                pass

    return CodexHome(
        path=home,
        hooks_path=hooks_path,
        hook_command=hook_command,
        integration_path=integration,
        auth_mode=auth_mode,
    )


def build_exec_command(
    *,
    binary: str,
    prompt: str,
    cwd: Path,
    model: Optional[str],
    last_message_path: Path,
) -> List[str]:
    """Argv for one non-interactive session. `prompt` is the task text only."""
    if prompt == "-" or prompt.startswith("-"):
        raise ValueError(
            "Refusing a prompt Codex would treat as stdin or a flag. "
            "Layer 4 passes the task prompt as a single argument."
        )
    command = [
        binary,
        "exec",
        "--json",
        "--color", "never",
        "--skip-git-repo-check",
        "--dangerously-bypass-hook-trust",
        "--sandbox", "workspace-write",
        "--ignore-user-config",
        "--cd", str(cwd),
        "--output-last-message", str(last_message_path),
    ]
    if model:
        command.extend(["--model", model])
    command.append(prompt)
    return command


def build_exec_env(
    base: Dict[str, str],
    *,
    codex_home: Path,
    db_path: str,
    project_id: str,
    hook_debug_path: Path,
    auth_mode: str,
) -> Dict[str, str]:
    """
    Same variables for both conditions. The hook reads OVERHAUST_DB_PATH and
    OVERHAUST_PROJECT_ID; baseline never starts the hook.
    """
    env = dict(base)
    env["CODEX_HOME"] = str(codex_home)
    env["OVERHAUST_DB_PATH"] = db_path
    env["OVERHAUST_PROJECT_ID"] = project_id
    env["OVERHAUST_INTEGRATION_DEBUG"] = "1"
    env["OVERHAUST_INTEGRATION_DEBUG_FILE"] = str(hook_debug_path)
    if auth_mode == "api_key":
        key = (env.get("CODEX_API_KEY") or env.get("OPENAI_API_KEY") or "").strip()
        if key:
            env["CODEX_API_KEY"] = key
    return env
