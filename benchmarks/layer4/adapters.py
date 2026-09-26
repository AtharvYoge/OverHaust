"""
Agent adapter interface for Layer 4.

Codex CLI and Cursor's headless `cursor-agent` are implemented. Claude Code
keeps the same session schema so a later adapter can register it. Cursor does
not reuse Codex's telemetry model: cache reads are a separate bucket.
"""

from __future__ import annotations

from typing import Protocol

from benchmarks.layer4.schema import Layer4SessionResult


class UnsupportedAgent(NotImplementedError):
    """Raised when a caller asks for an adapter this package does not build."""


class AgentAdapter(Protocol):
    """What the runner needs from any coding-agent backend."""

    agent_id: str

    def probe(self) -> "AgentProbe":
        """Binary presence and version. Must not start a model session."""

    def build_session_result(self, capture: "SessionCapture") -> Layer4SessionResult:
        """Map one captured session onto the shared schema."""


class AgentProbe(Protocol):
    agent: str
    version: str | None
    binary: str | None


class SessionCapture(Protocol):
    """Raw outputs the runner collected. Adapters do not launch processes."""

    session_id: str
    agent: str
    pair_id: str
    order_in_pair: int
    condition_order: str
    seed: int


def require_adapter(agent_id: str):
    """
    Return the adapter class for `agent_id`.

    Codex and Cursor are registered. Claude Code fails clearly instead of
    running another agent.
    """
    if agent_id == "codex":
        from benchmarks.layer4.codex_adapter import CodexAdapter

        return CodexAdapter
    if agent_id == "cursor":
        from benchmarks.layer4.cursor_adapter import CursorAdapter

        return CursorAdapter
    if agent_id == "claude_code":
        raise UnsupportedAgent(
            "claude_code adapter is not implemented. "
            "The Layer4SessionResult schema and AgentAdapter interface are ready."
        )
    raise UnsupportedAgent(f"unknown agent {agent_id!r}")
