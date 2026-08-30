"""Tests for knowledge supersession."""
import os
import sys
import tempfile

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from packages.memory.memory_store import MemoryStore
from packages.knowledge.versioning import supersede


def test_supersede_links_and_preserves_history():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        store.add_project("p", "P", "", "")
        old_id = store.add_memory(
            "p", "We use Firebase Auth", "permanent", 0.9,
            {"knowledge_type": "decision", "status": "active", "confidence": 0.8},
        )
        new_id = supersede(
            store, "p", old_id, "We use Auth0 for authentication",
            confidence=0.95, provenance="User update",
        )
        assert new_id != old_id
        old = store.get_memory(old_id)
        new = store.get_memory(new_id)
        assert old["content"] == "We use Firebase Auth"
        assert old["metadata"]["status"] == "superseded"
        assert old["metadata"]["superseded_by"] == new_id
        assert new["metadata"]["status"] == "active"
        assert new["metadata"]["supersedes"] == old_id
        assert new["content"] == "We use Auth0 for authentication"
    finally:
        os.unlink(db)


def test_supersede_wrong_project_raises():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        store.add_project("p1", "P1", "", "")
        store.add_project("p2", "P2", "", "")
        mid = store.add_memory("p1", "content", "permanent", 0.5)
        try:
            supersede(store, "p2", mid, "new")
            assert False, "expected ValueError"
        except ValueError:
            pass
    finally:
        os.unlink(db)
