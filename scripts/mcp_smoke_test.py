#!/usr/bin/env python3
"""In-process MCP smoke test for primary context tools (not a fake agent)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.memory.memory_store import MemoryStore
from packages.retrieval.test_index_retrieval import make_kot_tree
from services.ingestion.index_store import ProjectIndexStore
from services.mcp_server.server import OverhaustMCPServer


def payload(result):
    return json.loads(result.content[0].text)


def main() -> int:
    tmpdir = tempfile.mkdtemp()
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    root = Path(tmpdir)
    make_kot_tree(root)

    store = MemoryStore(db)
    store.add_project("smoke-p", "Smoke", "", str(root))
    ProjectIndexStore(store).sync_project("smoke-p", str(root))

    srv = OverhaustMCPServer(memory_store=store)

    projects = payload(srv._tool_list_projects({}))
    assert any(p["project_id"] == "smoke-p" for p in projects["projects"])
    print("list_projects: ok")

    ctx = payload(srv._tool_get_relevant_context({
        "project_id": "smoke-p",
        "prompt": "Where is the KOT generated?",
        "include_code_flow": False,
    }))
    assert ctx.get("context")
    assert ctx["metrics"]["files_count"] <= 5
    print("get_relevant_context: ok")

    unrelated = payload(srv._tool_get_relevant_context({
        "project_id": "smoke-p",
        "prompt": "How does Stripe billing work?",
    }))
    assert unrelated["insufficient_evidence"] is True
    print("insufficient_evidence: ok")

    print("MCP smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
