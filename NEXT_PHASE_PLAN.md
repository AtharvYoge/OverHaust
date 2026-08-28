# Overhaust Next Phase Plan

**Purpose:** Practical roadmap for RAG, KSoR-inspired knowledge, and a simple knowledge graph — without implementing them yet.  
**Audience:** Developers and product owners preparing Phase 2 work.  
**Prerequisite:** Read [ARCHITECTURE_AUDIT.md](ARCHITECTURE_AUDIT.md).

---

## Guiding principles

1. **Local-first** — Default path works offline with SQLite; no required cloud services.
2. **Hide complexity** — Users see "what your AI remembers" and "relevant context," not graphs or embeddings.
3. **Extend, don't rewrite** — Plug into `RelevanceEngine`, ingestion, and memory metadata.
4. **Optional depth** — Keyword retrieval remains the zero-dependency default; embeddings are opt-in.
5. **Honest outputs** — Citations, confidence, and abstention when evidence is weak.

---

## Phase 2 overview

```
Phase 2A: Foundation cleanup (1–2 weeks)
    └── Unify search, persist index, wire config, API tests

Phase 2B: Hybrid retrieval / RAG (2–4 weeks)
    └── Embedding abstraction, candidate pool, rerank, context selection

Phase 2C: KSoR knowledge layer (2–3 weeks)
    └── Provenance, trust, versioning, citations, abstention

Phase 2D: Simple knowledge graph (3–4 weeks)
    └── Nodes/edges in SQLite, hidden from UI, used for retrieval

Phase 2E: Integration & polish (1–2 weeks)
    └── MCP tools, evaluation expansion, docs
```

---

## Future architecture: RAG

### Design goals

- Hybrid **keyword + semantic** retrieval
- **Local-first** embeddings (e.g. `sentence-transformers` or ONNX runtime — evaluate when implementing)
- Same public interface: `RelevanceEngine.search(project_id, query, limit)`

### Proposed pipeline

```
Query
  │
  ├─► Keyword path (LayeredRelevanceEngine) ──► candidates A
  │
  └─► Semantic path (EmbeddingEngine) ────────► candidates B
            │
            ▼
      Merge + dedupe (by memory_id)
            │
            ▼
      Rerank (score fusion or cross-encoder)
            │
            ▼
      Context selector (token budget aware)
            │
            ▼
      ContextPackage (with citations)
```

### Embedding abstraction (new module: `packages/retrieval/`)

```python
# Conceptual — not implemented
class EmbeddingProvider(Protocol):
    def embed(self, texts: List[str]) -> List[List[float]]: ...
    def embed_query(self, query: str) -> List[float]: ...

class LocalEmbeddingProvider(EmbeddingProvider):
    """Default: small local model, lazy-loaded."""

class HybridRelevanceEngine(RelevanceEngine):
    def __init__(self, memory_store, keyword_engine, embedder, vector_store): ...
    def search(self, project_id, query, limit=10) -> List[ScoredMemory]: ...
```

### Vector storage (local-first options)

| Option | Pros | Cons |
|--------|------|------|
| SQLite + blob column | No new deps | Slow at scale |
| sqlite-vec extension | Stays in one file | Native extension dependency |
| In-memory numpy index | Simple prototype | Lost on restart unless snapshotted |

**Recommendation:** Start with **embedding column on `memories` + brute-force cosine** for <10k items; migrate to sqlite-vec if needed.

### Candidate retrieval

1. Fetch keyword top-50 from `LayeredRelevanceEngine` (existing).
2. Fetch semantic top-50 from vector similarity.
3. Union by `memory_id`.
4. Never return items below minimum score threshold.

### Reranking

Phase 2 minimal approach:

```
final_score = 0.6 * normalized_keyword_score + 0.4 * cosine_similarity
```

Optional later: lightweight cross-encoder reranker on top-20 only.

### Context selection

Extend `ContextAssembler.assemble_context()`:

- Accept `max_tokens` budget (not just item count).
- Greedy pack by score-per-token until budget filled.
- Always include highest-confidence decision if task implies "why" intent.

