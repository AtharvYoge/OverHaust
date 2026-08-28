"""Tests for unified retrieval abstraction."""
import os
import sys
import tempfile

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from packages.memory.memory_store import MemoryStore
from packages.context.retrieval import (
    search_project_knowledge,
    format_scored_results,
    get_relevance_engine,
)
from packages.context.relevance import LayeredRelevanceEngine, ScoredMemory


def test_unified_search_matches_relevance_engine():
    os.environ["OVERHAUST_EMBEDDINGS"] = "0"
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        store.add_project("u-p", "U", "", "")
        store.add_memory("u-p", "WebSocket reconnect bug is open", "task", 0.85,
                         {"knowledge_type": "open_issue", "status": "active"})
        store.add_memory("u-p", "Unrelated marketing copy", "temporary", 0.1, {})

        unified = search_project_knowledge("u-p", "WebSocket reconnect", memory_store=store)
        engine = LayeredRelevanceEngine(store)
        raw = engine.search("u-p", "WebSocket reconnect", limit=10)
        formatted = format_scored_results(raw)

        assert len(unified) == len(formatted)
        assert unified[0]["score"] == formatted[0]["score"]
        assert "relevance" in unified[0]["metadata"]
        assert unified[0]["reasons"]
        assert unified[0]["retrieval_methods"] == ["keyword"]
    finally:
        os.unlink(db)


def test_disabled_embeddings_uses_keyword_engine():
    os.environ["OVERHAUST_EMBEDDINGS"] = "0"
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        engine = get_relevance_engine(store)
        assert type(engine).__name__ == "LayeredRelevanceEngine"
    finally:
        os.unlink(db)


def test_format_scored_results_includes_methods():
    mem = {"id": "1", "content": "test", "metadata": {}}
    scored = [ScoredMemory(
        memory=mem, score=0.5, reasons=["kw"],
        retrieval_methods=["keyword", "semantic"],
    )]
    out = format_scored_results(scored)
    assert out[0]["retrieval_methods"] == ["keyword", "semantic"]
    assert out[0]["metadata"]["relevance"]["methods"] == ["keyword", "semantic"]
