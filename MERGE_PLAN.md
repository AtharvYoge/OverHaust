# Overhaust Merge Audit and Consolidation Plan

Date: 2026-08-19

Scope: audit-only comparison of the original GitHub Overhaust repo and the current Hermes Overhaust prototype. No source files were modified, no merge was performed, and no destructive git actions were taken.

## A. Repository structure comparison

### 1) High-level structure

Current Hermes Overhaust (this working repo):
- `apps/` — frontend demo
- `packages/` — Python core packages: agent, context, memory, tokenization, shared/core/storage
- `services/` — API, ingestion, agent connections, MCP server
- `scripts/` — demo, evaluation, verification scripts
- `tests/` — evaluation harness and scenario runner
- root docs: `README.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `SECURITY.md`, `DECISIONS.md`
- runtime artifacts: `.env.example`, `requirements.txt`

Original GitHub Overhaust:
- `backend/` — backend service layer
- `frontend/` — UI demo
- `memory/` — memory-related code
- `tests/` — legacy test artifacts
- `test_reports/` — reports
- root docs: `README.md`, `design_guidelines.md`, `plan.md`, `test_result.md`
- minimal developer structure compared with Hermes

### 2) Equivalent components

| Canonical concept | Old Overhaust | Hermes Overhaust |
| --- | --- | --- |
| API backend | `backend/` | `services/api/` |
| Memory store | `memory/` | `packages/memory/` |
| Context engine | conceptual in `plan.md` and docs | `packages/context/` |
| Autonomous agent | conceptual / partial | `packages/agent/` |
| Frontend demo | `frontend/` | `apps/web/` |
| Testing | `tests/`, `test_reports/` | `tests/evaluation/`, package test files |
| Ingestion | minimal or conceptual | `services/ingestion/` |
| MCP | not present | `services/mcp_server/` |
| Connection registry | not present | `services/agent/connections.py` |
| Project indexing | not present / conceptual | `services/ingestion/project_indexer.py` |
| Evaluation harness | static reports | `tests/evaluation/harness.py`, `scenarios.py`, `real_project.py` |

### 3) Components existing only in the old repository

- `backend/` as a coarse service boundary rather than the newer service module structure
- `memory/` as a more conceptual memory layer than the current packageized implementation
- `design_guidelines.md` and `plan.md` contain product, UX, and design intent that are not fully replicated in Hermes
- `test_result.md` and `test_reports/` still carry early validation notes and assumptions worth preserving
- original product positioning and the simpler “context reduction” narrative remain in the older docs

### 4) Components existing only in Hermes repository

- `packages/agent/runtime.py` — goal-directed runtime with gap detection and second-pass retrieval
- `services/mcp_server/server.py` — real stdio MCP server with tool definitions
- `services/agent/connections.py` — typed connection registry with local/API/MCP/IDE adapters
- `services/ingestion/conversation.py` — parser + classifier for raw conversation ingestion
- `services/ingestion/project_indexer.py` — project file/index scanner with symbol extraction and path constraints
- `tests/evaluation/` — structured evaluation framework and real-project validation harness
- `scripts/evaluate.py`, `scripts/e2e_demo.py`, and related runner scripts
- `apps/web` UI flow and product demo sequence (9-step marketing demo / task flow)
- richer relevance-layer and memory metadata modeling

## B. Feature comparison

| Feature | Old Overhaust | Hermes Overhaust | Best implementation | Keep / replace / merge | Reason |
| --- | --- | --- | --- | --- | --- |
| Persistent memory | SQLite-like local-first concept, basic store | Mature `MemoryStore` with metadata, types, access tracking | Hermes | Keep | More complete and operational |
| Context assembly | conceptual, simple knowledge extraction | `ContextAssembler` + `LayeredRelevanceEngine` | Hermes | Keep | More robust and task-aware |
| Relevance engine | not mature, likely keyword or conceptual | `LayeredRelevanceEngine` with phrase, keyword, intent, recency scoring | Hermes | Keep, then evolve | Better retrieval logic and explainability |
| Conversation ingestion | conceptual | `ConversationParser` + `MessageClassifier` | Hermes | Keep | Strong structured parsing and provenance |
| Project indexing | absent or minimal | `ProjectIndexer` for code/file analysis | Hermes | Keep | Critical for code/project context |
| Agent runtime | concept only | `AgentRuntime` with gap detection and second-pass retrieval | Hermes | Keep | Best operational flow |
| MCP server | absent | real stdio MCP tools | Hermes | Keep | Useful for IDE integration |
| Connection registry | absent | generic connection architecture | Hermes | Merge | Good abstraction; needs cleanup |
| API layer | basic REST concept | FastAPI endpoints with task/context/search APIs | Hermes | Keep | More concrete API surface |
| Frontend demo | basic Vite UI | richer product demo and UX flow | Hermes | Merge | Better demo narrative and flow |
| Evaluation framework | static reports | structured benchmark harness | Hermes | Keep | Needed for validation |
| Auth/security | no auth | still no auth | Old/none | Replace | Must be added before production |
| Deployment portability | local dev assumptions | still local dev assumptions | Neither | Replace | Both need env-based config |
| Knowledge graph / next phase | planned in concept | not implemented | Neither | Merge | Use as planned next architecture phase |

## C. Architecture comparison

### Backend
- Old Overhaust: simple layer split between a general backend and memory layer; better product docs than runtime implementation.
- Hermes: concrete Python backend with `services/api`, `services/ingestion`, `services/mcp_server`, and `services/agent`. More operational, but somewhat fragmented.
- Assessment: Hermes is the stronger backend starting point; old repo is the stronger product-design reference.

### Frontend
- Old Overhaust: Vite React app with simpler UI and basic API interactions.
- Hermes: richer multi-step demo flow and polished UX, but still tightly coupled to local backend assumptions (`localhost:8000`).
- Assessment: Hermes frontend is more mature as demo material, but both versions need a real production frontend contract and environment config.

### Database
- Old Overhaust: conceptual local-first design; likely intended to use SQLite/embedded storage.
- Hermes: SQLite-backed `MemoryStore` with explicit `projects`, `memories`, and `knowledge_extractions` tables.
- Assessment: Hermes wins on practicality; the upcoming architecture should preserve SQLite for local-first dev but keep a clean abstraction to support Postgres later.

### Memory architecture
- Old Overhaust: general local memory concept and context caching ideas.
- Hermes: concrete memory store with metadata, life cycle, access counts, and type annotations.
- Assessment: Hermes is the stronger implementation. The old repo’s conceptual framing helps shape the canonical product model.

### Context engine
- Old Overhaust: described architecturally but not strongly implemented.
- Hermes: real `ContextAssembler` and `LayeredRelevanceEngine` exist, but they still depend on placeholder file relevance and keyword heuristics.
- Assessment: Hermes is the better baseline, but it needs a clean contract with project indexing and knowledge graph expansion.

### Agent runtime
- Old Overhaust: product-level idea of an autonomous agent but not a working runtime.
- Hermes: actual `AgentRuntime` with task understanding, gap detection, and second-pass retrieval.
- Assessment: Hermes is clearly ahead here.

### MCP
- Old Overhaust: none.
- Hermes: actual stdio-based server and generic tool surface; good direction but not yet production-hardended.
- Assessment: Hermes should be retained; the real challenge is making it pluggable and environment-safe.

### API
- Old Overhaust: planned FastAPI-level API described in docs.
- Hermes: concrete FastAPI API is present and working as a demo backend.
- Assessment: Hermes should be the canonical API baseline, but unify routes and add auth and versioning.

### Ingestion
- Old Overhaust: conceptual instructions, not implementation.
- Hermes: parser and real project indexer are concrete and valuable.
- Assessment: Hermes clearly wins.

### Project indexing
- Old Overhaust: no real implementation.
- Hermes: `ProjectIndexer` is the strongest component in the codebase, despite being disconnected from the final context builder.
- Assessment: keep it; connect it properly to the context builder.

### Configuration
- Old Overhaust: design-oriented docs, some example paths.
- Hermes: better config ideas but still contains hardcoded local paths and no environment-driven config handling.
- Assessment: both need rewriting around env-driven configuration.

### Authentication/security
- Old Overhaust: not present in the design, explicitly noted as future work.
- Hermes: also not present; only basic CORS restriction and no auth.
- Assessment: neither is production-ready; add authentication in the merged architecture.

### Deployment
- Old Overhaust: mostly local dev docs.
- Hermes: demo-ready local dev flow with scripts, but no containerization or production deployment plan.
- Assessment: both need a deployment layer; Hermes is the better empirical base.

### Testing
- Old Overhaust: static reports, rough validation artifacts.
- Hermes: actual evaluation harness and tests; much stronger and more useful.
- Assessment: Hermes is definitely the better testing foundation.

## D. Preserve valuable old work

The original GitHub repo should not be lost because it contains:
- the high-level product narrative and positioning
- the original “context reduction” value proposition
- the design-guidelines thinking that keeps the product honest and engineering-first
- early plan and architecture docs that explain the founding intent
- the original assumptions around local-first architecture and memory retention
- static test and report artifacts that can help reconstruct early validation lessons

Most important artifacts to preserve from the old repo:
- `README.md`
- `ARCHITECTURE.md` (old conceptual architecture, if retained as historical reference)
- `design_guidelines.md`
- `plan.md`
- `test_result.md` and `test_reports/` as historical evidence

## E. Preserve valuable Hermes work

Everything in Hermes that is functionally real and not just placeholder work should be retained. Specifically:
- `packages/memory/memory_store.py` memory model and storage layer
- `packages/context/relevance.py` layered relevance engine
- `packages/context/context_engine.py` context compilation logic and token estimation integration
- `packages/agent/autonomous_agent.py` task understanding and action logging
- `packages/agent/runtime.py` highest-value runtime orchestration layer
- `services/ingestion/conversation.py` conversation parser and classifier
- `services/ingestion/project_indexer.py` project indexing and file analysis
- `services/mcp_server/server.py` robust MCP contract
- `services/agent/connections.py` registry and adapter abstraction
- `apps/web` demo UX and product narrative
- `tests/evaluation/` harness and scenario validation tooling
- `scripts/evaluate.py` and related batch validation scripts
- `requirements.txt` and the basic FastAPI + tiktoken baseline

## F. Conflicts

### 1) Duplicate functionality
- `search_memory` and `search_project_knowledge` are duplicated as aliases in the MCP server.
- `build_context` and `get_project_context` are aliases in multiple layers.
- `get_context` and `build_context` overlap in the API and agent surfaces.

### 2) Conflicting implementations
- `MemoryStore.search_memories()` uses SQL `LIKE` matching, while `LayeredRelevanceEngine.search()` does scored logic over the same data.
- `ContextAssembler` emits placeholder file relevance data, while `ProjectIndexer` is a real but disconnected code indexer.
- The app-level pipeline claims “project index connected to context builder,” but the current implementation does not actually wire those data sources together.

### 3) Incompatible APIs
- FastAPI endpoints and MCP tool names partially duplicate each other without a unified contract.
- The connection registry exposes different concepts: local, api, mcp, ide-config, but not a consistent typed interface for all runtime consumers.

### 4) Conflicting dependencies
- `requirements.txt` does not include the `mcp` package despite the server importing it.
- The frontend is a modern Vite/React setup with no repo-level lock or portability strategy.
- Some scripts and tests assume a specific developer machine path (`/Users/atharv11/Desktop/overhaust`), which is not portable.

### 5) Naming conflicts
- `knowledge_type` values are inconsistent across code: `decision`, `issue`, `open_issue`, `permanent_knowledge`, `resolved_issue`, `stale_info`, `task`, etc.
- `ContextPackage.relevant_files` and `ProjectIndexer` file metadata follow different conventions than memory metadata.
- Several modules use overlapping concepts (“context”, “memory”, “knowledge”, “state”) without a single canonical type model.

### 6) Schema conflicts
- `MemoryStore` stores metadata JSON blobs and project entries in SQLite.
- `ContextPackage` uses dataclasses and nested dictionaries that are not the same as database rows.
- `ProjectIndexer` returns file/symbol structures not yet normalized into `knowledge` objects used by the context engine.

### 7) Configuration conflicts
- Hardcoded `PYTHONPATH` and project root values appear in docs, scripts, and tests.
- Local backend and frontend are expected to run on fixed localhost ports, not env-driven configuration.

### 8) Frontend conflicts
- Frontend calls a hardcoded `http://localhost:8000` backend.
- The product flow is rich, but it assumes a specific local machine setup rather than a portable production stack.

