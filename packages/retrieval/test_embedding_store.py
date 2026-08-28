"""Tests for embedding persistence."""
import os
import sys
import tempfile

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from packages.memory.memory_store import MemoryStore
from packages.retrieval.embedding_store import EmbeddingStore


def test_upsert_and_get():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        es = EmbeddingStore(store)
        vec = [0.1, 0.2, 0.3]
        es.upsert("m1", "p1", "mock-model", "hash1", vec)
        got = es.get("m1", "mock-model")
        assert got is not None
        assert got[0] == "hash1"
        assert got[1] == vec
    finally:
        os.unlink(db)


def test_hash_invalidation():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        es = EmbeddingStore(store)
        es.upsert("m1", "p1", "mock", "old-hash", [1.0, 0.0])
        es.upsert("m1", "p1", "mock", "new-hash", [0.0, 1.0])
        got = es.get("m1", "mock")
        assert got[0] == "new-hash"
        assert got[1] == [0.0, 1.0]
    finally:
        os.unlink(db)


def test_delete_on_memory_delete():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        store.add_project("p1", "P", "", "")
        mid = store.add_memory("p1", "content to remember")
        es = EmbeddingStore(store)
        es.upsert(mid, "p1", "mock", "h", [1.0])
        store.delete_memory(mid)
        assert es.get(mid, "mock") is None
    finally:
        os.unlink(db)
