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
        "keyword": _f("OVERHAUST_HYBRID_KEYWORD_WEIGHT", 0.50),
        "semantic": _f("OVERHAUST_HYBRID_SEMANTIC_WEIGHT", 0.35),
        "confidence": _f("OVERHAUST_HYBRID_CONFIDENCE_WEIGHT", 0.10),
        "freshness": _f("OVERHAUST_HYBRID_FRESHNESS_WEIGHT", 0.05),
    }
