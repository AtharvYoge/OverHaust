"""
Semantic retrieval via local embeddings and cosine similarity.
"""

import math
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

from packages.context.relevance import _parse_time, _INTENT_CATEGORY_BOOST
from packages.retrieval.embeddings import EmbeddingProvider, get_embedding_provider
from packages.retrieval.embedding_store import EmbeddingStore

logger = logging.getLogger(__name__)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Pure-Python cosine similarity in [0, 1] (negative clamped to 0)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


@dataclass
class SemanticHit:
    """One semantic retrieval result."""
    memory: Dict[str, Any]
    similarity: float
    reasons: List[str]


class SemanticRetriever:
    """Top-k semantic search over persisted memory embeddings."""

    def __init__(
        self,
        memory_store,
        provider: Optional[EmbeddingProvider] = None,
        max_candidates: int = 200,
    ):
        self.store = memory_store
        self.provider = provider or get_embedding_provider()
        self.embedding_store = EmbeddingStore(memory_store)
        self.max_candidates = max_candidates

    def search(
        self, project_id: str, query: str, limit: int = 50
    ) -> List[SemanticHit]:
        if not self.provider.is_available:
            return []

        query_vec = self.provider.embed_query(query)
        if not query_vec:
            return []

        pool = self.store.get_project_memories(
            project_id, min_importance=0.0, limit=self.max_candidates
        )
        if not pool:
            return []

        model_id = self.provider.model_id
        q_lower = query.strip().lower()
        intent_boosts = self._intent_boosts(q_lower)
        now = datetime.now(timezone.utc)

        hits: List[SemanticHit] = []
        for mem in pool:
            mem_id = mem["id"]
            content_hash = mem.get("source_hash") or ""
            content = mem.get("content") or ""

            stored = self.embedding_store.get(mem_id, model_id)
            if stored is None or stored[0] != content_hash:
                try:
                    vec = self.provider.embed_texts([content])[0]
                    self.embedding_store.upsert(
                        mem_id, project_id, model_id, content_hash, vec
                    )
                except Exception as exc:
                    logger.warning("Embed failed for %s: %s", mem_id, exc)
                    continue
            else:
                vec = stored[1]

            sim = cosine_similarity(query_vec, vec)
            if sim <= 0.05:
                continue

            sim, reasons = self._apply_metadata_adjustments(
                mem, sim, intent_boosts, now
            )
            reasons.insert(0, f"semantic similarity: {sim:.3f}")
            hits.append(SemanticHit(memory=mem, similarity=round(sim, 4), reasons=reasons))

        hits.sort(key=lambda h: h.similarity, reverse=True)
        return hits[:limit]

    def _intent_boosts(self, q_lower: str) -> Dict[str, float]:
        boosts: Dict[str, float] = {}
        for word in q_lower.split():
            w = word.strip("?.,!")
            if w in _INTENT_CATEGORY_BOOST:
                for cat, b in _INTENT_CATEGORY_BOOST[w].items():
                    boosts[cat] = max(boosts.get(cat, 1.0), b)
        return boosts

    def _apply_metadata_adjustments(
        self,
        mem: Dict[str, Any],
        sim: float,
        intent_boosts: Dict[str, float],
        now: datetime,
    ) -> Tuple[float, List[str]]:
        meta = mem.get("metadata") or {}
        reasons: List[str] = []
        ktype = str(meta.get("knowledge_type", ""))
        status = str(meta.get("status", "active"))

        boost = intent_boosts.get(ktype, 1.0)
        if boost != 1.0:
            sim *= boost
            if boost > 1.0:
                reasons.append(f"intent boost x{boost} ({ktype})")
            else:
                reasons.append(f"intent demote x{boost} ({ktype})")

        if status == "stale" and "stale_info" not in intent_boosts:
            sim *= 0.5
            reasons.append("demoted: stale")
        elif status == "resolved" and "resolved_issue" not in intent_boosts:
            sim *= 0.75
            reasons.append("demoted: resolved")
        elif status == "rejected":
            sim *= 0.8
            reasons.append("demoted: rejected approach")

        ts = _parse_time(str(mem.get("updated_at", "")))
        if ts:
            age_days = max((now - ts).total_seconds() / 86400.0, 0.0)
            recency = math.exp(-age_days / 30.0)
            sim *= (0.7 + 0.3 * recency)

        return sim, reasons
