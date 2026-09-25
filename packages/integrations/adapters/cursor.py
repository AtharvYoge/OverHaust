"""Cursor host adapter — MCP + alwaysApply rule (not hook injection)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from packages.integrations.host import (
    HostCapabilities,
    HostEnvironment,
    IntegrationResult,
    IntegrationStatus,
)
from packages.integrations.install import (
    install_cursor_hooks,
    install_cursor_mcp,
    install_cursor_rules,
    repo_root,
)


class CursorAdapter:
    id = "cursor"
    product = "cursor"

    def detect(self) -> List[HostEnvironment]:
        home = Path.home()
        markers = [
            home / ".cursor" / "mcp.json",
            home / ".cursor" / "hooks.json",
            home / "Library" / "Application Support" / "Cursor",
            Path("/Applications/Cursor.app"),
        ]
        if not any(p.exists() for p in markers):
            return []
        return [
            HostEnvironment(
                product="cursor",
                runtime="desktop",
                version="",
                integration="mcp_always_apply_rule",
                details={"markers": [str(p) for p in markers if p.exists()]},
            )
        ]

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
            install_cursor_hooks(root=base, python=python, dry_run=dry_run),
            install_cursor_mcp(root=base, python=python, dry_run=dry_run),
            install_cursor_rules(root=base, dry_run=dry_run),
        ]

    def uninstall(self, *, dry_run: bool = False) -> List[str]:
        # Cursor install merges user MCP / project rules; automatic uninstall
        # would risk deleting user edits. Report ACTION via verify instead.
        return []

    def verify(self, environment: Optional[HostEnvironment] = None) -> IntegrationStatus:
        home = Path.home()
        root = repo_root()
        envs = self.detect()
        env = environment or (envs[0] if envs else HostEnvironment(
            product="cursor", runtime="desktop", integration="mcp_always_apply_rule",
        ))
        caps = self.capabilities(env)

        mcp_path = home / ".cursor" / "mcp.json"
        rule_path = root / ".cursor" / "rules" / "overhaust-context.mdc"
        mcp_ok = False
        if mcp_path.exists():
            try:
                data = json.loads(mcp_path.read_text(encoding="utf-8"))
                mcp_ok = "overhaust" in json.dumps(data).lower()
            except json.JSONDecodeError:
                mcp_ok = False
        rule_ok = False
        if rule_path.exists():
            text = rule_path.read_text(encoding="utf-8")
            rule_ok = "alwaysApply: true" in text and "get_relevant_context" in text

        if not envs:
            result = IntegrationResult.NOT_DETECTED
            message = "Cursor host markers not found on this machine."
            actions = ["Install Cursor, then: python3 scripts/install_agent_integration.py --agent cursor"]
        elif mcp_ok and rule_ok:
            result = IntegrationResult.READY
            message = "MCP + alwaysApply rule configured."
            actions = []
        else:
            result = IntegrationResult.ACTION_REQUIRED
            missing = []
            if not mcp_ok:
                missing.append("MCP overhaust server")
            if not rule_ok:
                missing.append("alwaysApply rule")
            message = "Missing: " + ", ".join(missing)
            actions = ["python3 scripts/install_agent_integration.py --agent cursor"]

        return IntegrationStatus(
            adapter_id=self.id,
            product="cursor",
            runtime=env.runtime,
            integration="mcp_always_apply_rule",
            result=result,
            configuration="FOUND" if (mcp_ok or rule_ok) else "MISSING",
            hook="N/A",
            trust="N/A",
            mcp="CONFIGURED" if mcp_ok else "MISSING",
            context_path="alwaysApply rule → MCP get_relevant_context → invoke_context_request",
            message=message,
            actions=actions,
            environment=env,
            capabilities=caps,
            extras={"rule_present": rule_ok, "mcp_path": str(mcp_path)},
        )
