"""Integration tests for the Overhaust FastAPI service."""
import sys
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from services.api.main import app, get_agent, get_memory_store_dep
from packages.memory.memory_store import MemoryStore
from packages.agent.autonomous_agent import OverhaustAgent
from services.ingestion.test_project_indexer import make_tree


@pytest.fixture()
def client():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    store = MemoryStore(db)
    agent = OverhaustAgent("test-api-agent", memory_store=store)
    app.dependency_overrides[get_memory_store_dep] = lambda: store
    app.dependency_overrides[get_agent] = lambda: agent
    with TestClient(app) as c:
        yield c, store, db
    app.dependency_overrides.clear()
    if os.path.exists(db):
        os.unlink(db)


def test_health(client):
    c, _, _ = client
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"
    assert "timestamp" in r.json()


def test_create_and_get_project(client):
    c, _, _ = client
    r = c.post("/api/v1/projects", json={
        "project_id": "proj-a", "name": "Project A", "root_path": "/tmp/x"
    })
    assert r.status_code == 200
    r2 = c.get("/api/v1/projects/proj-a")
    assert r2.status_code == 200
    assert r2.json()["name"] == "Project A"


def test_index_project_persists(client):
    c, _, _ = client
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_tree(root)
        c.post("/api/v1/projects", json={
            "project_id": "idx-p", "name": "Idx", "root_path": str(root)
        })
        r = c.post("/api/v1/index-project", json={
            "project_id": "idx-p", "root_path": str(root)
        })
        assert r.status_code == 200
        body = r.json()
        assert body["file_count"] >= 5
        assert body["sync"]["mode"] == "full"

        r2 = c.post("/api/v1/index-project", json={
            "project_id": "idx-p", "root_path": str(root)
        })
        assert r2.status_code == 200
        assert r2.json()["sync"]["mode"] == "unchanged"


def test_unified_search_scoring(client):
    c, store, _ = client
    store.add_project("s-p", "Search", "", "")
    store.add_memory("s-p", "We decided to use WebSockets with heartbeats",
                     "permanent", 0.9,
                     {"knowledge_type": "decision", "status": "active"})
    store.add_memory("s-p", "Marketing landing page pricing tiers",
                     "temporary", 0.2,
                     {"knowledge_type": "permanent_knowledge", "status": "active"})
    r = c.post("/api/v1/search-knowledge", json={
        "project_id": "s-p", "query": "WebSocket heartbeat", "limit": 5
    })
    assert r.status_code == 200
    body = r.json()
    assert body["scored"] is True
    assert body["count"] >= 1
    top = body["results"][0]
    assert "score" in top
    assert "reasons" in top
    assert "WebSocket" in top["content"]


def test_context_retrieval(client):
    c, store, _ = client
    store.add_project("ctx-p", "Ctx", "", "")
    store.add_memory("ctx-p", "We decided to use React for the frontend",
                     "permanent", 0.9,
                     {"knowledge_type": "decision", "status": "active"})
    r = c.post("/api/v1/get-context", json={
        "project_id": "ctx-p", "task": "How should we build the frontend?"
    })
    assert r.status_code == 200
    body = r.json()
    assert body["estimated_tokens"] > 0
    assert len(body["relevant_knowledge"]) >= 1


def test_ingest_conversation_provenance(client):
    c, store, _ = client
    store.add_project("ing-p", "Ingest", "", "")
    conv = (
        "User: We decided to use layered keyword retrieval first.\n"
        "Assistant: Sounds good.\n"
        "User: The WebSocket reconnect bug is still open.\n"
    )
    r = c.post("/api/v1/ingest-conversation", json={
        "project_id": "ing-p", "content": conv, "store": True
    })
    assert r.status_code == 200
    assert len(r.json()["stored_memory_ids"]) >= 1
    extractions = store.get_extractions("ing-p")
    assert len(extractions) >= 1
    assert "Conversation" in extractions[0]["source_content"]
    meta = extractions[0]["extracted_knowledge"]
    assert "confidence" in meta
    assert "status" in meta


def test_stale_and_resolved_knowledge(client):
    c, store, _ = client
    store.add_project("sr-p", "SR", "", "")
    stale_id = store.add_memory(
        "sr-p", "We used to use REST polling", "stale", 0.6,
        {"knowledge_type": "stale_info", "status": "stale"}
    )
    store.add_memory(
        "sr-p", "We decided to use WebSockets instead", "permanent", 0.9,
        {"knowledge_type": "decision", "status": "active"}
    )
    r = c.post("/api/v1/search-knowledge", json={
        "project_id": "sr-p", "query": "WebSocket approach", "limit": 5
    })
    assert r.status_code == 200
    contents = [x["content"] for x in r.json()["results"]]
    assert any("WebSocket" in c for c in contents)

    r2 = c.post("/api/v1/mark-resolved", json={
        "project_id": "sr-p", "issue_description": "Reconnect bug fixed"
    })
    assert r2.status_code == 200

    r3 = c.post("/api/v1/mark-stale", json={"memory_id": stale_id, "reason": "outdated"})
    assert r3.status_code == 200


def test_error_handling(client):
    c, _, _ = client
    r = c.get("/api/v1/projects/missing")
    assert r.status_code == 404

    r2 = c.post("/api/v1/update-memory", json={
        "project_id": "ghost", "content": "x"
    })
    assert r2.status_code == 404

    r3 = c.post("/api/v1/get-context", json={
        "project_id": "ghost", "task": "anything"
    })
    assert r3.status_code == 404

    r4 = c.post("/api/v1/index-project", json={
        "project_id": "no-proj", "root_path": "/tmp"
    })
    assert r4.status_code == 404
