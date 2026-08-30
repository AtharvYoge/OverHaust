"""
Knowledge metadata schema and normalization for Overhaust.

All versioning/trust fields live in memory metadata JSON (backward compatible).
"""

from typing import Any, Dict, Optional

VALID_STATUSES = frozenset({"active", "stale", "resolved", "superseded"})
VALID_SOURCE_TYPES = frozenset({"conversation", "file", "symbol", "user", "memory"})
VALID_AUTHORITIES = frozenset({"ingestion", "user", "indexer", "agent"})


def normalize_metadata(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Apply defaults and coerce knowledge metadata fields."""
    m = dict(meta or {})

    status = str(m.get("status", "active")).lower()
    if status not in VALID_STATUSES:
        status = "active"
    m["status"] = status

    m.setdefault("version", 1)
    m.setdefault("superseded_by", None)
    m.setdefault("supersedes", None)
    m.setdefault("authority", "ingestion")

    source_type = str(m.get("source_type", "conversation")).lower()
    if source_type not in VALID_SOURCE_TYPES:
        source_type = "memory"
    m["source_type"] = source_type

    if "source_ref" not in m or not m["source_ref"]:
        if m.get("provenance"):
            m["source_ref"] = m["provenance"]
        elif m.get("source_id"):
            m["source_ref"] = str(m["source_id"])

    if "provenance" not in m and m.get("source_ref"):
        m["provenance"] = str(m["source_ref"])

    if "confidence" in m and m["confidence"] is not None:
        m["confidence"] = float(m["confidence"])
    else:
        m["confidence"] = None  # not fabricated

    authority = str(m.get("authority", "ingestion")).lower()
    if authority not in VALID_AUTHORITIES:
        authority = "user"
    m["authority"] = authority

    return m


def bump_version(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Increment version when content changes."""
    m = normalize_metadata(meta)
    m["version"] = int(m.get("version", 1)) + 1
    return m
