# Overhaust Architecture Audit

**Date:** August 28, 2026  
**Scope:** Repository audit for RAG, KSoR-inspired knowledge, and simple knowledge-graph readiness  
**Status:** Phase 1 consolidation complete; advanced retrieval and graph features not yet implemented

---

## Executive summary

Overhaust is a **local-first AI memory and context-efficiency layer**. It ingests conversations and project files, stores structured knowledge in **SQLite**, retrieves relevant context with a **keyword-based relevance engine**, and exposes that capability through a **REST API**, **MCP server**, and a **React demo UI**.

The codebase is modular and test-covered (62 pytest tests passing). There is **no vector database**, **no embedding pipeline**, and **no knowledge graph** in code today — only documented extension points and early KSoR-like metadata (provenance, confidence, status) in the ingestion layer.

---

## 1. Current architecture

Overhaust has three layers:

```
┌─────────────────────────────────────────────────────────────┐
│  User layer: apps/web (React demo)                          │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP (REST)
┌──────────────────────────▼──────────────────────────────────┐
│  Service layer: services/api, services/mcp_server,            │
│                 services/agent/connections                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  Core layer: packages/memory, packages/context,              │
│              packages/agent, packages/tokenization            │
│              services/ingestion                               │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    SQLite (data/overhaust_memory.db)
```

**Design principles in practice:**

- Local-first: SQLite is the default store; no cloud services required.
- Modular packages: memory, context, agent, and tokenization are separate.
- Agent-agnostic connections: MCP, HTTP API, and in-process runtime share the same core.
- Honest token metrics: estimates use tiktoken; UI labels them as estimated.

---

## 2. Component map

| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| Memory store | `packages/memory/memory_store.py` | SQLite persistence for projects and memories | **Working** |
| Knowledge extractor | `packages/context/context_engine.py` | Regex-based extraction from text | **Working** (basic) |
| Context assembler | `packages/context/context_engine.py` | Builds `ContextPackage` for a task | **Working** |
| Relevance engine | `packages/context/relevance.py` | Layered keyword scoring + intent boosts | **Working** |
| Token estimator | `packages/tokenization/token_estimator.py` | tiktoken-based counts | **Working** |
| Autonomous agent | `packages/agent/autonomous_agent.py` | Task understanding, context, memory ops | **Working** |
| Agent runtime | `packages/agent/runtime.py` | Goal-directed loop with gap detection | **Working** |
| Conversation ingestor | `services/ingestion/conversation.py` | Parse, classify, dedupe, store conversations | **Working** |
| Project indexer | `services/ingestion/project_indexer.py` | Scan files, extract symbols/imports | **Working** |
| REST API | `services/api/main.py` | FastAPI endpoints | **Working** |
| MCP server | `services/mcp_server/server.py` | stdio MCP tools | **Working** |
| Connection registry | `services/agent/connections.py` | Local, API, MCP, IDE config adapters | **Working** |
| Web demo | `apps/web/src/App.tsx` | Step-by-step product demo | **Working** |
| Evaluation harness | `tests/evaluation/` | Scenario-based quality checks | **Working** |
| Knowledge graph | — | Not implemented | **Planned** |
| Vector / RAG | — | Not implemented | **Planned** |
| Graphify integration | — | Referenced in docs only | **Deferred** |

### Per-component detail

#### Memory store (`packages/memory`)

| Field | Detail |
|-------|--------|
| **Inputs** | Project metadata, memory content, type, importance, JSON metadata |
| **Outputs** | Memory IDs, search results, project records |
| **Dependencies** | Python stdlib (`sqlite3`, `json`, `hashlib`) |
| **Tables** | `projects`, `memories`, `knowledge_extractions` (schema only — unused) |
| **Limitations** | `search_memories()` uses SQL `LIKE`; no full-text index; `knowledge_extractions` table has no CRUD |

#### Relevance engine (`packages/context/relevance.py`)

| Field | Detail |
|-------|--------|
| **Inputs** | `project_id`, query string, optional limit |
| **Outputs** | `List[ScoredMemory]` with score + human-readable reasons |
| **Layers** | Exact phrase → keywords → metadata → intent boost → importance → recency |
| **Interface** | `RelevanceEngine` protocol; `LayeredRelevanceEngine` is default |
| **Limitations** | No semantic/embedding search; synonym handling is heuristic only |

#### Conversation ingestor (`services/ingestion/conversation.py`)

