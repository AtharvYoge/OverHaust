# Phase 12 — Real Agent Validation + Automatic Integration Research

## 1. Baseline benchmark

**Procedure:** `python3 scripts/agent_benchmark.py --project-id labkot`

**Task:** Add support for multiple kitchen printers and route each order to the appropriate printer.

**Fair baseline (A):** Simulated naïve agent — search top hits, then read **full file contents** from disk for each hit (same file cap as OverHaust budget).

**Cannot measure in this environment:**
- Live autonomous Cursor/Claude/Codex agent tool-call traces
- Actual task completion (code merged, tests pass)
- Provider-reported input tokens from a real agent session

**LabKOT results (fair baseline):**

| Metric | A: Naïve full files | B: OverHaust |
|--------|---------------------|--------------|
| Files read | 3 | 3 |
| Lines | 1,363 | 362 |
| Bytes | 44,728 | 22,297 |
| Est. tokens (tiktoken) | ~9,913 | ~1,397 |
| Latency | ~2,081 ms | ~409 ms |

Paths (A): test file + router + service (full contents).  
Paths (B): router + service first, then test (bounded snippets).

## 2. OverHaust benchmark

Same script, condition B via `invoke_context_request()`.

MCP path validated by `scripts/validate_labkot_context.py` — PASS.

Warm latency (3-run average after index warm):
- Implementation prompt: ~817 ms (first run cold ~1.8s)
- Flow prompt: ~297 ms
- Lookup prompt: ~89 ms

## 3. Context size comparison

**Fair comparison:** OverHaust vs naïve full-file reads (not search JSON).

| Dimension | Reduction vs naïve full files |
|-----------|-------------------------------|
| Tokens (est.) | **85.91%** |
| Bytes | **50.15%** |
| Lines | **73.44%** |
| Files | 0% (same 3 hits) |

**Legacy unfair comparison (Phase 11):** search metadata JSON vs snippet-rich `context` field showed ~0.57% token reduction — **not valid** for product thesis (metadata ≠ agent reads).

## 4. Estimated token comparison

- **Fair baseline tokens:** ~9,913 (full file concatenation)
- **OverHaust `context` field:** ~1,397
- **Method:** `TokenEstimator` (tiktoken, labeled estimate — not provider billing)

## 5. Actual measurable reduction

On LabKOT multi-printer task, OverHaust delivers **~86% fewer estimated tokens** than the simulated naïve agent reading full top search files, while returning bounded snippets from the same core files.

This supports the product thesis **for this task and baseline definition**. It does not prove reduction for all tasks or all agent behaviors.

## 6. Context quality assessment

**Present (good):**
- `kitchen_print_service.dart` — core implementation
- `kitchen_print_router.dart` — routing abstraction
- `KitchenPrintService`, `KitchenPrintRoute` symbols

**Improvement applied (minimal):**
- Development tasks now prefer `lib/` paths over `test/` in file/symbol ordering (same budget, better implementation focus)

**Potentially missing for full implementation:**
- Order pipeline integration (e.g. billing → print enqueue)
- Printer configuration models (`SavedPrinter`, station assignment)
- `kitchen_print_job.dart` model

**Verdict:** Sufficient to **begin** implementation; not exhaustive. Smallest sufficient context goal partially met — may need 1–2 additional files for order→print wiring without raising global budget (future ranking improvement).

**Irrelevant code:** No broad unrelated modules in top hits.

**Selective flow:** Correctly **off** for implementation prompt; **on** for kitchen flow question.

## 7. Task-success comparison

**Not measurable** in automated harness. Requires live MCP-connected agent completing the coding task with/without OverHaust context. Documented honestly in benchmark output.

## 8. MCP limitations

From [`services/mcp_server/server.py`](services/mcp_server/server.py) and MCP protocol behavior:

| Question | Answer |
|----------|--------|
| Requires explicit agent invocation? | **Yes** — agent must call `get_relevant_context` |
| Can MCP server intercept every user prompt automatically? | **No** — MCP servers expose tools; clients decide when to call |
| Can OverHaust guarantee context before agent reasoning? | **No** via MCP alone |
| Can MCP inject context without agent cooperation? | **No** — unless client/hook layer injects tool results |
| If agent never calls tool? | **No OverHaust context** — agent explores repo normally |
| MCP sufficient for ultimate workflow? | **Partial** — good portable tool surface; **insufficient alone** for automatic pre-reasoning injection |

MCP **resources** and **prompts** could nudge usage but still require client cooperation (verified: Cursor supports MCP prompts as user-invoked templates, not automatic interception).

## 9. Cursor integration findings

**Updated (Phase 13):** Cursor supports Agent hooks including `beforeSubmitPrompt`, but the **native output schema only supports `continue` / `user_message`** (block/allow) — not context injection. Claude Code-compatible hooks loaded via third-party skills *may* honor `hookSpecificOutput.additionalContext`; this requires live verification per workspace.

