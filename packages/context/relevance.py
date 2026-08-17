"""
Layered relevance engine for Overhaust.

Replaces naive SQL LIKE with a scored, layered retrieval system:

  1. exact phrase match
  2. keyword overlap (weighted by rarity-ish heuristics)
  3. metadata matches (knowledge_type, source_type, role)
  4. category boosts relevant to the query intent
  5. memory importance
  6. recency

Exposes a single interface — search_knowledge(project_id, query) — so a
future semantic/vector implementation can replace this without touching
callers.
"""

import re
import math
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Protocol

logger = logging.getLogger(__name__)


@dataclass
class ScoredMemory:
    """A memory with its relevance score and explanation."""
    memory: Dict[str, Any]
    score: float
    reasons: List[str]


class RelevanceEngine(Protocol):
    """Interface every retrieval implementation must satisfy."""
    def search(self, project_id: str, query: str, limit: int = 10) -> List[ScoredMemory]:
        ...


_STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of',
    'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have',
    'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
    'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'it',
    'its', 'i', 'we', 'you', 'they', 'he', 'she', 'me', 'my', 'our', 'your',
    'what', 'how', 'why', 'when', 'where', 'which', 'who', 'whom', 'there',
    'here', 'so', 'if', 'then', 'than', 'too', 'very', 'just', 'about',
    # intent words: they steer category boosts, not content matching
    'fix', 'bug', 'issue', 'error', 'problem', 'add', 'implement', 'build',
    'create', 'make', 'update', 'change', 'remove', 'delete', 'get', 'set',
}

_INTENT_CATEGORY_BOOST = {
    # query intent -> knowledge categories that matter most
    'fix':      {'open_issue': 1.4, 'decision': 1.2, 'current_task': 1.2, 'resolved_issue': 0.3, 'stale_info': 0.4},
    'bug':      {'open_issue': 1.4, 'decision': 1.2, 'current_task': 1.2, 'resolved_issue': 0.3, 'stale_info': 0.4},
    'error':    {'open_issue': 1.4, 'decision': 1.2, 'current_task': 1.2, 'stale_info': 0.4},
    'broken':   {'open_issue': 1.4, 'decision': 1.2, 'current_task': 1.2, 'stale_info': 0.4},
    'decided':  {'decision': 1.5, 'permanent_knowledge': 1.1},
    'decision': {'decision': 1.5, 'permanent_knowledge': 1.1},
    'why':      {'decision': 1.4, 'permanent_knowledge': 1.2},
    'architecture': {'permanent_knowledge': 1.5, 'decision': 1.2},
    'stack':    {'permanent_knowledge': 1.5, 'decision': 1.2},
    'currently':{'current_task': 1.5, 'open_issue': 1.2},
    'working':  {'current_task': 1.5, 'open_issue': 1.2},
    'implement':{'current_task': 1.3, 'permanent_knowledge': 1.2, 'decision': 1.1},
    'add':      {'current_task': 1.3, 'permanent_knowledge': 1.2, 'decision': 1.1},
    'old':      {'stale_info': 1.5, 'resolved_issue': 1.1},
    'previous': {'stale_info': 1.5, 'resolved_issue': 1.1},
}