| Field | Detail |
|-------|--------|
| **Inputs** | Raw conversation (plain text, Markdown, JSON, ChatGPT export) |
| **Outputs** | `IngestionResult` with classified memories + compression report |
| **Categories** | `permanent_knowledge`, `decision`, `current_task`, `open_issue`, `resolved_issue`, `stale_info`, `irrelevant` |
| **KSoR-like fields** | `provenance`, `confidence`, `status`, `source_id`, `message_index` |
| **Limitations** | Regex classification; near-duplicate dedup is exact-hash only |

#### Project indexer (`services/ingestion/project_indexer.py`)

| Field | Detail |
|-------|--------|
| **Inputs** | Authorized directory path, `project_id` |
| **Outputs** | `ProjectIndex` (files, symbols, imports, token counts, stats) |
| **Security** | Path containment, skip dirs, 1MB/file cap, 5000 files max |
| **Limitations** | In-memory only per request; not persisted to SQLite; regex symbol extraction |

#### MCP server (`services/mcp_server/server.py`)

| Field | Detail |
|-------|--------|
| **Tools** | `create_project`, `remember`, `search_memory`, `build_context`, `get_relevant_context`, `update_memory`, `estimate_context` (+ aliases) |
| **Transport** | stdio via `mcp` package |
| **Limitations** | `MCPConnection.handle()` in connections.py is not implemented (client uses MCP session directly) |

#### REST API (`services/api/main.py`)

| Field | Detail |
|-------|--------|
| **Endpoints** | `/api/v1/get-context`, `/update-memory`, `/search-knowledge`, `/ingest-conversation`, `/index-project`, `/projects`, token estimation, agent history |
| **Limitations** | CORS hardcoded to localhost; health timestamp is static; some env vars in `.env.example` not wired |

---

## 3. Data flow

### End-to-end user demo flow

```
User pastes conversation
        │
        ▼
POST /api/v1/ingest-conversation
        │
        ▼
ConversationIngestor: parse → dedupe → classify → store
        │
        ▼
SQLite memories (with provenance metadata)
        │
User describes current task
        │
        ▼
POST /api/v1/get-context
        │
        ▼
OverhaustAgent → ContextAssembler → LayeredRelevanceEngine
        │
        ▼
ContextPackage (knowledge, decisions, files, constraints, token estimate)
        │
        ▼
JSON response → frontend "Copy for AI"
```

### MCP agent flow

```
IDE / MCP client
        │
        ▼
stdio → OverhaustMCPServer
        │
        ├── remember → MemoryStore.add_memory
        ├── search_memory → LayeredRelevanceEngine.search
        └── build_context → OverhaustAgent.get_project_context
```

---

## 4. Memory lifecycle

```
┌──────────────┐     ingest / agent.update_memory     ┌──────────────┐
│  Raw source  │ ──────────────────────────────────► │   Memory     │
│ (conversation│                                     │  (SQLite)    │
│  or agent)   │                                     └──────┬───────┘
└──────────────┘                                            │
                                                            │
         ┌──────────────────────────────────────────────────┤
         │                                                  │
         ▼                                                  ▼
  memory_type:                                    metadata fields:
  permanent | temporary | task |                  knowledge_type, provenance,
  resolved | stale                                confidence, status, source_id
         │                                                  │
         ▼                                                  ▼
  Retrieved by relevance engine ◄──── accessed_at / access_count updated
         │
         ├── mark_stale → importance ↓, status=stale
         ├── mark_resolved → new resolved memory
         └── cleanup_stale_memories() → delete old low-importance non-permanent
```

**Memory types:**

| Type | Typical use |
|------|-------------|
| `permanent` | Architecture, decisions |
| `temporary` | Short-lived notes |
| `task` | Current focus, open issues |
| `resolved` | Closed issues |
| `stale` | Outdated information |

---

## 5. Conversation lifecycle

1. **Parse** — `ConversationParser` handles Markdown roles, JSON arrays, ChatGPT exports.
2. **Token count** — Each message gets an estimated token count.
3. **Dedupe** — Exact normalized-content hash; duplicates counted but not re-processed.
4. **Classify** — `MessageClassifier` applies regex patterns per category.
5. **Dedupe memories** — Same category + normalized content collapsed.
6. **Store** (optional) — `store_result()` writes to SQLite with full provenance metadata.
7. **Report** — `compression_report()` returns honest per-category token breakdown.

Irrelevant chatter (greetings, short acknowledgments) is classified but **not stored**.

---

## 6. Project indexing lifecycle

