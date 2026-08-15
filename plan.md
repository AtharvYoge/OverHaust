# OverHaust — AI Memory Layer (Universal) — Revision Plan (MVP)

## 1) Objectives
- Reposition OverHaust as a **universal AI Memory Layer**: simple UX, non-technical language; sophisticated engine stays under the hood.
- Preserve the working backend LLM core (**analyze_project_context + select_relevant_context**) and current APIs; keep all savings clearly labeled **estimated**.
- Add new user-facing pillars: **Connections** (agent-agnostic) and **Usage** (Simple/Advanced + plan advisor).
- Simplify app IA + navigation: **Home, My Projects, AI Memory, Usage, Connections, Settings**.
- Maintain **local-first** behavior (IndexedDB mirror) and fast “ready” feel.

---

## 2) Implementation Steps

### Phase 1 — Core Flow POC (UX + copy, engine untouched)
**User stories**
1. As a non-technical user, I can understand OverHaust in <10s on the landing page.
2. As a user, I can add information and see a simple “reading → organizing → ready” progress experience.
3. As a user, I can ask “what am I working on?” and get a prepared block to copy into my AI tool.
4. As a user, I can view savings in a Simple view without needing to understand tokens.
5. As a power user, I can switch to Advanced view and see token numbers labeled as estimates.

**POC tasks (must be stable before broad UI rewrite finishes)**
- Rewrite **Landing hero + sections** to consumer messaging (no MCP/context window/etc. above the fold).
- Implement a minimal **Prepare for AI** panel (input → call existing `/tasks` → show Relevant / Not needed + Copy).
- Implement a minimal **AI Memory view** (read latest cache → display “Things your AI knows” categories).
- Verify LabKOT demo end-to-end: **seed → add info (optional) → build memory → prepare for AI**.

---

### Phase 2 — V1 App Development (new IA + simplified product surface)
**User stories**
1. As a user, I can navigate clearly using Home / Projects / AI Memory / Usage / Connections / Settings.
2. As a user, I can create a project and add knowledge using simple options (paste, files, notes).
3. As a user, I can see a friendly processing overlay while my AI Memory is being updated.
4. As a user, I can prepare a task for my AI and copy the result in one click.
5. As a user, I can understand estimated savings and why I might not need to buy more credits.

**Frontend (React) changes**
- Landing page rebuild:
  - Hero: “Are Your AI Tokens Finishing Too Fast?” + CTAs “Try It Free” / “See How It Works”.
  - Add “Sound Familiar?” pain cards.
  - Add simple animation section (“Everything you give your AI → Our AI Layer → Only useful info”).
  - Add “Built for Anyone Who Uses AI” audience grid.
  - Add “Connect to tools you already use” integrations preview with accurate statuses.
  - Add Pricing section (Free/Pro/Team) as static.
- AppShell rename + nav update:
  - Replace “Overview/Analytics/Integrations” framing with **Home, My Projects, AI Memory, Usage, Connections, Settings**.
- Home dashboard:
  - Add “You’re getting more from your AI” hero card with before/after bars + “estimated unnecessary usage reduced”.
  - KPI cards: Information saved, Usage reduced, Projects, Connected agents (all estimated where needed).
- Project detail simplification:
  - Rename “Context Cache” → **AI Memory**; rename “Task Context Generator” → **Prepare for AI**.
  - “Give Your AI More Knowledge” intake with big options (paste/upload/notes/import conversation placeholders).
  - Processing overlay copy updated to non-technical steps.
  - Relevance output labels: **Relevant information** vs **Not needed right now**.
  - Keep token details behind **Simple/Advanced** toggle.
- Add new pages:
  - **AI Memory**: per-project memory categories + “Recently updated”.
  - **Usage**: Simple/Advanced toggle; Credit-savings narrative; “Before you buy more credits…” section.
  - **Connections**: agent cards (Available/Coming Soon/Compatible through Agent Connection) with no false claims.

**Backend (FastAPI) additions (keep engine untouched)**
- Add a small **usage service boundary** (new module) that computes estimates from existing cache/task metrics:
  - endpoints (MVP): `GET /api/usage/summary`, `POST /api/usage/plan-advice` (pure estimate + disclaimers).
- Add a small **connections service boundary** (new module) with persisted connection records:
  - endpoints (MVP): `GET/POST/DELETE /api/connections` storing {agent_name, status, notes}.
- Keep existing project/context/cache/task endpoints unchanged; reuse seeded LabKOT.

**Local-first**
- Extend IndexedDB usage to also store:
  - last usage summary per user (optional)
  - last prepared “copy block” per project

**Conclude Phase 2**
- Run automated end-to-end test pass (existing suite + update selectors/testIds where labels changed).

---

### Phase 3 — Feature Expansion + Polish (agent-ready architecture, still simple UX)
**User stories**
1. As a user, I can see “Knowledge ready in Xms” measured locally (real timings, no inflated claims).
2. As a user, I can view Usage savings by project and month (estimated).
3. As a user, I can see what changed since last AI Memory update (“new info detected”).
4. As a user, I can manage connections (add/remove) without setup complexity.
5. As a technical user, I can find “For developers / How it works” deeper section without it dominating.

**Work**
- Implement measured latency metrics on key actions (local timing + API timing).
- Add Usage history charts sourced from existing cache builds + tasks (no provider billing claims).
- Strengthen service boundaries in code structure (knowledge ingestion, memory, relevance, context prep, usage, connections) without overbuilding.
- Copy + micro-UX polish: consistent disclaimers, empty states, and Simple/Advanced toggles.

**Conclude Phase 3**
- Run full regression tests + manual demo run using LabKOT.

---

## 3) Next Actions
1. Rewrite Landing page content + sections per new positioning (keep dark teal aesthetic).
2. Update AppShell navigation + routes to new IA; keep old pages temporarily mapped until replaced.
3. Implement “Prepare for AI” simplified panel using existing `/tasks` endpoint + new labels.
4. Add **Usage** + **Connections** pages (UI) and minimal backend endpoints for estimates + stored connections.
5. Update testIds/e2e flows and run full test suite.

---

## 4) Success Criteria
- A first-time visitor understands the product in **10 seconds** without technical jargon.
- Core demo works end-to-end: **seed LabKOT → build AI Memory → prepare for AI → copy block**.
- Dashboard and Usage clearly emphasize **credit/usage savings** with **estimated** labeling.
- Connections page is agent-agnostic and does not claim unbuilt integrations.
- Local-first mirror works: cache/task outputs load quickly; no regressions in existing workflows.
- Automated tests pass with updated labels/routes; no broken navigation or dead ends.
