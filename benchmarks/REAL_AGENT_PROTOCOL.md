# Real-agent benchmark protocol (Layers 2–4)

> **No percentage token reduction should be claimed as a product result until
> Layer 3+ controlled experimental data exists.**

## Four layers (do not conflate)

| Layer | What it is | Proves |
|------:|------------|--------|
| 1 | Synthetic context-size (`simulate_naive` vs `invoke_context_request`) | Context packaging size only |
| 2 | Deterministic tool-using agent simulator | Exploration *structure* under identical tools |
| 3 | Real LLM/API with repository tools | Real token/tool behaviour (needs provider or ingest) |
| 4 | Live IDE sessions (Cursor/Codex/Claude) | In-product behaviour (ingest traces) |

Layer 1/2 **never** prove Layer 3/4.

## Conditions

**BASELINE** — same model, task, repo, tools, budgets; no OverHaust context.

**OVERHAUST** — identical setup; OverHaust context from unmodified
`invoke_context_request()` is available *before* the same tools.

## Controls

- Same model / version / temperature / timeout / max tool calls  
- Same repository commit / task wording  
- Randomized job order (`--seed`)  
- Multiple `--runs`  
- No benchmark-specific OverHaust retrieval changes  
- No per-task curated context  
- Rubrics defined in task JSON **before** collecting results  

## Layer 3 experiment contract (strict)

Layer 3 may only aggregate a baseline/OverHaust pair when
`validate_layer3_pair()` returns `comparable: true`.

Every run carries an `ExperimentContract` (`benchmarks/layer3/contract.py`) with
KNOWN / UNKNOWN / UNAVAILABLE field presence. Two UNKNOWN values are **never**
treated as equal.

**Sole intentional difference between conditions:** OverHaust context
availability. Shared system prompt, user prompt (from task JSON), tool set,
budgets, model, and repository commit must match.

Exact token reduction is labelled **EXACT MEASURED REDUCTION** only when:

1. both runs are SUCCESS  
2. the pair is comparable  
3. OverHaust context inclusion in the provider input is proven  
4. provider usage totals exist on both sides  

Otherwise use **ESTIMATED REDUCTION** or exclude from primary analysis.
Failed / rejected / unpaired runs are retained in the report and never
silently dropped.

Provider runner: OpenAI Chat Completions via `benchmarks/layer3/runner.py`
(same runner for both conditions). Use `--compare` with credentials, or
`--ingest` with contract-bearing traces. `--dry-run` checks fixture size and
restoration and does not call the provider. `--ingest` does not run that check.

Trace `repository_size` is the fixture built for `--repo-size`, not the size
named in the task JSON. Before each condition the fixture is restored from a
content snapshot (or git, when the tree is a work tree) and the restore is
verified. `repository_restore.status` is `KNOWN` only after that verification.

`--runs` repeats the same temperature, seed, prompt, tools, and fixture.
Temperature defaults to 0. Identical token counts across repetitions are
protocol replicates, not independent samples. No token noise is added. Baseline
and OverHaust share one runner configuration. Answer correctness is reported
beside any exact reduction. Tukey outlier notes are descriptive; the primary
mean keeps every successful comparable pair.

## Trace schema

See `benchmarks/trace.py` (`AgentTrace`) plus `ExperimentContract` on Layer 3.
Exact provider tokens live in `input_tokens` / `output_tokens` / `total_tokens`
with `*_kind = exact_token_count`. Estimates use `estimated_*` fields only.


## CLI

```bash
# Layer 2 simulation on MEDIUM fixture
python3 -m benchmarks.run --layer 2 --task-set initial --repo-size medium --runs 5 --seed 1

# Adversarial / negative cases
python3 -m benchmarks.run --layer 2 --task-set adversarial --repo-size small --runs 3

# Layer 3 live OpenAI pair (OPENAI_API_KEY or OVERHAUST_L3_API_KEY)
python3 -m benchmarks.run --layer 3 --compare --task sym_generate_kot --runs 5 --repo-size small --seed 1

# Layer 3/4: ingest provider or IDE traces (exact metrics)
python3 -m benchmarks.run --layer 3 --ingest path/to/traces.json --task-set initial
```

## Break-even

Pass `--indexing-cost-tokens` only when indexing cost was **measured**.
Otherwise break-even stays `insufficient_data`.

## Report sections

Every Layer 2+ report contains:

- **A.** Exact measured results  
- **B.** Estimated results  
- **C.** Unsupported claims  
- **D.** Limitations  
- **E.** Statistical uncertainty  

plus matrix scaffolding and break-even status.
