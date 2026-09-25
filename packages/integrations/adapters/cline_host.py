"""Cline host adapter — UserPromptSubmit → contextModification.

B/C stress test: Cline uses a different native injection field than
Codex/Claude (contextModification vs additionalContext) and a different
stdin shape (userPromptSubmit.prompt + workspaceRoots).

Capability flags already cover this (prompt_hooks + context_injection).
Host-specific I/O lives in scripts/integrations/overhaust_cline_user_prompt_hook.py
and MUST NOT modify packages.integrations.hook_io.

Question A (detect/install/verify config): supported by this adapter.
Question B (live model consumption): UNKNOWN / host-version-dependent —
Cline issue #13554 reports UserPromptSubmit contextModification discarded
on some VS Code builds; fix PR #13623 was open at audit time.
"""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import List, Optional

from packages.integrations.host import (
    HostCapabilities,
    HostEnvironment,
    IntegrationResult,
    IntegrationStatus,
)
from packages.integrations.install import (
    install_cline_hook,
    repo_root,
    uninstall_cline,
)

# Documented delivery caveat (do not claim READY implies model saw context).
_DELIVERY_WARNING = (
    "Live model consumption of UserPromptSubmit contextModification is "
    "host-version-dependent. Cline issue #13554 reports silent discard on "
    "some VS Code builds; enable Hooks in Features and verify on your version."
)


def _extension_dirs() -> List[Path]:
    home = Path.home()
    return [
        home / ".vscode" / "extensions",
        home / ".cursor" / "extensions",
        home / ".vscode-insiders" / "extensions",
    ]


def _iter_cline_extension_dirs() -> List[Path]:
    # Historical publisher id: saoudrizwan.claude-dev; also match *cline*
    patterns = [
        re.compile(r"^saoudrizwan\.claude-dev-"),
        re.compile(r"^saoudrizwan\.cline-"),
        re.compile(r".*\.cline-", re.I),
    ]
    found: List[Path] = []
    for base in _extension_dirs():
        if not base.is_dir():
            continue
        try:
            for child in base.iterdir():
                if not child.is_dir():
                    continue
                if any(p.match(child.name) for p in patterns):
                    found.append(child)
        except OSError:
            continue
    return found


def _find_cline_extension_version() -> str:
    for child in sorted(_iter_cline_extension_dirs(), reverse=True):
        pkg = child / "package.json"
        if pkg.is_file():
            try:
                data = json.loads(pkg.read_text(encoding="utf-8"))
                version = str(data.get("version") or "").strip()
                if version:
                    return version
            except (json.JSONDecodeError, OSError):
                pass
        # folder suffix often embeds version
        parts = child.name.rsplit("-", 1)
        if len(parts) == 2 and parts[1][0].isdigit():
            return parts[1]
    return ""


def _which_cline() -> Optional[Path]:
    from shutil import which

    found = which("cline")
    return Path(found) if found else None


def _cline_cli_version(binary: Path) -> str:
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


def _global_hooks_dir() -> Path:
    return Path.home() / "Documents" / "Cline" / "Hooks"


def _project_hook_path(root: Path) -> Path:
    return root / ".clinerules" / "hooks" / "UserPromptSubmit"