### 9) Test conflicts
- Tests from the older repo and Hermes repo are not aligned around a single contract or database path.
- Some tests assume the global singleton is active, while others need isolated in-memory or temporary DBs.
- Evaluation harness runs are more advanced than the old repo but may still not be cross-platform.

## G. Known technical problems

### 1) Hardcoded absolute paths
Confirmed in:
- `README.md` includes `PYTHONPATH=/Users/atharv11/Desktop/overhaust python main.py`
- `scripts/verify_frontend.py` contains `WEB = "/Users/atharv11/Desktop/overhaust/apps/web"`
- `services/agent/test_connections.py` creates an IDE config using a hardcoded project root

Impact: the code is not portable, cannot be safely reused by others, and violates repo portability assumptions.

### 2) Dependency reproducibility
- `requirements.txt` is too minimal and does not include transitive dependencies or a lockfile approach.
- The repo contains a frontend `package-lock.json`, but the overall Python repo has no reproducibility mechanism beyond bare requirements.
- There is no pinned environment file or devcontainer/venv management plan.

### 3) Missing Python dependencies
The server imports `mcp`, but the repo requirement list does not include it. Additional likely missing items for a robust runtime include tooling for tests, linting, or optional AI integration. The code is therefore not reproducible in a clean environment without manual dependency resolution.

