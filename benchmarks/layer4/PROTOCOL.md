# Layer 4 protocol

Layer 4 measures real coding-agent sessions on the same tasks as Layer 3.
The primary metric is the **agent's own provider token totals** for the
session. OverHaust's context tokens are reported beside that total and are
never subtracted from it.

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
6. Order is `random.Random(seed).shuffle` of the full matrix. The seed is
   stored on every session. Repetition index `rep` starts at 0.

The pilot matrix is:

`sym_generate_kot`, `arch_kitchen_hardware` × `baseline`, `overhaust` × 2 reps
= 8 sessions. Default seed is 1.

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

`agent_total_tokens` is exact only when a session rollout
`token_count.total_token_usage.total_tokens` is present **and** the rollout's
input/output/cached components agree with the exec usage. `last_token_usage`
is the latest request, not the session total. It is kept under
`supplemental_telemetry` and is never copied into `agent_*` fields.

OverHaust `estimated_context_tokens` comes from the hook debug file
(TokenEstimator). Kind is `estimated`. It is not subtracted from agent tokens.

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
