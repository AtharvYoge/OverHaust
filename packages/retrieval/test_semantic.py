"""Tests for semantic retrieval."""
import os
import sys
import tempfile
from typing import List

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from packages.memory.memory_store import MemoryStore
from packages.retrieval.semantic import SemanticRetriever, cosine_similarity
from packages.retrieval.embeddings import EmbeddingProvider


class MockEmbeddingProvider:
    """Deterministic mock: similar texts -> similar vectors."""

    model_id = "mock-test"

    @property
    def is_available(self) -> bool:
        return True

    def _vec(self, text: str) -> List[float]:
        t = text.lower()
        return [
            1.0 if "websocket" in t or "idle" in t or "connection" in t else 0.0,
            1.0 if "heartbeat" in t or "reconnect" in t else 0.0,
            1.0 if "marketing" in t else 0.0,
            0.1,
        ]

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, query: str) -> List[float]:
        return self._vec(query)


def test_cosine_similarity():
    assert cosine_similarity([1, 0], [1, 0]) == 1.0
    assert cosine_similarity([1, 0], [0, 1]) == 0.0
    assert cosine_similarity([], [1]) == 0.0


def test_semantic_finds_paraphrase():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        store.add_project("p", "P", "", "")
        store.add_memory(
            "p",
            "WebSocket reconnect bug: connection drops after 60s idle",
            "task", 0.85,
            {"knowledge_type": "open_issue", "status": "active"},
        )
        store.add_memory(
            "p", "Marketing landing page pricing", "temporary", 0.2, {}
        )
        ret = SemanticRetriever(store, MockEmbeddingProvider())
        hits = ret.search("p", "Fix idle connection recovery", limit=5)
        assert len(hits) >= 1
        assert "WebSocket" in hits[0].memory["content"]
        assert not any("Marketing" in h.memory["content"] for h in hits)
    finally:
        os.unlink(db)


def test_semantic_unavailable_returns_empty():
    from packages.retrieval.embeddings import NullEmbeddingProvider

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        store.add_project("p", "P", "", "")
        ret = SemanticRetriever(store, NullEmbeddingProvider())
        assert ret.search("p", "anything") == []
    finally:
        os.unlink(db)


def test_stale_demotion():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        store.add_project("p", "P", "", "")
        store.add_memory(
            "p", "We used to use REST polling for updates", "stale", 0.6,
            {"knowledge_type": "stale_info", "status": "stale"},
        )
        store.add_memory(
            "p", "WebSocket heartbeats keep connections alive", "permanent", 0.9,
            {"knowledge_type": "decision", "status": "active"},
        )
        ret = SemanticRetriever(store, MockEmbeddingProvider())
        hits = ret.search("p", "WebSocket connection keepalive", limit=5)
        assert hits[0].memory["content"].startswith("WebSocket")
    finally:
        os.unlink(db)
