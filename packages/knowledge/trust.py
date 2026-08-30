"""
Deterministic trust scoring — separate from relevance.

relevance = "Does this match the question?"
trust     = "Should we rely on it?"
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from packages.context.relevance import _parse_time, _INTENT_CATEGORY_BOOST
from packages.knowledge.schema import normalize_metadata
from packages.knowledge.provenance import format_provenance


STATUS_FACTORS = {
    "active": 1.0,
    "stale": 0.4,
    "resolved": 0.6,
    "superseded": 0.0,
}

TRUST_MIN_DEFAULT = 0.3


@dataclass
class TrustResult:
    score: float
    status: str
    confidence: Optional[float]
    fresh: bool
    reasons: List[str] = field(default_factory=list)
    include_in_context: bool = True
    provenance_display: str = ""


def _freshness(updated_at: str, now: datetime) -> float:
    ts = _parse_time(str(updated_at or ""))
    if not ts:
        return 0.5
    age_days = max((now - ts).total_seconds() / 86400.0, 0.0)
    return math.exp(-age_days / 30.0)


def _provenance_quality(meta: Dict[str, Any]) -> float:
    prov = meta.get("provenance")
    ref = meta.get("source_ref")
    if prov and ref:
        return 1.0
    if prov or ref:
        return 0.7
    return 0.5


def _query_intent_boosts(q_lower: str) -> Dict[str, float]:
    boosts: Dict[str, float] = {}
    for word in q_lower.split():
        w = word.strip("?.,!")
        if w in _INTENT_CATEGORY_BOOST:
            for cat, b in _INTENT_CATEGORY_BOOST[w].items():
                boosts[cat] = max(boosts.get(cat, 1.0), b)
    return boosts


def _is_fix_intent(q_lower: str) -> bool:
    return any(w in q_lower for w in ("fix", "bug", "error", "broken", "issue", "problem"))


def compute_trust(
    memory: Dict[str, Any],
    query: str = "",
    trust_min: float = TRUST_MIN_DEFAULT,
) -> TrustResult:
    """Compute explainable trust for one memory."""
    meta = normalize_metadata(memory.get("metadata"))
    status = meta["status"]
    now = datetime.now(timezone.utc)
    freshness = _freshness(memory.get("updated_at", ""), now)
    prov_q = _provenance_quality(meta)
    status_factor = STATUS_FACTORS.get(status, 0.5)

    confidence = meta.get("confidence")
    confidence_val = float(confidence) if confidence is not None else 0.5
    confidence_for_formula = confidence_val

    reasons: List[str] = []
    if confidence is None:
        reasons.append("confidence not recorded (using neutral 0.5 for scoring)")

    trust = (
        0.35 * confidence_for_formula
        + 0.25 * freshness
        + 0.25 * prov_q
        + 0.15 * status_factor
    )
    trust = round(max(0.0, min(1.0, trust)), 4)

    include = True
    if status == "superseded":
        include = False
        reasons.append("excluded: superseded by newer knowledge")

    q_lower = (query or "").lower()
    ktype = str(meta.get("knowledge_type", ""))
    if status == "resolved" and _is_fix_intent(q_lower):
        if ktype in ("resolved_issue", "issue") or "resolved" in (memory.get("content") or "").lower()[:20]:
            include = False
            reasons.append("excluded: resolved issue (fix/bug query)")

    if status == "stale" and "stale_info" not in _query_intent_boosts(q_lower):
        reasons.append("demoted: stale knowledge")

    if trust < trust_min:
        reasons.append(f"low trust ({trust})")

    provenance_display = format_provenance(meta)

    return TrustResult(
        score=trust,
        status=status,
        confidence=confidence if confidence is not None else None,
        fresh=freshness >= 0.7,
        reasons=reasons,
        include_in_context=include,
        provenance_display=provenance_display,
    )


def apply_trust_to_scored(
    scored: List[Any],
    query: str,
    trust_min: float = TRUST_MIN_DEFAULT,
) -> List[Any]:
    """
    Apply trust to ScoredMemory list: filter superseded, keep sole weak evidence.

    Relevance score (sm.score) is never modified.
    """
    if not scored:
        return []

    enriched = []
    for sm in scored:
        tr = compute_trust(sm.memory, query, trust_min)
        sm.trust_score = tr.score
        sm.trust_reasons = list(tr.reasons)
        sm.trust_status = tr.status
        sm.provenance_display = tr.provenance_display
        sm.trust_include = tr.include_in_context
        enriched.append(sm)

    included = [sm for sm in enriched if sm.trust_include]
    excluded = [sm for sm in enriched if not sm.trust_include]

    # Low-trust but only available evidence
    if not included and enriched:
        best = max(enriched, key=lambda s: s.score)
        best.trust_include = True
        if "Low confidence — only available source" not in best.trust_reasons:
            best.trust_reasons.append("Low confidence — only available source")
        included = [best]

    included.sort(key=lambda s: s.score, reverse=True)
    return included
