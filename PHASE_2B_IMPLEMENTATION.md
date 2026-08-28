# Phase 2B Implementation Report

**Date:** August 28, 2026  
**Scope:** Local-first hybrid RAG (keyword + semantic) behind existing `RelevanceEngine`  
**Default:** Keyword-only (`OVERHAUST_EMBEDDINGS=0`) — unchanged from Phase 2A

---

## Summary

Phase 2B adds optional hybrid retrieval using **fastembed** (local ONNX, no API key). Embeddings persist in SQLite. Score fusion combines keyword relevance, semantic similarity, confidence, and freshness. All 90 tests pass with embeddings disabled; benchmark produces measured paraphrase-recall improvements when hybrid is enabled.

---

## Architecture

```
Query
  │
  ▼
get_relevance_engine()  ── OVERHAUST_EMBEDDINGS=0 ──► LayeredRelevanceEngine
  │
  └── OVERHAUST_EMBEDDINGS=1 ──► HybridRelevanceEngine
           ├── LayeredRelevanceEngine (keyword top-50)
           ├── SemanticRetriever (embed query, cosine top-50)
           ├── merge by memory_id
           └── fuse: 0.50 kw + 0.35 sem + 0.10 confidence + 0.05 freshness
                    │
                    ▼
           search_project_knowledge() → API / MCP / Agent
```

**Embedding model (default):** `BAAI/bge-small-en-v1.5` via fastembed  
**Storage:** `memory_embeddings` SQLite table (vector JSON blob + content_hash, no duplicate text)

---

## Files changed

| File | Change |
|------|--------|
| `packages/retrieval/embeddings.py` | **New** — `EmbeddingProvider`, `NullEmbeddingProvider`, `FastEmbedProvider` |
| `packages/retrieval/embedding_store.py` | **New** — SQLite embedding CRUD |
| `packages/retrieval/semantic.py` | **New** — cosine similarity, semantic top-k, stale demotion |
| `packages/retrieval/hybrid.py` | **New** — `HybridRelevanceEngine` score fusion |
| `packages/retrieval/test_*.py` | **New** — 4 test modules (15 tests) |
| `packages/shared/config.py` | `embeddings_enabled()`, `get_embedding_model()`, `get_hybrid_weights()` |
| `packages/context/relevance.py` | Extended `ScoredMemory.retrieval_methods`; factory via `get_relevance_engine` |
| `packages/context/retrieval.py` | Hybrid factory; `format_scored_results` includes methods |
| `packages/context/context_engine.py` | Uses `get_relevance_engine()` |
| `packages/agent/runtime.py` | Uses `get_relevance_engine()` |
| `services/mcp_server/server.py` | Uses factory; MCP results include `retrieval_methods` |
| `packages/memory/memory_store.py` | Cascade delete embeddings on memory delete |
| `tests/evaluation/retrieval_benchmark.py` | **New** — paraphrase benchmark |
| `tests/evaluation/retrieval_benchmark_report.md` | **Generated** — measured results |
| `conftest.py` | **New** — auto `OVERHAUST_EMBEDDINGS=0` for tests |
| `pytest.ini` | `@pytest.mark.embeddings` marker |
| `requirements.txt` | Added `fastembed==0.6.0` |
| `.env.example` | Embedding and hybrid weight vars |

---

## Retrieval flow

1. **Enable hybrid:** `export OVERHAUST_EMBEDDINGS=1`
2. **Search** via any path (API, MCP, agent) → `search_project_knowledge()`
3. **Keyword path** scores up to 50 memories (existing layered engine)
4. **Semantic path** embeds query, loads/creates memory embeddings, cosine top-50
5. **Fusion** merges scores with explainable reasons and `retrieval_methods`
6. **Response** includes provenance from memory metadata (unchanged)

---

## Fallback behavior

| Condition | Behavior |
|-----------|----------|
| `OVERHAUST_EMBEDDINGS=0` (default) | Keyword-only `LayeredRelevanceEngine` |
| fastembed not installed + embeddings=1 | `FastEmbedProvider.is_available` false → semantic path empty → keyword-only via hybrid |
| Empty project | Empty results |
| Stale/resolved memories | Demoted (same rules as keyword engine) |

---

## Benchmark methodology