### 4) Frontend dependency portability
- Frontend is based on a modern Vite/React toolchain but still assumes a fixed local backend and repeated manual setup.
- No environment abstraction for API base URL, deploy target, or build config portability.
- The repo lacks a clear Node version policy and cross-platform validation path.

### 5) Placeholder relevant-file data
`ContextAssembler._get_relevant_files()` returns fake file names like `src/component-0.tsx` instead of actual project files. This is a direct placeholder and the code warns about it.

### 6) Project index not fully connected to context builder
`ProjectIndexer` extracts real project structure, but `ContextAssembler` ignores it and renders dummy file relevance data. This means the strongest “project-aware” feature is not yet connected to the final context-building pipeline.

### 7) Singleton/global state
- `MemoryStore` is a module-global singleton.
- `default_agent` is a module-global singleton.
- This makes tests and multi-project concurrency harder to reason about and can create cross-request contamination.

### 8) Lack of authentication
There is no user identity, token, session auth, or authorization layer in either repo. Any API or MCP server would accept unauthenticated access in a production environment.

### 9) Keyword-only relevance retrieval
The relevance engine is deterministic and heuristic, but it is still keyword-based. It contains explicit logic for phrase matching, plural tolerance, intent boosts, and recency — but no embedding/vector search and no semantic retrieval. This is acceptable as an intermediate stage, but not a final production-grade retrieval engine.