**Verified (Cursor docs, 2026):**
- MCP supported via `mcp.json` (project or global)
- Tools invoked when agent deems relevant OR user requests — **not automatic on every prompt**
- Auto-review / allowlist controls tool execution approval
- MCP prompts available as slash/template injection — **user or client triggered**
- No verified API for silent pre-prompt context injection without agent/tool cooperation

**Recommended path:** MCP tool `get_relevant_context` + optional Cursor rule instructing agent to call it first.

## 10. Claude Code integration findings

**Verified (Claude Code hooks docs):**
- `UserPromptSubmit` — fires before prompt processing; can inject context via hook output
- `PreToolUse` — can inject `additionalContext` or gate tool calls
- MCP tools appear as `mcp__server__tool`; hook matchers supported
- Hooks can call MCP tools (`mcp_tool` hook type in newer docs)

**Recommended path:** MCP for portable context + **`UserPromptSubmit` or `PreToolUse` hook** to auto-call OverHaust before first tool use (Phase 13 prototype, not built here).

## 11. Codex integration findings

**Verified (OpenAI Codex docs, 2026):**
- MCP via `~/.codex/config.toml` `[mcp_servers.*]`
- Hooks framework with lifecycle events
- MCP tool hooks can invoke connected MCP servers synchronously
- Same pull-model for tools — agent/hook must trigger

**Recommended path:** MCP + Codex hooks (similar to Claude Code) for automatic pre-context.

## 12. Universal architecture recommendation

**B) MCP + optional native hooks** (not MCP-only)

| Layer | Role |
|-------|------|
| OverHaust engine | Index, relevance, flow, `invoke_context_request` |
| FastAPI | Local service, indexing, health |
| MCP server | Portable agent tool surface (stdio) |
| Agent hooks (Claude Code / Codex) | Optional automatic pre-context (Phase 13) |
| IDE rules / prompts | Soft nudge for MCP tool usage |
| Desktop | Config, visibility, index management — not engine |

**Not recommended now:** Custom Cursor extension, proxy gateway, cloud backend.

## 13. Background-engine assessment

**Already independent of desktop UI:**
- Engine in `packages/`
- FastAPI (`services/api/main.py`) and MCP (`services/mcp_server/server.py`) run standalone
- SQLite persistence — no UI required

**Gaps for always-on background model:**
- No daemon/process supervisor yet (manual start)
- MCP stdio requires client-launched subprocess per session
- Single global SQLite path — fine for local use

**No large refactor needed** — add optional background service wrapper in Phase 13.

## 14. Latency measurements

| Request type | Latency (LabKOT, warm) |
|--------------|------------------------|
| Lookup | ~89 ms |
| Implementation context | ~184–413 ms |
| Flow (with trace) | ~297 ms |
| Naïve full-file baseline | ~2,081 ms |

**Target:** Sub-second for normal context — **met** after warm index (implementation ~200–400 ms). Cold first request can exceed 1s on large index.

Flow trace adds modest overhead on LabKOT (~200 ms vs lookup).

## 15. Privacy assessment

**Safe logging ([`packages/context/agent_context.py`](packages/context/agent_context.py)):**
```
context_request project_id=... latency_ms=... files=... symbols=... code_flow=... insufficient=...
```

**Not logged:** prompt text, snippets, source content, credentials.

**Review:** No grep hits for prompt/snippet logging in engine paths. Localhost/MCP stdio trust boundary unchanged.

## 16. Files changed

| File | Purpose |
|------|---------|
| `packages/context/benchmark.py` | Fair baseline measurement |
| `packages/context/agent_context.py` | lib-first ranking for development tasks |
| `packages/context/test_context_quality.py` | Quality + benchmark tests |
| `scripts/agent_benchmark.py` | Reproducible A/B benchmark |
| `scripts/measure_context_baseline.py` | Deprecated note for fair benchmark |
| `PHASE_12_IMPLEMENTATION.md` | This report |

## 17. Tests passed

```
242 pytest passed
6 desktop vitest passed
npm run build — success
git diff --check — clean
scripts/validate_labkot_context.py — PASS
scripts/agent_benchmark.py — PASS
```

## 18. What Phase 13 should build

1. **Claude Code / Codex hook prototype** — `UserPromptSubmit` auto-call OverHaust MCP or local API
2. **Background engine daemon** — always-on FastAPI + optional MCP socket/HTTP bridge
3. **Live agent A/B study** — one real MCP session with task completion metrics
4. **Fairer baseline v2** — compare vs agent grep+read simulation (multiple passes)
5. **Context quality ranking** — surface order→print wiring files without raising budget
6. **Cursor rules package** — documented rule snippet forcing `get_relevant_context` as step 1

## Critical conclusion

The product thesis is **supported on LabKOT multi-printer task** against a fair baseline (naïve full-file reads): ~86% estimated token reduction with relevant implementation files preserved.

MCP alone is **not sufficient** for automatic background context injection — hooks or rules layer needed (Phase 13).

Phase 11's ~0.57% figure was an **artifact of comparing unlike baselines** — now corrected.
