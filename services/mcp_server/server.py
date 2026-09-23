"""
MCP (Model Context Protocol) server for Overhaust.

Exposes real tools backed by the core memory/context engine over stdio.
Independent of the web UI and FastAPI service — the same core services
are shared.

Tools:
  get_project_context, search_project_knowledge, search_memory,
  get_relevant_context, remember, update_memory, estimate_context,
  build_context, create_project, trace_code_flow
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
                "supersedes_memory_id": _json_schema_string("Optional memory ID to supersede with this new knowledge"),
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
        description="Compact relevant context for a task. Accepts project_id or root_path, and prompt or task.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": _json_schema_string("Registered project id"),
                "root_path": _json_schema_string("Repository path used to resolve project_id"),
                "prompt": _json_schema_string("The current task/question"),
                "task": _json_schema_string("Alias of prompt"),
            },
            "required": [],
        },
    ),
    types.Tool(
        name="trace_code_flow",
        description="Trace a short ordered code-flow evidence path (file/symbol steps with relevance and trust).",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": _json_schema_string("Project to trace"),
                "query": _json_schema_string("Flow question, e.g. where is KOT generated"),
                "max_steps": {"type": "integer", "minimum": 1, "maximum": 20, "default": 6},
            },
            "required": ["project_id", "query"],
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
        from packages.context.retrieval import get_relevance_engine
        from packages.tokenization.token_estimator import TokenEstimator

        self.store = memory_store or get_memory_store()
        self.agent = OverhaustAgent("mcp-agent", memory_store=self.store)
        self.relevance = get_relevance_engine(self.store)
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
        if args.get("supersedes_memory_id"):
            try:
                mid = self.agent.supersede_knowledge(
                    args["project_id"],
                    args["supersedes_memory_id"],
                    args["content"],
                    confidence=args.get("confidence"),
                    knowledge_type=args.get("knowledge_type"),
                )
            except ValueError as e:
                return _err(str(e))
            return _ok({"memory_id": mid, "superseded": args["supersedes_memory_id"]})

        meta = {"authority": "user", "source_type": "user", "version": 1}
        if args.get("knowledge_type"):
            meta["knowledge_type"] = args["knowledge_type"]
        if args.get("confidence") is not None:
            meta["confidence"] = float(args["confidence"])
        try:
            mid = self.store.add_memory(
                args["project_id"], args["content"],
                memory_type=args.get("memory_type", "temporary"),
                importance_score=float(args.get("importance", 0.5)),
                metadata=meta,
            )
        except ValueError as e:
            return _err(str(e))
        return _ok({"memory_id": mid})

    def _tool_search_memory(self, args: Dict[str, Any]):
        from packages.context.retrieval import search_project_knowledge
        results = search_project_knowledge(
            args["project_id"], args["query"],
            memory_store=self.store, limit=int(args.get("limit", 10)),
        )
        return _ok({"results": [
            {"memory_id": r["id"], "content": r["content"],
             "score": r.get("score"), "reasons": r.get("reasons"),
             "trust_score": r.get("trust_score"),
             "retrieval_methods": r.get("retrieval_methods", ["keyword"]),
             "memory_type": r.get("memory_type"),
             "importance": r.get("importance_score"),
             "provenance": r.get("provenance"),
             "trust": (r.get("metadata") or {}).get("trust")}
            for r in results
        ]})

    _tool_search_project_knowledge = _tool_search_memory

    def _tool_trace_code_flow(self, args: Dict[str, Any]):
        from packages.context.retrieval import trace_code_flow
        max_steps = args.get("max_steps")
        result = trace_code_flow(
            args["project_id"],
            args["query"],
            memory_store=self.store,
            max_steps=int(max_steps) if max_steps is not None else None,
        )
        return _ok(result)

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
                 "relevance": (k.metadata or {}).get("relevance"),
                 "trust": (k.metadata or {}).get("trust"),
                 "provenance": (k.metadata or {}).get("provenance")}
                for k in ctx.relevant_knowledge
            ],
            "decisions": [d.content for d in ctx.relevant_decisions],
            "constraints": ctx.constraints,
            "insufficient_evidence": ctx.insufficient_evidence,
            "evidence_note": ctx.evidence_note,
        })

    _tool_get_project_context = _tool_build_context

    def _tool_get_relevant_context(self, args: Dict[str, Any]):
        """Compact context via assemble_agent_context (prompt or task, optional root_path)."""
        from packages.context.agent_context import (
            MCP_MAX_PROMPT_LENGTH,
            invoke_context_request,
        )

        prompt = args.get("prompt") or args.get("task") or ""
        include_code_flow = args.get("include_code_flow", "auto")
        try:
            response = invoke_context_request(
                args.get("project_id") or "",
                prompt,
                root_path=args.get("root_path"),
                memory_store=self.store,
                include_code_flow=include_code_flow,
                max_files=args.get("max_files"),
                max_symbols=args.get("max_symbols"),
                max_prompt_length=MCP_MAX_PROMPT_LENGTH,
            )
        except ValueError as e:
            return _err(str(e))
        return _ok(response.to_mcp_payload())

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
