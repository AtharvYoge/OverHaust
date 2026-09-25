# OverHaust context-efficiency benchmark

> **No percentage token reduction should be claimed until the benchmark has
> produced reproducible measurements.**

This package is an **isolated harness**. It measures experiments; it does not
participate in answering coding questions and is **not** part of the production
retrieval / context path.

## What is being measured

For each task, under two conditions:

| Condition | Meaning |
|-----------|---------|
| **baseline** | Same task prompt; agent explores the repo with its normal tools (or, in automated mode, a simulated naïve search + full-file read). |
| **overhaust** | Same task prompt; OverHaust context is obtained first via the existing `invoke_context_request()`, then (in a live session) made available before further exploration. |

Held constant across conditions (fairness rules):

1. Same repository / fixture  
2. Same task wording  
3. Same model (when a live agent is used)  
4. Same model configuration / temperature where applicable  
5. Same available repository tools where possible  
6. Multiple repetitions (`--runs N`)  
7. Individual runs retained (not only averages)

## What is NOT being measured

- Live Cursor / Codex / Claude session quality (unless you supply MANUAL run records)
- Product “tokens saved” marketing claims
- Indexing cost inside query-time totals
- Amortized cost (until indexing cost + enough runs are both measured)
- LLM-as-judge answer quality (first version is deterministic markers only)

## Architecture

```
benchmarks/
  tasks/initial|adversarial/   tasks + rubrics (defined before results)
  runners.py                   Layer 1 synthetic
  sim_agent.py                 Layer 2 deterministic agent
  providers.py                 Layer 3/4 ingest + provider interface
  experiment.py                Layer orchestration
  trace.py                     provider-neutral AgentTrace
  report.py                    A/B/C/D/E report sections
  breakeven.py                 break-even scaffolding (null if unmeasured)
  matrix.py                    category × size matrix
  repos.py                     SMALL / MEDIUM / LARGE fixtures
  REAL_AGENT_PROTOCOL.md       fairness + layer rules
  results/                     run / layer2 / layer3 artifacts
```

Four layers — **do not conflate** (see `REAL_AGENT_PROTOCOL.md`):

1. Synthetic context-size  
2. Deterministic tool simulator  
3. Real model/API (ingest or future provider)  
4. Live IDE sessions (ingest)

Production seam used (read-only call):

```
invoke_context_request(project_id, prompt, memory_store=...)
  → AgentContextResponse
```

Budgets and behaviour are **not** overridden by the harness.

## Baseline definition

**AUTOMATED (default):**  
`packages.context.benchmark.simulate_naive_agent_exploration` — search top hits, read full file contents. This is a **context-size proxy**, clearly labelled. `tool_calls`, `input_tokens`, and `output_tokens` stay `null`.

**MANUAL:**  
Ingest a real agent session record (see below). Prefer this for claims about agent token/tool behaviour.

## OverHaust definition

**AUTOMATED:** call existing `invoke_context_request()` with the task prompt and fixture `project_id`. Record returned `context` size and engine metrics. Do not change how context is generated.

**MANUAL:** ingest a session where OverHaust context was injected (hooks/MCP) before exploration.

## Token accounting

| Kind | When |
|------|------|
| `exact_token_count` | Provider / agent telemetry supplied via MANUAL ingest (`TokenCounter.record_exact`) |
| `estimated_token_count` | tiktoken via existing `TokenEstimator` (or explicit char/4 fallback if tiktoken unavailable) |
| `unavailable` | Field not measured (`null`) |

**Never** silently mix exact and estimated in one comparison.  
**Never** treat character-length heuristics as exact tokens.

### Query-time vs indexing cost

- **QUERY-TIME** metrics: `context_tokens` / `total_tokens` on the run (for automated mode, total = context size only).
- **Indexing cost**: stored separately as `indexing_cost_tokens` when known; **excluded** from query-time totals.
- **Amortized impact**: not computed until indexing cost and sufficient runs exist.

