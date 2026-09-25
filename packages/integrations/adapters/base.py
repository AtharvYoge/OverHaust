"""Integration adapter protocol — host install/detect/verify only."""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from packages.integrations.host import (
    HostCapabilities,
    HostEnvironment,
    IntegrationStatus,
)


@runtime_checkable
class IntegrationAdapter(Protocol):
    """
    Host/runtime adapter.

    MUST NOT call retrieval, ranking, indexing, or assemble_agent_context.
    Context enters OverHaust only via invoke_context_request / MCP / hooks
    that already exist outside this protocol.
    """

    @property
    def id(self) -> str:
        """Stable adapter id (e.g. 'codex', 'cursor', 'claude')."""

    @property
    def product(self) -> str:
        ...

    def detect(self) -> List[HostEnvironment]:
        """Return zero or more detected host/runtime environments."""

    def capabilities(self, environment: Optional[HostEnvironment] = None) -> HostCapabilities:
        """Static/runtime capability flags for this adapter."""

    def install(self, *, root=None, python: str = "python3", dry_run: bool = False) -> List[str]:
        """Configure this host's native integration; return written paths."""

    def verify(self, environment: Optional[HostEnvironment] = None) -> IntegrationStatus:
        """Inspect configuration / trust without driving the host UI."""

    def uninstall(self, *, dry_run: bool = False) -> List[str]:
        """Remove OverHaust-owned config when supported; else empty list."""