### 10) Incomplete real Cursor/agent integration
- `MCPConnection.handle()` raises `NotImplementedError` for duplex client-side calls.
- `IDEConfigAdapter` generates config blocks but marks them as `coming_soon`.
- This means the repo has a real server and config-generation idea, but not true end-to-end IDE integration.

## H. Git safety

Git inspection performed on the current working repo:
- Current branch: `atharvyoge-overhaust-merge-audit`
- Current HEAD: `b3a8f2d` (`chore(eval): refresh evaluation_report.md from latest run`)
- Uncommitted changes: none (`git status --short --branch` was clean)
- Important commits in the current history (and likely the branch worth preserving):
  - `b3a8f2d` — evaluation refresh
  - `bc8b1af` — real-world validation harness
  - `f742ba3` — full product UX demo flow
  - `6815acf` — changelog/docs update
  - `4924a3b` — API ingestion/indexing/connections endpoints
  - `b778f5b` — generic connection registry
  - `df5acac` — real MCP stdio server
  - `e6b5dbc` — autonomous runtime
  - `bde83d3` — relevance improvements
  - `2c1b4ce` — context builder and relevance-driven retrieval
  - `85c89cd` — project indexer
  - `2e6c936` — conversation parsing and ingestion
  - `12c711d` — security hardening and DB path portability
  - `27bff7d` — working prototype with API, frontend, demo

Conclusion: the current branch is not dirty, and the code history contains multiple valuable functional milestones. The old GitHub repo still holds design and product intent worth preserving, but the current repo contains the more complete implementation path.

## I. Recommended canonical architecture

The merged architecture should follow the planned direction without prematurely implementing a graph database layer:

Conversation + Documents + Code + Project State
 ↓
 Overhaust Memory
 ↓
 Knowledge Graph
 ↓
 Relevance Engine
 ↓
 Context Builder
 ↓
 Optimized Context
 ↓
 AI Agent / MCP

