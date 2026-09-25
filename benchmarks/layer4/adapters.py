"""
Agent adapter interface for Layer 4.

Codex CLI is the only adapter implemented here. Cursor and Claude Code keep
the same session schema and the same `AgentAdapter` methods so a later PR can
register them without changing the runner.
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


def require_adapter(agent_id: str):
    """
    Return the adapter class for `agent_id`.

    Cursor and Claude Code are named so the registry has a place for them,
    and so a request fails clearly instead of silently running Codex.
    """
    if agent_id == "codex":
        from benchmarks.layer4.codex_adapter import CodexAdapter

        return CodexAdapter
    if agent_id in {"cursor", "claude_code"}:
        raise UnsupportedAgent(
            f"{agent_id} adapter is not implemented. "
            "The Layer4SessionResult schema and AgentAdapter interface are ready."
        )
    raise UnsupportedAgent(f"unknown agent {agent_id!r}")
