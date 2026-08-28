# Phase 2A Implementation Report

**Date:** August 28, 2026  
**Scope:** Foundation cleanup for unified retrieval, persistent indexing, configuration, knowledge extractions, and API integration tests.  
**Out of scope:** RAG, embeddings, knowledge graph, auth, cloud services.

---

## Summary

Phase 2A aligns all search paths behind one retrieval abstraction, persists project file indexes in SQLite with incremental sync, wires documented environment variables, activates the `knowledge_extractions` table in the ingestion pipeline, and adds FastAPI integration tests. All 74 backend tests pass; MCP, frontend build, and demos verified.

---

## Changes made

### Task 1 — Unified retrieval

**Problem:** API `/search-knowledge` and agent search used SQL `LIKE` while MCP and context assembly used `LayeredRelevanceEngine`.

**Solution:** Added `packages/context/retrieval.py` as the single entry point:

- `search_project_knowledge()` — ranked search with explainable scores
- `format_scored_results()` — normalizes `ScoredMemory` to API-friendly dicts
- `get_relevance_engine()` — factory for the default engine

**Routed through unified retrieval:**

| Path | Before | After |
|------|--------|-------|
| `OverhaustAgent.search_project_knowledge` | `MemoryStore.search_memories` (LIKE) | `search_project_knowledge()` |
| `ContextAssembler._get_relevant_memory` | SQL LIKE | `search_project_knowledge()` |
| `ContextAssembler._get_relevant_knowledge` | Already used relevance engine | Unchanged |
| MCP `_tool_search_memory` | Direct engine call | `search_project_knowledge()` (same scores) |
| API `/api/v1/search-knowledge` | Via agent | Via agent (now unified) |

**API compatibility:** Existing memory fields preserved. Additive fields: `score`, `reasons`, `metadata.relevance`, response flag `scored: true`.

`MemoryStore.search_memories()` remains for internal/filter use but is no longer the primary retrieval path.

---

### Task 2 — Persist project index

**Added:** `services/ingestion/index_store.py` — `ProjectIndexStore`

**New SQLite tables** (created with `IF NOT EXISTS`, no breaking migration):

- `project_index_meta` — project_id, root_path, indexed_at, total_tokens, stats
- `project_index_files` — path, hash, token count, imports/exports (no file contents)
- `project_index_symbols` — name, kind, line, exported flag

**Behavior:**

- First index → full scan, persist snapshot
- Subsequent index → `diff_project()` + `apply_diff()` (reuses existing indexer logic)
- Unchanged tree → `sync.mode: "unchanged"` (no file re-reads)
- Modified files → incremental re-read only for changed paths
- Path normalization via `Path.resolve()` for consistent root comparison

**Integrated into:**

- `POST /api/v1/index-project` — persists index, returns `sync` report; requires project to exist
- `ContextAssembler._get_relevant_files` — loads/syncs persisted index instead of full rescan

**New optional request field:** `force_full: bool` on index-project (default false).

---

### Task 3 — Environment configuration

**Added:** `packages/shared/config.py`

| Variable | Wired to |
|----------|----------|
| `OVERHAUST_DB_PATH` | `MemoryStore` (via `get_db_path()`) |
| `OVERHAUST_API_HOST` | `uvicorn.run()` in `services/api/main.py` |
| `OVERHAUST_API_PORT` | `uvicorn.run()` |
| `OVERHAUST_ALLOWED_ORIGINS` | FastAPI CORS middleware |
| `OVERHAUST_DEFAULT_MODEL` | `TokenEstimator` default model |

**Also updated:**

- `.env.example` — added `OVERHAUST_API_HOST`, clarified `OVERHAUST_API_BASE_URL` (client-side, unchanged)
- `/health` — dynamic UTC timestamp (was hardcoded)

**Not removed:** `OVERHAUST_API_BASE_URL` — used by API connection adapter and demos (client URL, not server bind).

---

### Task 4 — Knowledge extractions

**Activated** the existing `knowledge_extractions` table.

**Added to `MemoryStore`:**

- `add_knowledge_extraction()` — stores provenance pointer + structured JSON (INSERT OR IGNORE)
- `extraction_exists()` — dedup guard before ingest
- `get_extractions()` — list extractions for a project

**Ingestion flow** (`ConversationIngestor.store_result`):

1. Skip if extraction already exists (same provenance + content)
2. Write memory with provenance/confidence/status metadata
3. Write extraction record with `source_ref` = provenance string (not full conversation text)
4. Link via `extraction_id` in memory metadata and `memory_id` in extraction JSON

No duplicate full-text storage; memories remain the queryable layer, extractions are the archive.

---

### Task 5 — API integration tests

**Added:** `services/api/test_api_integration.py` (8 tests)

