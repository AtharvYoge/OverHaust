"""Tests for host/runtime integration adapters."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pytest

from packages.integrations.adapters.base import IntegrationAdapter
from packages.integrations.adapters.claude import ClaudeAdapter
from packages.integrations.adapters.codex import CodexAdapter
from packages.integrations.adapters.cursor import CursorAdapter
from packages.integrations.adapters.registry import (
    clear_registry,
    discover_environments,
    ensure_default_adapters,
    freeze_registry,
    get_adapter,
    list_adapters,
    register_adapter,
    select_adapters,
    unregister_adapter,
    verify_all,
)
from packages.integrations.doctor import run_doctor
from packages.integrations.host import (
    HostCapabilities,
    HostEnvironment,
    IntegrationResult,
    IntegrationStatus,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_registry()
    yield
    clear_registry()


class _StubAdapter:
    def __init__(self, adapter_id: str, product: str, runtimes: List[str]):
        self.id = adapter_id
        self.product = product
        self._runtimes = runtimes

    def detect(self) -> List[HostEnvironment]:
        return [
            HostEnvironment(
                product=self.product,
                runtime=rt,
                integration="stub",
            )
            for rt in self._runtimes
        ]

    def capabilities(self, environment: Optional[HostEnvironment] = None) -> HostCapabilities:
        return HostCapabilities(prompt_hooks=True)

    def install(self, *, root=None, python: str = "python3", dry_run: bool = False) -> List[str]:
        return [f"/tmp/{self.id}"]

    def verify(self, environment: Optional[HostEnvironment] = None) -> IntegrationStatus:
        envs = self.detect()
        env = environment or envs[0]
        return IntegrationStatus(
            adapter_id=self.id,
            product=self.product,
            runtime=env.runtime,
            integration="stub",
            result=IntegrationResult.READY,
            message="ok",
            environment=env,
            capabilities=self.capabilities(env),
        )

    def uninstall(self, *, dry_run: bool = False) -> List[str]:
        return []


def test_adapter_registration_and_lookup():
    register_adapter(_StubAdapter("alpha", "alpha", ["desktop"]))
    freeze_registry()
    assert get_adapter("alpha") is not None
    assert get_adapter("alpha").product == "alpha"
    assert len(list_adapters()) == 1
    unregister_adapter("alpha")
    assert get_adapter("alpha") is None


def test_default_adapters_registered():
    ensure_default_adapters()
    ids = {a.id for a in list_adapters()}
    assert ids == {"cursor", "codex", "claude", "continue", "cline"}
    assert isinstance(get_adapter("cursor"), CursorAdapter)
    assert isinstance(get_adapter("codex"), CodexAdapter)
    assert isinstance(get_adapter("claude"), ClaudeAdapter)
    from packages.integrations.adapters.cline_host import ClineAdapter
    from packages.integrations.adapters.continue_host import ContinueAdapter

    assert isinstance(get_adapter("continue"), ContinueAdapter)
    assert isinstance(get_adapter("cline"), ClineAdapter)


def test_capability_reporting_matches_known_integrations():
    cursor = CursorAdapter().capabilities()
    assert cursor.mcp is True
    assert cursor.context_injection is False
    assert cursor.always_apply_rule is True

    codex = CodexAdapter().capabilities(
        HostEnvironment(product="codex", runtime="desktop", integration="user_prompt_hook")
    )
    assert codex.prompt_hooks is True
    assert codex.context_injection is True
    assert codex.hook_trust_required is True

    claude = ClaudeAdapter().capabilities()
    assert claude.prompt_hooks is True
    assert claude.hook_trust_required is False


def test_adapter_selection_by_product_and_runtime():
    register_adapter(_StubAdapter("codex", "codex", ["desktop", "cli"]))
    register_adapter(_StubAdapter("cursor", "cursor", ["desktop"]))
    register_adapter(_StubAdapter("ghost", "ghost", []))  # never detected
    freeze_registry()

    selected = select_adapters(prefer_detected=True)
    ids = {a.id for a in selected}
    assert "codex" in ids
    assert "cursor" in ids
    assert "ghost" not in ids

    desktop_only = select_adapters(product="codex", runtime="desktop", prefer_detected=True)
    assert len(desktop_only) == 1
    assert desktop_only[0].id == "codex"

    missing = select_adapters(product="windsurf", prefer_detected=True)
    assert missing == []


def test_codex_cli_vs_desktop_distinction(monkeypatch, tmp_path):
    desktop = tmp_path / "ChatGPT.app" / "Contents" / "Resources" / "codex"
    desktop.parent.mkdir(parents=True)
    desktop.write_text("#!/bin/sh\necho codex-cli 0.154.0-alpha.6.2\n", encoding="utf-8")
    desktop.chmod(0o755)

    cli_bin = tmp_path / "releases" / "0.146.0-aarch64-apple-darwin" / "bin" / "codex"
    cli_bin.parent.mkdir(parents=True)
    cli_bin.write_text("#!/bin/sh\necho codex-cli 0.146.0\n", encoding="utf-8")
    cli_bin.chmod(0o755)

    home = tmp_path / "home"
    home.mkdir()
    (home / ".codex" / "packages" / "standalone" / "releases" / "0.146.0-aarch64-apple-darwin" / "bin").mkdir(
        parents=True
    )
    packaged = (
        home / ".codex" / "packages" / "standalone" / "releases"
        / "0.146.0-aarch64-apple-darwin" / "bin" / "codex"
    )
    packaged.write_text("#!/bin/sh\necho codex-cli 0.146.0\n", encoding="utf-8")
    packaged.chmod(0o755)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_CLI_PATH", str(desktop))
    # Point Path.home at our fake home
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    # Patch module-level desktop constant used as fallback
    import packages.integrations.adapters.codex as codex_mod

    monkeypatch.setattr(codex_mod, "_DESKTOP_BIN", desktop)

    envs = CodexAdapter().detect()
    runtimes = {e.runtime for e in envs}
    assert "desktop" in runtimes
    assert "cli" in runtimes
    desktop_env = next(e for e in envs if e.runtime == "desktop")
    assert "0.154" in desktop_env.version or desktop_env.version == ""
    cli_env = next(e for e in envs if e.runtime == "cli")
    assert cli_env.binary_path


def test_claude_and_cursor_selection_when_detected(monkeypatch, tmp_path):
    home = tmp_path / "home"
    (home / ".cursor").mkdir(parents=True)
    (home / ".cursor" / "mcp.json").write_text("{}", encoding="utf-8")
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    register_adapter(CursorAdapter())
    register_adapter(ClaudeAdapter())
    freeze_registry()
    selected = select_adapters(prefer_detected=True)
    ids = {a.id for a in selected}
    assert "cursor" in ids
    assert "claude" in ids


def test_unsupported_host_status_does_not_crash():
    statuses = verify_all(["does-not-exist"])
    assert len(statuses) == 1
    assert statuses[0].result == IntegrationResult.UNSUPPORTED
    assert "No adapter" in statuses[0].message


def test_detector_failure_is_fail_open():
    class Boom:
        id = "boom"
        product = "boom"

        def detect(self):
            raise RuntimeError("boom")

        def capabilities(self, environment=None):
            return HostCapabilities()

        def install(self, *, root=None, python="python3", dry_run=False):
            return []

        def verify(self, environment=None):
            raise RuntimeError("verify boom")

        def uninstall(self, *, dry_run=False):
            return []

    register_adapter(Boom())
    freeze_registry()
    assert discover_environments(["boom"]) == []
    statuses = verify_all(["boom"])
    assert statuses[0].result == IntegrationResult.ACTION_REQUIRED


def test_codex_verify_reports_trust_action(monkeypatch, tmp_path):
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "hooks.json").write_text(
        '{"hooks":{"UserPromptSubmit":[{"hooks":[{"type":"command","command":"python3 \\"/x/overhaust_user_prompt_hook.py\\""}]}]}}',
        encoding="utf-8",
    )
    (home / ".codex" / "config.toml").write_text("# no hooks.state\n", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    # Pretend host exists
    import packages.integrations.adapters.codex as codex_mod

    monkeypatch.setattr(
        CodexAdapter,
        "detect",
        lambda self: [
            HostEnvironment(
                product="codex",
                runtime="desktop",
                version="0.154.0-alpha.6.2",
                integration="user_prompt_hook",
            )
        ],
    )
    # Hook script path may not exist in tmp — still ACTION_REQUIRED for trust or script
    status = CodexAdapter().verify()
    assert status.result == IntegrationResult.ACTION_REQUIRED
    assert status.trust in {"NOT_TRUSTED", "N/A"} or status.hook == "FOUND"
    assert status.integration == "user_prompt_hook"
    assert any("Trust" in a or "trust" in a.lower() for a in status.actions) or status.hook == "FOUND"


def test_protocol_runtime_check():
    adapter = CursorAdapter()
    assert isinstance(adapter, IntegrationAdapter)


def test_doctor_composes_without_crash():
    ensure_default_adapters()
    report = run_doctor()
    assert report.result in {r.value for r in IntegrationResult}
    assert isinstance(report.integrations, list)
