"""
Hybrid relevance engine: keyword + semantic score fusion.
"""

import math
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from packages.context.relevance import (
    LayeredRelevanceEngine,
    ScoredMemory,
    _parse_time,
)
from packages.retrieval.semantic import SemanticRetriever
from packages.retrieval.embeddings import get_embedding_provider
from packages.shared.config import get_hybrid_weights

logger = logging.getLogger(__name__)


class HybridRelevanceEngine:
    """
    Combines LayeredRelevanceEngine (keyword) with SemanticRetriever (embeddings).
    Implements RelevanceEngine protocol.
    """

    def __init__(self, memory_store, candidate_limit: int = 50):
        self.store = memory_store
        self.keyword_engine = LayeredRelevanceEngine(memory_store)
        self.semantic = SemanticRetriever(memory_store, get_embedding_provider())
        self.candidate_limit = candidate_limit
        self.weights = get_hybrid_weights()

    def search(self, project_id: str, query: str, limit: int = 10) -> List[ScoredMemory]:
        kw_results = self.keyword_engine.search(
            project_id, query, limit=self.candidate_limit
        )
        sem_results = self.semantic.search(
            project_id, query, limit=self.candidate_limit
        )

        merged: Dict[str, Dict[str, Any]] = {}

        max_kw = max((r.score for r in kw_results), default=0.0) or 1.0

        for kr in kw_results:
            mid = kr.memory["id"]
            merged[mid] = {
                "memory": kr.memory,
                "kw_score": kr.score,
                "kw_norm": kr.score / max_kw,
                "sem_score": 0.0,
                "kw_reasons": list(kr.reasons),
                "sem_reasons": [],
                "methods": ["keyword"],
            }

        for sr in sem_results:
            mid = sr.memory["id"]
            if mid not in merged:
                merged[mid] = {
                    "memory": sr.memory,
                    "kw_score": 0.0,
                    "kw_norm": 0.0,
                    "sem_score": sr.similarity,
                    "kw_reasons": [],
                    "sem_reasons": list(sr.reasons),
                    "methods": ["semantic"],
                }
            else:
                merged[mid]["sem_score"] = sr.similarity
                merged[mid]["sem_reasons"] = list(sr.reasons)
                if "semantic" not in merged[mid]["methods"]:
                    merged[mid]["methods"].append("semantic")

        if not merged:
            return []

        w = self.weights
        now = datetime.now(timezone.utc)
        scored: List[ScoredMemory] = []

        for entry in merged.values():
            mem = entry["memory"]
            freshness = self._freshness_factor(mem, now)

            final = (
                w["keyword"] * entry["kw_norm"]
                + w["semantic"] * entry["sem_score"]
                + w["freshness"] * freshness
            )

            reasons: List[str] = []
            if entry["kw_norm"] > 0:
                reasons.extend(entry["kw_reasons"])
            if entry["sem_score"] > 0:
                reasons.extend(entry["sem_reasons"])
            reasons.append(f"freshness {freshness:.2f}")

            if final > 0.05:
                scored.append(ScoredMemory(
                    memory=mem,
                    score=round(final, 4),
                    reasons=reasons,
                    retrieval_methods=list(entry["methods"]),
                ))

        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:limit]

    def _freshness_factor(self, mem: Dict[str, Any], now: datetime) -> float:
        ts = _parse_time(str(mem.get("updated_at", "")))
        if not ts:
            return 0.5
        age_days = max((now - ts).total_seconds() / 86400.0, 0.0)
        return math.exp(-age_days / 30.0)
