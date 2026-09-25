"""Tests for the Integration Manager (onboarding layer above the registry)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import List, Optional

import pytest

from packages.integrations import manager as manager_mod
from packages.integrations.adapters.registry import (
    clear_registry,
    freeze_registry,
    list_adapters,
    register_adapter,
)
from packages.integrations.doctor import run_doctor
from packages.integrations.host import (
    HostCapabilities,
    HostEnvironment,
    IntegrationResult,
    IntegrationState,
    IntegrationStatus,
)
from packages.integrations.manager import (
    IntegrationManager,
    derive_state,
    format_connect,
    format_integrations,
    format_status,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_registry()
    yield
    clear_registry()


class _Probe:
    def __init__(self, emitted: bool, ok: bool = True, error: str = ""):
        self.emitted = emitted
        self.ok = ok
        self.error = error


class FakeAdapter:
    """
    Configurable adapter. Simulates per-host config in an in-memory dict so
    idempotency / ownership can be asserted without touching disk.
    """

    def __init__(
        self,
        adapter_id: str,
        *,
        detected: bool = True,
        result: IntegrationResult = IntegrationResult.ACTION_REQUIRED,
        trust: str = "N/A",
        configured_result: IntegrationResult = IntegrationResult.READY,
        configured_trust: str = "N/A",
        probe: Optional[_Probe] = None,
        detect_error: Optional[Exception] = None,
        install_error: Optional[Exception] = None,
        uninstall_error: Optional[Exception] = None,
        version: str = "1.0",
        runtime: str = "cli",
    ):
        self.id = adapter_id
        self.product = adapter_id
        self._detected = detected
        self._result = result
        self._trust = trust
        self._configured_result = configured_result
        self._configured_trust = configured_trust
        self._probe = probe
        self._detect_error = detect_error
        self._install_error = install_error
        self._uninstall_error = uninstall_error
        self._version = version
        self._runtime = runtime
        # simulated host config file: unrelated user keys + optional overhaust key
        self.config = {"user_setting": "keep-me"}
        self.install_calls = 0
        self.uninstall_calls = 0

    # -- protocol --------------------------------------------------------- #

    def detect(self) -> List[HostEnvironment]:
        if self._detect_error:
            raise self._detect_error
        if not self._detected:
            return []
        return [HostEnvironment(product=self.product, runtime=self._runtime,
                                version=self._version, integration="fake")]

    def capabilities(self, environment=None) -> HostCapabilities:
        return HostCapabilities(prompt_hooks=True, context_injection=True)

    def install(self, *, root=None, python="python3", dry_run=False) -> List[str]:
        if self._install_error:
            raise self._install_error
        self.install_calls += 1
        # idempotent merge: never duplicates, never clobbers unrelated keys
        self.config["overhaust"] = {"hook": f"/x/{self.id}"}
        return [f"/tmp/{self.id}.json"]

    def uninstall(self, *, dry_run=False) -> List[str]:
        if self._uninstall_error:
            raise self._uninstall_error
        self.uninstall_calls += 1
        if "overhaust" in self.config:
            del self.config["overhaust"]
            return [f"/tmp/{self.id}.json"]
        return []

    def verify(self, environment=None) -> IntegrationStatus:
        configured = "overhaust" in self.config
        envs = self.detect()
        env = envs[0] if envs else None
        if configured:
            result, trust = self._configured_result, self._configured_trust
        else:
            result, trust = self._result, self._trust
        if not envs and result != IntegrationResult.UNSUPPORTED:
            result = IntegrationResult.NOT_DETECTED
        return IntegrationStatus(
            adapter_id=self.id,
            product=self.product,
            runtime=env.runtime if env else "unknown",
            integration="fake",
            result=result,
            configuration="FOUND" if configured else "MISSING",
            trust=trust,
            message="fake",
            actions=["do the thing"] if result == IntegrationResult.ACTION_REQUIRED else [],
            environment=env,
            capabilities=self.capabilities(env),
        )

    def probe_emission(self):
        if self._probe is None:
            raise RuntimeError("no probe configured")
        return self._probe


def _mgr(*adapters, **kw) -> IntegrationManager:
    return IntegrationManager(adapters=list(adapters), **kw)


# --------------------------------------------------------------------------- #
# derive_state
# --------------------------------------------------------------------------- #


def _status(result, *, configuration="MISSING", trust="N/A"):
    return IntegrationStatus(adapter_id="x", product="x", runtime="cli", integration="f",
                             result=result, configuration=configuration, trust=trust)


def test_derive_state_covers_all_ten_states():
    assert derive_state(None, False) == IntegrationState.NOT_DETECTED
    assert derive_state(None, True) == IntegrationState.DETECTED
    assert derive_state(_status(IntegrationResult.NOT_DETECTED, configuration="FOUND"), True) == IntegrationState.CONFIGURED
    assert derive_state(_status(IntegrationResult.ACTION_REQUIRED, configuration="FOUND", trust="NOT_TRUSTED"), True) == IntegrationState.TRUST_REQUIRED
    assert derive_state(_status(IntegrationResult.ACTION_REQUIRED), True) == IntegrationState.ACTION_REQUIRED
    assert derive_state(_status(IntegrationResult.READY, configuration="FOUND"), True) == IntegrationState.INTEGRATION_READY
    assert derive_state(_status(IntegrationResult.READY, configuration="FOUND"), True, emission_verified=True) == IntegrationState.CONTEXT_EMITTING
    assert derive_state(_status(IntegrationResult.READY, configuration="FOUND"), True, model_consumption_verified=True) == IntegrationState.CONTEXT_VERIFIED
    assert derive_state(_status(IntegrationResult.UNSUPPORTED), True) == IntegrationState.NOT_SUPPORTED
    assert derive_state(_status(IntegrationResult.NOT_DETECTED), False) == IntegrationState.NOT_DETECTED
    seen = {
        IntegrationState.NOT_DETECTED, IntegrationState.DETECTED, IntegrationState.CONFIGURED,
        IntegrationState.TRUST_REQUIRED, IntegrationState.ACTION_REQUIRED,
        IntegrationState.INTEGRATION_READY, IntegrationState.CONTEXT_EMITTING,
        IntegrationState.CONTEXT_VERIFIED, IntegrationState.NOT_SUPPORTED,
    }
    assert seen | {IntegrationState.UNKNOWN} == set(IntegrationState)


def test_configuration_success_does_not_collapse_into_ready():
    ready = derive_state(_status(IntegrationResult.READY, configuration="FOUND"), True)
    assert ready == IntegrationState.INTEGRATION_READY
    assert ready not in {IntegrationState.CONTEXT_EMITTING, IntegrationState.CONTEXT_VERIFIED}


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #


def test_discover_multiple_detected_hosts():
    mgr = _mgr(FakeAdapter("a"), FakeAdapter("b", runtime="desktop", version="2.0"), FakeAdapter("c", detected=False))
    records = {r.adapter_id: r for r in mgr.discover()}
    assert set(records) == {"a", "b", "c"}
    assert records["a"].detected and records["b"].detected and not records["c"].detected
    assert records["b"].runtime == "desktop" and records["b"].version == "2.0"
    assert records["c"].state == IntegrationState.NOT_DETECTED
    assert records["a"].state == IntegrationState.ACTION_REQUIRED
    for r in records.values():
        assert r.emission_verifiable is True  # FakeAdapter has probe_emission
        assert r.model_consumption_verified is False


def test_discover_no_detected_hosts():
    mgr = _mgr(FakeAdapter("a", detected=False), FakeAdapter("b", detected=False))
    records = mgr.discover()
    assert all(not r.detected for r in records)
    assert {r.state for r in records} == {IntegrationState.NOT_DETECTED}
    text = format_integrations(records)
    assert "✗ A" in text and "✗ B" in text


def test_discover_no_adapters_registered():
    assert IntegrationManager(adapters=[]).discover() == []


def test_trust_required_state_is_surfaced():
    a = FakeAdapter("codexish", configured_result=IntegrationResult.ACTION_REQUIRED, configured_trust="NOT_TRUSTED")
    mgr = _mgr(a)
    mgr.connect(["codexish"])
    rec = mgr.discover()[0]
    assert rec.state == IntegrationState.TRUST_REQUIRED
    assert rec.trust == "NOT_TRUSTED"
    assert rec.configuration == "FOUND"


def test_context_emitting_state_requires_probe_flag_and_ready():
    a = FakeAdapter("h", probe=_Probe(emitted=True))
    a.install()
    assert _mgr(a).discover()[0].state == IntegrationState.INTEGRATION_READY  # probe off
    rec = _mgr(a, probe_emission=True).discover()[0]
    assert rec.state == IntegrationState.CONTEXT_EMITTING
    assert rec.emission_verified is True


def test_context_emitting_not_claimed_when_probe_fails():
    a = FakeAdapter("h", probe=_Probe(emitted=False, ok=False, error="boom"))
    a.install()
    rec = _mgr(a, probe_emission=True).discover()[0]
    assert rec.state == IntegrationState.INTEGRATION_READY
    assert rec.emission_verified is False
    assert any("boom" in w for w in rec.warnings)


def test_context_verified_state_only_from_explicit_source():
    a = FakeAdapter("h")
    a.install()
    rec = _mgr(a, consumption_verified=lambda aid: aid == "h").discover()[0]
    assert rec.state == IntegrationState.CONTEXT_VERIFIED
    assert rec.model_consumption_verified is True
    # default: never invented
    assert _mgr(a).discover()[0].model_consumption_verified is False


def test_unsupported_host_state():
    a = FakeAdapter("u", result=IntegrationResult.UNSUPPORTED)
    rec = _mgr(a).discover()[0]
    assert rec.state == IntegrationState.NOT_SUPPORTED


def test_adapter_detection_failure_is_unknown_not_crash():
    a = FakeAdapter("broken", detect_error=RuntimeError("bad detector"))
    b = FakeAdapter("fine")
    records = {r.adapter_id: r for r in _mgr(a, b).discover()}
    assert records["broken"].state == IntegrationState.UNKNOWN
    assert "bad detector" in records["broken"].error
    assert records["fine"].state == IntegrationState.ACTION_REQUIRED


# --------------------------------------------------------------------------- #
# connect
# --------------------------------------------------------------------------- #


def test_connect_all_detected_only():
    a, b, c = FakeAdapter("a"), FakeAdapter("b"), FakeAdapter("c", detected=False)
    outcomes = {o.adapter_id: o for o in _mgr(a, b, c).connect()}
    assert a.install_calls == 1 and b.install_calls == 1 and c.install_calls == 0
    assert outcomes["a"].state == IntegrationState.INTEGRATION_READY
    assert outcomes["c"].skipped and outcomes["c"].state == IntegrationState.NOT_DETECTED
    assert outcomes["a"].paths == ["/tmp/a.json"]


def test_connect_selected_host_only():
    a, b = FakeAdapter("a"), FakeAdapter("b")
    outcomes = _mgr(a, b).connect(["b"])
    assert [o.adapter_id for o in outcomes] == ["b"]
    assert a.install_calls == 0 and b.install_calls == 1


def test_connect_unknown_adapter_id_is_ignored():
    a = FakeAdapter("a")
    assert _mgr(a).connect(["nope"]) == []
    assert a.install_calls == 0


def test_repeated_connect_is_idempotent_and_preserves_user_config():
    a = FakeAdapter("a")
    mgr = _mgr(a)
    mgr.connect(); mgr.connect(); mgr.connect()
    assert a.install_calls == 3
    assert a.config == {"user_setting": "keep-me", "overhaust": {"hook": "/x/a"}}
    assert mgr.discover()[0].state == IntegrationState.INTEGRATION_READY


def test_connect_one_adapter_failure_does_not_block_others():
    a = FakeAdapter("a", install_error=OSError("disk full"))
    b = FakeAdapter("b")
    outcomes = {o.adapter_id: o for o in _mgr(a, b).connect()}
    assert "disk full" in outcomes["a"].error
    assert outcomes["a"].state == IntegrationState.UNKNOWN
    assert outcomes["b"].state == IntegrationState.INTEGRATION_READY
    assert b.install_calls == 1
    text = format_connect(list(outcomes.values()))
    assert "disk full" in text


def test_connect_dry_run_passes_through():
    class Spy(FakeAdapter):
        def install(self, *, root=None, python="python3", dry_run=False):
            self.seen_dry_run = dry_run
            return super().install(root=root, python=python, dry_run=dry_run)
    s = Spy("s")
    _mgr(s).connect(dry_run=True)
    assert s.seen_dry_run is True


# --------------------------------------------------------------------------- #
# disconnect
# --------------------------------------------------------------------------- #


def test_disconnect_only_removes_owned_configuration():
    a = FakeAdapter("a")
    mgr = _mgr(a)
    mgr.connect()
    assert "overhaust" in a.config
    outcomes = mgr.disconnect()
    assert outcomes[0].removed == ["/tmp/a.json"]
    assert a.config == {"user_setting": "keep-me"}
    # second disconnect: nothing owned left, no error
    again = mgr.disconnect()
    assert again[0].removed == [] and again[0].error == "" and again[0].note


def test_disconnect_failure_isolated():
    a = FakeAdapter("a", uninstall_error=PermissionError("ro"))
    b = FakeAdapter("b")
    b.install()
    outcomes = {o.adapter_id: o for o in _mgr(a, b).disconnect()}
    assert "ro" in outcomes["a"].error
    assert outcomes["b"].removed == ["/tmp/b.json"]


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #


class _EmptyStore:
    db_path = "/tmp/fake.db"

    def list_projects(self):
        return []


def test_status_reports_core_projects_and_hosts():
    a = FakeAdapter("a")
    a.install()
    report = _mgr(a, FakeAdapter("b", detected=False)).status(memory_store=_EmptyStore())
    assert report.core["project_count"] == 0
    assert report.projects == []
    assert {h["adapter_id"] for h in report.hosts} == {"a", "b"}
    assert "1 connected host(s), 1 detected, 0 project(s)" == report.summary
    text = format_status(report)
    assert "model_consumption=unverified" in text
    assert "tokens" not in text.lower()  # no invented metrics


def test_status_core_failure_does_not_crash():
    class Boom:
        def list_projects(self):
            raise RuntimeError("db locked")
    report = _mgr(FakeAdapter("a")).status(memory_store=Boom())
    assert report.core["ok"] is False and report.core["error"]
    assert report.projects == []
    assert len(report.hosts) == 1


# --------------------------------------------------------------------------- #
# doctor composition / registry as source of truth
# --------------------------------------------------------------------------- #


def test_doctor_composes_via_manager_and_detects_once():
    a = FakeAdapter("a")
    calls = {"n": 0}
    orig = a.detect

    def counting_detect():
        calls["n"] += 1
        return orig()

    a.detect = counting_detect
    report = run_doctor(manager=_mgr(a))
    # manager._inspect calls detect() once; verify() inside FakeAdapter calls it again.
    # The manager itself must not add a third discovery pass (old doctor did).
    assert calls["n"] == 2
    assert report.hosts[0]["state"] == IntegrationState.ACTION_REQUIRED.value
    assert report.result == IntegrationResult.ACTION_REQUIRED.value


def test_doctor_rollup_trust_required_is_action():
    a = FakeAdapter("a", configured_result=IntegrationResult.ACTION_REQUIRED, configured_trust="NOT_TRUSTED")
    a.install()
    assert run_doctor(manager=_mgr(a)).result == IntegrationResult.ACTION_REQUIRED.value


def test_registry_is_single_source_of_truth_by_default():
    register_adapter(FakeAdapter("only"))
    freeze_registry()
    mgr = IntegrationManager()  # no injection → registry
    assert [a.id for a in mgr.adapters()] == ["only"]
    assert [a.id for a in list_adapters()] == ["only"]
    assert [r.adapter_id for r in mgr.discover()] == ["only"]


def test_manager_has_no_product_if_elif_chain():
    """Manager may not branch on product names for behaviour (display names excepted)."""
    src = inspect.getsource(manager_mod)
    tree = ast.parse(src)
    products = {"cursor", "codex", "claude", "continue", "cline"}
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in {"display_name"}:
            continue
        if isinstance(node, ast.Compare):
            for comp in node.comparators:
                if isinstance(comp, ast.Constant) and comp.value in products:
                    offenders.append(ast.get_source_segment(src, node))
    # display_name is presentation-only; strip its span from offenders
    display_src = inspect.getsource(manager_mod.display_name)
    offenders = [o for o in offenders if o not in display_src]
    assert offenders == [], offenders
    assert "hooks.json" not in src and "settings.json" not in src and "mcp.json" not in src


def test_real_default_adapters_discoverable_without_crash():
    """Real adapters + real filesystem: must produce a record per adapter, never raise."""
    mgr = IntegrationManager()
    records = mgr.discover()
    assert {r.adapter_id for r in records} == {"cursor", "codex", "claude", "continue", "cline"}
    for r in records:
        assert isinstance(r.state, IntegrationState)
        assert r.model_consumption_verified is False
