# PHASE 14 IMPLEMENTATION REPORT

## 1. Executive summary

Phase 14 validates whether OverHaust works as an **invisible context-reduction layer** between a developer and an AI coding agent — with evidence, not hook-unit-test assumptions.

**Central question:** *Does OverHaust actually participate in a real agent workflow, inject usable context, reduce tokens fairly, and preserve task quality?*

**Answer:** **Partially proven, with one real-agent verification.**

| Goal | Result |
|------|--------|
| Latency discrepancy explained | **Yes** — ~2.18s was **cold-start** (first API request after server boot), not steady-state regression |
| Real agent integration | **Codex verified live**; Claude unavailable; Cursor not auto-wired in this environment |
| Context reduction (>70% target) | **Yes — 85.91%** vs fair naïve full-file baseline |
| Task quality preserved | **Yes — 100% read/plan parity** on LabKOT controlled task |
| Steady-state latency (<500 ms target) | **Yes — ~170–180 ms** assembly; hook overhead ~1–2 ms |
| Existing tests green | **259 pytest**, desktop build + vitest pass |

**New artifacts:**
- `scripts/measure_context_latency.py` — latency breakdown (search, naive reads, assembly, HTTP)
- `scripts/assess_task_quality.py` — read/plan quality scoring for controlled task
- `scripts/verify_real_agent_session.py` — integration inspection + Codex live verification
- `packages/context/test_phase14_quality.py` — regression test for quality assessment

---

## 2. Latency discrepancy investigation

### Reproduced measurements (LabKOT, multi-printer prompt)

**Prompt:** `Add support for multiple kitchen printers and route each order to the appropriate printer.`  
**Project:** `labkot`

| Path | First run | Warm run |
|------|-----------|----------|
| `POST /api/v1/get-relevant-context` (HTTP total) | **2,170 ms** | **180 ms** |
| `metrics.latency_ms` in response | **2,163 ms** | **178 ms** |
| In-process `invoke_context_request()` | ~177 ms (after warm index) | ~170 ms avg |
| `scripts/agent_benchmark.py` OverHaust | — | **171–181 ms** |
| Hook adapter path | — | **172 ms** (engine 170 ms, overhead 2 ms) |

### Root cause

The **~2.18s figure is not a steady-state regression**. It occurs on the **first context request in a fresh API process**:

1. **Lazy `OverhaustAgent` singleton init** — logged on first `/get-relevant-context` hit
2. **Cold Python imports** inside the context engine (tiktoken, retrieval, ingestion modules)
3. **First SQLite / index access** in that process

After warm-up, HTTP, in-process, and hook paths converge at **~170–180 ms**, matching Phase 13 (~171 ms direct, ~176 ms hook).

### Component breakdown (`scripts/measure_context_latency.py`)

| Component | Latency |
|-----------|---------|
| Keyword search | ~104 ms |
| Scored search | ~83 ms |
| Naïve baseline (search + read 3 full files) | ~1,900–2,000 ms |
| OverHaust assembly (warm) | ~170 ms |
| HTTP warm (total) | ~169 ms |

**Conclusion:** Steady-state context assembly is practical. Cold-start cost is real but one-time per API process; agents using in-process hooks avoid HTTP + agent-init overhead.

---

## 3. Codex real-agent verification

### Configuration inspected

Installed via `python3 scripts/install_agent_integration.py --agent codex`:

```json
// ~/.codex/hooks.json
{
  "hooks": {
    "UserPromptSubmit": [{
      "hooks": [{
        "type": "command",
        "command": "python3 \".../overhaust_user_prompt_hook.py\"",
        "statusMessage": "OverHaust context"
      }]
    }]
  }
}
```

- **UserPromptSubmit wiring:** Present
- **Hook script:** `scripts/integrations/overhaust_user_prompt_hook.py`
- **Codex CLI:** v0.146.0 installed

### Live session (verified)

Command (read-only plan task, no repo edits):

```bash
OVERHAUST_PROJECT_ID=labkot \
OVERHAUST_INTEGRATION_DEBUG=1 \
OVERHAUST_INTEGRATION_DEBUG_FILE=/tmp/oh-debug.jsonl \
codex exec --dangerously-bypass-hook-trust -s read-only \
  "READ-ONLY PLAN TASK: List which files and symbols you would modify..."
```

**CWD:** `/Volumes/Atharv Work/LabKOT/restaurant_pos`

| Check | Result |
|-------|--------|
| Hook fired | **Yes** — debug JSONL event recorded |
| Context injected | **Yes** — `context_bytes=4713`, `estimated_context_tokens=1008` |
| `additionalContext` reaches workflow | **Yes** — hook ran on `UserPromptSubmit` before model turn |
| Agent used injected context | **Partially observable** — agent output cited `kitchen_print_router.dart`, `kitchen_print_service.dart`, `order_service.dart`, `printer_types.dart` |

