"""
Unified retrieval entry point for Overhaust.

All search/context paths should route through this module so API, MCP,
agent, and context assembly share the same relevance scoring behavior.
Trust is applied as a post-processor — RelevanceEngine is unchanged.
Index file/symbol metadata is merged after memory retrieval.
"""

from typing import Dict, List, Optional, Any

from packages.context.relevance import (
    RelevanceEngine,
    ScoredMemory,
    LayeredRelevanceEngine,
    search_knowledge,
)
from packages.knowledge.trust import apply_trust_to_scored
from packages.knowledge.schema import normalize_metadata
from packages.shared.config import get_trust_min, get_index_search_limit


def _load_project_index(memory_store, project_id):
    """Load persisted index only — no rescan on search."""
    from services.ingestion.index_store import ProjectIndexStore
    return ProjectIndexStore(memory_store).load_index_or_none(project_id)


def merge_scored_results(
    memory_scored: List[ScoredMemory],
    index_scored: List[ScoredMemory],
    limit: int,
) -> List[ScoredMemory]:
    """Merge memory and index hits, dedupe by file_path keeping higher score."""
    combined = list(memory_scored) + list(index_scored)
    if not combined:
        return []

    by_id: Dict[str, ScoredMemory] = {}
    by_path: Dict[str, ScoredMemory] = {}

    for sm in combined:
        mid = sm.memory.get("id", "")
        meta = sm.memory.get("metadata") or {}
        fpath = meta.get("file_path") or meta.get("source_ref") or ""

        existing_path = by_path.get(fpath) if fpath else None
        if fpath and existing_path and existing_path.score >= sm.score:
            continue

        existing_id = by_id.get(mid)
        if existing_id and existing_id.score >= sm.score:
            continue

        by_id[mid] = sm
        if fpath:
            by_path[fpath] = sm

    # Rebuild unique list preferring by_id (symbol + file may share path — keep both ids)
    seen_ids = set()
    merged: List[ScoredMemory] = []
    for sm in sorted(by_id.values(), key=lambda s: s.score, reverse=True):
        if sm.memory.get("id") in seen_ids:
            continue
        seen_ids.add(sm.memory.get("id"))
        merged.append(sm)

    merged.sort(key=lambda s: s.score, reverse=True)
    return merged[:limit]


def format_scored_results(scored: List[ScoredMemory]) -> List[Dict[str, Any]]:
    """Convert scored memories to API-friendly dicts with relevance and trust."""
    results: List[Dict[str, Any]] = []
    for sm in scored:
        mem = dict(sm.memory)
        meta = normalize_metadata(mem.get("metadata") or {})
        methods = list(sm.retrieval_methods) if sm.retrieval_methods else ["keyword"]
        meta["relevance"] = {
            "score": sm.score,
            "reasons": sm.reasons,
            "methods": methods,
        }
        confidence = meta.get("confidence")
        meta["trust"] = {
            "score": sm.trust_score,
            "status": sm.trust_status,
            "confidence": confidence,
            "fresh": sm.trust_score is not None and (sm.trust_score or 0) >= 0.55,
            "reasons": list(sm.trust_reasons),
        }
        prov = sm.provenance_display or meta.get("provenance", "")
        meta["provenance"] = prov
        mem["metadata"] = meta
        mem["score"] = sm.score
        mem["reasons"] = sm.reasons
        mem["retrieval_methods"] = methods
        mem["trust_score"] = sm.trust_score
        mem["provenance"] = prov
        record_type = meta.get("record_type", "memory")
        mem["record_type"] = record_type
        results.append(mem)
    return results


def apply_trust(scored: List[ScoredMemory], query: str) -> List[ScoredMemory]:
    """Apply deterministic trust post-processing after relevance scoring."""
    return apply_trust_to_scored(scored, query, trust_min=get_trust_min())


def _search_with_index(
    project_id: str,
    query: str,
    memory_store=None,
    engine: Optional[RelevanceEngine] = None,
    limit: int = 10,
) -> List[ScoredMemory]:
    """Memory + index retrieval merged before trust."""
    if memory_store is None:
        from packages.memory.memory_store import get_memory_store
        memory_store = get_memory_store()

    memory_scored = search_knowledge(
        project_id, query, memory_store=memory_store, engine=engine, limit=limit
    )
    index = _load_project_index(memory_store, project_id)
    index_scored: List[ScoredMemory] = []
    if index is not None:
        from packages.retrieval.index_retrieval import search_index_records
        index_scored = search_index_records(
            project_id, query, index,
            limit=get_index_search_limit(),
            memory_store=memory_store,
        )

    return merge_scored_results(memory_scored, index_scored, limit)


def search_project_knowledge(
    project_id: str,
    query: str,
    memory_store=None,
    engine: Optional[RelevanceEngine] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Single retrieval abstraction for ranked, explainable project knowledge.

    Returns memory dicts enriched with score, reasons, trust, and metadata.
    Includes indexed files/symbols when a project index exists.
    """
    scored = _search_with_index(
        project_id, query, memory_store=memory_store, engine=engine, limit=limit
    )
    scored = apply_trust(scored, query)
    return format_scored_results(scored)


def search_project_knowledge_scored(
    project_id: str,
    query: str,
    memory_store=None,
    engine: Optional[RelevanceEngine] = None,
    limit: int = 10,
) -> List[ScoredMemory]:
    """Return ScoredMemory list with trust applied (for context assembly)."""
    scored = _search_with_index(
        project_id, query, memory_store=memory_store, engine=engine, limit=limit
    )
    return apply_trust(scored, query)


def trace_code_flow(
    project_id: str,
    query: str,
    memory_store=None,
    *,
    max_steps: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Trace a short ordered code-flow evidence path for a project question.

    Loads the persisted index (no rescan) and walks import/export/call edges only.
    """
    if memory_store is None:
        from packages.memory.memory_store import get_memory_store
        memory_store = get_memory_store()

    index = _load_project_index(memory_store, project_id)
    if index is None:
        from packages.retrieval.code_flow import CodeFlowResult, code_flow_result_to_dict
        return code_flow_result_to_dict(CodeFlowResult(
            project_id=project_id,
            query=query,
            insufficient_evidence=True,
            evidence_note="Needs more information — no project index available.",
        ))

    from services.ingestion.index_store import ProjectIndexStore
    from packages.retrieval.code_flow import trace_code_flow as _trace, code_flow_result_to_dict

    root_path = ProjectIndexStore(memory_store).get_project_root(project_id)
    result = _trace(
        project_id,
        query,
        index,
        memory_store=memory_store,
        max_steps=max_steps,
        root_path=root_path,
    )
    return code_flow_result_to_dict(result)


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
