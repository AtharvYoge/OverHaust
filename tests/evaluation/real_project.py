"""
Real-project evaluation: index the Overhaust repo itself and measure
retrieval quality + latency for realistic developer questions.

This uses the ProjectIndexer for files and seeds project-knowledge memories
derived from the index so the relevance engine can retrieve them. All numbers
are MEASURED (wall-clock, tiktoken).
"""
import sys, os, time, tempfile
from dataclasses import dataclass, field
from typing import List, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.ingestion.project_indexer import ProjectIndexer
from packages.memory.memory_store import MemoryStore
from packages.context.relevance import LayeredRelevanceEngine
from packages.tokenization.token_estimator import TokenEstimator

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# Developer questions -> substrings we expect in relevant file paths
PROJECT_QUERIES = [
    ("How does conversation ingestion work?", ["conversation"]),
    ("Where is memory stored?", ["memory_store", "memory"]),
    ("How does context selection work?", ["context_engine", "relevance", "context"]),
    ("How does the MCP server expose tools?", ["mcp", "server"]),
    ("Where should I modify relevance scoring?", ["relevance"]),
]


@dataclass
class ProjectQueryResult:
    query: str
    latency_ms: float
    context_tokens: int
    relevant_files: List[str]
    irrelevant_files: List[str]
    hit: bool


def run_real_project() -> Dict[str, Any]:
    estimator = TokenEstimator()
    indexer = ProjectIndexer(estimator)

    t0 = time.perf_counter()
    idx = indexer.index_project(REPO_ROOT, "overhaust-self")
    index_ms = (time.perf_counter() - t0) * 1000

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        store.add_project("overhaust-self", "Overhaust repository")
        # Seed a project-knowledge memory per indexed file (path + top symbols),
        # so retrieval can rank files against a question. Content is derived
        # from the real index (not fabricated).
        for f in idx.files:
            syms = ", ".join(s.name for s in f.symbols[:8])
            content = f"File {f.path}"
            if syms:
                content += f" defines {syms}"
            if f.imports:
                content += f"; imports {', '.join(f.imports[:6])}"
            store.add_memory("overhaust-self", content, memory_type="permanent",
                             importance_score=0.6,
                             metadata={"knowledge_type": "permanent_knowledge",
                                       "status": "active", "file_path": f.path})

        engine = LayeredRelevanceEngine(store, max_candidates=500)
        results: List[ProjectQueryResult] = []
        for query, expect_substrings in PROJECT_QUERIES:
            t0 = time.perf_counter()
            hits = engine.search("overhaust-self", query, limit=5)
            latency_ms = (time.perf_counter() - t0) * 1000
            rel_files, irrel_files = [], []
            for h in hits:
                fp = (h.memory.get('metadata') or {}).get('file_path', '')
                if any(sub in fp.lower() for sub in expect_substrings):
                    rel_files.append(fp)
                else:
                    irrel_files.append(fp)
            ctx_tokens = sum(estimator.estimate_tokens(h.memory['content']) for h in hits)
            results.append(ProjectQueryResult(
                query=query, latency_ms=round(latency_ms, 2),
                context_tokens=ctx_tokens,
                relevant_files=rel_files, irrelevant_files=irrel_files,
                hit=len(rel_files) > 0,
            ))

        hit_rate = sum(1 for r in results if r.hit) / len(results) * 100
        avg_latency = sum(r.latency_ms for r in results) / len(results)
        return {
            "index_ms": round(index_ms, 1),
            "file_count": len(idx.files),
            "index_tokens": idx.total_tokens,
            "queries": results,
            "hit_rate_pct": round(hit_rate, 1),
            "avg_latency_ms": round(avg_latency, 2),
        }
    finally:
        if os.path.exists(db):
            os.unlink(db)


if __name__ == "__main__":
    r = run_real_project()
    print(f"Indexed {r['file_count']} files ({r['index_tokens']} tokens) in {r['index_ms']}ms")
    print(f"Hit rate: {r['hit_rate_pct']}% | avg query latency: {r['avg_latency_ms']}ms\n")
    for q in r['queries']:
        mark = "HIT " if q.hit else "MISS"
        print(f"[{mark}] {q.query}  ({q.latency_ms}ms, {q.context_tokens} tokens)")
        print(f"       relevant: {q.relevant_files}")
        if q.irrelevant_files:
            print(f"       other:    {q.irrelevant_files}")
