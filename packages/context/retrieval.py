"""
Unified retrieval entry point for Overhaust.

All search/context paths should route through this module so API, MCP,
agent, and context assembly share the same relevance scoring behavior.
"""

from typing import Dict, List, Optional, Any

from packages.context.relevance import (
    RelevanceEngine,
    ScoredMemory,
    LayeredRelevanceEngine,
    search_knowledge,
)


def format_scored_results(scored: List[ScoredMemory]) -> List[Dict[str, Any]]:
    """Convert scored memories to API-friendly dicts with explainable relevance."""
    results: List[Dict[str, Any]] = []
    for sm in scored:
        mem = dict(sm.memory)
        meta = dict(mem.get("metadata") or {})
        methods = list(sm.retrieval_methods) if sm.retrieval_methods else ["keyword"]
        meta["relevance"] = {
            "score": sm.score,
            "reasons": sm.reasons,
            "methods": methods,
        }
        mem["metadata"] = meta
        mem["score"] = sm.score
        mem["reasons"] = sm.reasons
        mem["retrieval_methods"] = methods
        results.append(mem)
    return results


def search_project_knowledge(
    project_id: str,
    query: str,
    memory_store=None,
    engine: Optional[RelevanceEngine] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Single retrieval abstraction for ranked, explainable project knowledge.

    Returns memory dicts enriched with score, reasons, and metadata.relevance.
    """
    scored = search_knowledge(
        project_id, query, memory_store=memory_store, engine=engine, limit=limit
    )
    return format_scored_results(scored)


def get_relevance_engine(memory_store=None) -> RelevanceEngine:
    """Factory: HybridRelevanceEngine when embeddings enabled, else keyword-only."""
    if memory_store is None:
        from packages.memory.memory_store import get_memory_store
        memory_store = get_memory_store()

    from packages.shared.config import embeddings_enabled
    if embeddings_enabled():
        from packages.retrieval.hybrid import HybridRelevanceEngine
        return HybridRelevanceEngine(memory_store)
    return LayeredRelevanceEngine(memory_store)