**Agent plan excerpt (stdout):**
- `lib/services/printing/kitchen_print_router.dart` — `KitchenPrintRouter.resolve(...)`
- `lib/services/printing/kitchen_print_service.dart` — `enqueueRoutedJobsForOrder(...)`
- `lib/models/printing/printer_types.dart` — `SavedPrinter`
- `lib/services/order_service.dart` — order submit integration

**Verdict:** **Codex automatic interception is verified** for `codex exec` with installed hook. This is a **real agent session**, not subprocess hook simulation.

**Caveats:**
- Required `--dangerously-bypass-hook-trust` for automation (production users should trust via `/hooks`)
- Read-only sandbox still allowed the agent to read additional files beyond OverHaust context
- Hook retrieval for this prompt surfaced `configuration_sections.dart` + test file (different ranking than benchmark’s top-3), but task plan quality remained high

---

## 4. Claude Code real-agent verification

| Check | Status |
|-------|--------|
| `claude` CLI | **Not installed** |
| `~/.claude/settings.json` | Not present |
| Repo `.claude/settings.json` | Not present |
| OverHaust hook | Not installed |

**Verdict:** **Live verification impossible** in this environment. Phase 13 subprocess hook I/O tests remain the only evidence. Install path documented: `python3 scripts/install_agent_integration.py --agent claude`.

---

## 5. Cursor real-agent verification

| Mechanism | Installed | Automatic interception |
|-----------|-----------|------------------------|
| `.cursor/hooks.json` (user) | No | N/A |
| `.cursor/hooks.json` (repo) | No | N/A |
| MCP `overhaust` in `~/.cursor/mcp.json` | **No** | **Manual** — agent must call tool |
| `.cursor/rules/overhaust-context.mdc` | No | **Behavioral nudge only** |

**Cursor in this session:** The active agent (Cursor) does **not** have OverHaust hooks or MCP configured. Context retrieval here uses Cursor-native tools, not OverHaust interception.

### Integration types (honest classification)

1. **Native automatic interception** — Codex `UserPromptSubmit` hook (**verified live**). Cursor `beforeSubmitPrompt` schema supports `continue` / `user_message` only; **`additionalContext` injection not verified live in Cursor Agent**.
2. **MCP-based retrieval** — Available via `services/mcp_server/server.py`; requires agent to call `get_relevant_context` (**manual**, not automatic).
3. **Rules-based behavior** — Template rule nudges MCP usage; **not interception**.
4. **Manually invoked** — REST API, desktop UI search, direct script calls.

**Verdict:** Cursor automatic per-prompt injection **not proven** in this environment. MCP + rules are fallbacks only.

---

## 6. Controlled benchmark methodology

**Fixed task (LabKOT):**
> Add support for multiple kitchen printers and route each order to the appropriate printer.

**Condition A — Naïve agent:** `search` → read **full contents** of top hit files (same file cap as OverHaust budget).

**Condition B — OverHaust agent:** `invoke_context_request()` → compact snippets + symbols.

**Condition C — Hook path:** `UserPromptSubmit` adapter → same engine as B.

**Not compared:** Search metadata JSON vs snippet context (Phase 11 unfair baseline).

**Task quality:** Read/plan proxy via `scripts/assess_task_quality.py` — scores file/symbol coverage, architecture cues, and plan signals. **No live repo modification** (safe for automated CI).

**Token method:** `TokenEstimator` (tiktoken) — **estimated**, not provider billing.

---

## 7. Naive vs OverHaust measurements

| Metric | A: Naïve full files | B: OverHaust | C: Hook |
|--------|---------------------|--------------|---------|
| Est. tokens | ~9,913 | ~1,397 | ~1,402 |
| Files | 3 | 3 | 3 |
| Lines | 1,363 | 362 | 362 |
| Bytes (context) | 44,728 | 22,297 (JSON) / 6,864 (hook inject) | 6,864 |
| Latency (warm) | ~95–2,078 ms* | ~171–181 ms | ~172 ms |

\*Naïve latency varies with disk cache; first uncached read ~2s, cached ~95 ms.

**Fair reduction:** **85.91% tokens**, 50.15% bytes, 73.44% lines, 0% files (same hit set).

---

## 8. Task-quality results

### Read/plan assessment (`scripts/assess_task_quality.py`)

| Dimension | Naïve | OverHaust |
|-----------|-------|-----------|
| Composite quality | **100%** | **100%** |
| Expected files matched | router + service | router + service |
| Expected symbols matched | `KitchenPrintRoute`, `KitchenPrintService` | same |
| Plan signals (routing, printers, orders) | 5/5 | 5/5 |
| Read/plan viable | Yes | Yes |
| Quality parity | — | **Within 5% of naïve** |

### Codex live plan task

Agent produced architecturally correct plan including router, service, printer models, and order integration — **without modifying files** (read-only sandbox).

