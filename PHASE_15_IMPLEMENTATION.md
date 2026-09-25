# Phase 15 — Real Coding Task Validation

## 1. Executive Summary

Phase 15 answers: **Can a real AI coding agent write correct code using dramatically less repository context because OverHaust selected the relevant context?**

**Answer: Yes — on Codex, with caveats.**

| Success criterion | Result |
|-------------------|--------|
| A. Real agent receives OverHaust context automatically | **Codex verified** (UserPromptSubmit hook, write-enabled) |
| B. Write-enabled controlled task completed | **Yes** — both conditions produced passing implementations |
| C. Relevant tests pass | **Yes** — `kitchen_print_service_test.dart` passes in both copies |
| D. Context reduction >70% | **Yes — 85.91%** (fair baseline) |
| E. No meaningful quality degradation | **Yes** — parity on automated quality checks |
| F. Cursor / Claude status honestly established | **Cursor: NOT AVAILABLE**; **Claude: NOT INSTALLED** |

**Key finding:** OverHaust compact context (~1,397 est. tokens) enabled Codex to complete the LabKOT multi-printer implementation task in **154s** with **focused diffs** and **passing tests**. The naïve full-file hook condition (~9,913 est. tokens) also succeeded but took **288s** and required more repository exploration (`rg`, broad reads).

**Important caveat:** LabKOT baseline (`7428be4`) **already contained** multi-printer routing (`KitchenPrintRouter`, category fan-out tests). The task became a **refinement/extension** exercise, not greenfield implementation. Both agents added regression tests for edge cases in catch-all routing.

**Canonical LabKOT repository was not modified.** All writes occurred in disposable clones under `benchmark-runs/phase15-20260902T110229Z/`.

---

## 2. Baseline Tests

Recorded before Phase 15 changes:

| Check | Result |
|-------|--------|
| `pytest -q` | **259 passed** |
| `npm run build` | **Pass** |
| `npm test` | **6 passed** |
| `git diff --check` | **Pass** |
| `integration_smoke_test.py --benchmark` | **PASS** (85.91% token reduction) |

After Phase 15 additions:

| Check | Result |
|-------|--------|
| `pytest -q` | **260 passed** (+1 implementation quality test) |

No retrieval engine behavior was changed.

---

## 3. Cursor Verification

**Classification: NOT AVAILABLE**

### What exists (templates + installer)

| Artifact | Location | Installed in this environment |
|----------|----------|-------------------------------|
| Hook template | `integrations/templates/cursor/hooks.json` | **No** |
| MCP template | `integrations/templates/cursor/mcp.json` | **No** (user `~/.cursor/mcp.json` has dart/render/aws only) |
| Rules template | `integrations/templates/cursor/rules/overhaust-context.mdc` | **No** |
| Repo `.cursor/hooks.json` | OverHaust-1 repo | **No** |
| User `.cursor/hooks.json` | `~/.cursor/hooks.json` | **Does not exist** |

Installer: `python3 scripts/install_agent_integration.py --agent cursor` writes repo hooks, merges MCP into `~/.cursor/mcp.json`, copies rules.

### Automatic interception assessment

- Cursor hook event: `beforeSubmitPrompt`
- Documented output schema: `continue` / `user_message` — **`additionalContext` injection not documented**
- **No programmatic API** to drive Cursor Agent chat and observe injection from this harness
- Real session requires manual user interaction in Cursor IDE

### Real session test

**Not performed.** Blocker: Cursor Agent cannot be triggered programmatically; no OverHaust hooks/MCP/rules installed for LabKOT or OverHaust repo.

If hooks were installed, result would still be **UNVERIFIED** until a human Agent session confirms context reaches the model.

---

## 4. Claude Verification

**Classification: NOT INSTALLED**

| Check | Status |
|-------|--------|
| `claude` CLI | **Not found** |
| `~/.claude/settings.json` | **Not present** |
| Repo `.claude/settings.json` | **Not present** |
| OverHaust hook | **Not installed** |

No modifications were made to fake verification. Template + installer exist from Phase 13.

---

## 5. Benchmark Environment

| Property | Value |
|----------|-------|
| Run directory | `benchmark-runs/phase15-20260902T110229Z/` |
| Source repo | `/Volumes/Atharv Work/LabKOT/restaurant_pos` |
| Baseline SHA | `7428be4deca9bc7bd58cebab933c99aba566cd94` |
| Naïve clone | `benchmark-runs/phase15-20260902T110229Z/naive/` |
| OverHaust clone | `benchmark-runs/phase15-20260902T110229Z/overhaust/` |
| Agent | Codex CLI v0.146.0 (`codex exec`) |
| Sandbox | `workspace-write` + hook trust bypass (disposable copies only) |
| OverHaust project_id | `labkot` (index from canonical registration) |

Clone method: `git clone` (not `--local` — cross-volume hardlink failure on macOS).

---

## 6. Exact Task

```
Add support for multiple kitchen printers and route each order to the appropriate printer.
```