1. **Authorize** — Caller provides explicit `root_path`; path must exist and be a directory.
2. **Walk** — Skip `node_modules`, `.git`, build dirs, etc.; only allowed extensions.
3. **Index file** — Read text, SHA-256 hash, token count, regex symbols/imports.
4. **Return** — `ProjectIndex` in memory (not persisted).
5. **Optional diff** — `diff_project()` / `apply_diff()` support incremental re-indexing.

**Context integration:** When assembling context, if a project has `root_path`, the indexer runs on-demand and keyword-matches files to the task. This is **live scanning**, not a cached index.

---

## 7. Context retrieval lifecycle

1. **Task received** — Via API, MCP, or agent runtime.
2. **Project lookup** — Must exist in SQLite.
3. **Knowledge retrieval** — `LayeredRelevanceEngine.search()` scores up to 200 candidate memories.
4. **File retrieval** — On-demand `ProjectIndexer` + keyword scoring (if `root_path` set).
5. **State assembly** — Recent task/state memories → `current_state` dict.
6. **Constraint extraction** — Regex on task + knowledge text.
7. **Token estimate** — Full context serialized to text → tiktoken count.
8. **Package returned** — `ContextPackage` with relevance explanations in metadata.

**Known inconsistency:** `/api/v1/search-knowledge` uses `MemoryStore.search_memories()` (SQL `LIKE`), while MCP `search_memory` uses `LayeredRelevanceEngine`. Context assembly always uses the relevance engine.

---

## 8. MCP lifecycle

1. **Start** — `python3 -m services.mcp_server.server` (stdio).
2. **Initialize** — MCP handshake via `mcp` library.
3. **List tools** — 9 tool definitions (some aliases).
4. **Call tool** — Routes to `OverhaustMCPServer._tool_*` handlers.
5. **Response** — JSON payload in `TextContent`.

IDE adapters (`IDEConfigAdapter`) generate MCP client config for Cursor, Claude Code, Windsurf — marked **coming_soon** until validated in real IDEs.

---

## 9. Frontend / backend interaction

| Frontend action | API endpoint | Notes |
|-----------------|--------------|-------|
| Create project | `POST /api/v1/projects` | Before ingestion |
| Ingest conversation | `POST /api/v1/ingest-conversation` | `store: true` |
| Get context | `POST /api/v1/get-context` | Step 5 → 7 in demo |
| List connections | `GET /api/v1/connections` | Loaded on mount, not displayed in UI |

**Config:** `VITE_API_BASE_URL` (default `http://localhost:8000`).

**UI scope:** Single-page demo wizard (9 steps). Nav links (Memory, Projects, Usage, Connections) are placeholders — no routing implemented.

---

## 10. Storage model

### SQLite schema (active)

**`projects`**

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | Project identifier |
| name | TEXT | Display name |
| description | TEXT | Optional |
| root_path | TEXT | For on-demand indexing |
| metadata | TEXT JSON | Extensible |
| created_at / updated_at | TIMESTAMP | Auto |

**`memories`**

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | Content hash (16 chars) |
| project_id | TEXT FK | Required |
| content | TEXT | Knowledge text |
| memory_type | TEXT | permanent/temporary/task/resolved/stale |
| importance_score | REAL | 0.0–1.0 |
| metadata | TEXT JSON | provenance, knowledge_type, status, confidence |
| source_hash | TEXT | Change detection |
| accessed_at / access_count | | Usage tracking |

**Indexes:** `project_id`, `memory_type`, `importance_score`, `updated_at`

### Unused schema

**`knowledge_extractions`** — Created at init but no read/write code exists. Likely intended for raw extraction storage before memory promotion.

### Default path

`<repo>/data/overhaust_memory.db` — overridable via `OVERHAUST_DB_PATH`.

---

## 11. Token optimization pipeline

Overhaust does **not** rewrite or compress text at retrieval time. Token savings come from:

1. **Ingestion deduplication** — Remove repeated messages and duplicate extracted memories.
2. **Irrelevant filtering** — Greetings and filler not stored.
3. **Task-focused retrieval** — Only top-N scored memories included in context.
4. **Intent demotion** — Stale/resolved items down-ranked unless query asks for them.

**Measurement:**

- `TokenEstimator.estimate_tokens()` — tiktoken `cl100k_base` (approximation for non-OpenAI models).
- `compression_report()` — Per-category breakdown after ingestion.
- Evaluation harness reports ~32.6% average reduction on repetitive inputs (estimated).

**Not implemented:** Summarization, chunk merging, semantic dedup, or provider-accurate billing counts.

---

## 12. Existing extension points

