# Layer 4 protocol

Protocol version: `layer4-protocol-v2`.

Layer 4 measures real coding-agent sessions on the same tasks as Layer 3.
The primary metric is the **agent's own provider token totals** for the
session. OverHaust's context tokens are reported beside that total and are
never subtracted from it.

Provider-side prompt caching was not independently controlled; cached-input usage was recorded and retained as part of the measured session usage.

This package is instrumentation. A pilot file is not a product result.
Layer 3 code, tasks, scoring, retrieval, and canonical result files stay frozen.

## Conditions

| Condition | What changes |
|-----------|----------------|
| `baseline` | Fresh Codex home. No `hooks.json`. The task prompt is the only user text. |
| `overhaust` | Same argv, sandbox, model, and prompt. `$CODEX_HOME/hooks.json` is the repo's Codex template (`integrations/templates/codex/hooks.json` via `install_codex`). The hook is `scripts/integrations/overhaust_user_prompt_hook.py`, which calls `invoke_context_request()`. |

Context is not pasted into the prompt. Both conditions pass the task JSON
`prompt` as a single `codex exec` argument.

The flag `--dangerously-bypass-hook-trust` is set on **both** conditions.
Codex will not run an untrusted hook unattended; on baseline, with no hooks
installed, the flag does not inject context. Permissions otherwise match:

- `--sandbox workspace-write`
- `--skip-git-repo-check` (the fixture is not a git checkout)
- `--ignore-user-config` (only `config.toml`; hooks still load from `CODEX_HOME`)
- not ephemeral, not `exec resume`, not `--dangerously-bypass-approvals-and-sandbox`

## Isolation

Every cell of the matrix is its own session:

1. New process. Codex is not resumed (`exec resume` is never used).
2. New `CODEX_HOME` directory, created empty. Sessions, logs, and the user's
   `hooks.json` are not copied. Login mode copies only `auth.json`.
3. The fixture tree is restored from the matrix snapshot and the tree hash is
   checked **before** the prompt. A mismatch is an invalid session and the
   agent is not started.
4. Same task prompt, model flag, sandbox, and timeout.
5. Same indexed fixture database (`OVERHAUST_DB_PATH`). The production
   `data/overhaust_memory.db` is not the database the hook sees.
6. Condition order is pair counterbalancing, not a global shuffle of
   sessions. See below. The seed is stored on every session. Repetition
   index `rep` starts at 0.

## Presets

| Preset | Matrix | Sessions |
|--------|--------|----------|
| `pilot` (default) | `sym_generate_kot`, `arch_kitchen_hardware` × `baseline`, `overhaust` × 2 reps | 8 |
| `full` | all 5 Layer 3 initial tasks, in `benchmarks/tasks/initial` filename order (`arch_kitchen_hardware`, `cross_order_to_printer`, `flow_order_to_kitchen`, `impact_change_generate_kot`, `sym_generate_kot`) × `baseline`, `overhaust` × 2 reps | 20 |

Default seed is 1. Dry run writes the plan for either preset and launches nothing.

`--conditions` selects which conditions run. The default is both (`baseline` and `overhaust`). One condition, for example `--conditions baseline`, builds the same pair-counterbalanced plan for that seed and then keeps only that condition's sessions, in the same relative order. Fixture, prompts, scoring, tool configuration, seed, and timeout do not change. Baseline still has no `hooks.json`. Each kept session records `original_pair_id` and `original_planned_position` (the pair id and `execution_order` from the two-condition plan). A single-condition report says so, and it does not report a cross-condition comparison or a reduction. Cache analysis and agent-behavior tables are still written for the condition that ran.

## Condition order

Each `(task, rep)` is a pair unit. Both sessions of a pair run adjacently.

`random.Random(seed)` assigns order, then shuffles pairs:

1. Walk tasks in preset order. For each task, assign one `condition_order`
   per rep so the two orders are as even as possible. With `reps=2`, one
   pair is `overhaust->baseline` and one is `baseline->overhaust`. With an
   odd rep count, the counts differ by one. The extra slot goes to
   baseline-first when `randrange(2) == 0`, otherwise to OverHaust-first.
   That assignment is then shuffled across reps.
