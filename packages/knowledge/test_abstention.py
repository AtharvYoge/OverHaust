"""Tests for evidence abstention."""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from packages.knowledge.abstention import assess_evidence


@dataclass
class FakeScored:
    score: float
    trust_score: Optional[float] = None
    trust_reasons: List[str] = field(default_factory=list)
    memory: Dict[str, Any] = field(default_factory=dict)


def test_insufficient_when_empty():
    r = assess_evidence([], "anything")
    assert r["insufficient_evidence"] is True
    assert "Needs more information" in r["evidence_note"]


def test_sufficient_with_good_evidence():
    r = assess_evidence([FakeScored(score=0.8, trust_score=0.7)], "websocket")
    assert r["insufficient_evidence"] is False
    assert r["evidence_note"] == ""


def test_low_trust_only_source():
    r = assess_evidence(
        [FakeScored(score=0.5, trust_score=0.3, trust_reasons=["Low confidence — only available source"])],
        "auth",
    )
    assert r["insufficient_evidence"] is False
    assert "Low confidence" in r["evidence_note"]