Uses `TestClient` with dependency overrides for isolated temp SQLite DB.

| Test | Covers |
|------|--------|
| `test_health` | Health endpoint + timestamp |
| `test_create_and_get_project` | Project CRUD |
| `test_index_project_persists` | Full + unchanged incremental index |
| `test_unified_search_scoring` | Scored search with reasons |
| `test_context_retrieval` | Context assembly via API |
| `test_ingest_conversation_provenance` | Ingestion + extractions |
| `test_stale_and_resolved_knowledge` | mark-resolved, mark-stale |
| `test_error_handling` | 404 for missing project/context/index |

**Also added:**

- `services/ingestion/test_index_store.py` (3 tests)
- `packages/context/test_retrieval.py` (1 test)

**Dependency:** `httpx` added to `requirements.txt` for TestClient.

---

## Files changed

| File | Change |
|------|--------|
| `packages/context/retrieval.py` | **New** — unified retrieval abstraction |
| `packages/context/test_retrieval.py` | **New** — retrieval tests |
| `packages/shared/config.py` | **New** — environment configuration |
| `packages/memory/memory_store.py` | `_connect()`, extractions API, config db path |
| `packages/agent/autonomous_agent.py` | Unified search |
| `packages/context/context_engine.py` | Unified memory search + persisted file index |
| `packages/tokenization/token_estimator.py` | Default model from config |
| `services/ingestion/index_store.py` | **New** — persistent index storage |
| `services/ingestion/test_index_store.py` | **New** — index persistence tests |
| `services/ingestion/conversation.py` | Write knowledge_extractions on ingest |
| `services/api/main.py` | Config, index persistence, search response, health fix |
| `services/api/test_api_integration.py` | **New** — API integration tests |
| `services/mcp_server/server.py` | MCP search via unified retrieval |
| `requirements.txt` | Added `httpx` |
| `.env.example` | Documented `OVERHAUST_API_HOST` |

---

## Architecture impact

```
                    ┌─────────────────────────────┐
                    │ packages/context/retrieval  │
                    │  search_project_knowledge() │
                    └─────────────┬───────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
   OverhaustAgent          ContextAssembler          MCP server
   /api/search-knowledge   _get_relevant_memory      search_memory
                          _get_relevant_knowledge
                                  │
                                  ▼
                    LayeredRelevanceEngine (unchanged interface)

   ProjectIndexer ──► ProjectIndexStore ──► SQLite index tables
                              │
                              ▼
                    ContextAssembler._get_relevant_files
                    POST /api/v1/index-project

   ConversationIngestor ──► MemoryStore.memories
                         └► MemoryStore.knowledge_extractions
```

- **RelevanceEngine protocol:** unchanged; hybrid engine can replace implementation in Phase 2B
- **MCP tool schemas:** unchanged
- **REST paths:** unchanged; index response adds `sync` object; search adds `scored` flag
- **SQLite:** additive tables only; existing databases open without migration scripts

---

## Test results

| Suite | Result |
|-------|--------|
| pytest (74 tests) | **Passed** |
| MCP tests (6) | **Passed** |
| Frontend build | **Passed** |
| Frontend verify script | **Passed** |
| In-process demo | **Passed** |

**Note:** `scripts/e2e_demo.py` requires a running API server (unchanged).

---

## Remaining limitations

1. **No semantic search** — keyword layered engine only (Phase 2B)
2. **No knowledge graph** — file/symbol index only, no node/edge model
3. **Project index** — metadata only; file contents never stored (by design)
4. **Global singletons** — API still uses global agent/store in production path; tests override via DI
5. **`read_document()`** — still a placeholder in the agent
6. **Re-ingest dedup** — identical provenance+content skipped entirely (won't refresh memory)
7. **Index sync on context** — triggers diff check when assembling file context (cheap if unchanged)

---

## Ready for Phase 2B (RAG)

Phase 2A leaves clean extension points:

| Extension | How |
|-----------|-----|
| Hybrid retrieval | Implement `RelevanceEngine` subclass; inject via `search_knowledge(engine=...)` |
| Embedding storage | Add nullable column on `memories` or new table; index on write |
| Vector search | Replace brute-force in new `packages/retrieval/vector_store.py` |
| Graph layer | Build nodes from `project_index_symbols` + memory links |
| KSoR versioning | Extend memory metadata; use `knowledge_extractions` as audit trail |

Unified retrieval, persisted indexes, and extraction archive are the foundation Phase 2B builds on.

---

## Quick verification commands

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest -v
python3 scripts/demo.py
cd apps/web && npm run build && python3 ../scripts/verify_frontend.py
python3 -m services.api.main   # then e2e_demo.py if needed
```