Implementation instruction appended for write benchmark:

> Implement this in the codebase. Add or update tests in test/kitchen_print_service_test.dart as needed. Keep changes focused on kitchen printing; do not modify unrelated files.

Same task used for both conditions.

---

## 7. Naïve Condition

**Integration:** `naive_user_prompt_hook.py` via Codex `UserPromptSubmit` — injects **full contents** of top search-hit files.

**Pre-agent context metrics (fair simulation):**

| Metric | Value |
|--------|-------|
| Est. tokens | ~9,913 |
| Files | 3 |
| Lines | 1,363 |
| Bytes | 44,728 |
| Assembly latency | 88 ms |

**Agent session:**

| Metric | Value |
|--------|-------|
| Completed | **Yes** (exit 0) |
| Agent time | **287,698 ms (~4.8 min)** |
| Hook in Codex stderr | `hook: UserPromptSubmit Completed` |
| Post-hoc exploration | `rg` across printing/config paths; agent read repo beyond hook |

**Changes:**

- `lib/services/printing/kitchen_print_router.dart` — unmatched items route to default printer only (avoid duplicate catch-all tickets)
- `test/kitchen_print_service_test.dart` — regression test for fallback behavior

**Note:** Debug JSONL capture for naïve hook was incomplete in the first run (fixed post-run to append to `OVERHAUST_INTEGRATION_DEBUG_FILE`). Codex stderr confirms hook execution.

---

## 8. OverHaust Condition

**Integration:** `overhaust_user_prompt_hook.py` → `invoke_context_request()` → `additionalContext` with `<!-- overhaust-context -->` marker.

**Pre-agent context metrics:**

| Metric | Value |
|--------|-------|
| Est. tokens (benchmark) | ~1,397 |
| Est. tokens (hook session) | ~1,188 |
| Files in context | 3 (router, service, test) |
| Lines | 362 |
| Inject bytes | 6,864 |
| Assembly latency | 185 ms (902 ms cold in agent subprocess) |
| Hook overhead | ~1 ms |

**Agent session:**

| Metric | Value |
|--------|-------|
| Completed | **Yes** (exit 0) |
| Agent time | **154,236 ms (~2.6 min)** |
| Hook fired | **Yes** (debug JSONL) |
| Context injected | **Yes** (5,550 bytes) |
| Post-hoc exploration | `sed` on service, router, job, printer_types |

**Hook retrieval note:** Session debug listed `kitchen_print_service.dart` + test file; **`kitchen_print_router.dart` omitted from top hook files** — agent still read router via shell. This is a retrieval-ranking observation, not a task failure.

**Changes:**

- `lib/services/printing/kitchen_print_router.dart` — fan-out to every catch-all kitchen printer when no category routes exist
- `test/kitchen_print_service_test.dart` — test for multi-printer fan-out

---

## 9. Context/Token Measurements

| Source | Naïve | OverHaust |
|--------|------:|----------:|
| Est. context tokens (fair baseline) | 9,913 | 1,397 |
| Token reduction vs naïve | — | **85.91%** |
| Files exposed | 3 | 3 |
| Lines exposed | 1,363 | 362 |
| Bytes exposed | 44,728 | 6,864 (hook inject) |
| Provider-reported tokens | **Not available** | **Not available** |

Method: `TokenEstimator` (tiktoken) — same as Phase 12/14.

---

## 10. Latency Measurements

| Metric | Cold | Warm |
|--------|------|------|
| HTTP `/get-relevant-context` | ~2,170 ms (first after API boot) | ~170–180 ms |
| In-process assembly | ~177 ms first | ~170 ms avg |
| Hook overhead | — | ~1–2 ms |
| Naïve context assembly | — | 88 ms |
| OverHaust context assembly | 902 ms (in agent subprocess) | 185 ms |
| Codex agent execution | 287,698 ms (naïve) | 154,236 ms (OverHaust) |

Cold start is a **one-time per-process** cost (agent init + imports + index). Not optimized in this phase — document only.

---

## 11. Implementation Results

| Check | Naïve | OverHaust |
|-------|-------|-----------|
| Agent completion | Yes | Yes |
| Multiple printer support | Yes | Yes |
| Routing logic present | Yes | Yes |
| Single-printer patterns intact | Yes | Yes |
| Architecture fit (Router/Service/Route) | Yes | Yes |
| Compile analyze (changed files) | Pass | Pass |
| Unrelated file changes | None | None |

Both implementations modified the **same two files** (router + test) with **different routing semantics** for catch-all multi-printer edge cases — reflecting stochastic agent behavior, not a retrieval failure.

---

## 12. Test Results

| Test | Naïve | OverHaust |
|------|-------|-----------|
| `flutter test test/kitchen_print_service_test.dart` | **PASS** | **PASS** |
| Tests updated | Yes | Yes |
| Post-agent fixes applied | **No** (benchmark rule) | **No** |

