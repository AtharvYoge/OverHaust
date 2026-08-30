"""Tests for knowledge trust scoring."""
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from packages.knowledge.trust import compute_trust, STATUS_FACTORS
from packages.knowledge.schema import normalize_metadata


def _mem(content, meta=None, updated_at=None):
    return {
        "id": "m1",
        "content": content,
        "updated_at": updated_at or datetime.now(timezone.utc).isoformat(),
        "metadata": meta or {},
    }


def test_status_factors():
    assert STATUS_FACTORS["active"] == 1.0
    assert STATUS_FACTORS["superseded"] == 0.0


def test_superseded_excluded():
    tr = compute_trust(_mem("old auth", {"status": "superseded", "confidence": 0.9}))
    assert tr.include_in_context is False
    assert any("superseded" in r for r in tr.reasons)


def test_high_confidence_higher_trust():
    high = compute_trust(_mem("x", {"confidence": 0.95, "status": "active", "provenance": "User", "source_ref": "User"}))
    low = compute_trust(_mem("x", {"confidence": 0.2, "status": "active", "provenance": "User", "source_ref": "User"}))
    assert high.score > low.score


def test_provenance_quality():
    full = compute_trust(_mem("x", {"provenance": "Conversation abc", "source_ref": "Conversation abc", "confidence": 0.5}))
    none = compute_trust(_mem("x", {"confidence": 0.5}))
    assert full.score > none.score


def test_resolved_excluded_on_fix_query():
    tr = compute_trust(
        _mem("RESOLVED: reconnect bug", {"status": "resolved", "knowledge_type": "resolved_issue", "confidence": 0.8}),
        query="fix reconnect bug",
    )
    assert tr.include_in_context is False


def test_confidence_not_fabricated():
    tr = compute_trust(_mem("x", {"status": "active"}))
    assert tr.confidence is None
    assert any("not recorded" in r for r in tr.reasons)


def test_stale_lower_trust():
    old = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    tr = compute_trust(_mem("x", {"status": "stale", "confidence": 0.5}, updated_at=old))
    active = compute_trust(_mem("x", {"status": "active", "confidence": 0.5}))
    assert tr.score < active.score
