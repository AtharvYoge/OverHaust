# Phase 13 — Real AI-Agent Interception Integrations

## 1. Agents integrated

| Agent | Integrated | Mechanism | Auto-inject verified |
|-------|------------|-----------|------------------------|
| **Codex** | Yes | `UserPromptSubmit` → `~/.codex/hooks.json` | Hook pipeline E2E **PASS** (subprocess); live Codex CLI session **not run** (requires hook trust via `/hooks`) |
| **Claude Code** | Yes (config + hook script) | `UserPromptSubmit` → `.claude/settings.json` | Hook pipeline E2E **PASS**; `claude` CLI **not installed** — live session **unverified** |
| **Cursor** | Partial | `.cursor/hooks.json` + MCP + rules | Hook pipeline E2E **PASS**; native `beforeSubmitPrompt` context injection **not verified live** |

## 2. Mechanisms used

```
User prompt
    ↓
UserPromptSubmit / beforeSubmitPrompt hook (agent-specific config)
    ↓
scripts/integrations/overhaust_user_prompt_hook.py
    ↓
packages/integrations/interception.run_user_prompt_interception()
    ↓
invoke_context_request(project_id, prompt)   ← canonical engine (unchanged)
    ↓
hookSpecificOutput.additionalContext  →  agent
```

- **No new retrieval pipeline** — hooks call `invoke_context_request()` in-process only.
- **REST** (`POST /api/v1/get-relevant-context`) and **MCP** (`get_relevant_context`) unchanged.

## 3. Files changed

### New

| File | Purpose |
|------|---------|
| `packages/integrations/__init__.py` | Package exports |
| `packages/integrations/hook_io.py` | Parse hook stdin; format stdout JSON |
| `packages/integrations/interception.py` | Adapter → `invoke_context_request()` |
| `packages/integrations/debug.py` | Safe debug observability (`OVERHAUST_INTEGRATION_DEBUG`) |
| `packages/integrations/install.py` | Merge-safe config installer |
| `packages/integrations/test_interception.py` | Unit tests |
| `packages/integrations/test_hook_e2e.py` | Subprocess hook E2E tests |
| `packages/integrations/test_install.py` | Installer tests |
| `scripts/integrations/overhaust_user_prompt_hook.py` | Hook entrypoint |
| `scripts/install_agent_integration.py` | CLI installer |
| `scripts/integration_smoke_test.py` | End-to-end smoke test |
| `integrations/templates/codex/hooks.json` | Codex hook template |
| `integrations/templates/claude/settings.json` | Claude Code hook template |
| `integrations/templates/cursor/hooks.json` | Cursor hook template |
| `integrations/templates/cursor/mcp.json` | Cursor MCP template |
| `integrations/templates/cursor/rules/overhaust-context.mdc` | Cursor MCP nudge rule (fallback) |

### Modified

| File | Purpose |
|------|---------|
| `packages/context/benchmark.py` | Added `measure_hook_interception()` |
| `scripts/agent_benchmark.py` | Reports hook-path timing |
| `services/agent/connections.py` | IDE adapter notes hook install path |
| `docs/MCP_AGENT_INTEGRATION.md` | Hooks section + debug mode |
| `PHASE_12_IMPLEMENTATION.md` | §9 Cursor hooks limitation note |

## 4. End-to-end smoke test

```bash
python3 scripts/integration_smoke_test.py --benchmark
```

**Result: PASS**

- In-process: prompt → `run_user_prompt_interception()` → `<!-- overhaust-context -->` marker in `additionalContext`
- Subprocess: synthetic `UserPromptSubmit` stdin → hook script → valid JSON stdout
- Debug stderr: `prompt_hash`, `project_id`, files, symbols, latency — **no full prompt logged**

## 5. Benchmark results (LabKOT, same task as Phase 12)

```bash
python3 scripts/agent_benchmark.py --project-id labkot
```

| Condition | Tokens (est.) | Bytes | Latency |
|-----------|---------------|-------|---------|
| A) Naïve full files | ~9,913 | 44,728 | 94 ms |
| B) OverHaust `invoke_context_request` | ~1,397 | 22,297 | 171 ms |
| C) Hook adapter path | ~1,402 | 6,864 | 176 ms (engine 175 ms, overhead ~1 ms) |

**Token/context reduction vs naïve full files: 85.91%**

Hook adapter adds ~1 ms overhead over direct `invoke_context_request()` on LabKOT (parse + format only).

**Task-quality improvement: not measured** (requires live agent completing the coding task).

## 6. Debug / observability

```bash
export OVERHAUST_INTEGRATION_DEBUG=1
```

Emits JSON to **stderr** only:

- `prompt_length`, `prompt_hash` (12-char SHA-256 prefix)
- `project_id`, `relevant_files`, `relevant_symbols`
- `context_bytes`, `estimated_context_tokens`
- `estimated_naive_tokens`, `reduction_pct` (debug-only baseline)
- `latency_ms`, `code_flow_used`, `insufficient_evidence`

Never logs full prompts or source snippets by default.

## 7. Agent-specific limitations

### Codex

- Hook must be **trusted** before first run (`/hooks` in Codex CLI, or `--dangerously-bypass-hook-trust` for automation).
- Project-local hooks require a **trusted** project `.codex/` layer.
- `MAX_PROMPT_LENGTH` (500) still applies.

### Claude Code

- `claude` CLI not present in the implementation environment — hook I/O verified synthetically only.
- Install: `python3 scripts/install_agent_integration.py --agent claude`

### Cursor

- Native `beforeSubmitPrompt` output schema supports **`continue` / `user_message` only** — not documented context injection.
- Claude-compat `hookSpecificOutput.additionalContext` *may* work when third-party skills load `.claude/settings.json` — **not verified in live Cursor Agent session**.
- Fallback shipped: MCP `get_relevant_context` + `.cursor/rules/overhaust-context.mdc` (agent must call tool — **not automatic interception**).

## 8. Install

```bash
python3 scripts/install_agent_integration.py --agent codex
python3 scripts/install_agent_integration.py --agent claude
python3 scripts/install_agent_integration.py --agent cursor
python3 scripts/install_agent_integration.py --agent all --dry-run
```

Requires registered + indexed OverHaust project matching hook `cwd`. Optional: `OVERHAUST_PROJECT_ID=labkot`.

## 9. Tests passed

```
258 pytest passed
python3 scripts/integration_smoke_test.py --benchmark — PASS
python3 scripts/agent_benchmark.py --project-id labkot — PASS
python3 scripts/install_agent_integration.py --agent all --dry-run — PASS
```

## 10. What could not be verified

| Item | Status |
|------|--------|
| Live Codex CLI session with trusted hook firing on real user send | Not run (hook trust + interactive session required) |
| Live Claude Code session | Not run (`claude` not installed) |
| Cursor automatic per-prompt context injection in Agent chat | Not verified live |
| Agent task completion with/without OverHaust | Not measurable in harness |

## 11. Backward compatibility

- REST API unchanged
- MCP tools unchanged
- Desktop UI unchanged
- Retrieval algorithm unchanged
