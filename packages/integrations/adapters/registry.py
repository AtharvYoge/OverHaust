"""
Adapter registry and selection.

New host adapters register here without touching context/retrieval core.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from packages.integrations.adapters.base import IntegrationAdapter
from packages.integrations.host import (
    HostEnvironment,
    IntegrationResult,
    IntegrationStatus,
)

_REGISTRY: Dict[str, IntegrationAdapter] = {}
_DEFAULT_LOADED = False


def register_adapter(adapter: IntegrationAdapter) -> IntegrationAdapter:
    """Register (or replace) an adapter by id."""
    _REGISTRY[adapter.id] = adapter
    return adapter


def unregister_adapter(adapter_id: str) -> None:
    _REGISTRY.pop(adapter_id, None)


def clear_registry() -> None:
    """Test helper — removes all adapters and allows defaults to reload."""
    global _DEFAULT_LOADED
    _REGISTRY.clear()
    _DEFAULT_LOADED = False


def freeze_registry() -> None:
    """Test helper — keep current registry; do not inject default adapters."""
    global _DEFAULT_LOADED
    _DEFAULT_LOADED = True


def ensure_default_adapters() -> None:
    """Lazily register the shipping host adapters once."""
    global _DEFAULT_LOADED
    if _DEFAULT_LOADED:
        return
    from packages.integrations.adapters.claude import ClaudeAdapter
    from packages.integrations.adapters.cline_host import ClineAdapter
    from packages.integrations.adapters.codex import CodexAdapter
    from packages.integrations.adapters.continue_host import ContinueAdapter
    from packages.integrations.adapters.cursor import CursorAdapter

    register_adapter(CursorAdapter())
    register_adapter(CodexAdapter())
    register_adapter(ClaudeAdapter())
    register_adapter(ContinueAdapter())
    register_adapter(ClineAdapter())
    _DEFAULT_LOADED = True


def list_adapters() -> List[IntegrationAdapter]:
    ensure_default_adapters()
    return list(_REGISTRY.values())


def get_adapter(adapter_id: str) -> Optional[IntegrationAdapter]:
    ensure_default_adapters()
    return _REGISTRY.get(adapter_id)


def discover_environments(
    adapter_ids: Optional[Sequence[str]] = None,
) -> List[HostEnvironment]:
    """Run detect() across adapters; skip unknown ids quietly."""
    ensure_default_adapters()
    found: List[HostEnvironment] = []
    adapters: Iterable[IntegrationAdapter]
    if adapter_ids is None:
        adapters = _REGISTRY.values()
    else:
        adapters = [a for aid in adapter_ids if (a := _REGISTRY.get(aid))]
    for adapter in adapters:
        try:
            found.extend(adapter.detect())
        except Exception:
            # Fail-open: a broken detector must not crash selection.
            continue
    return found


def select_adapters(
    *,
    product: Optional[str] = None,
    runtime: Optional[str] = None,
    prefer_detected: bool = True,
) -> List[IntegrationAdapter]:
    """
    Choose adapters without a hard-coded if/elif product chain in callers.

    If prefer_detected, only adapters that detect at least one environment
    are returned (filtered by optional product/runtime). Otherwise return
    registered adapters matching the filters (useful for install-by-name).
    """
    ensure_default_adapters()
    selected: List[IntegrationAdapter] = []
    for adapter in _REGISTRY.values():
        if product and adapter.product != product:
            continue
        if prefer_detected:
            try:
                envs = adapter.detect()
            except Exception:
                envs = []
            if not envs:
                continue
            if runtime and not any(e.runtime == runtime for e in envs):
                continue
        elif runtime:
            # Without detection, runtime filter only applies when caller
            # already knows the adapter (install path ignores runtime).
            pass
        selected.append(adapter)
    return selected


def verify_all(
    adapter_ids: Optional[Sequence[str]] = None,
) -> List[IntegrationStatus]:
    """Verify each requested (or all default) adapters once."""
    ensure_default_adapters()
    statuses: List[IntegrationStatus] = []
    ids = list(adapter_ids) if adapter_ids is not None else list(_REGISTRY.keys())
    for adapter_id in ids:
        adapter = _REGISTRY.get(adapter_id)
        if adapter is None:
            statuses.append(
                IntegrationStatus(
                    adapter_id=adapter_id,
                    product=adapter_id,
                    runtime="unknown",
                    integration="unknown",
                    result=IntegrationResult.UNSUPPORTED,
                    message=f"No adapter registered for {adapter_id!r}",
                )
            )
            continue
        try:
            statuses.append(adapter.verify())
        except Exception as exc:
            statuses.append(
                IntegrationStatus(
                    adapter_id=adapter.id,
                    product=adapter.product,
                    runtime="unknown",
                    integration="unknown",
                    result=IntegrationResult.ACTION_REQUIRED,
                    message=f"verify failed: {exc}",
                )
            )
    return statuses
