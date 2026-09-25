"""Focused tests for the Continue.dev fourth-host adapter experiment."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pytest

from packages.integrations.adapters.continue_host import ContinueAdapter
from packages.integrations.adapters.registry import (
    clear_registry,
    freeze_registry,
    register_adapter,
    select_adapters,
    verify_all,
)
from packages.integrations.host import (
    HostEnvironment,
    IntegrationResult,
)
from packages.integrations.install import (
    install_continue_mcp,
    install_continue_rules,
    uninstall_continue,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def continue_templates(tmp_path):
    repo = tmp_path / "repo"
    (repo / "integrations" / "templates" / "continue" / "mcpServers").mkdir(parents=True)
    (repo / "integrations" / "templates" / "continue" / "rules").mkdir(parents=True)
    (repo / "integrations" / "templates" / "continue" / "mcpServers" / "overhaust.yaml").write_text(
        "name: OverHaust MCP\nversion: 0.0.1\nschema: v1\n"
        "mcpServers:\n  - name: overhaust\n    command: \"{{PYTHON}}\"\n"
        "    args: [\"-m\", \"services.mcp_server.server\"]\n"
        "    cwd: \"{{REPO_ROOT}}\"\n"
        "    env:\n      PYTHONPATH: \"{{REPO_ROOT}}\"\n"
        "      OVERHAUST_ROOT: \"{{REPO_ROOT}}\"\n",
        encoding="utf-8",
    )
    (repo / "integrations" / "templates" / "continue" / "rules" / "overhaust-context.md").write_text(
        "---\nname: OverHaust\nalwaysApply: true\n---\n"
        "call get_relevant_context\n",
        encoding="utf-8",
    )
    return repo


def test_continue_capabilities():
    caps = ContinueAdapter().capabilities()
    assert caps.mcp is True
    assert caps.always_apply_rule is True
    assert caps.prompt_hooks is False
    assert caps.context_injection is False
    assert caps.hook_trust_required is False


def test_continue_not_detected_without_markers(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "empty-home"))
    (tmp_path / "empty-home").mkdir()
    import packages.integrations.adapters.continue_host as mod

    monkeypatch.setattr(mod, "_extension_dirs", lambda: [tmp_path / "no-ext"])
    monkeypatch.setattr(mod, "_jetbrains_continue_present", lambda: False)
    monkeypatch.setattr(mod, "_which_cn", lambda: None)
    assert ContinueAdapter().detect() == []
    status = ContinueAdapter().verify()
    assert status.result == IntegrationResult.NOT_DETECTED


def test_continue_detects_vscode_extension_runtime(monkeypatch, tmp_path):
    home = tmp_path / "home"
    ext = home / ".vscode" / "extensions" / "continue.continue-1.2.3"
    ext.mkdir(parents=True)
    (ext / "package.json").write_text(
        '{"name":"continue","version":"1.2.3"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    import packages.integrations.adapters.continue_host as mod

    monkeypatch.setattr(mod, "_extension_dirs", lambda: [home / ".vscode" / "extensions"])
    monkeypatch.setattr(mod, "_jetbrains_continue_present", lambda: False)
    monkeypatch.setattr(mod, "_which_cn", lambda: None)

    envs = ContinueAdapter().detect()
    assert len(envs) == 1
    assert envs[0].product == "continue"
    assert envs[0].runtime == "vscode_extension"
    assert envs[0].version == "1.2.3"
    assert envs[0].integration == "mcp_always_apply_rule"


def test_continue_detects_cli_and_jetbrains(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    cn = tmp_path / "cn"
    cn.write_text("#!/bin/sh\necho continue-cli 0.9.0\n", encoding="utf-8")
    cn.chmod(0o755)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    import packages.integrations.adapters.continue_host as mod

    monkeypatch.setattr(mod, "_extension_dirs", lambda: [])
    monkeypatch.setattr(mod, "_jetbrains_continue_present", lambda: True)
    monkeypatch.setattr(mod, "_which_cn", lambda: cn)
    monkeypatch.setattr(mod, "_cn_version", lambda _b: "0.9.0")

    envs = ContinueAdapter().detect()
    runtimes = {e.runtime for e in envs}
    assert "jetbrains_plugin" in runtimes
    assert "cli" in runtimes


def test_continue_selection_when_detected(monkeypatch, tmp_path):
    home = tmp_path / "home"
    (home / ".continue").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    import packages.integrations.adapters.continue_host as mod

    monkeypatch.setattr(mod, "_extension_dirs", lambda: [])
    monkeypatch.setattr(mod, "_jetbrains_continue_present", lambda: False)
    monkeypatch.setattr(mod, "_which_cn", lambda: None)

    register_adapter(ContinueAdapter())
    freeze_registry()
    selected = select_adapters(product="continue", prefer_detected=True)
    assert len(selected) == 1
    assert selected[0].id == "continue"


def test_continue_install_and_verify_ready(monkeypatch, continue_templates):
    import packages.integrations.adapters.continue_host as mod
    from packages.integrations import install as install_mod

    monkeypatch.setattr(install_mod, "repo_root", lambda: continue_templates)
    monkeypatch.setattr(mod, "repo_root", lambda: continue_templates)
    monkeypatch.setattr(
        ContinueAdapter,
        "detect",
        lambda self: [
            HostEnvironment(
                product="continue",
                runtime="vscode_extension",
                version="1.0.0",
                integration="mcp_always_apply_rule",
            )
        ],
    )

    written = ContinueAdapter().install(root=continue_templates)
    assert len(written) == 2
    status = ContinueAdapter().verify()
    assert status.result == IntegrationResult.READY
    assert status.mcp == "CONFIGURED"
    assert status.capabilities and status.capabilities.mcp is True


def test_continue_verify_action_required_when_missing_files(monkeypatch, continue_templates):
    import packages.integrations.adapters.continue_host as mod

    monkeypatch.setattr(mod, "repo_root", lambda: continue_templates)
    monkeypatch.setattr(
        ContinueAdapter,
        "detect",
        lambda self: [
            HostEnvironment(
                product="continue",
                runtime="cli",
                integration="mcp_always_apply_rule",
            )
        ],
    )
    status = ContinueAdapter().verify()
    assert status.result == IntegrationResult.ACTION_REQUIRED
    assert status.mcp == "MISSING"


def test_continue_uninstall_removes_owned_files(continue_templates):
    install_continue_mcp(root=continue_templates)
    install_continue_rules(root=continue_templates)
    removed = uninstall_continue(root=continue_templates)
    assert len(removed) == 2
    assert not (continue_templates / ".continue" / "mcpServers" / "overhaust.yaml").exists()
    assert not (continue_templates / ".continue" / "rules" / "overhaust-context.md").exists()


def test_continue_detector_failure_fail_open():
    class Boom(ContinueAdapter):
        def detect(self) -> List[HostEnvironment]:
            raise RuntimeError("boom")

    register_adapter(Boom())
    freeze_registry()
    from packages.integrations.adapters.registry import discover_environments

    assert discover_environments(["continue"]) == []


def test_unsupported_continue_id_when_unregistered():
    # Registry empty + frozen → continue missing
    freeze_registry()
    statuses = verify_all(["continue"])
    assert statuses[0].result == IntegrationResult.UNSUPPORTED
