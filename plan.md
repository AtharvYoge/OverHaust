# OverHaust — Development Plan (MVP)

## 1) Objectives
- Prove the core: **LLM-powered Context Cache generation** + **task-relevant context assembly** from large raw inputs.
- Ship a dark-first web app with the primary flows: **Project → Add Context → Build Context Cache → View Cache → Generate Task Context**.
- Persist data: MongoDB (server) + IndexedDB (local cache) with clear “estimated tokens” metrics.
- Deliver a polished v1 UX (Linear/Vercel/Raycast feel) with basic analytics + integrations preview.

---

## 2) Implementation Steps

### Phase 1 — Core POC (LLM in isolation; must work before app)
**User stories (POC):**
1. As a builder, I can submit a large mixed context blob and receive a **valid structured JSON Context Cache**.
2. As a builder, I can submit a task prompt and get a **relevant subset** of the cache + an “AI-ready context block”.
3. As a builder, I can see robust validation errors when the LLM output is malformed.
4. As a builder, I can run the POC repeatedly on LabKOT sample and get stable category coverage.
5. As a builder, I can estimate tokens deterministically (chars/4) without calling an LLM.

**Steps:**
- Add `EMERGENT_LLM_KEY` to backend `.env`; choose model for POC (OpenAI `gpt-4.1-mini` or Anthropic `claude-haiku-4-5-20251001`).
- Define strict Pydantic schemas for:
  - `ContextCache` (Identity, Architecture, Components, Decisions, Current State, Conversation Memory buckets)
  - `TaskContextResult` (relevant_items, ignored_items, assembled_context_block)
- Write a standalone Python script (`backend/poc_context_runtime.py`) that:
  - Loads LabKOT sample context
  - Calls `emergentintegrations.llm.chat.LlmChat.stream_message()`
  - Forces JSON-only output (prompt contract) and validates with Pydantic
  - Runs task selection against the produced cache
- Fix until it works: iterate prompt + schema until success rate is high on repeated runs.
- Minimal “best practices” websearch target: structured JSON prompting + schema validation patterns for streamed LLM outputs.

**Exit criteria (Phase 1):**
- POC consistently returns valid JSON for both cache generation and task-context selection.

---

### Phase 2 — V1 App Development (no auth yet)
**User stories (V1 core app):**
1. As a user, I can create a project with name/description/stack and immediately start adding context.
2. As a user, I can paste/upload context across tabs (Conversation/Docs/Files/Notes) and see it stored.
3. As a user, I can click “Build Context Cache” and watch an animated analysis pipeline to completion.
4. As a user, I can browse the Context Cache by category and quickly understand the project.
5. As a user, I can enter a task, generate optimized context, and copy it with one click.

**Backend (FastAPI + Mongo):**
- Replace template endpoints with:
  - Projects CRUD
  - Context ingestion (text + uploaded files metadata)
  - Build cache (async job-like endpoint; initial MVP can be synchronous with progress mocked)
  - Task context generation (uses stored cache)
- Implement “Hybrid” rules:
  - Real LLM for: `analyze_context()` + `select_relevant_context()`
  - Deterministic `TokenEstimator` for all displayed token counts
- Store:
  - Raw context sources (by type)
  - Generated cache JSON + timestamps + version
  - Task runs (prompt + output + metrics)

**Frontend (React + TypeScript + Tailwind + Radix):**
- Convert to TypeScript; set up typed API client.
- Routing:
  - `/` Landing (marketing)
  - `/app/*` App shell
- App shell UI:
  - Sidebar: Overview, Projects, Context Cache, Tasks, Analytics, Integrations, Settings
  - Dark-first theme defaults
- Screens (MVP):
  - Projects list + create
  - Project detail with Context tabs + upload
  - “Build Context Cache” pipeline animation view
  - Context Cache viewer (7 categories)
  - Task Context generator (relevant vs ignored + context block + copy)
  - Compression viz (before/after + reduction % + “estimated”)
  - Local knowledge status card (IndexedDB sync state)

**Local persistence (IndexedDB):**
- Cache last Context Cache + last task contexts per project.
- Show “Active / last updated / cache size / knowledge items / refresh” card.

**Conclude Phase 2:**
- Run `testing_agent_v3` for one end-to-end pass: create project → ingest context → build cache → generate task context.

---

### Phase 3 — Add requested features + polish
**User stories (expansion):**
1. As a user, I can see analytics for context size reduction over time per project.
2. As a user, I can compare runs (tokens/items/files) in a clear table.
3. As a user, I can trigger incremental updates and see what changed.
4. As a user, I can explore Integrations/MCP preview and understand how it will connect.
5. As a user, I can preload the LabKOT demo project and click through the full flow.

**Additions:**
- Analytics page: charts for before/after, tasks, cache updates, “most-used knowledge”.
- Comparison table view across cache builds / task runs.
- Incremental update MVP: diff context sources by hash → if changed, rebuild cache; show “changed inputs” list.
- Integrations/MCP page: Coming Soon cards + mock command + mock tool list.
- Preloaded LabKOT dataset seed endpoint + one-click import.

**Conclude Phase 3:**
- Run `testing_agent_v3` again on both blank project + LabKOT demo.

---

### Phase 4 — Simple email-only demo auth (last)
**User stories (auth):**
1. As a user, I can log in with email and keep my projects separated from others.
2. As a user, I can log out and see the app return to demo login.
3. As a user, I can keep using the app without password resets or complex flows.
4. As a user, I can revisit later and see my projects restored.
5. As a user, I can still use local IndexedDB cache to load faster after login.

**Steps:**
- Add minimal login (email-only) + JWT; scope Mongo queries by `user_id`.
- Migrate existing demo data path to a “demo user”.
- Final test pass with `testing_agent_v3`.

---

## 3) Next Actions
1. Implement Phase 1 POC script + schemas and run it on LabKOT sample until stable.
2. Lock prompts (analysis + selection) and store them in versioned files.
3. Convert frontend to TypeScript + create app shell routes (`/` and `/app/*`).
4. Build minimal backend endpoints for projects/context/cache/task.

---

## 4) Success Criteria
- POC: Validated `ContextCache` JSON + `TaskContextResult` produced reliably from large inputs.
- App: User can complete the full core flow in <5 minutes with no dead ends.
- Metrics: Token estimates shown everywhere with clear “estimated” labeling; reduction % matches demo narrative.
- Persistence: Mongo stores canonical data; IndexedDB improves perceived performance and shows accurate status.
- Testing: `testing_agent_v3` passes end-to-end on at least 2 scenarios (fresh project + LabKOT demo).
