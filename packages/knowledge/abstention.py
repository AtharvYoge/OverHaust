"""
Evidence-aware abstention — no pretend certainty when evidence is weak.
"""

from typing import Any, Dict, List

TRUST_SUFFICIENT = 0.55
RELEVANCE_SUFFICIENT = 0.15


def assess_evidence(scored_trusted: List[Any], query: str = "") -> Dict[str, Any]:
    """
    Decide if retrieved evidence is sufficient for context assembly.

    Returns:
      insufficient_evidence: bool
      evidence_note: str (user-friendly)
    """
    if not scored_trusted:
        return {
            "insufficient_evidence": True,
            "evidence_note": "Needs more information — no project knowledge matched this task.",
        }

    top = scored_trusted[0]
    trust = getattr(top, "trust_score", None) or 0.0
    relevance = getattr(top, "score", 0.0)

    low_trust_only = (
        trust < TRUST_SUFFICIENT
        and all(
            (getattr(s, "trust_score", 0) or 0) < TRUST_SUFFICIENT
            for s in scored_trusted
        )
    )

    if relevance < RELEVANCE_SUFFICIENT:
        return {
            "insufficient_evidence": True,
            "evidence_note": "Needs more information — nothing relevant was found in project memory.",
        }

    if low_trust_only:
        note = "Low confidence — only available source"
        if any("Low confidence" in r for r in getattr(top, "trust_reasons", [])):
            note = "Low confidence — only available source"
        return {
            "insufficient_evidence": False,
            "evidence_note": note,
        }

    return {
        "insufficient_evidence": False,
        "evidence_note": "",
    }