2. Shuffle the pair units with the same generator.
3. Emit the pair's two sessions back-to-back, `order_in_pair` 1 then 2,
   in `condition_order`.

Every session result records `pair_id` (`{task_id}-r{rep}`), `order_in_pair`
(1 or 2), `condition_order`, and `seed`. The run result records
`planned_execution_order` and `actual_execution_order`. A dry run has a
planned order and an empty actual order.

A single-condition run does not draw a new shuffle. After the pair plan
above is built, sessions of the other condition are dropped and the kept
sessions stay in that relative order. `execution_order` is then the index
among sessions this run will execute. `original_pair_id` repeats the pair
id, and `original_planned_position` is the `execution_order` that session
had in the two-condition plan, so the record shows which counterbalanced
slot it came from. With both conditions selected, those two fields are
omitted and `execution_order` is the pair-plan sequence.

## What counts as a valid session

`valid: true` means the isolation contract held. It does not mean the agent
succeeded, and it does not mean every metric was present.

A session is **invalid** (`outcome: "invalid"`, still written) when any of
these are true:

- the snapshot did not restore to the matrix hash
- the Codex home already contained sessions
- the prompt argument differs from the task JSON prompt, or the OverHaust
  context marker was pasted into the prompt
- baseline produced hook-debug output (contamination)
- overhaust was missing the UserPromptSubmit hook, the hook command was not
  `overhaust_user_prompt_hook.py`, the hook did not fire, or it fired with an
  error or with empty context

`outcome` is otherwise:

| Outcome | Meaning |
|---------|---------|
| `completed` | Exit 0 and a `turn.completed` event. |
| `failed` | `turn.failed`, or a non-zero exit, while isolation held. Tokens are kept. |
| `error` | Timeout, launcher failure, or no terminal turn event. |
| `invalid` | Isolation broke. Telemetry captured before the failure is kept. |

## Failures and missing telemetry

Every planned cell is written. `dropped_session_count` must be 0.
A launcher exception becomes an `error` session whose metrics are
`unavailable`, not a missing row.

A missing number is `kind: "unavailable"` and `value: null`. It is not stored
as zero. `telemetry_gaps` lists those fields. `primary_metric_status` is:

| Status | Meaning |
|--------|---------|
| `complete` | Agent input, cached input, and output are exact. |
| `partial` | Input and output are exact. Cached input was not reported. |
| `missing` | Input or output was not reported. The session is still in the file. |

Exact and estimated values never share a field. Agent token fields reject
`estimated`. Two unavailable values are not a comparison.

## Token accounting

Codex CLI **0.146.0** (`openai/codex` tag `rust-v0.146.0`) `codex exec --json`
emits `turn.completed.usage` with:

- `input_tokens`
- `cached_input_tokens` (a subset of input, not an extra bucket)
- `cache_write_input_tokens`
- `output_tokens`
- `reasoning_output_tokens` (stored separately; not subtracted from output)

Those figures are cumulative across model requests in the thread
(`ThreadTokenUsage.total`). The **last** `turn.completed` is the session
total. Earlier turns are not summed. The exec usage object has **no**
`total_tokens` field. This harness does not invent one from
`input + output` or `input + cached + output`.

`cached_input_tokens` is a component of `input_tokens`. It is recorded and
kept. It is never subtracted from input. Prompt caching is not disabled, and
the harness does not cache-bust the prompt (no nonce, no cache-control flag).

Provider-side prompt caching was not independently controlled; cached-input usage was recorded and retained as part of the measured session usage.

`agent_total_tokens` is exact only when a provider reports `total_tokens`.
For Codex 0.146.0 that is a session rollout
`token_count.total_token_usage.total_tokens`, and only when the rollout's
input/output/cached components agree with the exec usage. If that total is
absent, the field stays `unavailable`. It is never replaced with a computed
sum. `last_token_usage` is the latest request, not the session total. It is
kept under `supplemental_telemetry` and is never copied into `agent_*` fields.

OverHaust `estimated_context_tokens` comes from the hook debug file
(TokenEstimator). Kind is `estimated`. It is not subtracted from agent tokens
and it is not mixed into cache analysis.

## Cache analysis

JSON and markdown reports include a cache analysis for each task × condition
and for each condition overall:

- n valid sessions
- mean input tokens
- mean cached input tokens
- cached-input rate (`sum(cached input) / sum(input)`)
- mean output tokens
- mean total tokens (provider-reported total only)

Only valid sessions with an exact figure contribute to that figure's mean.
Invalid sessions, and valid sessions whose figure is unavailable, are excluded
and the counts are stated. A missing cached-input value is not treated as
zero. Estimated OverHaust context tokens are not part of these sums.

## Agent behavior

For each task × condition the report gives the mean tool-call count and the
number of sessions with zero tool calls, using valid sessions with an exact
`tool_calls` figure. The markdown session table includes each session's
tool-call count.

## Secondary metrics

| Metric | Codex 0.146.0 |
|--------|----------------|
| Tool calls | Exact count of completed `command_execution`, `mcp_tool_call`, `collab_tool_call`, and `web_search` items. |
| Files changed | Exact workspace diff against the snapshot (`snapshot_diff`), plus a separate exact count of `file_change` paths. Shell writes show up in the diff. |
| Files inspected | **Unavailable.** Exec JSONL has no file-read item. Shell strings are not parsed into a file list. |
| Elapsed time | Exact harness wall clock around the subprocess. |
| OverHaust retrieval latency | **Unavailable.** With debug enabled, hook `latency_ms` is end-to-end hook wall time (the naïve probe overwrites `response.metrics.latency_ms` before the debug line is written). That wall time is `overhaust_hook_latency_ms` (exact). It is not labeled as retrieval latency. |
| Correctness | Layer 3 rubric via `benchmarks.evaluate.evaluate_answer` on the last `agent_message`. `null` when the agent produced no answer. |

## Results

New files only, in `benchmarks/results/` (gitignored local results, same
directory as other harness runs):

- `layer4-<UTC stamp>.json`
- `layer4-<UTC stamp>.md`
- `layer4-<UTC stamp>-<session_id>.exec.jsonl` (and `.rollout.jsonl`, `.hook.jsonl` when present)

If a stamp is already taken, the writer appends `-1`, `-2`, … and does not
overwrite. Failed sessions stay in the JSON.

## Cursor adapter

Cursor is a separate adapter (`--agent cursor`). It does not use Codex homes,
Codex exec JSONL, or Codex token accounting. Codex behavior in this file is
unchanged.

| Preset | Matrix | Sessions |
|--------|--------|----------|
| `pilot` | all 5 Layer 3 initial tasks × `baseline`, `overhaust` × 1 rep | 10 |
| `full` | those tasks × both conditions × 2 reps | 20 |

Order is the same pair-counterbalanced generator as Codex (`random.Random(seed)`).
With one rep, each task has one pair and the within-pair order is the odd-rep
rule. Default model is `gpt-5.5-medium`. There is no plain `gpt-5.5` id.

The verified headless command is:

`cursor-agent -p --output-format stream-json --trust --model <id> '<prompt>'`

with stdin from `/dev/null`. `--trust` is required. `--force` is not added.

### Condition

| Condition | What changes |
|-----------|----------------|
| `baseline` | Fresh copy of the LabKOT fixture. No `.cursor/hooks.json`. No OverHaust rules or MCP config. |
| `overhaust` | Same argv, model, and prompt. The copy contains only `.cursor/hooks.json` with a `sessionStart` hook: `scripts/integrations/overhaust_cursor_session_start_hook.py`. |

The hook calls `invoke_context_request(project_id, prompt, memory_store=...)`.
`sessionStart` stdin has no user prompt, and Cursor's `session_id` does not
exist until the hook runs, so the harness cannot key the prompt on that id.
It writes a mode-0600 JSON file in the session directory
(`harness_session_id`, `workspace_root`, `prompt`) and sets
`OVERHAUST_CURSOR_PROMPT_FILE` plus `OVERHAUST_CURSOR_SESSION_ID` on that
child only. The prompt is not an environment variable. The hook reads the
file only when the harness session id matches and `workspace_root` is one of
stdin `workspace_roots`. On a resolver or seam error it prints `{}`, writes
a debug record, and logs the error. It does not inject empty context.

The debug record has `fired`, `error`, exact `context_bytes`, ESTIMATED
`estimated_context_tokens` from `TokenEstimator`, and exact `latency_ms`
(hook wall time). Retrieval latency stays unavailable.