Baseline canonical LabKOT had a pre-existing compile issue in unrelated UI files when tested from external volume earlier; **disposable clones compiled and tested cleanly** for kitchen print scope.

---

## 13. Code Quality Comparison

Automated evaluation via `packages/benchmark/implementation_quality.py`:

| Dimension | Naïve | OverHaust |
|-----------|-------|-----------|
| `correct_implementation` | **True** | **True** |
| `tests_passed` | **True** | **True** |
| `unrelated_changes` | [] | [] |
| Composite architecture signals | Router, Service, Route, Preferences, enqueueRoutedJobsForOrder | Same |

**Quality parity:** No degradation with OverHaust context. OverHaust condition completed **46% faster** agent wall time in this single run (stochastic — not a guaranteed speedup claim).

---

## 14. Retrieval Failures / Missing Context

| Issue | Severity | Impact |
|-------|----------|--------|
| OverHaust hook omitted `kitchen_print_router.dart` in one session | Low | Agent read router via `sed` anyway |
| LabKOT task largely pre-implemented at baseline | Medium | Benchmark tests refinement, not greenfield |
| Agents still explore repo beyond injected context | Expected | Codex exec allows shell reads; measures hook value not isolation |
| Naïve hook debug JSONL not captured (first run) | Measurement only | Fixed in `naive_user_prompt_hook.py` |
| `configuration_sections.dart` / order pipeline not in top OverHaust files | Low | Not required for this run's successful diffs |

**No immediate context budget expansion recommended** — task succeeded with current budget.

---

## 15. What Is Proven

1. **Codex write-enabled task completion with OverHaust automatic hook injection** — tests pass, focused diffs.
2. **~86% estimated token reduction** preserved under real coding conditions.
3. **No quality degradation** vs naïve full-file hook on automated checks (single run).
4. **Canonical repo safety** — disposable git clones at fixed SHA.
5. **Cursor honestly classified NOT AVAILABLE**; **Claude NOT INSTALLED**.
6. **Retrieval engine unchanged** — 260 tests green.

---

## 16. What Is Not Proven

1. **Cursor automatic Agent interception** — not testable programmatically here.
2. **Claude Code live interception** — CLI absent.
3. **Greenfield implementation** — baseline already had multi-printer routing.
4. **Provider billing token savings** — no usage API data.
5. **Agent uses only injected context** — both sessions ran additional shell reads.
6. **Reproducibility across model seeds** — single run per condition.
7. **Identical implementation semantics** — naïve vs OverHaust chose different catch-all routing policies.

---

## 17. Product Implications

- OverHaust can serve as an **automatic pre-prompt context layer for Codex** on real implementation tasks, not just read/plan.
- **Compact context does not block correct implementation** for this LabKOT task; may reduce agent exploration time.
- **Cursor remains the largest integration gap** for the core product thesis in this environment.
- Task selection for future benchmarks should include **repos/tasks without pre-existing feature coverage** to stress retrieval harder.

---

## 18. Recommendation for Phase 16

1. **Cursor manual verification protocol** — install integration, human Agent session checklist, capture hook/MCP logs.
2. **Claude Code verification** when CLI available.
3. **Greenfield benchmark task** on fixture repo without existing routing implementation.
4. **Optional API warm-start** — eager context engine init on boot (documented in Phase 14, not implemented).
5. **Retrieval ranking** — ensure `kitchen_print_router.dart` consistently appears for implementation prompts (hook session miss).
6. **Repeat benchmark** (2–3 runs) to quantify stochastic agent variance.

---

## Summary Table

| Metric | Naïve | OverHaust |
|---|---:|---:|
| Estimated context tokens | 9,913 | 1,397 |
| Token reduction | — | **85.91%** |
| Files exposed | 3 | 3 |
| Lines exposed | 1,363 | 362 |
| Bytes exposed | 44,728 | 6,864 |
| Context latency | 88 ms | 185 ms |
| Agent completion | Yes | Yes |
| Tests passing | Yes | Yes |
| Correct implementation | Yes | Yes |
| Unrelated changes | No | No |

---

## New Artifacts

| File | Purpose |
|------|---------|
| `scripts/write_task_benchmark.py` | Disposable clone write benchmark orchestrator |
| `scripts/integrations/naive_user_prompt_hook.py` | Fair naïve full-file UserPromptSubmit hook |
| `scripts/verify_cursor_integration.py` | Cursor integration inspection + classification |
| `packages/benchmark/implementation_quality.py` | Deterministic post-agent quality checks |
| `packages/benchmark/test_implementation_quality.py` | Regression test |

## Commands

```bash
# Full write benchmark (Codex, ~8–10 min)
python3 scripts/write_task_benchmark.py --project-id labkot

# Cursor inspection
python3 scripts/verify_cursor_integration.py

# Context-only (skip agent)
python3 scripts/write_task_benchmark.py --skip-agent
```

Results: `benchmark-runs/phase15-20260902T110229Z/summary.json`
