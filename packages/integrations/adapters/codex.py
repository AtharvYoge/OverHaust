"""Codex host adapter — UserPromptSubmit hook; CLI vs Desktop runtimes."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from packages.integrations.host import (
    HostCapabilities,
    HostEnvironment,
    IntegrationResult,
    IntegrationStatus,
)
from packages.integrations.install import (
    hook_script_path,
    install_codex,
    repo_root,
)

_DESKTOP_BIN = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
_OVERHAUST_HOOK_TOKEN = "overhaust_user_prompt_hook"


def _version_of(binary: Path) -> str:
    try:
        out = subprocess.check_output(
            [str(binary), "--version"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
        text = (out or "").strip()
        # e.g. "codex-cli 0.154.0-alpha.6.2"
        parts = text.split()
        return parts[-1] if parts else text
    except Exception:
        return ""


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


def _config_has_hook_trust(config_text: str) -> Tuple[str, bool]:
    """
    Best-effort trust signal from ~/.codex/config.toml.

    Presence of hooks.state + trusted_hash means at least one hook was trusted.
    Absence does not prove Desktop never trusted via another store — UNKNOWN.
    """
    if not config_text.strip():
        return "UNKNOWN", False
    has_state = "hooks.state" in config_text
    has_hash = "trusted_hash" in config_text
    if has_state and has_hash:
        return "TRUSTED", True
    if has_state:
        return "PARTIAL", True
    return "NOT_TRUSTED", True


def _standalone_cli_binaries(home: Path) -> List[Path]:
    releases = home / ".codex" / "packages" / "standalone" / "releases"
    if not releases.is_dir():
        return []
    found: List[Path] = []
    for child in sorted(releases.iterdir(), reverse=True):
        candidate = child / "bin" / "codex"
        if candidate.is_file():
            found.append(candidate)
    return found


class CodexAdapter:
    id = "codex"
    product = "codex"

    def detect(self) -> List[HostEnvironment]:
        home = Path.home()
        envs: List[HostEnvironment] = []

        desktop = Path(os.environ.get("CODEX_CLI_PATH", "") or _DESKTOP_BIN)
        if desktop.is_file() or _DESKTOP_BIN.is_file():
            binary = desktop if desktop.is_file() else _DESKTOP_BIN
            envs.append(
                HostEnvironment(
                    product="codex",
                    runtime="desktop",
                    version=_version_of(binary),
                    integration="user_prompt_hook",
                    binary_path=str(binary),
                )
            )

        for binary in _standalone_cli_binaries(home):
            envs.append(
                HostEnvironment(
                    product="codex",
                    runtime="cli",
                    version=_version_of(binary),
                    integration="user_prompt_hook",
                    binary_path=str(binary),
                )
            )

        # Generic PATH binary if no standalone package detected
        if not any(e.runtime == "cli" for e in envs):
            which = _which("codex")
            if which and which.resolve() != _DESKTOP_BIN.resolve():
                envs.append(
                    HostEnvironment(
                        product="codex",
                        runtime="cli",
                        version=_version_of(which),
                        integration="user_prompt_hook",
                        binary_path=str(which),
                    )
                )

        # Config present without binary still counts as a codex product home
        if not envs and (home / ".codex").exists():
            envs.append(
                HostEnvironment(
                    product="codex",
                    runtime="unknown",
                    integration="user_prompt_hook",
                    details={"codex_home": str(home / ".codex")},
                )
            )
        return envs

    def capabilities(self, environment: Optional[HostEnvironment] = None) -> HostCapabilities:
        runtime = (environment.runtime if environment else "") or ""
        return HostCapabilities(
            prompt_hooks=True,
            context_injection=True,
            mcp=True,  # Desktop/CLI may expose MCP; not OverHaust's injection path
            always_apply_rule=False,
            hook_trust_required=True,  # unmanaged hooks need trust (Desktop + CLI)
        )

    def install(self, *, root=None, python: str = "python3", dry_run: bool = False) -> List[str]:
        return [install_codex(root=root or repo_root(), python=python, dry_run=dry_run)]

    def uninstall(self, *, dry_run: bool = False) -> List[str]:
        from packages.integrations.install import uninstall_codex

        path = uninstall_codex(dry_run=dry_run)
        return [path] if path else []

    def probe_emission(self):
        """Local hook emission check (not Codex UI consumption)."""
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
        env = environment or _prefer_environment(envs)
        caps = self.capabilities(env)

        hooks_path = home / ".codex" / "hooks.json"
        config_path = home / ".codex" / "config.toml"
        hooks_data = _read_json(hooks_path)
        commands = _extract_ups_commands(hooks_data)
        overhaust = [c for c in commands if _OVERHAUST_HOOK_TOKEN in c]
        script = hook_script_path(repo_root())

        trust_label = "N/A"
        trust_known = False
        if config_path.exists():
            trust_label, trust_known = _config_has_hook_trust(
                config_path.read_text(encoding="utf-8")
            )
        elif overhaust:
            trust_label = "NOT_TRUSTED"
            trust_known = True

        warnings: List[str] = []
        actions: List[str] = []

        if hooks_data is None:
            configuration = "MISSING"
            hook = "MISSING"
            result = IntegrationResult.ACTION_REQUIRED if envs else IntegrationResult.NOT_DETECTED
            message = "No ~/.codex/hooks.json found."
            actions.append("python3 scripts/install_agent_integration.py --agent codex")
        elif hooks_data.get("_parse_error"):
            configuration = "INVALID"
            hook = "INVALID"
            result = IntegrationResult.ACTION_REQUIRED
            message = "~/.codex/hooks.json is not valid JSON."
        elif overhaust:
            configuration = "FOUND"
            hook = "FOUND"
            if not script.exists():
                warnings.append(f"Hook script missing: {script}")
                result = IntegrationResult.ACTION_REQUIRED
                message = "OverHaust hook configured but script is missing."
                actions.append("python3 scripts/install_agent_integration.py --agent codex")
            elif trust_label in {"NOT_TRUSTED", "PARTIAL"} and trust_known:
                result = IntegrationResult.ACTION_REQUIRED
                message = (
                    "OverHaust UserPromptSubmit hook is configured but hook trust "
                    "is not confirmed in ~/.codex/config.toml."
                )
                if env and env.runtime == "desktop":
                    actions.append(
                        "In ChatGPT/Codex Desktop: Settings → Hooks → Trust OverHaust UserPromptSubmit"
                    )
                actions.append("Or in Codex CLI: run /hooks and trust the OverHaust command")
            else:
                result = IntegrationResult.READY
                message = (
                    "UserPromptSubmit hook configured"
                    + (f" (trust={trust_label})" if trust_known else "")
                )
                if trust_label == "UNKNOWN":
                    warnings.append(
                        "Could not confirm hooks.state trust from config.toml; "
                        "Desktop may still require Settings → Hooks trust."
                    )
        else:
            configuration = "FOUND"
            hook = "MISSING"
            result = IntegrationResult.ACTION_REQUIRED
            message = "hooks.json exists but OverHaust UserPromptSubmit was not found."
            actions.append("python3 scripts/install_agent_integration.py --agent codex")

        if not envs and result != IntegrationResult.NOT_DETECTED:
            # Config without detectable binary — still report status
            pass
        elif not envs:
            result = IntegrationResult.NOT_DETECTED
            message = "Codex host not detected."

        runtimes = sorted({e.runtime for e in envs}) if envs else [env.runtime if env else "unknown"]

        return IntegrationStatus(
            adapter_id=self.id,
            product="codex",
            runtime=",".join(runtimes) if len(runtimes) > 1 else (env.runtime if env else "unknown"),
            integration="user_prompt_hook",
            result=result,
            configuration=configuration,
            hook=hook,
            trust=trust_label if overhaust else "N/A",
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
            extras={
                "hooks_json": str(hooks_path),
                "overhaust_commands": overhaust,
                "detected_runtimes": [e.to_dict() for e in envs],
            },
        )


def _prefer_environment(envs: List[HostEnvironment]) -> HostEnvironment:
    if not envs:
        return HostEnvironment(
            product="codex",
            runtime="unknown",
            integration="user_prompt_hook",
        )
    for preferred in ("desktop", "cli", "unknown"):
        for env in envs:
            if env.runtime == preferred:
                return env
    return envs[0]


def _which(name: str) -> Optional[Path]:
    from shutil import which

    found = which(name)
    return Path(found) if found else None