### Canonical architecture components

1. Ingestion layer
- Conversation parser and message classifier
- Document ingestion and file ingestion adapters
- Source provenance tracking
- Dedupe and structured memory extraction

2. Overhaust Memory
- SQLite first, local-first storage
- Raw memory tables, project metadata, and source provenance
- Clean CRUD layer with explicit schema boundaries
- Replace global singleton usage with dependency-injected stores and per-request/session instances

3. Knowledge Graph (planned next step; Graphify-inspired)
- Graph nodes for project concepts, decisions, files, issues, tasks, symbols, states
- Relationship modeling without implementing full graph complexity in this phase
- Leave this as a future extension on top of the memory layer

4. Relevance Engine
- Keep `LayeredRelevanceEngine` as the canonical retrieval implementation for this phase
- Add semantic/vector retrieval as an optional later layer behind the same interface
- Keep ranking reasons and explainability

5. Context Builder
- Consume memory + graph + project index outputs
- Select relevant knowledge and files using scored retrieval, not placeholder mocks
- Build a final “optimized context” for an agent task

6. AI Agent / MCP layer
- Use one canonical runtime for agent planning and memory updates
- MCP server tools should expose the same underlying engine surface as the API
- Keep connection registry and IDE adapter generation, but treat as integration scaffolding not the core engine

### Non-goals for this phase
- Do not implement Graphify or a heavy graph database in this merge phase.
- Do not overengineer auth or multi-tenant deployment in the first consolidation.
- Do not force all components into a single monolith; keep service boundaries clear.

## J. Final recommendation

1. What should become the canonical codebase
- The Hermes Overhaust repository should be the canonical implementation base, because it contains the actual runtime, MCP server, project indexer, context engine, evaluation harness, and working product demo.
- The old GitHub repo should remain the canonical design reference for product vision and architecture thinking.

2. What should be copied from the old repository
- Product narrative and marketing insight
- Original architectural intent and “context reduction” framing
- Design docs and early product plan
- Legacy test artifacts as historical validation context

3. What should be retained from Hermes
- Everything in `packages/agent`, `packages/context`, `packages/memory`, `services/ingestion`, `services/mcp_server`, `services/agent/connections.py`, and the evaluation harness
- The frontend demo flow, with improvements to portability and config handling
- The working API interface as the starting point for a cleaner unified contract

4. What should be rewritten
- Environment/config management for all local path assumptions
- Connection registry to standardize interfaces and reduce duplication
- Memory store + singleton usage pattern to support test isolation and multi-instance contexts
- `ContextAssembler._get_relevant_files()` so it reads real project index results instead of dummy data
- Relevance layer contract and schema naming to unify memory metadata / knowledge types / project/index data
- Auth and security model before any production deployment

5. What should be deleted
- Placeholder file relevance data generation
- Hardcoded developer-specific paths in scripts, docs, and tests
- Obsolete duplicate API/method aliases that do not add real semantics
- Unused or dead config adapter generation for IDEs until end-to-end real validation exists
- Any duplicate or non-canonical route names that create ambiguity

6. What must be tested after merging
- Database portability and temp-path behavior
- Project indexer → context builder connectivity
- Relevance ranking robustness on real project data
- API + MCP tool parity
- End-to-end ingestion pipeline from conversation or project to memory and context
- Auth and authorization flow if added
- Cross-platform frontend build and backend startup
- Evaluation benchmarks and regression tests

7. Recommended merge order
1. Preserve and normalize docs and product intent from old repo
2. Standardize config and path portability (remove hardcoded paths)
3. Unify memory store and singleton patterns behind injectable services
4. Connect project indexer to context builder and remove placeholder file data
5. Merge API + MCP surface into a single canonical runtime contract
6. Merge evaluation harness and fix test compatibility
7. Rework frontend to use env-driven config and real backend contract
8. Add security/auth baseline and deployment config
9. Only after this, consider the Graphify-inspired knowledge graph phase

Final assessment: Hermes is the clearer implementation base, while the old GitHub repo is the clearer product and design reference. The right merge is not a raw overwrite or a straight copy. It is a guided consolidation: keep Hermes as the engineering baseline, copy the valuable design intent from the older repo, and rewrite the weak points around config, portability, indexing connectivity, and security.
