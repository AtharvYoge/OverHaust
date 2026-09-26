"""
Host/runtime integrations for OverHaust.

Context seam (agent-agnostic): packages.context.invoke_context_request.
Host adapters (product/runtime-specific): packages.integrations.adapters.

Codex/Claude UserPromptSubmit hooks call invoke_context_request().
Cursor IDE uses alwaysApply rules + MCP get_relevant_context
(beforeSubmitPrompt does not inject). Headless cursor-agent Layer 4 runs
inject through the sessionStart hook in cursor_session_start.py, which also
calls invoke_context_request.
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
