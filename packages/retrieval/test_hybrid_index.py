"""Regression tests for hybrid index retrieval performance."""
import hashlib
import os
import sys
import tempfile
from pathlib import Path
from typing import List

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from packages.memory.memory_store import MemoryStore
from services.ingestion.index_store import ProjectIndexStore
from packages.retrieval.index_retrieval import (
    search_index_hybrid,
    search_index_semantic,
    search_index_keyword,
)
from packages.retrieval.embeddings import reset_embedding_provider, get_embedding_provider
from packages.retrieval.embedding_store import EmbeddingStore
from packages.context.retrieval import search_project_knowledge
from packages.retrieval.test_index_retrieval import make_kot_tree


class CountingProvider:
    model_id = "mock-counting"
    embed_calls = 0
    texts_embedded = 0
    document_texts_embedded = 0
    _in_query = False

    @property
    def is_available(self) -> bool:
        return True

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        CountingProvider.embed_calls += 1
        CountingProvider.texts_embedded += len(texts)
        if not CountingProvider._in_query:
            CountingProvider.document_texts_embedded += len(texts)
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            out.append([float(h[i % len(h)]) / 255.0 for i in range(8)])
        return out

    def embed_query(self, query: str) -> List[float]:
        CountingProvider._in_query = True
        try:
            return self.embed_texts([query])[0]
        finally:
            CountingProvider._in_query = False


@pytest.fixture(autouse=True)
def _reset_provider():
    CountingProvider.embed_calls = 0
    CountingProvider.texts_embedded = 0
    CountingProvider.document_texts_embedded = 0
    reset_embedding_provider()
    yield
    reset_embedding_provider()


def _kot_setup(db: str):
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    make_kot_tree(root)
    store = MemoryStore(db)
    store.add_project("labkot", "LabKOT", "", str(root))
    idx_store = ProjectIndexStore(store)
    index, _ = idx_store.sync_project("labkot", str(root))
    return store, index, tmp


def test_embedding_provider_singleton():
    os.environ["OVERHAUST_EMBEDDINGS"] = "1"
    reset_embedding_provider()
    p1 = get_embedding_provider()
    p2 = get_embedding_provider()
    assert p1 is p2


def test_index_semantic_reuses_stored_embeddings():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, tmp = _kot_setup(db)
        provider = CountingProvider()
        q = "kitchen order flow"
        search_index_semantic(
            "labkot", q, index, limit=5,
            provider=provider, memory_store=store,
        )
        embed_store = EmbeddingStore(store)
        stored_count = len(embed_store.list_for_project("labkot", provider.model_id))
        doc_embeds_first = CountingProvider.document_texts_embedded

        search_index_semantic(
            "labkot", q, index, limit=5,
            provider=provider, memory_store=store,
        )
        assert len(embed_store.list_for_project("labkot", provider.model_id)) == stored_count
        assert CountingProvider.document_texts_embedded == doc_embeds_first
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_unchanged_index_content_not_reembedded():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, tmp = _kot_setup(db)
        provider = CountingProvider()
        q = "KOT generated"
        search_index_semantic(
            "labkot", q, index, limit=5,
            provider=provider, memory_store=store,
        )
        embed_store = EmbeddingStore(store)
        rows_first = {
            r["memory_id"]: r["content_hash"]
            for r in embed_store.list_for_project("labkot", provider.model_id)
        }
        doc_embeds_first = CountingProvider.document_texts_embedded

        search_index_semantic(
            "labkot", q, index, limit=5,
            provider=provider, memory_store=store,
        )
        rows_second = {
            r["memory_id"]: r["content_hash"]
            for r in embed_store.list_for_project("labkot", provider.model_id)
        }
        assert rows_second == rows_first
        assert CountingProvider.document_texts_embedded == doc_embeds_first
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_hybrid_index_search_completes():
    os.environ["OVERHAUST_EMBEDDINGS"] = "1"
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, tmp = _kot_setup(db)
        provider = CountingProvider()
        results = search_index_hybrid(
            "labkot",
            "How does a food order reach the kitchen?",
            index,
            limit=5,
            provider=provider,
            memory_store=store,
        )
        assert isinstance(results, list)
        assert CountingProvider.document_texts_embedded < 500
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_unified_hybrid_search_with_index():
    os.environ["OVERHAUST_EMBEDDINGS"] = "1"
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, tmp = _kot_setup(db)
        reset_embedding_provider()
        results = search_project_knowledge(
            "labkot",
            "How does a food order reach the kitchen?",
            memory_store=store,
            limit=5,
        )
        assert isinstance(results, list)
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_keyword_hits_limit_semantic_candidates():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, tmp = _kot_setup(db)
        provider = CountingProvider()
        kw = search_index_keyword("labkot", "kitchen order", index, limit=24)
        assert len(kw) < 50
        search_index_semantic(
            "labkot", "kitchen order", index, limit=5,
            provider=provider, memory_store=store, keyword_hits=kw,
        )
        assert CountingProvider.document_texts_embedded <= len(kw)
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_cold_query_caps_file_level_candidates():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, tmp = _kot_setup(db)
        provider = CountingProvider()
        search_index_semantic(
            "labkot", "xyznonexistentquery123", index, limit=8,
            provider=provider, memory_store=store, keyword_hits=None,
        )
        assert CountingProvider.document_texts_embedded <= 100
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
