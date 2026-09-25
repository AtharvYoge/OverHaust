"""
Host/runtime integrations for OverHaust.

Context seam (agent-agnostic): packages.context.invoke_context_request.
Host adapters (product/runtime-specific): packages.integrations.adapters.

Codex/Claude UserPromptSubmit hooks call invoke_context_request().
Cursor uses alwaysApply rules + MCP get_relevant_context (not hook injection).
"""

from packages.integrations.debug import InterceptionDebugReport
from packages.integrations.host import (
    HostCapabilities,
    HostEnvironment,
    IntegrationResult,
    IntegrationState,
    IntegrationStatus,
)
from packages.integrations.interception import (
    CONTEXT_MARKER,
    InterceptionResult,
    run_cursor_before_submit_hook,
    run_user_prompt_interception,
)

__all__ = [
    "CONTEXT_MARKER",
    "HostCapabilities",
    "HostEnvironment",
    "IntegrationResult",
    "IntegrationState",
    "IntegrationStatus",
    "InterceptionDebugReport",
    "InterceptionResult",
    "run_cursor_before_submit_hook",
    "run_user_prompt_interception",
]
