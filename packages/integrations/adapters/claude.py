"""Claude Code host adapter — UserPromptSubmit hook."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from packages.integrations.host import (
    HostCapabilities,
    HostEnvironment,
    IntegrationResult,
    IntegrationStatus,
)
from packages.integrations.install import (
    hook_script_path,
    install_claude,
    repo_root,
)

_OVERHAUST_HOOK_TOKEN = "overhaust_user_prompt_hook"


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_parse_error": True}


def _extract_ups_commands(hooks_data: Optional[Dict[str, Any]]) -> List[str]:
    if not hooks_data or not isinstance(hooks_data, dict):
        return []
    hooks = hooks_data.get("hooks") or {}
    groups = hooks.get("UserPromptSubmit") or []
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


class ClaudeAdapter:
    id = "claude"
    product = "claude"

    def detect(self) -> List[HostEnvironment]:
        home = Path.home()
        markers = [
            home / ".claude" / "settings.json",
            home / ".claude",
            Path("/Applications/Claude.app"),
        ]
        if not any(p.exists() for p in markers):
            return []
        return [
            HostEnvironment(
                product="claude",
                runtime="cli",
                version="",
                integration="user_prompt_hook",
                details={"markers": [str(p) for p in markers if p.exists()]},
            )
        ]

    def capabilities(self, environment: Optional[HostEnvironment] = None) -> HostCapabilities:
        return HostCapabilities(
            prompt_hooks=True,
            context_injection=True,
            mcp=False,
            always_apply_rule=False,
            hook_trust_required=False,
        )

    def install(self, *, root=None, python: str = "python3", dry_run: bool = False) -> List[str]:
        return [install_claude(root=root or repo_root(), python=python, dry_run=dry_run)]

    def uninstall(self, *, dry_run: bool = False) -> List[str]:
        from packages.integrations.install import uninstall_claude

        path = uninstall_claude(dry_run=dry_run)
        return [path] if path else []

    def probe_emission(self):
        """Local hook emission check (not Claude Code UI consumption)."""
        from packages.integrations.emission import (
            additional_context_from,
            probe_hook_emission,
            user_prompt_submit_stdin,
        )

        return probe_hook_emission(
            hook_script_path(repo_root()),
            user_prompt_submit_stdin,
            additional_context_from,
            repo_root=repo_root(),
        )

    def verify(self, environment: Optional[HostEnvironment] = None) -> IntegrationStatus:
        home = Path.home()
        envs = self.detect()
        env = environment or (envs[0] if envs else HostEnvironment(
            product="claude", runtime="cli", integration="user_prompt_hook",
        ))
        caps = self.capabilities(env)

        settings_path = home / ".claude" / "settings.json"
        settings = _read_json(settings_path)
        commands = _extract_ups_commands(settings)
        overhaust = [c for c in commands if _OVERHAUST_HOOK_TOKEN in c]
        script = hook_script_path(repo_root())
        actions: List[str] = []
        warnings: List[str] = []

        if not envs:
            result = IntegrationResult.NOT_DETECTED
            message = "Claude Code host markers not found."
            configuration = "MISSING"
            hook = "MISSING"
        elif settings is None:
            result = IntegrationResult.ACTION_REQUIRED
            message = "No ~/.claude/settings.json found."
            configuration = "MISSING"
            hook = "MISSING"
            actions.append("python3 scripts/install_agent_integration.py --agent claude")
        elif settings.get("_parse_error"):
            result = IntegrationResult.ACTION_REQUIRED
            message = "~/.claude/settings.json is not valid JSON."
            configuration = "INVALID"
            hook = "INVALID"
        elif overhaust:
            configuration = "FOUND"
            hook = "FOUND"
            if not script.exists():
                result = IntegrationResult.ACTION_REQUIRED
                message = "OverHaust hook configured but script is missing."
                warnings.append(f"Hook script missing: {script}")
                actions.append("python3 scripts/install_agent_integration.py --agent claude")
            else:
                result = IntegrationResult.READY
                message = "UserPromptSubmit hook configured."
        else:
            configuration = "FOUND"
            hook = "MISSING"
            result = IntegrationResult.ACTION_REQUIRED
            message = "settings.json exists but OverHaust UserPromptSubmit was not found."
            actions.append("python3 scripts/install_agent_integration.py --agent claude")

        return IntegrationStatus(
            adapter_id=self.id,
            product="claude",
            runtime=env.runtime,
            integration="user_prompt_hook",
            result=result,
            configuration=configuration,
            hook=hook,
            trust="N/A",
            mcp="N/A",
            context_path=(
                "UserPromptSubmit → overhaust_user_prompt_hook.py → "
                "invoke_context_request → hookSpecificOutput.additionalContext"
            ),
            message=message,
            actions=actions,
            warnings=warnings,
            environment=env,
            capabilities=caps,
            extras={"settings_json": str(settings_path), "overhaust_commands": overhaust},
        )