### What NOT to add

- Pinecone, Weaviate, or other cloud vector DBs (Phase 2)
- Automatic LLM summarization of all memories
- Real-time embedding of every keystroke

---

## Future architecture: KSoR-inspired knowledge

KSoR (Knowledge Sources of Record) principles adapted for Overhaust:

### Data model extensions (metadata JSON → typed fields over time)

| Field | Purpose | Current status |
|-------|---------|----------------|
| `provenance` | Human-readable source | **Exists** in ingestion |
| `source_id` | Conversation/file ID | **Exists** |
| `source_type` | conversation / document / code | **Exists** |
| `confidence` | Extraction confidence 0–1 | **Exists** (heuristic) |
| `authority` | Who/what is trusted (user, indexer, agent) | **Missing** |
| `version` | Knowledge version number | **Missing** |
| `supersedes_id` | Links to replaced memory | **Missing** |
| `valid_from` / `valid_until` | Temporal validity | **Missing** |
| `evidence_refs` | List of supporting memory/file IDs | **Missing** |

### Source tracking

```
Source (conversation | file | agent_action)
    │
    ▼
Extraction (knowledge_extractions table — activate this)
    │
    ▼
Memory (promoted, queryable)
    │
    ▼
Context citation (returned to user/AI)
```

**Action:** Wire `KnowledgeExtractor` and `ConversationIngestor` to write `knowledge_extractions` before or alongside `memories`.

### Confidence and authority

| Source | Default authority | Default confidence |
|--------|-------------------|-------------------|
| User explicit decision in chat | high | 0.8+ |
| Regex extraction | medium | 0.6–0.75 |
| Agent auto-learn (`runtime.run`) | low | 0.5–0.7 |
| Project indexer (code facts) | high | 0.85+ |

Retrieval should multiply score by authority weight.

### Versioning and current vs outdated

When a new decision contradicts an old one:

1. Store new memory with `supersedes_id` pointing to old.
2. Mark old memory `status: superseded` (new status value).
3. Relevance engine demotes superseded unless query asks for history.

Stale detection already partially works via `stale_info` category and `_STALE_PATTERNS`.

### Citations

Every item in `ContextPackage.relevant_knowledge` should expose:

```json
{
  "content": "...",
  "citation": "Conversation abc123, Message #42",
  "confidence": 0.75,
  "source_type": "conversation"
}
```

Frontend shows plain language: *"From your conversation on March 5"* — not raw IDs.

### Abstention

When top retrieval score < threshold (e.g. 0.15) or gap detection flags missing evidence:

```json
{
  "abstain": true,
  "reason": "No reliable project knowledge found for this task.",
  "suggested_actions": ["Ingest a conversation about this topic", "Index your project folder"]
}
```

Extend `AgentRuntime._detect_gaps()` to drive abstention responses in API/MCP.

---

## Future architecture: Simple knowledge graph

### Goals

- Model relationships between project entities
- Improve retrieval ("what depends on X?", "what decisions affect Y?")
- **Never show graph UI to end users in Phase 2**

### Node types

| Node | Example | Source |
|------|---------|--------|
| Project | overhaust-demo | `projects` table |
| File | src/App.tsx | ProjectIndexer |
| Feature | "payment flow" | Manual or extracted |
| Component | ConnectionManager | Symbol extraction |
| Function | handleIngest | Symbol extraction |
| Decision | "use WebSockets" | Conversation ingestion |
| Memory | memory_id hash | memories table |
| Dependency | npm:react | package.json parse |

### Edge types

| Edge | Meaning |
|------|---------|
| `CONTAINS` | Project → File |
| `DEFINES` | File → Function/Component |
| `IMPORTS` | File → File/Dependency |
| `DOCUMENTS` | Memory → Decision |
| `SUPERSEDES` | Memory → Memory |
| `RELATES_TO` | Memory → Feature |
| `AFFECTS` | Decision → Component |

### Storage (SQLite — no Neo4j)

New tables:

```sql
graph_nodes (id, project_id, node_type, label, ref_id, metadata, created_at)
graph_edges (id, project_id, from_node, to_node, edge_type, weight, metadata)
```

