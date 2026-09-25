"""
Compose host-adapter status into an OverHaust doctor report.

Composition goes through IntegrationManager so detection/verification run
exactly once per adapter. Does not drive host UIs or mutate config. The
context engine is only invoked when `probe_emission=True` (local hook
subprocess against a throwaway fixture — never the user's projects).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from packages.integrations.host import IntegrationResult, IntegrationState
from packages.integrations.manager import HostRecord, IntegrationManager


@dataclass
class DoctorReport:
    environments: List[Dict[str, Any]] = field(default_factory=list)
    integrations: List[Dict[str, Any]] = field(default_factory=list)
    hosts: List[Dict[str, Any]] = field(default_factory=list)
    result: str = IntegrationResult.UNSUPPORTED.value
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _rollup(records: Sequence[HostRecord]) -> IntegrationResult:
    if not records:
        return IntegrationResult.UNSUPPORTED
    states = {r.state for r in records}
    if states & {IntegrationState.ACTION_REQUIRED, IntegrationState.TRUST_REQUIRED, IntegrationState.UNKNOWN}:
        return IntegrationResult.ACTION_REQUIRED
    if states & {
        IntegrationState.INTEGRATION_READY,
        IntegrationState.CONTEXT_EMITTING,
        IntegrationState.CONTEXT_VERIFIED,
    }:
        return IntegrationResult.READY
    if states == {IntegrationState.NOT_DETECTED}:
        return IntegrationResult.NOT_DETECTED
    if IntegrationState.NOT_SUPPORTED in states:
        return IntegrationResult.UNSUPPORTED
    return IntegrationResult.NOT_DETECTED


def run_doctor(
    adapter_ids: Optional[Sequence[str]] = None,
    *,
    manager: Optional[IntegrationManager] = None,
    probe_emission: bool = False,
) -> DoctorReport:
    mgr = manager or IntegrationManager(probe_emission=probe_emission)
    records = mgr.discover(adapter_ids)
    rollup = _rollup(records)
    ready = sum(
        1 for r in records
        if r.state in {
            IntegrationState.INTEGRATION_READY,
            IntegrationState.CONTEXT_EMITTING,
            IntegrationState.CONTEXT_VERIFIED,
        }
    )
    action = sum(
        1 for r in records
        if r.state in {IntegrationState.ACTION_REQUIRED, IntegrationState.TRUST_REQUIRED}
    )
    envs = [e for r in records for e in r.environments]
    summary = (
        f"{ready} ready, {action} action required, "
        f"{len(envs)} host environment(s) detected"
    )
    return DoctorReport(
        environments=envs,
        integrations=[r.status for r in records if r.status],
        hosts=[r.to_dict() for r in records],
        result=rollup.value,
        summary=summary,
    )


def format_doctor_report(report: DoctorReport) -> str:
    lines = [
        "OverHaust Doctor",
        "",
        "Host environments",
    ]
    if not report.environments:
        lines.append("  (none detected)")
    for env in report.environments:
        lines.append(
            f"  Product={env.get('product')}  Runtime={env.get('runtime')}  "
            f"Version={env.get('version') or '-'}  Integration={env.get('integration')}"
        )
        if env.get("binary_path"):
            lines.append(f"    Binary  {env['binary_path']}")

    lines.extend(["", "Integrations"])
    for host in report.hosts:
        emit = host.get("emission_verified")
        emission = (
            "verified" if emit else
            ("unverified" if host.get("emission_verifiable") else "n/a")
        )
        lines.append(
            f"  [{host.get('adapter_id')}] state={host.get('state')}  "
            f"config={host.get('configuration')}  trust={host.get('trust')}  "
            f"emission={emission}  "
            f"model_consumption={'verified' if host.get('model_consumption_verified') else 'unverified'}"
        )
        if host.get("message"):
            lines.append(f"    {host['message']}")
        for action in host.get("actions") or []:
            lines.append(f"    → {action}")
        for warning in host.get("warnings") or []:
            lines.append(f"    ! {warning}")
        if host.get("error"):
            lines.append(f"    ! {host['error']}")

    lines.extend([
        "",
        "Result",
        f"  {report.result}",
        f"  {report.summary}",
    ])
    return "\n".join(lines) + "\n"
