"""Tests for hybrid relevance engine."""
import os
import sys
import tempfile
from typing import List

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from packages.memory.memory_store import MemoryStore
from packages.retrieval.hybrid import HybridRelevanceEngine
from packages.retrieval.semantic import SemanticRetriever
from packages.retrieval.embeddings import EmbeddingProvider
from packages.context.relevance import LayeredRelevanceEngine


class MockEmbeddingProvider:
    model_id = "mock-hybrid"

    @property
    def is_available(self) -> bool:
        return True

    def _vec(self, text: str) -> List[float]:
        t = text.lower()
        return [
            1.0 if any(w in t for w in ("websocket", "idle", "connection", "recovery")) else 0.0,
            1.0 if any(w in t for w in ("heartbeat", "reconnect")) else 0.0,
            1.0 if "marketing" in t else 0.0,
            0.1,
        ]

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, query: str) -> List[float]:
        return self._vec(query)


def _seed_store(db):
    store = MemoryStore(db)
    store.add_project("p", "P", "", "")
    store.add_memory(
        "p",
        "WebSocket reconnect bug: connection drops after 60s idle",
        "task", 0.85,
        {"knowledge_type": "open_issue", "status": "active", "confidence": 0.8},
    )
    store.add_memory(
        "p", "Marketing landing page pricing tiers", "temporary", 0.2,
        {"knowledge_type": "permanent_knowledge", "confidence": 0.3},
    )
    return store


def test_hybrid_explainable_methods():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store = _seed_store(db)
        engine = HybridRelevanceEngine(store)
        engine.semantic = SemanticRetriever(store, MockEmbeddingProvider())
        results = engine.search("p", "Fix idle connection recovery", limit=5)
        assert len(results) >= 1
        top = results[0]
        assert top.retrieval_methods
        assert "WebSocket" in top.memory["content"]
        assert top.reasons
    finally:
        os.unlink(db)


def test_hybrid_deterministic_ranking():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store = _seed_store(db)
        engine = HybridRelevanceEngine(store)
        engine.semantic = SemanticRetriever(store, MockEmbeddingProvider())
        r1 = engine.search("p", "WebSocket idle bug", limit=5)
        r2 = engine.search("p", "WebSocket idle bug", limit=5)
        assert [x.memory["id"] for x in r1] == [x.memory["id"] for x in r2]
    finally:
        os.unlink(db)


def test_keyword_only_when_semantic_unavailable():
    from packages.retrieval.embeddings import NullEmbeddingProvider

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store = _seed_store(db)
        engine = HybridRelevanceEngine(store)
        engine.semantic = SemanticRetriever(store, NullEmbeddingProvider())
        results = engine.search("p", "WebSocket reconnect", limit=5)
        assert all("keyword" in m.retrieval_methods for m in results)
    finally:
        os.unlink(db)


def test_provenance_preserved():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        store.add_project("p", "P", "", "")
        store.add_memory(
            "p", "We decided to use WebSockets", "permanent", 0.9,
            {
                "knowledge_type": "decision",
                "provenance": "Conversation abc, Message #3",
                "confidence": 0.75,
                "status": "active",
            },
        )
        engine = HybridRelevanceEngine(store)
        engine.semantic = SemanticRetriever(store, MockEmbeddingProvider())
        results = engine.search("p", "realtime messaging approach", limit=3)
        assert results[0].memory["metadata"]["provenance"] == "Conversation abc, Message #3"
    finally:
        os.unlink(db)
