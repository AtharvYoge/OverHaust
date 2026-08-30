"""Tests for project index retrieval integrated with unified search."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from packages.memory.memory_store import MemoryStore
from services.ingestion.index_store import ProjectIndexStore
from services.ingestion.project_indexer import PathSecurityError
from packages.retrieval.index_retrieval import (
    search_index_keyword,
    search_index_records,
    read_indexed_snippet,
)
from packages.context.retrieval import search_project_knowledge, merge_scored_results
from packages.context.relevance import ScoredMemory


from packages.retrieval.test_fixtures import make_kot_tree


def _setup_kot_index(db_path: str):
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    make_kot_tree(root)
    store = MemoryStore(db_path)
    store.add_project("labkot", "LabKOT", "", str(root))
    idx_store = ProjectIndexStore(store)
    index, _ = idx_store.sync_project("labkot", str(root))
    return store, index, str(root)


def test_index_keyword_finds_kot_file():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store, index, _ = _setup_kot_index(db)
        hits = search_index_keyword("labkot", "Where is the KOT generated?", index)
        paths = [
            (h.memory.get("metadata") or {}).get("file_path", "")
            for h in hits
        ]
        assert any("kot_generator" in p for p in paths)
    finally:
        os.unlink(db)


def test_index_keyword_finds_order_flow():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store, index, _ = _setup_kot_index(db)
        hits = search_index_keyword("labkot", "order marked ready", index)
        paths = [(h.memory.get("metadata") or {}).get("file_path", "") for h in hits]
        assert any("order_flow" in p for p in paths)
    finally:
        os.unlink(db)


def test_index_excludes_irrelevant():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store, index, _ = _setup_kot_index(db)
        hits = search_index_keyword("labkot", "KOT generated kitchen", index, limit=5)
        paths = [(h.memory.get("metadata") or {}).get("file_path", "") for h in hits]
        assert not any("marketing" in p for p in paths)
    finally:
        os.unlink(db)


def test_index_symbol_hit():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store, index, _ = _setup_kot_index(db)
        hits = search_index_keyword("labkot", "notifyKitchen", index)
        assert hits
        top_meta = hits[0].memory.get("metadata") or {}
        assert top_meta.get("symbol_name") == "notifyKitchen" or "notifyKitchen" in hits[0].memory.get("content", "")
        if top_meta.get("record_type") == "indexed_symbol":
            assert top_meta.get("symbol_line", 0) > 0
    finally:
        os.unlink(db)


def test_keyword_only_no_index_embeddings():
    os.environ["OVERHAUST_EMBEDDINGS"] = "0"
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store, index, _ = _setup_kot_index(db)
        hits = search_index_records("labkot", "database connection configured", index)
        paths = [(h.memory.get("metadata") or {}).get("file_path", "") for h in hits]
        assert any("database" in p for p in paths)
        assert all("index_keyword" in m for h in hits for m in h.retrieval_methods)
    finally:
        os.unlink(db)


@pytest.mark.embeddings
def test_index_semantic_paraphrase():
    os.environ["OVERHAUST_EMBEDDINGS"] = "1"
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store, index, _ = _setup_kot_index(db)
        from packages.retrieval.index_retrieval import search_index_hybrid
        hits = search_index_hybrid("labkot", "kitchen ticket printing", index, limit=5)
        paths = [(h.memory.get("metadata") or {}).get("file_path", "") for h in hits]
        assert any("kot_generator" in p for p in paths)
    finally:
        os.environ["OVERHAUST_EMBEDDINGS"] = "0"
        os.unlink(db)


def test_path_containment_blocks_escape():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_kot_tree(root)
        snippet = read_indexed_snippet(str(root), "../../etc/passwd")
        assert snippet is None


def test_missing_index_returns_empty():
    os.environ["OVERHAUST_EMBEDDINGS"] = "0"
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        store.add_project("empty", "Empty", "", "")
        store.add_memory("empty", "Some stored memory about auth", "permanent", 0.8)
        results = search_project_knowledge("empty", "auth", memory_store=store)
        assert len(results) == 1
        assert results[0].get("record_type", "memory") == "memory"
    finally:
        os.unlink(db)


def test_merge_with_memory_results():
    mem = {
        "id": "mem1", "content": "We decided kitchen uses WebSockets",
        "metadata": {"knowledge_type": "decision"},
    }
    idx_mem = {
        "id": "index:file:abc",
        "content": "File src/kitchen/kot_generator.ts defines generateKOT",
        "metadata": {"file_path": "src/kitchen/kot_generator.ts", "record_type": "indexed_file"},
    }
    memory_scored = [ScoredMemory(memory=mem, score=0.9, reasons=["kw"])]
    index_scored = [ScoredMemory(memory=idx_mem, score=0.7, reasons=["index"])]
    merged = merge_scored_results(memory_scored, index_scored, limit=5)
    assert len(merged) == 2
    assert merged[0].score == 0.9


def test_unified_search_returns_index_record_type():
    os.environ["OVERHAUST_EMBEDDINGS"] = "0"
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        _setup_kot_index(db)
        store = MemoryStore(db)
        results = search_project_knowledge(
            "labkot", "Where is the KOT generated?", memory_store=store, limit=5
        )
        assert results
        index_hits = [r for r in results if r.get("record_type") in ("indexed_file", "indexed_symbol")]
        assert index_hits
        assert any("kot_generator" in (r.get("metadata") or {}).get("file_path", "") for r in index_hits)
    finally:
        os.unlink(db)


def test_read_snippet_from_disk():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_kot_tree(root)
        snippet = read_indexed_snippet(str(root), "src/kitchen/kot_generator.ts")
        assert snippet is not None
        assert "generateKOT" in snippet
        assert "kot_generator.ts" in snippet
