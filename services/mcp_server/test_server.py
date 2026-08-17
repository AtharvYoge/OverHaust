"""Tests for the Overhaust MCP server (real tools, real core services)."""
import sys, os, json, tempfile, asyncio, subprocess, time
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from services.mcp_server.server import OverhaustMCPServer
from packages.memory.memory_store import MemoryStore


def make_server(db):
    store = MemoryStore(db)
    return OverhaustMCPServer(memory_store=store), store


def payload(result):
    """Extract JSON payload from a CallToolResult."""
    assert result.content, "empty result content"
    return json.loads(result.content[0].text)


def test_create_project_and_remember():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        srv, store = make_server(db)
        r = srv._tool_create_project({"project_id": "mcp-p", "name": "MCP Test"})
        assert payload(r)["project_id"] == "mcp-p"
        r = srv._tool_remember({"project_id": "mcp-p",
                                "content": "We decided to use MCP for agent integration",
                                "memory_type": "permanent", "importance": 0.9,
                                "knowledge_type": "decision"})
        assert "memory_id" in payload(r)
        print("✓ create_project + remember tools work")
    finally:
        os.unlink(db)


def test_remember_rejects_ghost_project():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        srv, _ = make_server(db)
        r = srv._tool_remember({"project_id": "ghost", "content": "x"})
        assert getattr(r, 'is_error', False) or 'error' in payload(r)
        print("✓ remember rejects ghost project")
    finally:
        os.unlink(db)


def test_search_and_build_context():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        srv, store = make_server(db)
        srv._tool_create_project({"project_id": "chat", "name": "Chat"})
        srv._tool_remember({"project_id": "chat", "content": "We decided to use WebSockets with heartbeats",
                            "memory_type": "permanent", "importance": 0.9, "knowledge_type": "decision"})
        srv._tool_remember({"project_id": "chat", "content": "The WebSocket reconnect bug is still open",
                            "memory_type": "task", "importance": 0.85, "knowledge_type": "open_issue"})
        srv._tool_remember({"project_id": "chat", "content": "Marketing landing page copy and pricing",
                            "memory_type": "temporary", "importance": 0.2})

        r = srv._tool_search_memory({"project_id": "chat", "query": "Fix the WebSocket reconnect bug"})
        results = payload(r)["results"]
        assert len(results) >= 2
        assert results[0]["score"] >= results[-1]["score"]
        assert not any("Marketing" in x["content"] for x in results)
        print(f"✓ search_memory: {len(results)} ranked results")

        r = srv._tool_build_context({"project_id": "chat", "task": "Fix the WebSocket reconnect bug"})
        ctx = payload(r)
        assert ctx["estimated_tokens"] > 0
        assert ctx["estimated"] is True
        assert len(ctx["knowledge"]) >= 2
        assert any("WebSocket" in d for d in ctx["decisions"])
        print(f"✓ build_context: {ctx['estimated_tokens']} est. tokens, "
              f"{len(ctx['knowledge'])} knowledge items")
    finally:
        os.unlink(db)


def test_estimate_and_update():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        srv, store = make_server(db)
        r = srv._tool_estimate_context({"text": "Hello world, this is a test."})
        p = payload(r)
        assert p["estimated_tokens"] > 0 and p["estimated"] is True

        srv._tool_create_project({"project_id": "u", "name": "U"})
        r = srv._tool_remember({"project_id": "u", "content": "initial content"})
        mid = payload(r)["memory_id"]
        r = srv._tool_update_memory({"memory_id": mid, "content": "updated content", "importance": 0.9})
        assert payload(r)["updated"] is True
        mem = store.get_memory(mid)
        assert mem["content"] == "updated content"
        assert mem["importance_score"] == 0.9
        print("✓ estimate_context + update_memory tools work")
    finally:
        os.unlink(db)


def test_unknown_tool_error():
    srv, _ = make_server(":memory:") if False else (None, None)
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        srv, _ = make_server(db)
        async def call():
            class P: name = "nope_tool"; arguments = {}
            return await srv._call_tool(None, P())
        r = asyncio.run(call())
        assert 'error' in payload(r)
        print("✓ unknown tool returns structured error")
    finally:
        os.unlink(db)


def test_stdio_roundtrip():
    """Real MCP stdio handshake: initialize + list_tools via subprocess pipes."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    env = dict(os.environ)
    env['PYTHONPATH'] = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    # Run server with isolated DB via a tiny bootstrap
    bootstrap = (
        "import sys; sys.path.insert(0, %r);"
        "from services.mcp_server.server import OverhaustMCPServer;"
        "from packages.memory.memory_store import MemoryStore;"
        "import asyncio;"
        "srv = OverhaustMCPServer(memory_store=MemoryStore(%r));"
        "asyncio.run(srv.run_stdio())"
    ) % (env['PYTHONPATH'], db)
    proc = subprocess.Popen(
        [sys.executable, "-c", bootstrap],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env,
    )
    try:
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05",
                           "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}}
        proc.stdin.write(json.dumps(init) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        resp = json.loads(line)
        assert resp.get("result", {}).get("serverInfo", {}).get("name") == "overhaust", resp
        print("✓ stdio initialize handshake ok:", resp["result"]["serverInfo"])

        req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()
        # may receive notification lines first; read until id=2 response
        for _ in range(10):
            line = proc.stdout.readline()
            if not line:
                break
            resp = json.loads(line)
            if resp.get("id") == 2:
                tools = resp["result"]["tools"]
                names = {t["name"] for t in tools}
                assert "build_context" in names and "remember" in names and "search_memory" in names
                print(f"✓ tools/list over stdio: {len(tools)} tools")
                break
        else:
            raise AssertionError("no tools/list response")
    finally:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        if os.path.exists(db):
            os.unlink(db)


if __name__ == "__main__":
    print("Running MCP server tests...\n")
    test_create_project_and_remember()
    test_remember_rejects_ghost_project()
    test_search_and_build_context()
    test_estimate_and_update()
    test_unknown_tool_error()
    test_stdio_roundtrip()
    print("\n✓ All MCP server tests passed!")
