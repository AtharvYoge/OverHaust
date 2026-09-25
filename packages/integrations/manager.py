"""
Integration Manager — onboarding/UX layer above the adapter registry.

    CLI / future GUI
          ↓
    IntegrationManager        (this module: discover / connect / disconnect / status)
          ↓
    Adapter Registry          (packages.integrations.adapters.registry)
          ↓
    Host Adapter              (detect / capabilities / install / verify / uninstall)
          ↓
    Native host mechanism     (hooks, MCP, rules — adapter-owned)
          ↓
    invoke_context_request()  (unchanged context seam)

The manager never touches host configuration and never branches on product
names. Every host-specific behaviour is delegated to the adapter looked up in
the registry. One adapter failing is reported, not propagated.

Repository sources (local filesystem today; GitHub/GitLab later) are a
separate boundary from host adapters: a repository is a *project*, an AI
host is a *consumer*. See docs/INTEGRATION_MANAGER.md.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from packages.integrations.adapters.registry import (
    ensure_default_adapters,
    get_adapter,
    list_adapters,
)
from packages.integrations.host import (
    HostEnvironment,
    IntegrationResult,
    IntegrationState,
    IntegrationStatus,
)

# Labels emitted by existing adapters' verify(); the manager only reads them.
_TRUST_BLOCKING = {"NOT_TRUSTED", "PARTIAL"}
_CONFIGURED_LABELS = {"FOUND"}


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #


@dataclass
class HostRecord:
    """Everything the UI needs to know about one adapter, in one place."""

    adapter_id: str
    product: str
    detected: bool
    state: IntegrationState
    environments: List[Dict[str, Any]] = field(default_factory=list)
    runtime: str = ""
    version: str = ""
    integration: str = ""
    configuration: str = "UNKNOWN"
    trust: str = "N/A"
    emission_verifiable: bool = False
    emission_verified: Optional[bool] = None
    model_consumption_verified: bool = False
    message: str = ""
    actions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error: str = ""
    status: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data


@dataclass
class ConnectOutcome:
    adapter_id: str
    product: str
    paths: List[str] = field(default_factory=list)
    state: IntegrationState = IntegrationState.UNKNOWN
    error: str = ""
    skipped: bool = False
    record: Optional[HostRecord] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "product": self.product,
            "paths": list(self.paths),
            "state": self.state.value,
            "error": self.error,
            "skipped": self.skipped,
            "record": self.record.to_dict() if self.record else None,
        }


@dataclass
class DisconnectOutcome:
    adapter_id: str
    product: str
    removed: List[str] = field(default_factory=list)
    error: str = ""
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StatusReport:
    core: Dict[str, Any] = field(default_factory=dict)
    projects: List[Dict[str, Any]] = field(default_factory=list)
    hosts: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# State derivation (pure; no host IO)
# --------------------------------------------------------------------------- #


def derive_state(
    status: Optional[IntegrationStatus],
    detected: bool,
    *,
    emission_verified: Optional[bool] = None,
    model_consumption_verified: bool = False,
) -> IntegrationState:
    """
    Map an adapter's IntegrationStatus onto the user-facing lifecycle.

    Ordering matters: model consumption > emission > readiness > trust >
    action > configured > detected. Configuration success never collapses
    into READY on its own.
    """
    if status is None:
        return IntegrationState.DETECTED if detected else IntegrationState.NOT_DETECTED

    result = status.result
    trust = (status.trust or "N/A").upper()
    configuration = (status.configuration or "").upper()

    if result == IntegrationResult.UNSUPPORTED:
        return IntegrationState.NOT_SUPPORTED
    if result == IntegrationResult.NOT_DETECTED and not detected:
        return IntegrationState.NOT_DETECTED

    if model_consumption_verified:
        return IntegrationState.CONTEXT_VERIFIED

    if result == IntegrationResult.READY:
        if emission_verified is True:
            return IntegrationState.CONTEXT_EMITTING
        return IntegrationState.INTEGRATION_READY

    if result == IntegrationResult.ACTION_REQUIRED:
        if configuration in _CONFIGURED_LABELS and trust in _TRUST_BLOCKING:
            return IntegrationState.TRUST_REQUIRED
        return IntegrationState.ACTION_REQUIRED

    if configuration in _CONFIGURED_LABELS:
        return IntegrationState.CONFIGURED
    if detected:
        return IntegrationState.DETECTED
    return IntegrationState.UNKNOWN


def _prefer_environment(envs: Sequence[HostEnvironment]) -> Optional[HostEnvironment]:
    for env in envs:
        if env.version:
            return env
    return envs[0] if envs else None


def _adapter_can_probe(adapter: Any) -> bool:
    return callable(getattr(adapter, "probe_emission", None))


# --------------------------------------------------------------------------- #
# Manager
# --------------------------------------------------------------------------- #


class IntegrationManager:
    """
    Composes registry adapters into user-facing operations.

    `adapters` may be injected for tests; by default the registry is the
    single source of truth (defaults are loaded lazily by the registry).
    """

    def __init__(
        self,
        *,
        adapters: Optional[Iterable[Any]] = None,
        probe_emission: bool = False,
        consumption_verified: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self._injected = list(adapters) if adapters is not None else None
        self._probe = probe_emission
        # Optional hook for a future GUI/telemetry-free store of live model
        # verification. Defaults to "never verified" — we don't invent it.
        self._consumption_verified = consumption_verified or (lambda _aid: False)

    # -- registry access ---------------------------------------------------- #

    def adapters(self) -> List[Any]:
        if self._injected is not None:
            return list(self._injected)
        ensure_default_adapters()
        return list(list_adapters())

    def _adapter(self, adapter_id: str) -> Optional[Any]:
        if self._injected is not None:
            for adapter in self._injected:
                if getattr(adapter, "id", None) == adapter_id:
                    return adapter
            return None
        ensure_default_adapters()
        return get_adapter(adapter_id)

    # -- discovery ---------------------------------------------------------- #

    def discover(self, adapter_ids: Optional[Sequence[str]] = None) -> List[HostRecord]:
        wanted = set(adapter_ids) if adapter_ids else None
        records: List[HostRecord] = []
        for adapter in self.adapters():
            if wanted is not None and adapter.id not in wanted:
                continue
            records.append(self._inspect(adapter))
        return records

    def _inspect(self, adapter: Any) -> HostRecord:
        product = getattr(adapter, "product", adapter.id)
        error = ""
        envs: List[HostEnvironment] = []
        try:
            envs = list(adapter.detect() or [])
        except Exception as exc:  # one adapter must not sink the rest
            error = f"detect failed: {exc}"

        detected = bool(envs)
        status: Optional[IntegrationStatus] = None
        if not error:
            try:
                status = adapter.verify(_prefer_environment(envs))
            except Exception as exc:
                error = f"verify failed: {exc}"

        emission_verifiable = _adapter_can_probe(adapter)
        emission_verified: Optional[bool] = None
        warnings: List[str] = list(status.warnings) if status else []
        if (
            self._probe
            and emission_verifiable
            and status is not None
            and status.result == IntegrationResult.READY
        ):
            try:
                probe = adapter.probe_emission()
                emission_verified = bool(getattr(probe, "emitted", False))
                if not probe.ok and probe.error:
                    warnings.append(f"emission probe: {probe.error}")
            except Exception as exc:
                emission_verified = False
                warnings.append(f"emission probe failed: {exc}")

        consumption = bool(self._consumption_verified(adapter.id))

        if error:
            state = IntegrationState.UNKNOWN
        else:
            state = derive_state(
                status,
                detected,
                emission_verified=emission_verified,
                model_consumption_verified=consumption,
            )

        env = _prefer_environment(envs)
        return HostRecord(
            adapter_id=adapter.id,
            product=product,
            detected=detected,
            state=state,
            environments=[e.to_dict() for e in envs],
            runtime=(env.runtime if env else "") or (status.runtime if status else ""),
            version=(env.version if env else "") or "",
            integration=(env.integration if env else "") or (status.integration if status else ""),
            configuration=(status.configuration if status else "UNKNOWN"),
            trust=(status.trust if status else "N/A"),
            emission_verifiable=emission_verifiable,
            emission_verified=emission_verified,
            model_consumption_verified=consumption,
            message=(status.message if status else ""),
            actions=list(status.actions) if status else [],
            warnings=warnings,
            error=error,
            status=status.to_dict() if status else None,
        )

    # -- connect ------------------------------------------------------------ #

    def connect(
        self,
        adapter_ids: Optional[Sequence[str]] = None,
        *,
        root=None,
        python: str = "python3",
        dry_run: bool = False,
        only_detected: bool = True,
    ) -> List[ConnectOutcome]:
        """
        Install OverHaust into hosts via adapter.install().

        Idempotency and preservation of unrelated config are adapter
        responsibilities (install functions merge, not overwrite). The manager
        only decides *which* adapters run and reports the resulting state.
        """
        outcomes: List[ConnectOutcome] = []
        targets = self._resolve_targets(adapter_ids)
        for adapter in targets:
            product = getattr(adapter, "product", adapter.id)
            if only_detected and adapter_ids is None:
                try:
                    if not adapter.detect():
                        outcomes.append(
                            ConnectOutcome(
                                adapter_id=adapter.id,
                                product=product,
                                state=IntegrationState.NOT_DETECTED,
                                skipped=True,
                            )
                        )
                        continue
                except Exception as exc:
                    outcomes.append(
                        ConnectOutcome(
                            adapter_id=adapter.id,
                            product=product,
                            error=f"detect failed: {exc}",
                            state=IntegrationState.UNKNOWN,
                            skipped=True,
                        )
                    )
                    continue
            try:
                paths = list(adapter.install(root=root, python=python, dry_run=dry_run) or [])
            except Exception as exc:
                outcomes.append(
                    ConnectOutcome(
                        adapter_id=adapter.id,
                        product=product,
                        error=f"install failed: {exc}",
                        state=IntegrationState.UNKNOWN,
                    )
                )
                continue
            record = self._inspect(adapter)
            outcomes.append(
                ConnectOutcome(
                    adapter_id=adapter.id,
                    product=product,
                    paths=paths,
                    state=record.state,
                    record=record,
                )
            )
        return outcomes

    # -- disconnect --------------------------------------------------------- #

    def disconnect(
        self,
        adapter_ids: Optional[Sequence[str]] = None,
        *,
        dry_run: bool = False,
    ) -> List[DisconnectOutcome]:
        """Remove OverHaust-owned config via adapter.uninstall(); nothing else."""
        outcomes: List[DisconnectOutcome] = []
        for adapter in self._resolve_targets(adapter_ids):
            product = getattr(adapter, "product", adapter.id)
            try:
                removed = list(adapter.uninstall(dry_run=dry_run) or [])
            except Exception as exc:
                outcomes.append(
                    DisconnectOutcome(adapter_id=adapter.id, product=product, error=str(exc))
                )
                continue
            note = ""
            if not removed:
                note = "nothing to remove (adapter reported no OverHaust-owned config)"
            outcomes.append(
                DisconnectOutcome(adapter_id=adapter.id, product=product, removed=removed, note=note)
            )
        return outcomes

    # -- status ------------------------------------------------------------- #

    def status(
        self,
        adapter_ids: Optional[Sequence[str]] = None,
        *,
        memory_store=None,
        include_projects: bool = True,
    ) -> StatusReport:
        core = self._core_health(memory_store) if include_projects else {"ok": None}
        projects = core.pop("projects", []) if include_projects else []
        hosts = self.discover(adapter_ids)
        connected = [h for h in hosts if h.state in _CONNECTED_STATES]
        summary = (
            f"{len(connected)} connected host(s), "
            f"{sum(1 for h in hosts if h.detected)} detected, "
            f"{len(projects)} project(s)"
        )
        return StatusReport(
            core=core,
            projects=projects,
            hosts=[h.to_dict() for h in hosts],
            summary=summary,
        )

    @staticmethod
    def _core_health(memory_store=None) -> Dict[str, Any]:
        """Reuse ProjectIndexStore.index_health — no new metrics."""
        try:
            from packages.memory.memory_store import get_memory_store
            from services.ingestion.index_store import ProjectIndexStore

            store = memory_store or get_memory_store()
            index_store = ProjectIndexStore(store)
            reports: List[Dict[str, Any]] = []
            for project in store.list_projects():
                pid = project.get("id") or project.get("project_id")
                if not pid:
                    continue
                health = index_store.index_health(pid)
                health.setdefault("name", project.get("name", ""))
                reports.append(health)
            return {
                "ok": all(r.get("ok") for r in reports) if reports else False,
                "db_path": os.environ.get("OVERHAUST_DB_PATH") or getattr(store, "db_path", ""),
                "project_count": len(reports),
                "projects": reports,
            }
        except Exception as exc:  # status must never crash on core issues
            return {"ok": False, "error": str(exc), "project_count": 0, "projects": []}

    # -- helpers ------------------------------------------------------------ #

    def _resolve_targets(self, adapter_ids: Optional[Sequence[str]]) -> List[Any]:
        if not adapter_ids:
            return self.adapters()
        targets: List[Any] = []
        for aid in adapter_ids:
            adapter = self._adapter(aid)
            if adapter is not None:
                targets.append(adapter)
        return targets


_CONNECTED_STATES = {
    IntegrationState.CONFIGURED,
    IntegrationState.TRUST_REQUIRED,
    IntegrationState.INTEGRATION_READY,
    IntegrationState.CONTEXT_EMITTING,
    IntegrationState.CONTEXT_VERIFIED,
}


# --------------------------------------------------------------------------- #
# Formatting (plain text; JSON is via to_dict on the records)
# --------------------------------------------------------------------------- #

_STATE_GLYPH = {
    IntegrationState.NOT_DETECTED: "✗",
    IntegrationState.DETECTED: "○",
    IntegrationState.CONFIGURED: "◐",
    IntegrationState.TRUST_REQUIRED: "!",
    IntegrationState.ACTION_REQUIRED: "!",
    IntegrationState.INTEGRATION_READY: "✓",
    IntegrationState.CONTEXT_EMITTING: "✓",
    IntegrationState.CONTEXT_VERIFIED: "✓",
    IntegrationState.NOT_SUPPORTED: "–",
    IntegrationState.UNKNOWN: "?",
}


def display_name(record: HostRecord) -> str:
    base = record.product.replace("_", " ").title()
    runtime = (record.runtime or "").lower()
    if runtime and runtime not in {"unknown", ""} and record.product in {"codex"}:
        return f"{base} {runtime.upper() if runtime == 'cli' else runtime.title()}"
    if record.product == "claude":
        return "Claude Code"
    return base


def format_host_line(record: HostRecord, *, verbose: bool = False) -> str:
    glyph = _STATE_GLYPH.get(record.state, "?")
    line = f"{glyph} {display_name(record):<16} {record.state.value}"
    if record.version:
        line += f"  v{record.version}"
    if verbose and record.trust and record.trust != "N/A":
        line += f"  trust={record.trust}"
    return line


def format_integrations(records: Sequence[HostRecord], *, verbose: bool = False) -> str:
    lines = ["OverHaust", "", "Detected environments:", ""]
    if not records:
        lines.append("  (no adapters registered)")
    for record in records:
        lines.append("  " + format_host_line(record, verbose=verbose))
        # One adapter may own several runtimes (e.g. Codex Desktop + CLI).
        if len(record.environments) > 1:
            for env in record.environments:
                rt = (env.get("runtime") or "").replace("_", " ")
                ver = env.get("version") or "-"
                lines.append(f"      · {rt:<10} v{ver}")
        if verbose or record.state in {
            IntegrationState.TRUST_REQUIRED,
            IntegrationState.ACTION_REQUIRED,
            IntegrationState.UNKNOWN,
        }:
            if record.message:
                lines.append(f"      {record.message}")
            for action in record.actions:
                lines.append(f"      → {action}")
            for warning in record.warnings:
                lines.append(f"      ! {warning}")
            if record.error:
                lines.append(f"      ! {record.error}")
    return "\n".join(lines) + "\n"


def format_status(report: StatusReport) -> str:
    core = report.core
    lines = ["OverHaust status", "", "Core"]
    if "error" in core:
        lines.append(f"  ! {core['error']}")
    else:
        lines.append(f"  index health: {'OK' if core.get('ok') else 'ISSUES'}")
        if core.get("db_path"):
            lines.append(f"  db: {core['db_path']}")
    lines.extend(["", f"Projects ({len(report.projects)})"])
    if not report.projects:
        lines.append("  (none registered)")
    for p in report.projects:
        flag = "OK" if p.get("ok") else "ISSUES"
        lines.append(
            f"  [{flag}] {p.get('project_id')}  indexed={p.get('indexed')} "
            f"files={p.get('file_count')} root_exists={p.get('root_exists')}"
        )
        if p.get("issues"):
            lines.append(f"      issues: {', '.join(p['issues'])}")
    lines.extend(["", "Hosts"])
    for h in report.hosts:
        state = IntegrationState(h["state"])
        rec = HostRecord(
            adapter_id=h["adapter_id"], product=h["product"], detected=h["detected"],
            state=state, runtime=h.get("runtime", ""), version=h.get("version", ""),
            trust=h.get("trust", "N/A"),
        )
        lines.append("  " + format_host_line(rec, verbose=True))
        emit = h.get("emission_verified")
        lines.append(
            f"      config={h.get('configuration')}  "
            f"emission={'verified' if emit else ('unverified' if h.get('emission_verifiable') else 'n/a')}  "
            f"model_consumption={'verified' if h.get('model_consumption_verified') else 'unverified'}"
        )
    lines.extend(["", report.summary])
    return "\n".join(lines) + "\n"


def format_connect(outcomes: Sequence[ConnectOutcome]) -> str:
    lines = ["", "Connect results:", ""]
    for o in outcomes:
        if o.skipped:
            lines.append(f"  – {o.product:<12} skipped ({o.state.value.lower()}{': ' + o.error if o.error else ''})")
            continue
        if o.error:
            lines.append(f"  ✗ {o.product:<12} {o.error}")
            continue
        lines.append(f"  {_STATE_GLYPH.get(o.state, '?')} {o.product:<12} {o.state.value}")
        for p in o.paths:
            lines.append(f"      wrote {p}")
        if o.record:
            for action in o.record.actions:
                lines.append(f"      → {action}")
    return "\n".join(lines) + "\n"


def format_disconnect(outcomes: Sequence[DisconnectOutcome]) -> str:
    lines = ["", "Disconnect results:", ""]
    for o in outcomes:
        if o.error:
            lines.append(f"  ✗ {o.product:<12} {o.error}")
            continue
        lines.append(f"  ✓ {o.product:<12} removed {len(o.removed)} item(s)")
        for p in o.removed:
            lines.append(f"      {p}")
        if o.note:
            lines.append(f"      {o.note}")
    return "\n".join(lines) + "\n"
