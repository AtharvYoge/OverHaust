# Layer 4 — real-agent session instrumentation

Measures isolated coding-agent sessions on the Layer 3 tasks. Codex CLI is
the first adapter. Cursor and Claude Code are not implemented; the
`AgentAdapter` interface and `Layer4SessionResult` schema are what they will
share.

This is not a product benchmark result. It does not modify Layer 3, retrieval,
or `invoke_context_request`.

Read [PROTOCOL.md](PROTOCOL.md) for isolation rules, validity, and what happens
to failures.

## Presets

The default preset is the 8-session pilot. `--preset full` is all 5 Layer 3
tasks × both conditions × 2 reps = 20 sessions. Seed defaults to `1`.
Each `(task, rep)` is a pair: within a task the two reps use opposite
condition orders, and the two sessions of a pair run back-to-back. Pair units
are shuffled with that seed.

```bash
python3 -m benchmarks.layer4.pilot --model <model>
python3 -m benchmarks.layer4.pilot --preset full --model <model>
```

`<model>` is passed to every session as `codex exec --model`. Use the same
model Codex is actually configured to run (whatever you would pass to
`codex exec -m` on that machine). You can also set `LAYER4_CODEX_MODEL`.

Plan only, no Codex process and no provider call:

```bash
python3 -m benchmarks.layer4.pilot --dry-run
python3 -m benchmarks.layer4.pilot --preset full --dry-run
```

The same full plan, baseline sessions only (10 sessions for seed 1). Fixture,
prompts, scoring, tool configuration, seed, and timeout match the 20-session
run. The hook stays absent on baseline.

```bash
python3 -m benchmarks.layer4.pilot --dry-run --preset full --conditions baseline --model gpt-5.5
```

`--conditions` defaults to both `baseline` and `overhaust`. One condition
keeps that condition's sessions from the pair-counterbalanced plan, in the
same relative order. The report records each kept session's original pair id
and its original planned position.

The pilot matrix is `sym_generate_kot` and `arch_kitchen_hardware` ×
`baseline` / `overhaust` × 2 reps. The full matrix uses every task in
`benchmarks/tasks/initial`.

Results land in `benchmarks/results/layer4-<timestamp>.json` (and a `.md`
summary). Existing result files are not overwritten.

## Prerequisites

1. **Codex CLI 0.146.0** on `PATH` (`codex --version`). The adapter was checked
   against the `rust-v0.146.0` JSONL schema. Another version still runs; the
   report records the real version and a warning, and fields that CLI does not
   emit stay `unavailable`.
2. **Auth, one of:**
   - **API key:** `OPENAI_API_KEY` or `CODEX_API_KEY` in the environment.
     `codex exec` reads `CODEX_API_KEY`. If only `OPENAI_API_KEY` is set, the
     runner copies it into `CODEX_API_KEY` for the child process. The key is
     not written into the result file.
   - **Codex login:** `codex login` so `~/.codex/auth.json` exists (or
     `$CODEX_HOME/auth.json` if `CODEX_HOME` is already set). The runner copies
     **only** that file into each session's private Codex home. It does not
     copy sessions or hooks.
3. **This repo's Python environment**, because the OverHaust condition runs
   `scripts/integrations/overhaust_user_prompt_hook.py`. The runner builds and
   indexes a temporary LabKOT fixture and points the hook at it with
   `OVERHAUST_DB_PATH` and `OVERHAUST_PROJECT_ID`. The production memory
   database is not used.
4. **Network access to the model provider** for a live run. Eight sessions
   for the pilot, twenty for `--preset full`. CI and unit tests do not make
   that call.

Example:

```bash
OPENAI_API_KEY=sk-... python3 -m benchmarks.layer4.pilot --model gpt-5.4
```

Replace `gpt-5.4` if that is not the model your Codex CLI should run.
A live pilot without `--model` still starts, but `model_pinned` is false and
later comparison should not treat the model as controlled.

## What the Codex adapter captures

Checked against Codex CLI 0.146.0 `codex exec --json` and session rollouts
under the isolated `CODEX_HOME`. Details are in [PROTOCOL.md](PROTOCOL.md).

| Measurement | Captured? | Kind |
|-------------|-----------|------|
| Input tokens | Yes, from the last `turn.completed.usage.input_tokens` (cumulative thread total). Cached input is not subtracted. | exact |
| Cached input tokens | Yes, when that field is present. A missing field stays null, not zero. Cached tokens are a component of input and stay inside that total. Provider prompt caching is not disabled and prompts are not cache-busted. | exact or unavailable |
| Output tokens | Yes, from `usage.output_tokens` | exact |
| Reasoning output tokens | Yes, when present. Not subtracted from output. | exact or unavailable |
| Cache-write input tokens | Yes, when present. | exact or unavailable |
| Single `total_tokens` | Not in the exec JSON usage object. Taken only from a rollout `token_count.total_token_usage.total_tokens` when its components match the exec usage. If that provider total is absent, the field stays unavailable. Never summed by this harness. | exact or unavailable |
| Per-request `last_token_usage` | Stored as supplemental telemetry only. Not the session total. | not a primary field |
| Tool calls | Yes, completed command / MCP / collab / web-search items | exact |
| Files changed | Yes, byte diff of the fixture against the snapshot, plus Codex `file_change` paths as a separate count | exact |
| Files inspected | No structured file-read event in 0.146.0 exec JSONL | unavailable |
| Elapsed time | Yes, wall clock around the subprocess | exact |
| OverHaust context tokens | Yes, hook debug `estimated_context_tokens` (TokenEstimator). Separate from agent tokens. Never subtracted. | estimated |
| OverHaust context bytes | Yes, hook debug `context_bytes` | exact |
| OverHaust retrieval latency | No. Hook `latency_ms` under debug is end-to-end hook time, recorded as `overhaust_hook_latency_ms` instead. | unavailable |
| Correctness | Yes, Layer 3 task rubric on the final agent message | bool or null |
| Agent version, model, condition, task, rep, seed, pair id, order in pair, condition order, execution order, snapshot hash, raw telemetry paths | Yes | — |
| Cache analysis (task × condition and condition overall) and per-session tool-call counts | Yes, in the JSON and markdown reports. Means use valid sessions with exact figures. | — |

Provider-side prompt caching was not independently controlled; cached-input usage was recorded and retained as part of the measured session usage.

The OverHaust condition is the existing UserPromptSubmit hook, not a prompt prefix.
Baseline is the same command with no hook installed.

## Layout

```
benchmarks/layer4/
  PROTOCOL.md          isolation, validity, missing data
  schema.py            Layer4SessionResult
  adapters.py          interface; Cursor and Claude Code are refused
  codex_adapter.py     map a captured Codex session onto the schema
  codex_parse.py       exec JSONL, rollout, hook debug
  condition.py         baseline vs OverHaust Codex home
  matrix.py            pilot and full presets, pair order
  runner.py            execute the matrix, write timestamped results
  cli.py / pilot.py    python3 -m benchmarks.layer4.pilot
  fixtures/            recorded Codex output for unit tests
  test_layer4.py
```

## Tests

```bash
python3 -m pytest benchmarks/layer4/test_layer4.py -q
```

Tests replay fixture JSONL and a fake `codex` process. They do not need
`OPENAI_API_KEY` or a network.