Do **not** claim “OverHaust saves X% tokens” from query-time context size alone while ignoring indexing.

## Correctness accounting

Deterministic checks (no LLM judge yet):

- required fact markers must appear in `answer_text`
- expected files / symbols scored for `evidence_score`

If `answer_text` is absent (automated context-size runs), `correctness` is `null`.

## How to run

```bash
# Layer 1 — synthetic context-size
python3 -m benchmarks.run --layer 1 --compare --task-set initial --runs 5

# Layer 2 — deterministic agent (same tools; OverHaust context optional)
python3 -m benchmarks.run --layer 2 --task-set initial --repo-size medium --runs 5 --seed 1
python3 -m benchmarks.run --layer 2 --task-set adversarial --repo-size small --runs 3

# Layer 3 live pair (same runner; OverHaust context is the only difference)
python3 -m benchmarks.run --layer 3 --compare --dry-run --task sym_generate_kot --runs 1 --repo-size small
python3 -m benchmarks.run --layer 3 --compare --task sym_generate_kot --runs 5 --repo-size small --seed 1

# Layer 3/4 — ingest real provider/IDE traces (exact tokens)
python3 -m benchmarks.run --layer 3 --ingest path/to/traces.json --task-set initial

# Optional measured indexing cost for break-even (do not invent)
python3 -m benchmarks.run --layer 2 --task-set initial --runs 5 \
  --indexing-cost-tokens 12000
```

Outputs:

- `benchmarks/results/run-<timestamp>.json`
- `benchmarks/results/run-<timestamp>.md`

## Manual run record shape

```json
{
  "runs": [
    {
      "task_id": "sym_generate_kot",
      "condition": "baseline",
      "timestamp": "2026-09-20T12:00:00Z",
      "model": "your-model",
      "input_tokens": 1500,
      "output_tokens": 300,
      "total_tokens": 1800,
      "input_tokens_kind": "exact_token_count",
      "output_tokens_kind": "exact_token_count",
      "total_tokens_kind": "exact_token_count",
      "tool_calls": 8,
      "files_inspected": 5,
      "answer_text": "...",
      "measurement_source": "MANUAL"
    }
  ]
}
```

Omit fields you cannot measure; leave them `null`. Do not invent values.

## How to add tasks

1. Add `benchmarks/tasks/<set>/<task_id>.json` with required fields  
   (`task_id`, `title`, `prompt`, `project_id`, `expected_answer_requirements`,
   `difficulty`, `category`).
2. Prefer real fixture or indexed-repo concepts (no unanswerable invented questions).
3. Categories: `symbol_lookup`, `code_flow`, `architecture`, `cross_file_reasoning`, `change_impact`.
4. Load with `--task-set <set>`.

## How to interpret results

- Read `measurement_source` and `*_tokens_kind` on every run.
- Prefer MANUAL + exact counts for agent-efficiency claims.
- Automated reductions are **query-time context-size** only.
- Check correctness / evidence before celebrating a token reduction.
- Indexing cost is out of band until explicitly measured.

## Relation to older scripts

| Path | Role |
|------|------|
| `packages/context/benchmark.py` | Earlier size-comparison helpers (reused, not modified) |
| `scripts/agent_benchmark.py` | Ad-hoc CLI for one prompt |
| `tests/evaluation/retrieval_benchmark.py` | Conversation-memory retrieval precision |
| **`benchmarks/` (this package)** | Controlled A/B harness + schema + ingest |

## Initial five tasks

All use fixture `labkot_retrieval` (`make_labkot_retrieval_tree`):

1. `sym_generate_kot` — symbol lookup  
2. `flow_order_to_kitchen` — forward code flow  
3. `cross_order_to_printer` — cross-file reasoning  
4. `impact_change_generate_kot` — change impact  
5. `arch_kitchen_hardware` — architecture explanation  
