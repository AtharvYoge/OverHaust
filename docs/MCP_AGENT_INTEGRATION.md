# OverHaust MCP Agent Integration

OverHaust is a **background context-intelligence layer** for AI coding agents. It does not answer users or edit code. An MCP-compatible agent calls OverHaust to obtain compact, relevant repository context, then reasons over that context itself.

## What OverHaust provides

- Ranked search over indexed files and symbols
- Bounded source snippets (not whole files)
- Selective code-flow tracing for process/flow questions
- Evidence abstention when nothing relevant matches
- Project discovery via registered `project_id`

## Running the MCP server

From the repository root:

```bash
python3 -m services.mcp_server.server
```

The server uses **stdio** transport. Configure your MCP client to launch this command.

Example client configuration (verified pattern from this repository):

```json
{
  "mcpServers": {
    "overhaust": {
      "command": "python3",
      "args": ["-m", "services.mcp_server.server"],
      "cwd": "/path/to/OverHaust-1"
    }
  }
}
```

The repo also includes config helpers in `services/agent/connections.py` for generating MCP client blocks.

## Primary MCP tools

### `list_projects`

Discover registered projects before requesting context.

**Input:** `{}`

**Output:**

```json
{
  "projects": [
    {
      "project_id": "labkot",
      "name": "LabKOT",
      "description": "...",
      "root_path": "/path/to/repo",
      "indexed": true
    }
  ]
}
```

No secrets or credentials are returned.

### `get_relevant_context`

Primary tool. Returns compact repository context for a natural-language task.

**Input:**

| Field | Required | Description |
|-------|----------|-------------|
| `prompt` or `task` | yes | Natural-language question or task |
| `project_id` | one of | Registered project identifier |
| `root_path` | one of | Resolve project from repository path |
| `include_code_flow` | no | `"auto"` (default), `true`, or `false` |
| `max_files` | no | Clamped to `OVERHAUST_CONTEXT_MAX_FILES` |
| `max_symbols` | no | Clamped to `OVERHAUST_CONTEXT_MAX_SYMBOLS` |

**Output (stable fields):**

```json
{
  "project_id": "labkot",
  "prompt": "...",
  "context": "## Task\n...",
  "summary": "...",
  "relevant_files": [],
  "relevant_symbols": [],
  "evidence": [],
  "code_flow": null,
  "relationships": [],
  "insufficient_evidence": false,
  "evidence_note": "",
  "confidence": "high",
  "disclaimer": "...",
  "metrics": {
    "files_count": 3,
    "symbols_count": 5,
    "approx_source_lines": 42,
    "response_bytes": 4800,
    "latency_ms": 180,
    "code_flow_included": false
  }
}
```

Inject the `context` field into the agent's working context. Structured fields are optional detail.

## Project discovery workflow

1. Register and index a repository (via desktop or API):
   - `POST /api/v1/projects`
   - `POST /api/v1/index-project`
2. Call MCP `list_projects` to find `project_id`
3. Call `get_relevant_context` with `project_id` + `prompt`

Or pass `root_path` if the repository path is already registered.

## Selective code flow

Code flow is **not** run on every prompt.

| Prompt type | Auto behavior |
|-------------|---------------|
| Implementation ("Add support for…") | Search + snippets only |
| Lookup ("What does X do?") | Search + snippets only |
| Flow ("Where does an order reach the kitchen?") | Search + selective trace |

Set `include_code_flow: false` to disable tracing entirely.

## Insufficient evidence

When nothing relevant matches, OverHaust returns:

- `insufficient_evidence: true`
- `confidence: "insufficient"`
- Empty or minimal `relevant_files` / `relevant_symbols`
- An `evidence_note` explaining the gap

OverHaust does **not** invent repository facts in this case.

## Context budgets

Configured via environment variables:

| Variable | Default |
|----------|---------|
| `OVERHAUST_CONTEXT_MAX_FILES` | 5 |
| `OVERHAUST_CONTEXT_MAX_SYMBOLS` | 8 |
| `OVERHAUST_CONTEXT_MAX_EVIDENCE` | 10 |
| `OVERHAUST_CONTEXT_SEARCH_LIMIT` | 20 |

## Cursor setup (quick start)

From the OverHaust repository root:

```bash
# 1. Install Cursor integration (rule + MCP merge + empty hooks)
python3 scripts/install_agent_integration.py --agent cursor

# 2. Register/index this checkout as project_id=overhaust
python3 scripts/ensure_overhaust_indexed.py

# 3. Reload MCP servers in Cursor (Settings → MCP, or restart Cursor)

# 4. Verify static configuration (does not drive the Cursor Agent UI)
python3 scripts/verify_cursor_integration.py

# 5. Open Cursor Agent in this workspace and ask a repository question
```

Expected architecture: alwaysApply rule → MCP `get_relevant_context` → compact context → gap-only exploration.

If OverHaust MCP is unavailable, the rule tells the Agent to continue with normal Glob/Grep/Read. Do not block coding on OverHaust.

**Manual smoke (not automated):** In Cursor Agent, confirm it calls `get_relevant_context` first on a substantive task such as “Where is OverhaustAgent.get_relevant_context defined and what does it call?”