### Isolation

The only intended difference between conditions is that hook. Neither
condition may have OverHaust MCP tools. Two strategies:

1. `isolated-home` — per-session temp HOME, no copied credentials, auth from
   `CURSOR_API_KEY`. Preflight runs `cursor-agent mcp list` in a temp HOME
   that contains only a sentinel server. The strategy is usable only when
   that list shows the sentinel and does not show `overhaust`. That preflight
   does not call `mcp disable`.
2. `mcp-toggle` — for each session, both conditions the same way,
   `cursor-agent mcp disable overhaust` with cwd set to that session's fresh
   temp workspace, then `mcp list` from the same cwd. CLI 2026.09.26 writes
   the server name to `~/.cursor/projects/<slug>/mcp-disabled.json`, and the
   slug is derived from `process.cwd()`. Disabling from the user home does
   not hide OverHaust in the session workspace. The harness diffs
   `~/.cursor/projects` before and after the command and deletes only slug
   directories that appeared for that call. It does not modify a slug that
   already existed. After the session, including on failure or interrupt, it
   checks that those new directories are gone. Other global MCP servers stay.
   That is a confounder of this strategy, not of `isolated-home`.

`mcp list` and `mcp disable` start configured MCP servers. Each workspace
calls each command once. Cleanup does not call them again.

Preflight (`--preflight`) checks the CLI, auth, whether the model is listed,
and only the strategy named by `--isolation`. Every preflight command uses a
throwaway directory as cwd. It does not use the user home or a project
directory. Before any CLI call it snapshots `cli-config.json`,
`agent-cli-state.json`, `statsig-cache.json`, `mcp.json`, and the
`~/.cursor/projects` listing, and it restores those files and deletes slug
directories created during the probe, including when a probe raises.
Pre-existing slugs are not modified. After restore, `mcp.json` must be
byte-identical; that check is in the preflight output. If the isolated-home
probe's temp HOME is ignored and the CLI writes a slug under the real
`~/.cursor/projects`, that slug is removed and isolated-home is unusable.
The mcp-toggle probe disables OverHaust in its own throwaway workspace and
deletes only the slug that command created. It does not pass `-p`.

If an OverHaust MCP tool is available or called in either condition, that
session is invalid and the run stops before the next session. The report is
still written and the Cursor state files are restored.

`--model` rewrites `~/.cursor/cli-config.json` keys `model`, `selectedModel`,
`modelParameters`, `hasChangedDefaultModel`, and `modelSelectionHistory`.
The run also rewrites `agent-cli-state.json` and `statsig-cache.json`. The
harness snapshots those files and restores them afterward, including when a
session fails.

### Telemetry

`cacheReadTokens` is a separate bucket. It is not included in `inputTokens`
and is not subtracted. Reasoning tokens and a provider total are
UNAVAILABLE. A sum of exact components is labeled DERIVED and is not stored
as `agent_total_tokens`. Missing numbers stay null. Files inspected are
EXACT unique `readToolCall` paths, or UNAVAILABLE when tool events were not
parsed. They are never inferred from the prompt.

Do not compare Cursor figures to Codex figures.

### Injection check

Hook debug is required for an OverHaust session to be valid. When
`~/.cursor/chats/<hash>/<session>/store.db` can be scanned, the marker
`<!-- overhaust-context -->` must be present for OverHaust and absent for
baseline, and an OverHaust tool catalog entry or tool call marks the session
invalid. If the store cannot be parsed, verification is `hook-log-only`.

### Validity and means

Invalid sessions (bad snapshot, wrong hooks file, hook error, empty context,
MCP tool available or called, marker mismatch, overhaust still listed after
a workspace disable, a pre-existing project slug touched, or slug cleanup
not verified) stay in the dataset and are excluded from means. Failed
outcomes and incorrect answers stay in the dataset and in the primary means.
Timeouts are recorded. Unavailable figures are not treated as zero.

Provider-side prompt caching was not independently controlled; cached-input usage was recorded and retained as part of the measured session usage.

Reports: `benchmarks/results/layer4-cursor-<UTC stamp>.json` and `.md`.
Names are never overwritten. This remains an instrumentation record, not a
product claim.