def _keywords(text: str) -> List[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_+#.]{1,}", text.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 2]


def _stem_variants(word: str) -> set:
    """Cheap plural/singular tolerance without a stemmer dependency."""
    variants = {word}
    if word.endswith('s') and len(word) > 3:
        variants.add(word[:-1])
        if word.endswith('es'):
            variants.add(word[:-2])
    else:
        variants.add(word + 's')
    return variants


def _parse_time(ts: str) -> Optional[datetime]:
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


class LayeredRelevanceEngine:
    """
    Default retrieval implementation: deterministic layered scoring over
    the memory store. No external infra; swap for a vector engine later
    by providing another RelevanceEngine implementation.
    """

    def __init__(self, memory_store, max_candidates: int = 200):
        self.store = memory_store
        self.max_candidates = max_candidates

    def search(self, project_id: str, query: str, limit: int = 10) -> List[ScoredMemory]:
        # Fetch a candidate pool (recent + important), then score in Python
        pool = self.store.get_project_memories(
            project_id, min_importance=0.0, limit=self.max_candidates)
        if not pool:
            return []

        q = query.strip()
        q_lower = q.lower()
        q_keywords = set(_keywords(q))
        intent_boosts = self._intent_boosts(q_lower)
        now = datetime.now(timezone.utc)

        scored: List[ScoredMemory] = []
        for mem in pool:
            score, reasons = self._score(mem, q_lower, q_keywords, intent_boosts, now)
            if score > 0.05:
                scored.append(ScoredMemory(memory=mem, score=round(score, 4), reasons=reasons))

        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:limit]

    # ------------------------------------------------------------------

    def _intent_boosts(self, q_lower: str) -> Dict[str, float]:
        boosts: Dict[str, float] = {}
        for word in q_lower.split():
            w = word.strip('?.,!')
            if w in _INTENT_CATEGORY_BOOST:
                for cat, b in _INTENT_CATEGORY_BOOST[w].items():
                    boosts[cat] = max(boosts.get(cat, 1.0), b)
        return boosts

    def _score(self, mem: Dict[str, Any], q_lower: str, q_keywords: set,
               intent_boosts: Dict[str, float], now: datetime):
        content = (mem.get('content') or '').lower()
        meta = mem.get('metadata') or {}
        reasons: List[str] = []
        score = 0.0

        # Layer 1: exact phrase
        if q_lower and q_lower in content:
            score += 2.0
            reasons.append('exact phrase match')

        # Layer 2: keyword overlap with cheap plural tolerance (log-scaled)
        if q_keywords:
            content_words = set(_keywords(content))
            overlap = q_keywords & content_words
            # also match plural/singular variants
            for qk in q_keywords - overlap:
                if _stem_variants(qk) & content_words:
                    overlap = overlap | {qk}
            if overlap:
                kw_score = 0.6 + math.log1p(len(overlap))
                score += kw_score
                reasons.append(f'keywords: {sorted(overlap)[:6]}')

        # Layer 3: metadata matches (knowledge_type words in query)
        ktype = str(meta.get('knowledge_type', ''))
        if ktype and any(part in q_lower for part in ktype.replace('_', ' ').split()):
            score += 0.5
            reasons.append(f'metadata type: {ktype}')

        # Layer 4: intent category boost. When the query intent targets a
        # category (e.g. "old approach" -> stale_info), memories in that
        # category surface even with zero keyword overlap. Boost values
        # below 1.0 demote (e.g. resolved issues on a fresh bug query).
        ktype_for_floor = str(meta.get('knowledge_type', ''))
        intent_floor = intent_boosts.get(ktype_for_floor, 1.0)
        if score == 0.0 and intent_floor > 1.2:
            score += 0.4 * intent_floor
            reasons.append(f'intent match: {ktype_for_floor}')

        boost = intent_boosts.get(ktype, 1.0)
        if boost != 1.0 and score > 0:
            score *= boost
            if boost > 1.0:
                reasons.append(f'intent boost x{boost} ({ktype})')
            else:
                reasons.append(f'intent demote x{boost} ({ktype})')

        # Stale/resolved demotion by default
        status = str(meta.get('status', 'active'))
        if status == 'stale' and 'stale_info' not in intent_boosts:
            score *= 0.5
            reasons.append('demoted: stale')
        elif status == 'resolved' and 'resolved_issue' not in intent_boosts:
            score *= 0.75
            reasons.append('demoted: resolved')
        elif status == 'rejected':
            score *= 0.8
            reasons.append('demoted: rejected approach')

        # Layer 5: importance
        imp = float(mem.get('importance_score', 0.5))
        score *= (0.5 + imp)  # importance in [0,1] -> multiplier [0.5,1.5]
        reasons.append(f'importance {imp}')

        # Layer 6: recency (half-life ~30 days)
        ts = _parse_time(str(mem.get('updated_at', '')))
        if ts:
            age_days = max((now - ts).total_seconds() / 86400.0, 0.0)
            recency = math.exp(-age_days / 30.0)
            score *= (0.7 + 0.3 * recency)

        return score, reasons


def search_knowledge(project_id: str, query: str, memory_store=None,
                     engine: Optional[RelevanceEngine] = None,
                     limit: int = 10) -> List[ScoredMemory]:
    """Module-level convenience: the single retrieval entry point."""
    if engine is None:
        if memory_store is None:
            from packages.memory.memory_store import get_memory_store
            memory_store = get_memory_store()
        engine = LayeredRelevanceEngine(memory_store)
    return engine.search(project_id, query, limit=limit)
