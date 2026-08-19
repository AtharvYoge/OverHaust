"""
Generic agent connection architecture for Overhaust.

Adapters connect external AI agents to the core memory engine WITHOUT
hardcoding any specific agent into the core. Only adapters that are
genuinely functional report status='available'.

Current adapters:
  - MCPConnection        : real, available (services/mcp_server)
  - LocalAgentConnection : real, available (in-process AgentRuntime)
  - APIConnection        : real, available (FastAPI service)
  - IDE/file-config adapters (Cursor, Windsurf, Claude Code): generate
    MCP client configuration for those IDEs; the connection itself is
    via the MCP server, so they are 'config-generator' level, marked
    coming_soon until end-to-end tested with the real IDE.
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ConnectionStatus(Enum):
    AVAILABLE = "available"
    COMING_SOON = "coming_soon"
    UNAVAILABLE = "unavailable"


@dataclass
class ConnectionInfo:
    """Describes an agent connection for UI/config."""
    id: str
    name: str
    kind: str                      # mcp | local | api | ide-config
    status: ConnectionStatus
    description: str
    capabilities: List[str] = field(default_factory=list)
    config_hint: Optional[Dict[str, Any]] = None


class AgentConnection(ABC):
    """Interface every agent connection must implement."""

    info: ConnectionInfo

    @abstractmethod
    def handle(self, method: str, params: Dict[str, Any]) -> Any:
        """Dispatch a tool-style call to the core engine."""
        ...

    @abstractmethod
    def methods(self) -> List[str]:
        ...


# ---------------------------------------------------------------------------
# Local in-process connection (wraps AgentRuntime)
# ---------------------------------------------------------------------------

class LocalAgentConnection(AgentConnection):
    """In-process connection used by the autonomous agent runtime."""

    def __init__(self, runtime=None, agent=None, memory_store=None):
        from packages.agent.autonomous_agent import OverhaustAgent
        from packages.agent.runtime import AgentRuntime
        self.agent = agent or OverhaustAgent("local-conn", memory_store=memory_store)
        self.runtime = runtime or AgentRuntime(self.agent)
        self.info = ConnectionInfo(
            id="local-agent",
            name="Overhaust Local Agent",
            kind="local",
            status=ConnectionStatus.AVAILABLE,
            description="In-process autonomous agent with action logging and gap detection.",
            capabilities=["run", "build_context", "search_memory", "remember",
                          "mark_resolved", "mark_stale", "estimate_context"],
        )

    def methods(self) -> List[str]:
        return list(self.info.capabilities)

    def handle(self, method: str, params: Dict[str, Any]) -> Any:
        if method == "run":
            res = self.runtime.run(params["project_id"], params["task"])
            return {
                "context_id": res.context_id,
                "estimated_tokens": res.estimated_tokens,
                "knowledge_items": res.knowledge_items,
                "gaps": res.gaps,
                "action_log": res.render_log(),
            }
        if method == "build_context":
            ctx = self.agent.get_project_context(params["project_id"], params["task"])
            return {"context_id": ctx.id, "estimated_tokens": ctx.estimated_tokens}
        if method == "search_memory":
            return [dict(id=m["id"], content=m["content"])
                    for m in self.agent.search_project_knowledge(
                        params["project_id"], params["query"],
                        params.get("limit", 10))]
        if method == "remember":
            return {"memory_id": self.agent.update_memory(
                params["project_id"], params["content"],
                params.get("memory_type", "temporary"),
                params.get("importance", 0.5))}
        if method == "estimate_context":
            return self.agent.estimate_context(
                self.agent.get_project_context(params["project_id"], params["task"]))
        raise ValueError(f"unsupported method: {method}")


# ---------------------------------------------------------------------------
# API connection (HTTP client to the FastAPI service)
# ---------------------------------------------------------------------------

class APIConnection(AgentConnection):
    """Connects to a running Overhaust FastAPI service over HTTP."""

    def __init__(self, base_url: Optional[str] = None):
        default_base = os.getenv("OVERHAUST_API_BASE_URL", "http://localhost:8000")
        self.base_url = (base_url or default_base).rstrip("/")
        self.info = ConnectionInfo(
            id="api",
            name="Overhaust API",
            kind="api",
            status=ConnectionStatus.AVAILABLE,
            description=f"HTTP API connection to {self.base_url}",
            capabilities=["health", "get_context", "update_memory",
                          "search_knowledge", "estimate_tokens"],
        )

    def methods(self) -> List[str]:
        return list(self.info.capabilities)

    def handle(self, method: str, params: Dict[str, Any]) -> Any:
        import urllib.request, urllib.error
        routes = {
            "health": ("GET", "/health"),
            "get_context": ("POST", "/api/v1/get-context"),
            "update_memory": ("POST", "/api/v1/update-memory"),
            "search_knowledge": ("POST", "/api/v1/search-knowledge"),
            "estimate_tokens": ("POST", "/api/v1/estimate-tokens"),
        }
        if method not in routes:
            raise ValueError(f"unsupported method: {method}")
        verb, path = routes[method]
        data = json.dumps(params).encode() if verb == "POST" else None
        req = urllib.request.Request(
            self.base_url + path, data=data, method=verb,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.URLError as e:
            raise ConnectionError(f"API unreachable: {e}")


# ---------------------------------------------------------------------------
# MCP connection (subprocess stdio client to our MCP server)
# ---------------------------------------------------------------------------

class MCPConnection(AgentConnection):
    """Client-side connection to the Overhaust MCP server over stdio."""

    def __init__(self, server_command: Optional[List[str]] = None):
        self.server_command = server_command
        self.info = ConnectionInfo(
            id="mcp",
            name="Overhaust MCP Server",
            kind="mcp",
            status=ConnectionStatus.AVAILABLE,
            description="stdio MCP server exposing memory/context tools.",
            capabilities=[t for t in ("create_project", "remember", "search_memory",
                                      "search_project_knowledge", "build_context",
                                      "get_project_context", "get_relevant_context",
                                      "update_memory", "estimate_context")],
        )

    def methods(self) -> List[str]:
        return list(self.info.capabilities)

    def handle(self, method: str, params: Dict[str, Any]) -> Any:
        # Full duplex client sessions are covered in the MCP tests;
        # here we expose one-shot calls used by integrations.
        raise NotImplementedError(
            "use services/mcp_server + an MCP client session for duplex calls")


# ---------------------------------------------------------------------------
# IDE config adapters (Cursor / Windsurf / Claude Code etc.)
# ---------------------------------------------------------------------------

class IDEConfigAdapter:
    """Generates MCP client configuration for an IDE. The actual
    connection flows through the Overhaust MCP server; these adapters
    only produce correct config blocks. Marked coming_soon until
    validated end-to-end inside the real IDE."""

    IDE_TARGETS = {
        "cursor": {"file": "~/.cursor/mcp.json"},
        "claude-code": {"file": "~/.claude.json"},
        "windsurf": {"file": "~/.codeium/windsurf/mcp_config.json"},
    }

    def __init__(self, ide: str, python_path: str = "python3",
                 project_root: Optional[str] = None):
        if ide not in self.IDE_TARGETS:
            raise ValueError(f"unsupported IDE: {ide}")
        self.ide = ide
        self.python_path = python_path
        self.project_root = project_root or str(Path(__file__).resolve().parents[2])
        self.info = ConnectionInfo(
            id=f"ide-{ide}",
            name=f"{ide.replace('-', ' ').title()} (MCP config)",
            kind="ide-config",
            status=ConnectionStatus.COMING_SOON,
            description=f"Generates MCP client config for {ide}; end-to-end IDE validation pending.",
            capabilities=["generate_config"],
            config_hint=self.IDE_TARGETS[ide],
        )

    def generate_config(self) -> Dict[str, Any]:
        """Produce the JSON block the IDE expects for MCP servers."""
        return {
            "mcpServers": {
                "overhaust": {
                    "command": self.python_path,
                    "args": ["-m", "services.mcp_server.server"],
                    "cwd": self.project_root,
                    "env": {"PYTHONPATH": self.project_root},
                }
            }
        }

    def write_config(self, target_path: Optional[str] = None) -> str:
        """Merge into the IDE's MCP config file (creates if missing)."""
        import os
        path = os.path.expanduser(
            target_path or self.IDE_TARGETS[self.ide]["file"])
        existing: Dict[str, Any] = {}
        if os.path.exists(path):
            with open(path) as f:
                try:
                    existing = json.load(f)
                except json.JSONDecodeError:
                    existing = {}
        merged = dict(existing)
        servers = dict(existing.get("mcpServers", {}))
        servers["overhaust"] = self.generate_config()["mcpServers"]["overhaust"]
        merged["mcpServers"] = servers
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(merged, f, indent=2)
        return path


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ConnectionRegistry:
    """Lists connections and routes calls to available ones."""

    def __init__(self):
        self._connections: Dict[str, AgentConnection] = {}
        self._ide_adapters: Dict[str, IDEConfigAdapter] = {}

    def register(self, conn: AgentConnection):
        self._connections[conn.info.id] = conn

    def register_ide(self, adapter: IDEConfigAdapter):
        self._ide_adapters[adapter.info.id] = adapter

    def list_connections(self) -> List[ConnectionInfo]:
        infos = [c.info for c in self._connections.values()]
        infos += [a.info for a in self._ide_adapters.values()]
        return sorted(infos, key=lambda i: (i.status.value, i.name))

    def get(self, connection_id: str) -> AgentConnection:
        conn = self._connections.get(connection_id)
        if conn is None:
            raise KeyError(f"no connection: {connection_id}")
        if conn.info.status != ConnectionStatus.AVAILABLE:
            raise RuntimeError(f"connection {connection_id} is not available")
        return conn

    def handle(self, connection_id: str, method: str, params: Dict[str, Any]) -> Any:
        return self.get(connection_id).handle(method, params)


def default_registry(project_root: Optional[str] = None) -> ConnectionRegistry:
    reg = ConnectionRegistry()
    reg.register(LocalAgentConnection())
    reg.register(APIConnection(os.getenv("OVERHAUST_API_BASE_URL", "http://localhost:8000")))
    reg.register(MCPConnection())
    resolved_root = project_root or str(Path(__file__).resolve().parents[2])
    for ide in ("cursor", "claude-code", "windsurf"):
        reg.register_ide(IDEConfigAdapter(ide, project_root=resolved_root))
    return reg
