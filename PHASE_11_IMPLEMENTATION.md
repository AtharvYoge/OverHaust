# Phase 11 — MCP End-to-End Agent Integration

## 1. MCP architecture discovered

```
MCP Client (stdio)
    ↓
services/mcp_server/server.py
    ├── list_projects → list_projects_for_agent()
    └── get_relevant_context → invoke_context_request()
            ↓
        assemble_agent_context()
            ├── search_project_knowledge_scored()
            ├── ContextAssembler._get_relevant_files() + snippets
            ├── assess_evidence() / abstention
            └── trace_code_flow() (selective, flow-questions only)
```

No duplicate retrieval in MCP. Primary tools call the canonical engine path in [`packages/context/agent_context.py`](packages/context/agent_context.py).

## 2. Files changed

| File | Change |
|------|--------|
| `packages/context/agent_context.py` | `invoke_context_request()`, validation, budget clamping, `_is_flow_question()`, observability logging, `to_mcp_payload()` |
| `packages/agent/autonomous_agent.py` | Delegates to `invoke_context_request()` |
| `services/mcp_server/server.py` | MCP calls `invoke_context_request()` directly |
| `services/api/main.py` | `/health` adds `engine.running` |
| `packages/context/test_agent_context.py` | Budget, validation, selective flow tests |
| `services/mcp_server/test_server.py` | MCP tool + stdio smoke tests |
| `services/api/test_api_integration.py` | Health engine field |
| `scripts/measure_context_baseline.py` | Reduction percentages |
| `scripts/ensure_labkot_indexed.py` | LabKOT register/index (new) |
| `scripts/validate_labkot_context.py` | LabKOT validation (new) |
| `scripts/mcp_smoke_test.py` | In-process MCP smoke (new) |
| `docs/MCP_AGENT_INTEGRATION.md` | Agent integration guide (new) |
| `apps/desktop/src/components/BackendStatus.tsx` | Engine / Context API status labels |

## 3. Exact MCP tool contracts

### `list_projects`

**Input:** `{}`

**Output:**
```json
{
  "projects": [
    {
      "project_id": "labkot",
      "name": "LabKOT",
      "description": "...",
      "root_path": "/Volumes/Atharv Work/LabKOT/restaurant_pos",
      "indexed": true
    }
  ]
}
```

### `get_relevant_context`

**Input:** `project_id` or `root_path`, `prompt` (or `task`), optional `include_code_flow`, `max_files`, `max_symbols`

**Output:** Full `AgentContextResponse` JSON including:
- `context` — compact injectable text
- `relevant_files`, `relevant_symbols`, `evidence`
- `code_flow`, `relationships` (when selectively traced)
- `insufficient_evidence`, `evidence_note`, `confidence`
- `metrics`: `files_count`, `symbols_count`, `approx_source_lines`, `response_bytes`, `latency_ms`, `code_flow_included`

See [`docs/MCP_AGENT_INTEGRATION.md`](docs/MCP_AGENT_INTEGRATION.md) for full documentation.

## 4. End-to-end smoke-test result

| Check | Result |
|-------|--------|
| MCP server starts (stdio) | PASS |
| `list_projects` | PASS |
| `get_relevant_context` bounded response | PASS |
| Insufficient evidence (unrelated prompt) | PASS |
| Selective flow (impl vs flow question) | PASS |
| Stdio `tools/call` roundtrip | PASS (`test_stdio_context_tools`) |
| In-process smoke script | PASS (`scripts/mcp_smoke_test.py`) |

## 5. LabKOT context result

**Prompt:** Add support for multiple kitchen printers and route each order to the appropriate printer.

**Top files returned:**
- `lib/services/printing/kitchen_print_service.dart`
- `lib/services/printing/kitchen_print_router.dart`
- `test/kitchen_print_service_test.dart`

**Top symbols:**
- `KitchenPrintService`
- `KitchenPrintRoute`
- `enableKitchenPrinterWithDefault`

**Manual inspection:** Context targets the kitchen printing implementation layer (service, router, tests) — not generic unrelated modules. Relevant for an implementation task.

**Validation:** `scripts/validate_labkot_context.py` — PASS

## 6. Context size before/after

LabKOT multi-printer prompt (`measure_context_baseline.py`):

| Metric | A: Raw search JSON (limit=10) | B: Compact context |
|--------|--------------------------------|--------------------|
| Files | 3 | 3 |
| Symbols | — | 3 |
| Approx lines | 3 | 362 |
| Response bytes | 4,770 | 22,301 |
| Latency | 90 ms | 175 ms |

**Note:** Raw search JSON contains index metadata only (no disk snippets). Compact context includes bounded source snippets in the `context` field — so byte/line counts are not directly comparable as “less is smaller.” The product value is **relevance + bounded caps**, not raw JSON size vs snippet-rich context on the same 3 files.

## 7. Estimated token reduction

Using tiktoken estimate (`TokenEstimator`, labeled estimate):

| Comparison | A (search JSON) | B (`context` field) | Reduction |
|------------|-----------------|---------------------|-----------|
| Tokens | ~1,405 | ~1,397 | **0.57%** |

Token estimate on this prompt shows minimal reduction vs search metadata because both return similar hit counts. The meaningful savings vs naïve agent behavior is avoiding whole-repo reads and unrelated files — not vs thin search JSON alone.

## 8. Latency

| Operation | Latency |
|-----------|---------|
| Raw search (LabKOT) | ~90 ms |
| `get_relevant_context` (LabKOT, no flow) | ~175–193 ms |
| With code flow (flow question, fixture) | higher (trace cost) |

## 9. Selective code flow verification

| Prompt | `code_flow_included` |
|--------|----------------------|
| What does the order service do? | false |
| Add support for multiple kitchen printers | false |
| Where does a food order reach the kitchen? | true |

**Fix applied:** Auto trace requires a flow **question** (`how`/`where` + process verbs), not merely `hardware_transport` intent. Prevents implementation prompts mentioning “printers” from triggering trace on LabKOT.

## 10. Tests passed

```
235 passed (pytest)
6 passed (desktop vitest)
npm run build — success
git diff --check — clean
scripts/mcp_smoke_test.py — PASS
scripts/validate_labkot_context.py — PASS
```

## 11. Limitations

- Localhost / stdio trust boundary — no auth
- Token baseline compares search metadata JSON vs snippet-rich `context` — misleading if interpreted as “always smaller bytes”
- LabKOT must be registered/indexed before MCP use (`scripts/ensure_labkot_indexed.py`)
- MCP server uses same SQLite DB as API (`OVERHAUST_DB_PATH`)
- No background daemon yet — MCP client must launch the server

## 12. Phase 12 recommendation

1. **Background engine daemon** — always-on context service without manual MCP launch
2. **GitHub / remote project registration** — connect repos without local path setup
3. **Desktop integration panel** — generate/copy MCP config, index status, last context request stats
4. **Fairer baseline metric** — compare vs “agent reads top-N full files” not search metadata JSON
5. **Optional HTTP MCP or SSE transport** for agents that cannot use stdio subprocess