`ref_id` links back to source row (memory id, file path, etc.).

### Graph-augmented retrieval (Phase 2D)

1. Keyword/semantic search returns seed memories.
2. 1-hop graph expansion adds related decisions/files.
3. Re-score expanded set with decay for hop distance.
4. Return flat list to user — graph is internal.

---

## Integration plan

### What to reuse (keep stable)

| Component | Reuse strategy |
|-----------|----------------|
| `MemoryStore` | Extend schema; keep `add_memory` / `get_project` API |
| `RelevanceEngine` protocol | Add `HybridRelevanceEngine` implementation |
| `ContextAssembler` | Add token-budget selection; keep `ContextPackage` shape |
| `ConversationIngestor` | Extend metadata; activate extractions table |
| `ProjectIndexer` | Feed graph builder; persist index |
| MCP tool names | Do not rename; add optional tools only |
| REST paths `/api/v1/*` | Additive endpoints only |

### What needs refactoring

| Item | Why | Effort |
|------|-----|--------|
| `OverhaustAgent.search_project_knowledge` | Uses SQL LIKE, not relevance engine | Small |
| `_get_relevant_memory` in ContextAssembler | Same issue | Small |
| Global singletons in API/MCP | Harder to test/configure | Medium |
| `services/api/main.py` sys.path hack | Fragile imports | Small |
| Project index ephemeral | Re-scan cost | Medium |

### What to add

| Module | Responsibility |
|--------|----------------|
| `packages/retrieval/embeddings.py` | EmbeddingProvider implementations |
| `packages/retrieval/hybrid.py` | HybridRelevanceEngine |
| `packages/retrieval/vector_store.py` | Local vector search |
| `packages/graph/builder.py` | Index → graph nodes/edges |
| `packages/graph/store.py` | Graph CRUD in SQLite |
| `packages/graph/expansion.py` | Hop-based retrieval boost |
| `packages/knowledge/provenance.py` | Typed provenance helpers |
| `packages/knowledge/versioning.py` | Supersede logic |

### What NOT to add

- MongoDB or cloud database migration (defer)
- Full Graphify port or external graph SaaS
- User accounts, billing, team workspaces
- Automatic cloud backup
- LLM calls in the default ingestion path (keep regex default; LLM optional later)

---

## Recommended implementation order

### Step 1 — Foundation cleanup (Phase 2A)

1. Route all search through `search_knowledge()` / `LayeredRelevanceEngine`.
2. Persist `ProjectIndex` to SQLite (`project_files`, `project_symbols` tables).
3. Wire `OVERHAUST_API_PORT`, `OVERHAUST_ALLOWED_ORIGINS`, `OVERHAUST_DEFAULT_MODEL`.
4. Add FastAPI integration tests with `TestClient` (no live server).
5. Write to `knowledge_extractions` from conversation ingestor.

**Exit criteria:** All search endpoints behave like MCP; index survives restart.

### Step 2 — Embedding layer (Phase 2B.1)

1. Define `EmbeddingProvider` protocol.
2. Add optional `LocalEmbeddingProvider` behind feature flag `OVERHAUST_EMBEDDINGS=1`.
3. Store embeddings in SQLite column on `memories`.
4. Background job to embed on memory write.

**Exit criteria:** Semantic search works offline on ingested memories; keyword-only still default.

### Step 3 — Hybrid retrieval (Phase 2B.2)

1. Implement `HybridRelevanceEngine`.
2. Inject via `ContextAssembler` constructor.
3. Add evaluation scenarios for synonym/paraphrase queries.

**Exit criteria:** Evaluation harness shows improved recall on paraphrase scenarios without keyword regression.

### Step 4 — KSoR metadata (Phase 2C)

1. Add `supersedes_id`, `authority`, `version` to metadata schema.
2. Contradiction handler on ingest (decision overrides).
3. Citation fields in API/MCP context responses.
4. Abstention flag when evidence insufficient.

**Exit criteria:** Context responses include citations; low-evidence tasks abstain with guidance.

