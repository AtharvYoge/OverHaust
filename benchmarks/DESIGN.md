# Design note — context-efficiency benchmark harness

Written before implementation (2026-09-20).

## Files inspected

- `packages/context/agent_context.py` — `invoke_context_request`, `AgentContextResponse`
- `packages/context/benchmark.py` — naïve exploration + OverHaust size helpers
- `packages/tokenization/token_estimator.py` — tiktoken `TokenEstimator`
- `tests/evaluation/retrieval_benchmark.py` — conversation retrieval scenarios
- `packages/benchmark/` — write-task implementation quality (orthogonal)
- `packages/retrieval/test_fixtures.py` — `make_labkot_retrieval_tree`
- `scripts/agent_benchmark.py` — ad-hoc single-prompt CLI

## Reused components

| Component | Use |
|-----------|-----|
| `invoke_context_request()` | OverHaust condition (unchanged call signature / budgets) |
| `simulate_naive_agent_exploration()` | Automated baseline context-size proxy |
| `TokenEstimator` | Underlying tiktoken counts inside `TokenCounter` |
| `make_labkot_retrieval_tree` | Controlled, objectively evaluable fixture |

## Where the harness lives

Top-level `benchmarks/` — separate from `packages/context` and `packages/retrieval`.
Not imported by production context code.

## Why production behaviour is unmodified

- No edits to `agent_context.py`, retrieval, indexing, or integrations.
- OverHaust runner passes only `project_id`, `prompt`, and `memory_store`.
- Fixture uses a temporary DB; production `data/overhaust_memory.db` is unused.
- Automated metrics are labelled ESTIMATED / AUTOMATED; live agent fields stay null unless MANUAL ingest supplies them.