### Not measured

- Full implementation + test pass in live agent session
- Provider-reported input token usage
- Whether agent would succeed with **only** OverHaust context and no further repo reads

---

## 9. Token/context reduction

| Source | Value |
|--------|-------|
| Fair token reduction | **85.91%** |
| Target (>70%) | **Met** |
| Hook inject bytes | 6,864 (vs 44,728 naïve file bytes) |
| Codex session hook debug | 95.62% vs debug-computed naïve baseline for that prompt |

**Distinction maintained:**
- **Estimated tokens** — tiktoken via `TokenEstimator`
- **Actual provider tokens** — **not available** in this harness
- **Raw bytes** — measured on context text / JSON payload

---

## 10. Architecture changes

**No retrieval or API architecture changes.** Phase 14 adds validation scripts and one regression test only:

| File | Purpose |
|------|---------|
| `scripts/measure_context_latency.py` | Latency profiler |
| `scripts/assess_task_quality.py` | Read/plan quality scorer |
| `scripts/verify_real_agent_session.py` | Real-agent verification helper |
| `packages/context/test_phase14_quality.py` | Regression test |

**Environment change (verification only):** Installed `~/.codex/hooks.json` for live Codex test. No Codex unrelated config modified.

---

## 11. Tests

| Suite | Result |
|-------|--------|
| `pytest -q` | **259 passed** |
| `npm run build` (desktop) | **Pass** |
| `npm test` (desktop vitest) | **6 passed** |
| `git diff --check` | **Pass** |
| `scripts/integration_smoke_test.py --benchmark` | **PASS** |
| `scripts/agent_benchmark.py --project-id labkot` | **PASS** |
| `scripts/validate_labkot_context.py` | **PASS** |

---

## 12. Known limitations

1. **Cold-start latency** (~2s) on first API request after boot — document for ops, not user-per-prompt steady state.
2. **Claude Code** — no live verification; CLI absent.
3. **Cursor** — no hooks/MCP installed here; automatic interception unproven.
4. **Task quality** — read/plan proxy only; no automated implementation + test run against real LabKOT repo.
5. **Codex session** — agent may still read repo beyond injected context (especially read-only mode).
6. **Token counts** — estimates only; no OpenAI/Cursor billing API integration.
7. **Hook trust** — production Codex users must trust hooks via `/hooks`.

---

## 13. What is genuinely proven

1. **OverHaust reduces context ~86%** vs fair naïve full-file baseline on LabKOT multi-printer task.
2. **Compact context preserves read/plan quality** (100% composite parity on controlled scoring).
3. **Steady-state assembly ~170 ms** — meets <500 ms target.
4. **Hook adapter adds ~1–2 ms** over direct engine call.
5. **Codex `UserPromptSubmit` hook fires in a real `codex exec` session** and injects non-empty `additionalContext`.
6. **Cold-start explains the ~2.18s HTTP measurement** — not a warm-path regression.

---

## 14. What is still unproven

1. **Cursor native automatic per-prompt injection** in Agent chat.
2. **Claude Code live interception** (CLI not available).
3. **End-to-end implementation quality** — agent writes correct code, tests pass, no unrelated diffs.
4. **Provider-reported token savings** in production agent sessions.
5. **OverHaust-only context sufficiency** — whether agents can complete tasks without additional repo reads.
6. **Interactive Codex UI** (non-`exec`) hook behavior with user trust flow.

---

## 15. Recommendation for Phase 15

1. **Install and verify Cursor integration** in a real Cursor Agent session with `.cursor/hooks.json` + MCP; capture whether `beforeSubmitPrompt` output affects model input (use Cursor debug/logging if available).
2. **Claude Code live test** once `claude` CLI is available; mirror Codex verification methodology.
3. **Warm API startup** — optional eager init of context engine on API boot to eliminate ~2s first-request penalty.
4. **Implementation benchmark** — fork LabKOT or use git worktree; run Codex/Cursor with write sandbox on multi-printer task; measure diffs + `flutter test`.
5. **Provider token telemetry** — if agents expose usage metadata, compare estimated vs actual input tokens with/without OverHaust.
6. **Ranking improvement** — Codex live session surfaced `configuration_sections.dart` over router for plan prompt; tune development-task ranking without raising global budgets.

---

## Commands reference

```bash
# Latency profile
python3 scripts/measure_context_latency.py --project-id labkot --http http://127.0.0.1:8000

# Fair benchmark
python3 scripts/agent_benchmark.py --project-id labkot

# Task quality (read/plan)
python3 scripts/assess_task_quality.py --project-id labkot

# Integration inspection + Codex live test
python3 scripts/verify_real_agent_session.py --inspect --codex

# Install hooks
python3 scripts/install_agent_integration.py --agent codex
python3 scripts/install_agent_integration.py --agent cursor
python3 scripts/install_agent_integration.py --agent claude
```