Run: `python3 -m tests.evaluation.retrieval_benchmark`

Three **paraphrase scenarios** (query wording differs from stored memories):

- `paraphrase_websocket` — "Fix idle connection recovery" vs "WebSocket reconnect bug"
- `paraphrase_auth` — "user login and session renewal" vs JWT/httpOnly content
- `paraphrase_database` — "persistence layer" vs "PostgreSQL"

**Metrics (all measured):**

| Metric | Definition |
|--------|------------|
| Precision@k | Fraction of top-k results containing ≥1 expected term |
| Coverage | Fraction of expected terms found across top-k |
| Irrelevant hits | Results containing irrelevant terms |
| Latency | Mean of 3 search calls (ms) |
| Tokens | tiktoken estimates (not billing) |

---

## Measured benchmark results

From [`tests/evaluation/retrieval_benchmark_report.md`](tests/evaluation/retrieval_benchmark_report.md) (Aug 28, 2026):

| Scenario | Mode | Precision@k | Coverage | Latency ms | Orig tokens | Prepared tokens |
|----------|------|-------------|----------|------------|-------------|-----------------|
| paraphrase_websocket | keyword | 100% | 75% | 0.3 | 46 | 16 |
| paraphrase_websocket | hybrid | 100% | **100%** | 1486 | 46 | 26 |
| paraphrase_auth | keyword | **0%** | **0%** | 0.2 | 34 | 0 |
| paraphrase_auth | hybrid | **100%** | **100%** | 1514 | 34 | 37 |
| paraphrase_database | keyword | **0%** | **0%** | 0.2 | 24 | 0 |
| paraphrase_database | hybrid | **100%** | **100%** | 1432 | 24 | 10 |

**Honest findings:**

- Hybrid dramatically improves paraphrase recall on auth/database scenarios where keyword search returns nothing.
- WebSocket scenario: keyword already works; hybrid improves coverage (75% → 100%).
- Hybrid latency ~1.4–1.5s on first run (embed-on-demand + model load); keyword ~0.2–0.3ms.
- Prepared token counts vary by mode because hybrid retrieves different (more) memories for paraphrase queries.

---

## Test results

| Suite | Result |
|-------|--------|
| pytest (90 tests, embeddings off) | **Passed** |
| MCP tests | **Passed** |
| Frontend build + verify | **Passed** |
| `scripts/demo.py` | **Passed** |
| Retrieval benchmark | **Generated** (measured) |

**New tests:** 16 (retrieval package + extended context tests + conftest)

---

## Limitations

1. **Not mandatory** — embeddings off by default; zero behavior change unless enabled
2. **Brute-force cosine** over project embeddings (fine for local scale <10k)
3. **First-search latency** — embed-on-demand per memory; no background indexer yet
4. **File relevance** — hybrid scores memories only; file ranking unchanged (Phase 2A index)
5. **No knowledge graph** — deferred to Phase 2C/2D
6. **Model download** — fastembed downloads ONNX model on first use (~one-time)

---

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `OVERHAUST_EMBEDDINGS` | `0` | Enable hybrid retrieval |
| `OVERHAUST_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | fastembed model |
| `OVERHAUST_HYBRID_KEYWORD_WEIGHT` | `0.50` | Fusion weight |
| `OVERHAUST_HYBRID_SEMANTIC_WEIGHT` | `0.35` | Fusion weight |
| `OVERHAUST_HYBRID_CONFIDENCE_WEIGHT` | `0.10` | Fusion weight |
| `OVERHAUST_HYBRID_FRESHNESS_WEIGHT` | `0.05` | Fusion weight |

---

## Recommended Phase 2C

1. **KSoR metadata** — supersede links, citations in context responses, abstention when evidence weak
2. **Background embedding** — embed on ingest/write instead of on-demand search
3. **Token-budget context selection** — greedy pack by score-per-token
4. **Knowledge graph** — nodes from index symbols + memory links (Phase 2D)

---

## Quick verification

```bash
python3 -m pip install -r requirements.txt
OVERHAUST_EMBEDDINGS=0 python3 -m pytest -v
OVERHAUST_EMBEDDINGS=1 python3 -m tests.evaluation.retrieval_benchmark
python3 scripts/demo.py
```