def _hook_mentions_overhaust(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return "overhaust_cline_user_prompt_hook" in text or "overhaust-context" in text


def _is_executable(path: Path) -> bool:
    try:
        mode = path.stat().st_mode
        return bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    except OSError:
        return False


class ClineAdapter:
    id = "cline"
    product = "cline"

    def detect(self) -> List[HostEnvironment]:
        home = Path.home()
        envs: List[HostEnvironment] = []

        version = _find_cline_extension_version()
        if version or _iter_cline_extension_dirs():
            envs.append(
                HostEnvironment(
                    product="cline",
                    runtime="vscode_extension",
                    version=version,
                    integration="user_prompt_context_modification",
                )
            )

        cli = _which_cline()
        if cli:
            envs.append(
                HostEnvironment(
                    product="cline",
                    runtime="cli",
                    version=_cline_cli_version(cli),
                    integration="user_prompt_context_modification",
                    binary_path=str(cli),
                )
            )

        # Config markers without a binary/extension
        markers = [
            home / ".cline",
            _global_hooks_dir(),
            home / "Documents" / "Cline",
        ]
        if not envs and any(p.exists() for p in markers):
            envs.append(
                HostEnvironment(
                    product="cline",
                    runtime="unknown",
                    integration="user_prompt_context_modification",
                    details={"markers": [str(p) for p in markers if p.exists()]},
                )
            )
        return envs

    def capabilities(self, environment: Optional[HostEnvironment] = None) -> HostCapabilities:
        return HostCapabilities(
            prompt_hooks=True,
            context_injection=True,
            mcp=True,  # Cline also supports MCP; this adapter uses hooks
            always_apply_rule=True,  # .clinerules exist separately
            hook_trust_required=True,  # Features → Enable Hooks
        )

    def install(self, *, root=None, python: str = "python3", dry_run: bool = False) -> List[str]:
        base = root or repo_root()
        return [install_cline_hook(root=base, python=python, dry_run=dry_run)]

    def uninstall(self, *, dry_run: bool = False) -> List[str]:
        return uninstall_cline(root=repo_root(), dry_run=dry_run)

    def probe_emission(self):
        """Local contextModification emission check (not Cline UI consumption)."""
        from packages.integrations.emission import probe_hook_emission
        from packages.integrations.install import cline_hook_script_path

        def build_stdin(prompt: str, cwd: str) -> str:
            return json.dumps({
                "hookName": "UserPromptSubmit",
                "workspaceRoots": [cwd],
                "userPromptSubmit": {"prompt": prompt, "attachments": []},
            })

        def extract(payload):
            value = payload.get("contextModification")
            return value if isinstance(value, str) else None

        return probe_hook_emission(
            cline_hook_script_path(repo_root()),
            build_stdin,
            extract,
            repo_root=repo_root(),
        )

    def verify(self, environment: Optional[HostEnvironment] = None) -> IntegrationStatus:
        root = repo_root()
        envs = self.detect()
        env = environment or (
            envs[0]
            if envs
            else HostEnvironment(
                product="cline",
                runtime="unknown",
                integration="user_prompt_context_modification",
            )
        )
        caps = self.capabilities(env)

        project_hook = _project_hook_path(root)
        global_hook = _global_hooks_dir() / "UserPromptSubmit"
        project_ok = _hook_mentions_overhaust(project_hook)
        global_ok = _hook_mentions_overhaust(global_hook)
        hook_path = project_hook if project_ok else (global_hook if global_ok else project_hook)
        hook_ok = project_ok or global_ok
        executable = _is_executable(hook_path) if hook_ok else False

        runtimes = sorted({e.runtime for e in envs}) if envs else [env.runtime]
        runtime_label = ",".join(runtimes) if len(runtimes) > 1 else runtimes[0]

        warnings = [_DELIVERY_WARNING]
        actions: List[str] = []

        if os.name == "nt" or runtime_label == "unsupported_windows":
            # Official hooks README: Windows shebang hooks not currently supported.
            pass

        if not envs:
            result = IntegrationResult.NOT_DETECTED
            message = "Cline host markers not found (extension, cline CLI, or ~/Documents/Cline)."
            configuration = "MISSING"
            hook = "MISSING"
            trust = "N/A"
            actions.append(
                "Install Cline, then: python3 scripts/install_agent_integration.py --agent cline"
            )
        elif not hook_ok:
            result = IntegrationResult.ACTION_REQUIRED
            message = "Cline detected but OverHaust UserPromptSubmit hook is not installed."
            configuration = "MISSING"
            hook = "MISSING"
            trust = "UNKNOWN"
            actions.append("python3 scripts/install_agent_integration.py --agent cline")
            actions.append("Enable Hooks in Cline Feature Settings")
        elif not executable:
            result = IntegrationResult.ACTION_REQUIRED
            message = f"Hook present but not executable: {hook_path}"
            configuration = "FOUND"
            hook = "FOUND"
            trust = "UNKNOWN"
            actions.append(f"chmod +x {hook_path}")
            actions.append("Enable Hooks in Cline Feature Settings")
        else:
            # Config is in place; Enable Hooks cannot be proven from disk.
            result = IntegrationResult.ACTION_REQUIRED
            message = (
                "OverHaust Cline hook is installed. Enable Hooks in Cline Features, "
                "then manually confirm the model receives <!-- overhaust-context --> "
                "(not proven by this doctor)."
            )
            configuration = "FOUND"
            hook = "FOUND"
            trust = "UNKNOWN"
            actions.append("Enable Hooks in Cline Feature Settings (if not already on)")
            actions.append(
                "Manual smoke: submit a repo question and check for overhaust-context"
            )

        return IntegrationStatus(
            adapter_id=self.id,
            product="cline",
            runtime=runtime_label,
            integration="user_prompt_context_modification",
            result=result,
            configuration=configuration,
            hook=hook,
            trust=trust,
            mcp="N/A",
            context_path=(
                "Cline UserPromptSubmit → overhaust_cline_user_prompt_hook.py → "
                "invoke_context_request → contextModification"
            ),
            message=message,
            actions=actions,
            warnings=warnings,
            environment=env,
            capabilities=caps,
            extras={
                "project_hook": str(project_hook),
                "global_hook": str(global_hook),
                "hook_executable": executable,
                "live_consumption": "not_tested",
                "delivery_caveat": "cline_issue_13554",
            },
        )