| Extension point | Location | Intended use |
|-----------------|----------|--------------|
| `RelevanceEngine` protocol | `packages/context/relevance.py` | Swap in hybrid/semantic retrieval |
| `search_knowledge()` helper | Same file | Single retrieval entry point |
| Memory metadata JSON | `MemoryStore.add_memory()` | Provenance, confidence, graph node refs |
| `KnowledgeExtractor` patterns | `context_engine.py` | Add extraction types |
| `ConversationIngestor.store_result()` | `conversation.py` | Custom storage backends |
| `ProjectIndexer` output | `project_indexer.py` | Feed graph builder |
| `AgentConnection` ABC | `connections.py` | New agent transports |
| MCP tool handlers | `mcp_server/server.py` | New agent-facing tools |
| `knowledge_extractions` table | Schema exists | Raw extraction archive |

---

## 13. Technical debt

| Issue | Severity | Notes |
|-------|----------|-------|
| API search vs MCP search use different engines | Medium | API `/search-knowledge` uses SQL LIKE |
| `knowledge_extractions` table unused | Low | Schema dead code |
| Project index not persisted | Medium | Re-indexed on every context request with files |
| Env vars documented but partially wired | Low | `OVERHAUST_API_PORT`, CORS, default model |
| Global singleton `memory_store` | Low | Tests use temp DBs; production needs injection |
| `read_document()` is placeholder | Medium | Does not read filesystem |
| No `__init__.py` in packages | Low | Works via `sys.path` hacks in services |
| Health endpoint static timestamp | Low | Misleading for monitoring |
| Frontend nav links non-functional | Low | Demo-only UI |
| ARCHITECTURE.md said MCP was future | Fixed | MCP is implemented |

---

## 14. Architecture risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Keyword retrieval misses synonyms | Wrong context sent to AI | Phase 2 hybrid retrieval behind same interface |
| Regex ingestion misclassifies | Bad memories stored | Confidence scores + human review path later |
| On-demand re-indexing slow on large repos | Latency spikes | Persist index + incremental diff |
| SQLite single-writer | Concurrent agent issues | Acceptable for local-first; document limits |
| Global agent singleton | State leaks between tests/requests | Inject per-request in API later |
| No auth on API/MCP | Local exposure risk | Document localhost-only; add auth only if multi-user |
| Content-hash memory IDs | Updates overwrite same ID | By design for dedup; document behavior |

---

## 15. Missing functionality

**Not in codebase (verified):**

- Vector embeddings or semantic search
- Reranking model
- Knowledge graph (nodes/edges/traversal)
- Graphify integration
- Persisted project index
- Full-text search (FTS5)
- LLM-based extraction or summarization
- User authentication / multi-tenancy
- Cloud storage or sync
- Real filesystem document reading in agent
- Abstention ("insufficient evidence") in responses
- Citation rendering in UI

**Partially present (KSoR-inspired foundations):**

- Provenance strings on ingested memories
- Confidence heuristics (0.0–1.0)
- Status field (`active`, `resolved`, `stale`, `rejected`)
- Source tracking (`source_id`, `source_type`, `message_index`)

---

## 16. Recommended next steps

See [NEXT_PHASE_PLAN.md](NEXT_PHASE_PLAN.md) for the detailed implementation roadmap.

**Immediate priorities:**

1. Unify search paths (API + agent → `LayeredRelevanceEngine`).
2. Persist project index snapshots in SQLite.
3. Activate `knowledge_extractions` or remove from schema (with migration plan).
4. Add `RelevanceEngine` embedding backend (optional, local-first).
5. Introduce lightweight graph tables (nodes/edges) without exposing graph UI.
6. Wire remaining environment variables.
7. Add API integration tests (currently only manual `test_api.py`).

**Do not add yet:** Cloud vector DB, auth/billing, heavy graph database, SaaS features.

---

## Verification summary (audit run)

| Check | Result |
|-------|--------|
| Backend pytest (62 tests) | **Passed** |
| MCP tests (incl. stdio roundtrip) | **Passed** |
| Frontend build (`npm run build`) | **Passed** |
| Frontend verify script | **Passed** |
| In-process demo (`scripts/demo.py`) | **Passed** |
| E2E demo (`scripts/e2e_demo.py`) | **Failed** — requires running API server (connection refused) |

**Warnings:**

- E2E demo is not self-contained; start API first.
- `test_api.py` is a manual script, not part of pytest.
- Evaluation metrics are scenario-based estimates, not production benchmarks.

**Regressions:** None observed during this audit.