**Limitation:** `~/.cursor/mcp.json` stores absolute paths for this checkout. After moving the repo, re-run the install command. `verify_cursor_integration.py` prints a WARNING (non-fatal) if the configured MCP path does not match this repository.

## Local development setup

1. Start the API (optional, for indexing and desktop):

   ```bash
   python3 -m services.api.main
   ```

2. Register and index a project (or use `scripts/ensure_labkot_indexed.py` / `scripts/ensure_overhaust_indexed.py`)

3. Configure MCP client to run `python3 -m services.mcp_server.server` (or use the Cursor install command above)

4. Verify:

   ```bash
   python3 scripts/mcp_smoke_test.py
   python3 -m pytest services/mcp_server/test_server.py -q
   ```

## Two integration modes

### Cursor (MCP + alwaysApply rule)

Cursor Agent does **not** receive automatic prompt injection. Native `beforeSubmitPrompt` has no supported context-injection field. `hookSpecificOutput.additionalContext` is a Codex/Claude format and must not be treated as Cursor model input.

Intended path:

```
User prompt
  → Cursor Agent (alwaysApply rule)
  → MCP get_relevant_context(prompt, root_path|project_id)
  → compact context
  → Agent explores only remaining gaps
```

Install (writes rule, merges `~/.cursor/mcp.json`, clears OverHaust injection hooks):

```bash
python3 scripts/install_agent_integration.py --agent cursor
python3 scripts/ensure_overhaust_indexed.py
python3 scripts/verify_cursor_integration.py
```

Prefer passing `root_path` (workspace root) to `get_relevant_context` for any registered repository. Use `project_id` when known (this monorepo: `overhaust`).

MCP `get_relevant_context` accepts prompts up to 8000 characters. REST `/api/v1/get-relevant-context` remains limited to 500.

Compare compact context size (not Cursor billing tokens):

```bash
python3 scripts/cursor_mcp_experiment.py --project-id overhaust
```

## Claude Code setup (quick start)

From the OverHaust repository root:

```bash
# 1. Install Claude UserPromptSubmit hook (merges into ~/.claude/settings.json)
python3 scripts/install_agent_integration.py --agent claude

# 2. Register/index the repository Claude will work in
python3 scripts/ensure_overhaust_indexed.py
# or: register/index another project_id whose root matches the Claude cwd

# 3. Verify configuration + local hook smoke (does not drive Claude Code UI)
python3 scripts/verify_claude_integration.py --smoke

# 4. Start Claude Code in the indexed repository and ask a repo question
```

Expected architecture:

```
User prompt
  → Claude Code UserPromptSubmit
  → overhaust_user_prompt_hook.py
  → invoke_context_request → assemble_agent_context
  → hookSpecificOutput.additionalContext
```

The installer **merges** hooks and preserves unrelated settings (for example `PreToolUse → Bash → rtk hook claude`). Re-running install does not duplicate the OverHaust hook.

If OverHaust cannot resolve the project or context retrieval fails, the hook returns empty `additionalContext` and exits 0 so Claude Code continues normally.

**Manual smoke (not automated):** In Claude Code, confirm context feels available for a repository question. This repo’s harness does **not** prove live model consumption.

## Index lifecycle + multi-repository

OverHaust stores many projects in one SQLite database. Retrieval is scoped by `project_id`. Context requests **load** the persisted index — they do **not** auto-reindex.

```
register project (+ root_path)
  → sync_project (full or incremental)
  → agent resolves project_id (explicit id, root_path, or cwd under registered root)
  → invoke_context_request / get_relevant_context (load-only)
  → when the tree changes: re-run ensure_project_indexed / index-project
```

### Initial setup (any repository)

```bash
python3 scripts/ensure_project_indexed.py \
  --project-id my-app \
  --root /path/to/my-app \
  --name "My App"

python3 scripts/verify_index_health.py --project-id my-app
```

Convenience wrappers:

```bash
python3 scripts/ensure_overhaust_indexed.py   # this monorepo → project_id=overhaust
python3 scripts/ensure_labkot_indexed.py      # LabKOT fixture path → labkot
```

### Maintenance

```bash
# Incremental sync (added/modified/deleted files via content hash)
python3 scripts/ensure_project_indexed.py --project-id my-app --root /path/to/my-app

# Force full rebuild
python3 scripts/ensure_project_indexed.py --project-id my-app --root /path/to/my-app --force-full

python3 scripts/verify_index_health.py
```

### Multi-repo rules

- One `root_path` → one `project_id` (duplicate registration is rejected).
- Path resolution uses exact root match, or the longest registered ancestor (subdirectory cwd works for Codex/Claude).
- Ambiguous duplicate roots resolve to no project (fail-open for hooks).
- Cursor should pass `root_path` (or a known `project_id`) to `get_relevant_context`.
- Deleting a project removes its index/memory/embedding rows (`DELETE /api/v1/projects/{id}` or `MemoryStore.delete_project`).

### Codex / Claude Code (automatic UserPromptSubmit hooks)

