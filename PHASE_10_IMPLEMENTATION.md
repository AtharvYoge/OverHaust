# Phase 10 — External Agent Context Layer

## Summary

Phase 10 introduces a single canonical engine operation — `assemble_agent_context()` — that external AI agents consume via FastAPI and MCP without duplicating retrieval logic.

## What was added

| Component | Path |
|-----------|------|
| Engine assembler | `packages/context/agent_context.py` |
| Context budget config | `packages/shared/config.py` (`OVERHAUST_CONTEXT_*`) |
| REST endpoint | `POST /api/v1/get-relevant-context` |
| MCP tools | Updated `get_relevant_context`, new `list_projects` |
| Project resolution | `ProjectIndexStore.resolve_project_id()` |
| Baseline script | `scripts/measure_context_baseline.py` |
| Tests | `packages/context/test_agent_context.py`, API integration tests |

## Primary operation

```
assemble_agent_context(project_id, prompt) → compact structured context
```

Reuses:
- `search_project_knowledge_scored()` — unified search
- `ContextAssembler._get_relevant_files()` — bounded snippets
- `assess_evidence()` — abstention
- `trace_code_flow()` — selective, not on every prompt

## Selective code-flow policy

Tracing runs when `include_code_flow` is:
- `"auto"` (default) and `classify_flow_traversal_intent()` is flow-oriented **and** top relevance ≥ threshold
- `true` explicitly (still requires sufficient relevance)

Implementation/feature prompts (e.g. multi-printer) do **not** auto-trace unless flow intent matches.

## Baseline measurement

Run against an indexed project:

```bash
python scripts/measure_context_baseline.py \
  --project-id labkot \
  --prompt "Add support for multiple kitchen printers and route each order to the appropriate printer."
```

Compares:
- **A)** Raw `/search-knowledge` JSON (limit 10)
- **B)** Compact `get_relevant_context` response

Metrics: files, approx lines, response bytes, estimated tokens on `context` field, latency.

## MCP usage

Configure MCP client to run `services/mcp_server/server.py` (stdio).

Primary tool: `get_relevant_context` with `project_id` + `prompt`.

Discovery: `list_projects`.

## Security

- Requires registered `project_id` (or resolvable `root_path`)
- Snippets only via `read_indexed_snippet()` path containment
- Localhost API / stdio MCP — no auth (local trust boundary)

## Not in this phase

GitHub OAuth, editor extensions, LLM synthesis, conversation persistence.
