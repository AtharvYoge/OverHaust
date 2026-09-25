"""Continue.dev host adapter — MCP + alwaysApply rule (project `.continue/`).

Stress-tests the host-adapter boundary with a fourth product that:
- shares MCP + rule capabilities with Cursor, but
- uses different config paths/formats (YAML under `.continue/`), and
- has distinct runtimes (VS Code extension, JetBrains plugin, Continue CLI).

Does not call invoke_context_request or touch retrieval.

Module name is continue_host.py because ``continue`` is a Python keyword.
Adapter id remains ``continue``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

from packages.integrations.host import (
    HostCapabilities,
    HostEnvironment,
    IntegrationResult,
    IntegrationStatus,
)
from packages.integrations.install import (
    install_continue_mcp,
    install_continue_rules,
    repo_root,
    uninstall_continue,
)


def _extension_dirs() -> List[Path]:
    home = Path.home()
    return [
        home / ".vscode" / "extensions",
        home / ".cursor" / "extensions",
        home / ".vscode-insiders" / "extensions",
    ]


def _iter_continue_extension_dirs() -> List[Path]:
    pattern = re.compile(r"^continue\.continue-")
    found: List[Path] = []
    for base in _extension_dirs():
        if not base.is_dir():
            continue
        try:
            for child in base.iterdir():
                if child.is_dir() and pattern.match(child.name):
                    found.append(child)
        except OSError:
            continue
    return found


def _find_vscode_continue_version() -> str:
    pattern = re.compile(r"^continue\.continue-(.+)$")
    for child in sorted(_iter_continue_extension_dirs(), reverse=True):
        pkg = child / "package.json"
        if pkg.is_file():
            try:
                data = json.loads(pkg.read_text(encoding="utf-8"))
                version = str(data.get("version") or "").strip()
                if version:
                    return version
            except (json.JSONDecodeError, OSError):
                pass
        match = pattern.match(child.name)
        if match:
            return match.group(1)
    return ""


def _jetbrains_continue_present() -> bool:
    home = Path.home()
    candidates = [
        home / "Library" / "Application Support" / "JetBrains",
        home / ".local" / "share" / "JetBrains",
    ]
    for jetbrains in candidates:
        if not jetbrains.is_dir():
            continue
        try:
            # Prefer shallow plugin dirs over full rglob.
            for ide_dir in jetbrains.iterdir():
                plugins = ide_dir / "plugins"
                if not plugins.is_dir():
                    continue
                for plugin in plugins.iterdir():
                    if "continue" in plugin.name.lower():
                        return True
        except OSError:
            continue
    return False


def _which_cn() -> Optional[Path]:
    from shutil import which

    found = which("cn")
    return Path(found) if found else None


def _cn_version(binary: Path) -> str:
    import subprocess

    try:
        out = subprocess.check_output(
            [str(binary), "--version"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
        return (out or "").strip().split()[-1]
    except Exception:
        return ""


class ContinueAdapter:
    id = "continue"
    product = "continue"

    def detect(self) -> List[HostEnvironment]:
        home = Path.home()
        envs: List[HostEnvironment] = []

        vscode_version = _find_vscode_continue_version()
        if vscode_version or _iter_continue_extension_dirs():
            envs.append(
                HostEnvironment(
                    product="continue",
                    runtime="vscode_extension",
                    version=vscode_version,
                    integration="mcp_always_apply_rule",
                )
            )

        if _jetbrains_continue_present():
            envs.append(
                HostEnvironment(
                    product="continue",
                    runtime="jetbrains_plugin",
                    version="",
                    integration="mcp_always_apply_rule",
                )
            )

        cn = _which_cn()
        if cn:
            envs.append(
                HostEnvironment(
                    product="continue",
                    runtime="cli",
                    version=_cn_version(cn),
                    integration="mcp_always_apply_rule",
                    binary_path=str(cn),
                )
            )

        continue_home = home / ".continue"
        if not envs and continue_home.exists():
            envs.append(
                HostEnvironment(
                    product="continue",
                    runtime="unknown",
                    integration="mcp_always_apply_rule",
                    details={"continue_home": str(continue_home)},
                )
            )
        return envs

    def capabilities(self, environment: Optional[HostEnvironment] = None) -> HostCapabilities:
        return HostCapabilities(
            prompt_hooks=False,
            context_injection=False,
            mcp=True,
            always_apply_rule=True,
            hook_trust_required=False,
        )

    def install(self, *, root=None, python: str = "python3", dry_run: bool = False) -> List[str]:
        base = root or repo_root()
        return [
            install_continue_mcp(root=base, python=python, dry_run=dry_run),
            install_continue_rules(root=base, dry_run=dry_run),
        ]

    def uninstall(self, *, dry_run: bool = False) -> List[str]:
        return uninstall_continue(root=repo_root(), dry_run=dry_run)

    def verify(self, environment: Optional[HostEnvironment] = None) -> IntegrationStatus:
        root = repo_root()
        envs = self.detect()
        env = environment or (
            envs[0]
            if envs
            else HostEnvironment(
                product="continue",
                runtime="unknown",
                integration="mcp_always_apply_rule",
            )
        )
        caps = self.capabilities(env)

        mcp_path = root / ".continue" / "mcpServers" / "overhaust.yaml"
        rule_path = root / ".continue" / "rules" / "overhaust-context.md"
        mcp_ok = False
        if mcp_path.exists():
            text = mcp_path.read_text(encoding="utf-8")
            mcp_ok = "overhaust" in text.lower() and "services.mcp_server.server" in text
        rule_ok = False
        if rule_path.exists():
            text = rule_path.read_text(encoding="utf-8")
            rule_ok = "alwaysApply: true" in text and "get_relevant_context" in text

        runtimes = sorted({e.runtime for e in envs}) if envs else [env.runtime]
        runtime_label = ",".join(runtimes) if len(runtimes) > 1 else runtimes[0]

        actions: List[str] = []
        if not envs:
            result = IntegrationResult.NOT_DETECTED
            message = (
                "Continue host markers not found "
                "(no VS Code/JetBrains extension, cn CLI, or ~/.continue)."
            )
            actions.append(
                "Install Continue, then: "
                "python3 scripts/install_agent_integration.py --agent continue"
            )
        elif mcp_ok and rule_ok:
            result = IntegrationResult.READY
            message = "Project .continue MCP + alwaysApply rule configured."
        else:
            result = IntegrationResult.ACTION_REQUIRED
            missing = []
            if not mcp_ok:
                missing.append(".continue/mcpServers/overhaust.yaml")
            if not rule_ok:
                missing.append(".continue/rules/overhaust-context.md")
            message = "Missing: " + ", ".join(missing)
            actions.append(
                "python3 scripts/install_agent_integration.py --agent continue"
            )

        return IntegrationStatus(
            adapter_id=self.id,
            product="continue",
            runtime=runtime_label,
            integration="mcp_always_apply_rule",
            result=result,
            configuration="FOUND" if (mcp_ok or rule_ok) else "MISSING",
            hook="N/A",
            trust="N/A",
            mcp="CONFIGURED" if mcp_ok else "MISSING",
            context_path=(
                "Continue alwaysApply rule → MCP get_relevant_context "
                "→ invoke_context_request"
            ),
            message=message,
            actions=actions,
            environment=env,
            capabilities=caps,
            extras={
                "mcp_path": str(mcp_path),
                "rule_path": str(rule_path),
                "detected_runtimes": [e.to_dict() for e in envs],
                "live_consumption": "not_tested",
            },
        )
