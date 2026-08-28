"""Tests for embedding providers."""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from packages.retrieval.embeddings import (
    NullEmbeddingProvider,
    get_embedding_provider,
)


def test_null_provider_unavailable():
    os.environ["OVERHAUST_EMBEDDINGS"] = "0"
    p = NullEmbeddingProvider()
    assert not p.is_available
    assert p.embed_query("hello") == []
    assert p.embed_texts(["a"]) == []


def test_get_embedding_provider_disabled():
    os.environ["OVERHAUST_EMBEDDINGS"] = "0"
    p = get_embedding_provider()
    assert not p.is_available


def test_fastembed_provider_optional():
    """Runs only when fastembed installed and embeddings enabled."""
    import pytest
    pytest.importorskip("fastembed")
    os.environ["OVERHAUST_EMBEDDINGS"] = "1"
    p = get_embedding_provider()
    if not p.is_available:
        pytest.skip("fastembed model could not load")
    vec = p.embed_query("test query for embeddings")
    assert len(vec) > 0
    assert all(isinstance(x, float) for x in vec[:5])


test_fastembed_provider_optional.__pytestmark__ = __import__("pytest").mark.embeddings
