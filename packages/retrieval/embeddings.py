"""
Embedding provider abstraction for Overhaust hybrid retrieval.

Local-first: fastembed when OVERHAUST_EMBEDDINGS=1, no API keys required.
"""

from typing import List, Protocol, runtime_checkable, Optional
import logging

logger = logging.getLogger(__name__)


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Minimal interface for text embedding backends."""

    @property
    def model_id(self) -> str:
        ...

    @property
    def is_available(self) -> bool:
        ...

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        ...

    def embed_query(self, query: str) -> List[float]:
        ...


class NullEmbeddingProvider:
    """Disabled provider — semantic path returns no candidates."""

    model_id = "none"

    @property
    def is_available(self) -> bool:
        return False

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return []

    def embed_query(self, query: str) -> List[float]:
        return []


class FastEmbedProvider:
    """Local ONNX embeddings via fastembed (no API key)."""

    def __init__(self, model_id: str):
        self._model_id = model_id
        self._model = None

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def is_available(self) -> bool:
        try:
            self._ensure_model()
            return True
        except ImportError:
            return False

    def _ensure_model(self):
        if self._model is not None:
            return
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise ImportError(
                "fastembed is required when OVERHAUST_EMBEDDINGS=1. "
                "Install with: pip install fastembed"
            ) from exc
        self._model = TextEmbedding(model_name=self._model_id)
        logger.info("Loaded embedding model: %s", self._model_id)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        self._ensure_model()
        return [list(float(v) for v in vec) for vec in self._model.embed(texts)]

    def embed_query(self, query: str) -> List[float]:
        if not query.strip():
            return []
        vecs = self.embed_texts([query])
        return vecs[0] if vecs else []


_provider_cache: Optional[EmbeddingProvider] = None
_provider_cache_key: Optional[tuple] = None


def get_embedding_provider() -> EmbeddingProvider:
    """Return the configured embedding provider (singleton per process)."""
    from packages.shared.config import embeddings_enabled, get_embedding_model

    key = (embeddings_enabled(), get_embedding_model())
    global _provider_cache, _provider_cache_key
    if _provider_cache is not None and _provider_cache_key == key:
        return _provider_cache

    if not embeddings_enabled():
        _provider_cache = NullEmbeddingProvider()
    else:
        _provider_cache = FastEmbedProvider(get_embedding_model())
    _provider_cache_key = key
    return _provider_cache


def reset_embedding_provider() -> None:
    """Clear cached provider (for tests)."""
    global _provider_cache, _provider_cache_key
    _provider_cache = None
    _provider_cache_key = None