For **automatic** pre-prompt context (no MCP tool call), install agent hooks:

```bash
python3 scripts/install_agent_integration.py --agent codex    # ~/.codex/hooks.json
python3 scripts/install_agent_integration.py --agent claude   # ~/.claude/settings.json
python3 scripts/install_agent_integration.py --agent all --dry-run
```

Codex/Claude hooks invoke:

```
scripts/integrations/overhaust_user_prompt_hook.py
  → invoke_context_request(project_id, prompt)
  → hookSpecificOutput.additionalContext
```

| Agent | Hook event | Mechanism | Auto-inject |
|-------|------------|-----------|-------------|
| **Codex CLI** | `UserPromptSubmit` | `~/.codex/hooks.json` | Yes (after hook trust via `/hooks`) |
| **Codex Desktop** | `UserPromptSubmit` | same `~/.codex/hooks.json` | Yes (after trust in Settings → Hooks) |
| **Claude Code** | `UserPromptSubmit` | `~/.claude/settings.json` | Yes |
| **Cursor** | MCP tool + alwaysApply rule | `.cursor/rules` + MCP | Agent calls `get_relevant_context` first |
| **Continue** | MCP tool + alwaysApply rule | `.continue/rules` + `.continue/mcpServers` | Agent calls `get_relevant_context` first |
| **Cline** | `UserPromptSubmit` hook | `.clinerules/hooks/UserPromptSubmit` → `contextModification` | Intended auto-inject (host-version dependent) |

Continue is a fourth-host adapter experiment: same OverHaust context seam as Cursor, different product config layout and runtimes (VS Code extension / JetBrains plugin / `cn` CLI). Live Continue UI consumption is **not** claimed by the adapter tests.

Cline is a B/C stress test: different native injection field (`contextModification`) and stdin shape than Codex/Claude. OverHaust uses a Cline-specific hook script that still calls `invoke_context_request` without changing `hook_io.py`. Live model delivery depends on Cline version (see Cline issue #13554); doctor reports `ACTION_REQUIRED` / `NOT_DETECTED` and does **not** claim READY for unproven Enable Hooks / consumption.

Codex CLI and Codex Desktop share the same product adapter and hook file, but are distinct **runtimes** (version, trust UX, verification). Treat `product=codex` + `runtime=cli|desktop` separately when diagnosing injection failures.

### Host adapters + doctor

Install/verify are routed through host adapters under `packages/integrations/adapters/` (detect, capabilities, install, verify). Context assembly remains `invoke_context_request` — adapters never retrieve or rank code.

```bash
python3 scripts/overhaust_doctor.py
python3 scripts/overhaust_doctor.py --adapter codex
python3 scripts/overhaust_doctor.py --json
```

### Unified CLI (Integration Manager)

The preferred user path is the manager CLI, which composes every registered adapter
(see `docs/INTEGRATION_MANAGER.md` for states and architecture):

```bash
scripts/overhaust integrations        # what is detected, what state each host is in
scripts/overhaust connect             # install into all detected hosts (prompts; -y to skip)
scripts/overhaust connect --host codex
scripts/overhaust disconnect --host claude
scripts/overhaust status              # core + projects + hosts
scripts/overhaust doctor --probe-emission
```

`install_agent_integration.py` and `overhaust_doctor.py` remain as thin compatibility entry points.

### Requirements

1. Register and index the repository in OverHaust (`project_id` or workspace root must resolve)
2. Optional override: `OVERHAUST_PROJECT_ID=labkot`
3. This repo: `python3 scripts/ensure_overhaust_indexed.py` (`project_id=overhaust`)

### Debug / observability

```bash
export OVERHAUST_INTEGRATION_DEBUG=1
# optional: OVERHAUST_INTEGRATION_DEBUG_FILE=~/.overhaust/integration-debug.log
```

Emits safe JSON to **stderr** (stdout reserved for hook response):

- `prompt_length`, `prompt_hash` (not full prompt)
- `project_id`, `relevant_files`, `relevant_symbols`
- `context_bytes`, `estimated_context_tokens`
- `estimated_naive_tokens`, `reduction_pct` (debug only)
- `latency_ms`, `code_flow_used`, `injection_mode`

Never logs full prompts or source snippets by default.

### Verify installation

```bash
python3 scripts/overhaust_doctor.py
python3 scripts/integration_smoke_test.py
python3 scripts/mcp_smoke_test.py
python3 scripts/verify_cursor_integration.py
python3 scripts/verify_codex_integration.py
python3 scripts/verify_claude_integration.py --smoke
python3 scripts/verify_index_health.py --project-id overhaust
python3 -m pytest packages/integrations/ services/mcp_server/test_server.py packages/context/test_agent_context.py services/ingestion/ -q
```

## REST alternative

The same context operation is available at:

```
POST /api/v1/get-relevant-context
```

MCP is the recommended integration for coding agents.

## Security

- Local trust boundary (stdio MCP / localhost API)
- Snippets read only from registered project roots with path containment
- Context request logs include operational metadata only (no prompt text or source content)
- Hook debug mode logs prompt hash/length only — not full prompts or snippets