### Step 5 — Knowledge graph (Phase 2D)

1. Create `graph_nodes` / `graph_edges` tables.
2. Build graph from project index + memories on index/ingest.
3. 1-hop expansion in hybrid retrieval.
4. No UI changes except optional "sources" list in demo.

**Exit criteria:** File→symbol→memory links queryable internally; retrieval quality improves on code tasks.

### Step 6 — Polish (Phase 2E)

1. New MCP tools: `index_project`, `ingest_conversation` (optional).
2. Expand evaluation report.
3. Update user-facing docs.

---

## Testing requirements

### Unit tests (each step)

| Area | Tests to add |
|------|--------------|
| Hybrid retrieval | Synonym match, score fusion, empty embedding fallback |
| Embeddings | Mock provider; verify store/load roundtrip |
| Versioning | Supersede demotes old; explicit "old approach" query promotes |
| Graph | Node/edge creation from indexer; 1-hop expansion |
| Abstention | Low-score query returns abstain payload |
| API | TestClient coverage for all `/api/v1/*` routes |

### Evaluation scenarios (extend `tests/evaluation/scenarios.py`)

- Paraphrase query matches ingested decision (semantic)
- Contradictory decisions → current wins
- Code symbol query retrieves correct file via graph
- Unrelated task abstains or returns empty with reason

### Regression gates

Before each phase merge:

```bash
python3 -m pytest -v
python3 scripts/verify_frontend.py
python3 scripts/demo.py
```

### Manual smoke tests

- MCP stdio roundtrip with Cursor config
- Full demo UI flow with API running
- Index a real project directory (this repo) and query file-related task

---

## Migration risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| SQLite schema migration breaks existing DBs | Medium | Versioned migrations; backup `data/` before upgrade |
| Embedding model size/complexity | Medium | Optional dependency group `pip install overhaust[embeddings]` |
| Hybrid search slower than keyword-only | High | Cache embeddings; limit candidate pool; async embed |
| Behavior change on unified search | Medium | Run A/B in evaluation harness before switching API default |
| Graph table growth | Low | Prune on project delete; cap edges per node |
| False confidence from regex | Existing | Don't auto-promote low-confidence to permanent |

### Backward compatibility

- Existing SQLite files must open without re-ingest.
- New columns nullable; new tables created with `IF NOT EXISTS`.
- MCP tool schemas remain backward compatible (new fields optional).
- Keyword-only mode remains available with `OVERHAUST_EMBEDDINGS=0`.

---

## Files changed in this audit (Phase 5 cleanup)

| File | Change |
|------|--------|
| `ARCHITECTURE_AUDIT.md` | Created — full architecture audit |
| `NEXT_PHASE_PLAN.md` | Created — this document |
| `DEVELOPMENT.md` | Created — dev setup (was referenced by README but missing) |
| `ARCHITECTURE.md` | Removed stray `EOF` line |
| `packages/memory/memory_store.py` | Wired `OVERHAUST_DB_PATH` env var |

No RAG, graph, embedding, auth, or cloud features were implemented.

---

## Quick reference: current vs future

| Capability | Today | Phase 2 target |
|------------|-------|----------------|
| Retrieval | Keyword layers | Hybrid keyword + semantic |
| Provenance | On ingested memories | Full KSoR with versioning |
| Project structure | Ephemeral index | Persisted + graph-linked |
| Citations | In metadata only | In every context response |
| Abstention | Gap hints in agent log | Structured API/MCP response |
| Graph | None | SQLite nodes/edges, hidden |
| Vector DB | None | Local embeddings in SQLite |

---

## Decision log (for future implementers)

1. **Keep SQLite** — Do not switch to MongoDB/Postgres until multi-user is a confirmed requirement.
2. **Interface-first RAG** — Implement behind `RelevanceEngine`, not as parallel code path.
3. **Graph is internal** — Users see sources and relationships in plain language, not node graphs.
4. **Embeddings optional** — Ship and test keyword path always; embeddings enhance, not replace.
5. **No LLM in default ingest** — Regex/heuristics stay default for predictability and offline use.
