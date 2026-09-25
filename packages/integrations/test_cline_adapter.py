"""Focused tests for the Cline B/C stress-test adapter."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import List

import pytest

from packages.integrations.adapters.cline_host import ClineAdapter
from packages.integrations.adapters.registry import (
    clear_registry,
    discover_environments,
    freeze_registry,
    register_adapter,
    select_adapters,
    verify_all,
)
from packages.integrations.host import HostEnvironment, IntegrationResult
from packages.integrations.install import install_cline_hook, uninstall_cline


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def cline_templates(tmp_path):
    repo = tmp_path / "repo"
    (repo / "integrations" / "templates" / "cline" / "hooks").mkdir(parents=True)
    (repo / "scripts" / "integrations").mkdir(parents=True)
    (repo / "integrations" / "templates" / "cline" / "hooks" / "UserPromptSubmit").write_text(
        "#!/usr/bin/env bash\nexec {{PYTHON}} \"{{CLINE_HOOK_SCRIPT}}\"\n",
        encoding="utf-8",
    )
    # Minimal stub script path referenced by installer
    stub = repo / "scripts" / "integrations" / "overhaust_cline_user_prompt_hook.py"
    stub.write_text("#!/usr/bin/env python3\nprint('{}')\n", encoding="utf-8")
    return repo


def test_cline_capabilities():
    caps = ClineAdapter().capabilities()
    assert caps.prompt_hooks is True
    assert caps.context_injection is True
    assert caps.hook_trust_required is True
    assert caps.mcp is True


def test_cline_not_detected_without_markers(monkeypatch, tmp_path):
    home = tmp_path / "empty-home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    import packages.integrations.adapters.cline_host as mod

    monkeypatch.setattr(mod, "_extension_dirs", lambda: [tmp_path / "no-ext"])
    monkeypatch.setattr(mod, "_which_cline", lambda: None)
    assert ClineAdapter().detect() == []
    status = ClineAdapter().verify()
    assert status.result == IntegrationResult.NOT_DETECTED


def test_cline_detects_vscode_extension_version(monkeypatch, tmp_path):
    home = tmp_path / "home"
    ext = home / ".vscode" / "extensions" / "saoudrizwan.claude-dev-3.36.0"
    ext.mkdir(parents=True)
    (ext / "package.json").write_text(
        '{"name":"claude-dev","version":"3.36.0"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    import packages.integrations.adapters.cline_host as mod

    monkeypatch.setattr(mod, "_extension_dirs", lambda: [home / ".vscode" / "extensions"])
    monkeypatch.setattr(mod, "_which_cline", lambda: None)

    envs = ClineAdapter().detect()
    assert len(envs) == 1
    assert envs[0].runtime == "vscode_extension"
    assert envs[0].version == "3.36.0"
    assert envs[0].integration == "user_prompt_context_modification"


def test_cline_detects_cli_runtime(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    cli = tmp_path / "cline"
    cli.write_text("#!/bin/sh\necho cline 1.0.0\n", encoding="utf-8")
    cli.chmod(0o755)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    import packages.integrations.adapters.cline_host as mod

    monkeypatch.setattr(mod, "_extension_dirs", lambda: [])
    monkeypatch.setattr(mod, "_which_cline", lambda: cli)
    monkeypatch.setattr(mod, "_cline_cli_version", lambda _b: "1.0.0")

    envs = ClineAdapter().detect()
    assert any(e.runtime == "cli" and e.version == "1.0.0" for e in envs)


def test_cline_selection_when_detected(monkeypatch, tmp_path):
    home = tmp_path / "home"
    (home / "Documents" / "Cline").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    import packages.integrations.adapters.cline_host as mod

    monkeypatch.setattr(mod, "_extension_dirs", lambda: [])
    monkeypatch.setattr(mod, "_which_cline", lambda: None)

    register_adapter(ClineAdapter())
    freeze_registry()
    selected = select_adapters(product="cline", prefer_detected=True)
    assert len(selected) == 1
    assert selected[0].id == "cline"


def test_cline_install_and_verify_action_required(monkeypatch, cline_templates):
    import packages.integrations.adapters.cline_host as mod
    from packages.integrations import install as install_mod

    monkeypatch.setattr(install_mod, "repo_root", lambda: cline_templates)
    monkeypatch.setattr(mod, "repo_root", lambda: cline_templates)
    monkeypatch.setattr(
        ClineAdapter,
        "detect",
        lambda self: [
            HostEnvironment(
                product="cline",
                runtime="vscode_extension",
                version="3.36.0",
                integration="user_prompt_context_modification",
            )
        ],
    )

    written = ClineAdapter().install(root=cline_templates)
    assert len(written) == 1
    hook = Path(written[0])
    assert hook.exists()
    assert hook.stat().st_mode & stat.S_IXUSR
    assert "overhaust_cline_user_prompt_hook" in hook.read_text(encoding="utf-8")

    status = ClineAdapter().verify()
    # Trust / Enable Hooks cannot be proven from disk → ACTION_REQUIRED
    assert status.result == IntegrationResult.ACTION_REQUIRED
    assert status.hook == "FOUND"
    assert status.configuration == "FOUND"
    assert status.trust == "UNKNOWN"
    assert status.extras.get("live_consumption") == "not_tested"
    assert any("Enable Hooks" in a for a in status.actions)


def test_cline_verify_missing_hook_action_required(monkeypatch, cline_templates):
    import packages.integrations.adapters.cline_host as mod

    monkeypatch.setattr(mod, "repo_root", lambda: cline_templates)
    monkeypatch.setattr(
        ClineAdapter,
        "detect",
        lambda self: [
            HostEnvironment(
                product="cline",
                runtime="cli",
                integration="user_prompt_context_modification",
            )
        ],
    )
    status = ClineAdapter().verify()
    assert status.result == IntegrationResult.ACTION_REQUIRED
    assert status.hook == "MISSING"


def test_cline_uninstall(cline_templates):
    path = install_cline_hook(root=cline_templates)
    assert Path(path).exists()
    removed = uninstall_cline(root=cline_templates)
    assert removed == [path]
    assert not Path(path).exists()


def test_cline_detector_fail_open():
    class Boom(ClineAdapter):
        def detect(self) -> List[HostEnvironment]:
            raise RuntimeError("boom")

    register_adapter(Boom())
    freeze_registry()
    assert discover_environments(["cline"]) == []


def test_unsupported_when_unregistered():
    freeze_registry()
    statuses = verify_all(["cline"])
    assert statuses[0].result == IntegrationResult.UNSUPPORTED


def test_cline_hook_script_emits_context_modification(tmp_path):
    """Unit-level: Cline stdout schema, not live Cline UI."""
    from packages.memory.memory_store import MemoryStore
    from services.ingestion.index_store import ProjectIndexStore

    repo = tmp_path / "proj"
    repo.mkdir()
    (repo / "demo.py").write_text("class ClineProbeToken:\n    x = 1\n", encoding="utf-8")
    db = tmp_path / "db.sqlite"
    store = MemoryStore(str(db))
    store.add_project("cline-probe", "ClineProbe", "", str(repo))
    ProjectIndexStore(store).sync_project("cline-probe", str(repo))

    hook = Path(__file__).resolve().parents[2] / "scripts" / "integrations" / "overhaust_cline_user_prompt_hook.py"
    env = os.environ.copy()
    env["OVERHAUST_DB_PATH"] = str(db)
    proc = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps({
            "hookName": "UserPromptSubmit",
            "clineVersion": "3.36.0",
            "workspaceRoots": [str(repo)],
            "userPromptSubmit": {"prompt": "Where is ClineProbeToken?", "attachments": []},
        }),
        text=True,
        capture_output=True,
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out.get("cancel") is False
    assert "contextModification" in out
    assert "additionalContext" not in out
    assert "hookSpecificOutput" not in out
    ctx = out.get("contextModification") or ""
    assert "<!-- overhaust-context -->" in ctx or ctx == ""


def test_cline_hook_fail_open_unknown_project():
    hook = Path(__file__).resolve().parents[2] / "scripts" / "integrations" / "overhaust_cline_user_prompt_hook.py"
    proc = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps({
            "hookName": "UserPromptSubmit",
            "workspaceRoots": ["/no/such/overhaust/project"],
            "userPromptSubmit": {"prompt": "hello", "attachments": []},
        }),
        text=True,
        capture_output=True,
        cwd=str(Path(__file__).resolve().parents[2]),
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["cancel"] is False
    assert out["contextModification"] == ""
