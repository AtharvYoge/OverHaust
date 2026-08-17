"""
MCP (Model Context Protocol) server for Overhaust.

Exposes real tools backed by the core memory/context engine over stdio.
Independent of the web UI and FastAPI service — the same core services
are shared.

Tools:
  get_project_context, search_project_knowledge, search_memory,
  get_relevant_context, remember, update_memory, estimate_context,
  build_context, create_project
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

logger = logging.getLogger("overhaust.mcp")


def _json_schema_string(desc: str) -> Dict[str, Any]:
    return {"type": "string", "description": desc}


TOOL_DEFS = [
    types.Tool(
        name="create_project",
        description="Create a project in Overhaust memory (required before storing memories).",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": _json_schema_string("Unique project identifier"),
                "name": _json_schema_string("Human-readable project name"),
                "description": _json_schema_string("Optional description"),
            },
            "required": ["project_id", "name"],
        },
    ),
    types.Tool(
        name="remember",
        description="Store a piece of knowledge/memory for a project (decision, architecture, issue, preference).",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": _json_schema_string("Project to attach the memory to"),
                "content": _json_schema_string("The knowledge to remember"),
                "memory_type": {"type": "string", "enum": ["permanent", "temporary", "task", "resolved", "stale"], "default": "temporary"},
                "importance": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.5},
                "knowledge_type": _json_schema_string("Optional category: decision | permanent_knowledge | open_issue | current_task | resolved_issue | stale_info"),
            },
            "required": ["project_id", "content"],
        },
    ),
    types.Tool(
        name="search_memory",
        description="Search project memories with the layered relevance engine. Returns ranked results with scores and reasons.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": _json_schema_string("Project to search"),
                "query": _json_schema_string("What to look for"),
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
            "required": ["project_id", "query"],
        },
    ),
    types.Tool(
        name="search_project_knowledge",
        description="Alias of search_memory — ranked relevance search over project knowledge.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": _json_schema_string("Project to search"),
                "query": _json_schema_string("What to look for"),
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
            "required": ["project_id", "query"],
        },
    ),
    types.Tool(
        name="build_context",
        description="Build an optimized context package for a task: relevant knowledge, decisions, constraints + token estimate.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": _json_schema_string("Project"),
                "task": _json_schema_string("The current task/question"),
                "max_items": {"type": "integer", "minimum": 1, "maximum": 30, "default": 10},
            },
            "required": ["project_id", "task"],
        },
    ),
    types.Tool(
        name="get_project_context",
        description="Alias of build_context.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": _json_schema_string("Project"),
                "task": _json_schema_string("The current task/question"),
                "max_items": {"type": "integer", "minimum": 1, "maximum": 30, "default": 10},
            },
            "required": ["project_id", "task"],
        },
    ),
    types.Tool(
        name="get_relevant_context",
        description="Compact relevant context for a task (knowledge + decisions + constraints, no files).",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": _json_schema_string("Project"),
                "task": _json_schema_string("The current task/question"),
            },
            "required": ["project_id", "task"],
        },
    ),
    types.Tool(
        name="update_memory",
        description="Update an existing memory's content, importance or metadata.",
        input_schema={
            "type": "object",
            "properties": {
                "memory_id": _json_schema_string("Memory ID to update"),
                "content": _json_schema_string("New content (optional)"),
                "importance": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["memory_id"],
        },
    ),
    types.Tool(
        name="estimate_context",
        description="Estimate token usage for arbitrary text (tiktoken-based estimate, not provider billing).",
        input_schema={
            "type": "object",
            "properties": {
                "text": _json_schema_string("Text to estimate"),
                "model": _json_schema_string("Model name (default gpt-4)"),
            },
            "required": ["text"],
        },
    ),
]


def _ok(payload: Any) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]
    )


def _err(message: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps({"error": message}))],
        is_error=True,
    )


class OverhaustMCPServer:
    """MCP server wired to the real Overhaust core services."""

    def __init__(self, memory_store=None):
        from packages.memory.memory_store import get_memory_store
        from packages.agent.autonomous_agent import OverhaustAgent
        from packages.context.relevance import LayeredRelevanceEngine
        from packages.tokenization.token_estimator import TokenEstimator

        self.store = memory_store or get_memory_store()
        self.agent = OverhaustAgent("mcp-agent", memory_store=self.store)
        self.relevance = LayeredRelevanceEngine(self.store)
        self.estimator = TokenEstimator()
        self.server = Server("overhaust", on_list_tools=self._list_tools,
                             on_call_tool=self._call_tool)

    async def _list_tools(self, ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=TOOL_DEFS)

    async def _call_tool(self, ctx, params) -> types.CallToolResult:
        name = params.name
        args = params.arguments or {}
        try:
            handler = getattr(self, f"_tool_{name}", None)
            if handler is None:
                return _err(f"unknown tool: {name}")
            return handler(args)
        except Exception as e:
            logger.exception(f"tool {name} failed")
            return _err(f"{type(e).__name__}: {e}")

    # ------------------------------------------------------------------

    def _tool_create_project(self, args: Dict[str, Any]):
        pid = self.store.add_project(args["project_id"], args["name"],
                                     args.get("description", ""))
        return _ok({"project_id": pid, "message": "project created"})

    def _tool_remember(self, args: Dict[str, Any]):
        meta = {}
        if args.get("knowledge_type"):
            meta["knowledge_type"] = args["knowledge_type"]
        try:
            mid = self.store.add_memory(
                args["project_id"], args["content"],
                memory_type=args.get("memory_type", "temporary"),
                importance_score=float(args.get("importance", 0.5)),
                metadata=meta or None,
            )
        except ValueError as e:
            return _err(str(e))
        return _ok({"memory_id": mid})

    def _tool_search_memory(self, args: Dict[str, Any]):
        results = self.relevance.search(args["project_id"], args["query"],
                                        limit=int(args.get("limit", 10)))
        return _ok({"results": [
            {"memory_id": sm.memory["id"], "content": sm.memory["content"],
             "score": sm.score, "reasons": sm.reasons,
             "memory_type": sm.memory.get("memory_type"),
             "importance": sm.memory.get("importance_score"),
             "provenance": (sm.memory.get("metadata") or {}).get("provenance")}
            for sm in results
        ]})

    _tool_search_project_knowledge = _tool_search_memory

    def _tool_build_context(self, args: Dict[str, Any]):
        try:
            ctx = self.agent.get_project_context(
                args["project_id"], args["task"],
                max_knowledge_items=int(args.get("max_items", 10)))
        except ValueError as e:
            return _err(str(e))
        return _ok({
            "context_id": ctx.id,
            "estimated_tokens": ctx.estimated_tokens,
            "estimated": True,
            "knowledge": [
                {"content": k.content, "type": k.knowledge_type,
                 "importance": k.importance_score,
                 "relevance": (k.metadata or {}).get("relevance")}
                for k in ctx.relevant_knowledge
            ],
            "decisions": [d.content for d in ctx.relevant_decisions],
            "constraints": ctx.constraints,
        })

    _tool_get_project_context = _tool_build_context

    def _tool_get_relevant_context(self, args: Dict[str, Any]):
        try:
            rc = self.agent.get_relevant_context(args["project_id"], args["task"])
        except ValueError as e:
            return _err(str(e))
        return _ok(rc)

    def _tool_update_memory(self, args: Dict[str, Any]):
        ok = self.store.update_memory(args["memory_id"],
                                      content=args.get("content"),
                                      importance_score=args.get("importance"))
        if not ok:
            return _err("memory not found or no fields to update")
        return _ok({"memory_id": args["memory_id"], "updated": True})

    def _tool_estimate_context(self, args: Dict[str, Any]):
        tokens = self.estimator.estimate_tokens(args["text"], args.get("model", "gpt-4"))
        return _ok({"estimated_tokens": tokens, "estimated": True,
                    "model": args.get("model", "gpt-4")})

    async def run_stdio(self):
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream,
                                  self.server.create_initialization_options())


def main():
    logging.basicConfig(level=logging.INFO, stream=__import__('sys').stderr)
    server = OverhaustMCPServer()
    asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()
