"""Tests for trust integration in retrieval."""
import os
import sys
import tempfile

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from packages.memory.memory_store import MemoryStore
from packages.context.retrieval import search_project_knowledge
from packages.knowledge.versioning import supersede


def test_relevance_and_trust_separate():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        store.add_project("p", "P", "", "")
        store.add_memory(
            "p", "We use Auth0", "permanent", 0.9,
            {"knowledge_type": "decision", "confidence": 0.9, "status": "active",
             "provenance": "User", "source_ref": "User"},
        )
        results = search_project_knowledge("p", "Auth0 authentication", memory_store=store)
        assert results
        top = results[0]
        assert "score" in top
        assert "trust_score" in top
        assert top["metadata"]["relevance"]["score"] == top["score"]
        assert top["metadata"]["trust"]["score"] == top["trust_score"]
    finally:
        os.unlink(db)


def test_superseded_excluded_from_search():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        store.add_project("p", "P", "", "")
        old_id = store.add_memory(
            "p", "We use Firebase Auth for login", "permanent", 0.9,
            {"knowledge_type": "decision", "confidence": 0.8, "status": "active"},
        )
        supersede(store, "p", old_id, "We use Auth0 for login", confidence=0.95)
        results = search_project_knowledge("p", "authentication login", memory_store=store)
        contents = [r["content"] for r in results]
        assert any("Auth0" in c for c in contents)
        assert not any("Firebase" in c for c in contents)
    finally:
        os.unlink(db)
