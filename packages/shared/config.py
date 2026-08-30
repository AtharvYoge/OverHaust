"""
Central configuration for Overhaust.

Reads documented environment variables with safe local-first defaults.
"""

import os
from pathlib import Path
from typing import List


def project_root() -> Path:
    """Repository root (packages/shared -> packages -> root)."""
    return Path(__file__).resolve().parents[2]


def get_db_path() -> str:
    """SQLite database file path."""
    env_path = os.getenv("OVERHAUST_DB_PATH")
    if env_path:
        return env_path
    return str(project_root() / "data" / "overhaust_memory.db")


def get_api_host() -> str:
    """API bind host."""
    return os.getenv("OVERHAUST_API_HOST", "0.0.0.0")


def get_api_port() -> int:
    """API listen port."""
    raw = os.getenv("OVERHAUST_API_PORT", "8000")
    try:
        return int(raw)
    except ValueError:
        return 8000


def get_allowed_origins() -> List[str]:
    """CORS allowed origins (comma-separated env or localhost defaults)."""
    raw = os.getenv("OVERHAUST_ALLOWED_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]


def get_default_model() -> str:
    """Default token-estimation model name."""
    return os.getenv("OVERHAUST_DEFAULT_MODEL", "gpt-4")


def embeddings_enabled() -> bool:
    """Whether hybrid semantic retrieval is enabled."""
    return os.getenv("OVERHAUST_EMBEDDINGS", "0").strip().lower() in ("1", "true", "yes")


def get_embedding_model() -> str:
    """fastembed model identifier for local embeddings."""
    return os.getenv("OVERHAUST_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")


def get_hybrid_weights() -> dict:
    """Score fusion weights for hybrid retrieval (must sum to ~1.0)."""
    def _f(name: str, default: float) -> float:
        raw = os.getenv(name, str(default))
        try:
            return float(raw)
        except ValueError:
            return default

    return {
        "keyword": _f("OVERHAUST_HYBRID_KEYWORD_WEIGHT", 0.55),
        "semantic": _f("OVERHAUST_HYBRID_SEMANTIC_WEIGHT", 0.40),
        "freshness": _f("OVERHAUST_HYBRID_FRESHNESS_WEIGHT", 0.05),
    }


def get_trust_min() -> float:
    """Minimum trust threshold for filtering (sole evidence may override)."""
    raw = os.getenv("OVERHAUST_TRUST_MIN", "0.3")
    try:
        return float(raw)
    except ValueError:
        return 0.3


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def get_index_search_limit() -> int:
    """Max index file/symbol hits per query."""
    return _int_env("OVERHAUST_INDEX_SEARCH_LIMIT", 8)


def get_index_snippet_max_lines() -> int:
    """Max lines read from disk when building file context."""
    return _int_env("OVERHAUST_INDEX_SNIPPET_MAX_LINES", 60)


def get_index_snippet_max_chars() -> int:
    """Max characters per file snippet in context."""
    return _int_env("OVERHAUST_INDEX_SNIPPET_MAX_CHARS", 8000)


def get_index_semantic_batch_size() -> int:
    """Batch size for index embedding generation."""
    return _int_env("OVERHAUST_INDEX_SEMANTIC_BATCH_SIZE", 32)


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        return float(raw)
    except ValueError:
        return default


def get_flow_seed_search_limit() -> int:
    """Max index hits considered for code-flow seed selection."""
    return _int_env("OVERHAUST_FLOW_SEED_SEARCH_LIMIT", 36)


def get_flow_beam_width() -> int:
    """Number of partial paths retained during code-flow beam search."""
    return _int_env("OVERHAUST_FLOW_BEAM_WIDTH", 4)


def get_flow_max_steps() -> int:
    """Max steps in a code-flow evidence path."""
    return _int_env("OVERHAUST_FLOW_MAX_STEPS", 6)


def get_flow_min_relevance() -> float:
    """Stop code-flow expansion when neighbor relevance drops below this (0–1)."""
    return _float_env("OVERHAUST_FLOW_MIN_RELEVANCE", 0.12)


def flow_read_calls_enabled() -> bool:
    """Whether to detect call edges by reading source files from disk."""
    return os.getenv("OVERHAUST_FLOW_READ_CALLS", "1").strip().lower() in ("1", "true", "yes")


def get_index_weak_kw_threshold() -> float:
    """Raw keyword score below which hybrid retrieval favors semantic."""
    return _float_env("OVERHAUST_INDEX_WEAK_KW_THRESHOLD", 2.5)


def get_index_generic_penalty() -> float:
    """Score multiplier for generic boilerplate symbol/path hits."""
    return _float_env("OVERHAUST_INDEX_GENERIC_PENALTY", 0.15)
