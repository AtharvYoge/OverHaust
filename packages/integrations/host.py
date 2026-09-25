"""
Host/runtime identity for OverHaust integrations.

Separates product (codex/cursor/claude) from runtime (cli/desktop) and
integration mechanism. Context assembly stays in packages.context —
this module only describes *how* an environment receives context.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class IntegrationResult(str, Enum):
    READY = "READY"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"
    NOT_DETECTED = "NOT_DETECTED"


class IntegrationState(str, Enum):
    """
    User-facing lifecycle state (Integration Manager).

    Finer than IntegrationResult: configuration success is separated from
    trust and from proven context emission / model consumption.
    """

    NOT_DETECTED = "NOT_DETECTED"
    DETECTED = "DETECTED"
    CONFIGURED = "CONFIGURED"
    TRUST_REQUIRED = "TRUST_REQUIRED"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    INTEGRATION_READY = "INTEGRATION_READY"
    CONTEXT_EMITTING = "CONTEXT_EMITTING"
    CONTEXT_VERIFIED = "CONTEXT_VERIFIED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    UNKNOWN = "UNKNOWN"


@dataclass
class HostCapabilities:
    """Practical capability flags justified by existing integrations."""

    prompt_hooks: bool = False
    context_injection: bool = False
    mcp: bool = False
    always_apply_rule: bool = False
    hook_trust_required: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HostEnvironment:
    """Detected host/runtime — not an agent-personality label."""

    product: str
    runtime: str
    version: str = ""
    integration: str = ""
    binary_path: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IntegrationStatus:
    """Health snapshot for one adapter against one environment."""

    adapter_id: str
    product: str
    runtime: str
    integration: str
    result: IntegrationResult
    configuration: str = "UNKNOWN"
    hook: str = "N/A"
    trust: str = "N/A"
    mcp: str = "N/A"
    context_path: str = ""
    message: str = ""
    actions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    environment: Optional[HostEnvironment] = None
    capabilities: Optional[HostCapabilities] = None
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["result"] = self.result.value
        if self.environment is not None:
            payload["environment"] = self.environment.to_dict()
        if self.capabilities is not None:
            payload["capabilities"] = self.capabilities.to_dict()
        return payload
