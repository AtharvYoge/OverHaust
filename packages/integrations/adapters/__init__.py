"""Package exports for host integration adapters."""

from packages.integrations.adapters.base import IntegrationAdapter
from packages.integrations.adapters.claude import ClaudeAdapter
from packages.integrations.adapters.cline_host import ClineAdapter
from packages.integrations.adapters.codex import CodexAdapter
from packages.integrations.adapters.continue_host import ContinueAdapter
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

__all__ = [
    "ClaudeAdapter",
    "ClineAdapter",
    "CodexAdapter",
    "ContinueAdapter",
    "CursorAdapter",
    "IntegrationAdapter",
    "clear_registry",
    "discover_environments",
    "ensure_default_adapters",
    "freeze_registry",
    "get_adapter",
    "list_adapters",
    "register_adapter",
    "select_adapters",
    "unregister_adapter",
    "verify_all",
]
