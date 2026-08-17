# Overhaust Evaluation Report

_Generated: 2026-08-17T16:50:56_

All token counts are **measured** via tiktoken (`cl100k_base`). Reduction % is an **estimate** (tiktoken is not provider billing). Retention / removal use **human-reviewed** ground-truth expectations defined in `tests/evaluation/scenarios.py`.

## Summary (measured + estimated)

- Scenarios: **10**
- Inputs actually reduced: **4** / compact (no reduction): **6**
- Average reduction (reduced inputs only): **32.6%** _(estimated)_
- Median reduction: **20.9%** _(estimated)_
- Best-case reduction: **76.0%** _(estimated)_
- Worst-case reduction: **12.5%** _(estimated)_
- Average information retention: **100.0%** _(human-reviewed)_
- Average irrelevant-removal: **100.0%** _(human-reviewed)_
- Scenario failures: **0**

> The average reduction is **not** the general result. Reduction depends heavily on input repetition — see per-scenario table and limitations.

## Per-scenario results

| Scenario | Original | Structured | Prepared | Reduction | Retention | Removal | Product verdict |
|----------|---------:|-----------:|---------:|-----------|-----------|---------|-----------------|
| Long coding conversation | 240 | 92 | 191 | 20.4% | 100.0% | 100.0% | Estimated context reduction: 20.4% |
| Long startup/project conversation | 176 | 53 | 154 | 12.5% | 100.0% | 100.0% | Estimated context reduction: 12.5% |
| Research conversation | 112 | 47 | 132 | — | 100.0% | 100.0% | This input is already compact. |
| Repetitive AI conversation | 103 | 17 | 112 | — | 100.0% | 100.0% | This input is already compact. |
| Conversation with contradictory decisions | 75 | 6 | 107 | — | 100.0% | 100.0% | This input is already compact. |
| Conversation with resolved and unresolved issues | 78 | 44 | 99 | — | 100.0% | 100.0% | This input is already compact. |
| Conversation with irrelevant discussion | 88 | 19 | 101 | — | 100.0% | 100.0% | This input is already compact. |
| Important information buried deep | 496 | 39 | 119 | 76.0% | 100.0% | 100.0% | Estimated context reduction: 76.0% |
| Short conversation | 20 | 8 | 79 | — | 100.0% | 100.0% | This input is already compact. |
| Conversation with almost no repetition | 103 | 40 | 81 | 21.4% | 100.0% | 100.0% | Estimated context reduction: 21.4% |

- **Original** → **Structured**: conversation ingested into structured memory (measured).
- **Prepared**: task-specific context built by the engine (measured).
- **Reduction**: original → prepared, only shown when prepared < original (estimated).

## Failures & flags

No hard failures across the scenario suite (all critical info retained, all known-irrelevant info removed). Documented **limitations** below still apply.

## Real-project test (Overhaust repo indexed by the engine)

- Files indexed: **65** (83617 tokens) in **110.5ms** _(measured)_
- Retrieval hit-rate: **80.0%** _(human-reviewed relevance)_
- Average query latency: **0.99ms** _(measured)_

| Query | Latency | Context tokens | Result | Relevant files |
|-------|--------:|---------------:|--------|----------------|
| How does conversation ingestion work? | 1.04ms | 330 | HIT | services/ingestion/conversation.py, services/ingestion/test_conversation.py |
| Where is memory stored? | 0.95ms | 266 | MISS | (none) |
| How does context selection work? | 0.97ms | 290 | HIT | packages/context/test_context_builder.py |
| How does the MCP server expose tools? | 1.0ms | 132 | HIT | services/mcp_server/server.py, services/mcp_server/__init__.py, services/mcp_server/test_server.py |
| Where should I modify relevance scoring? | 0.99ms | 309 | HIT | packages/context/test_relevance.py, packages/context/relevance.py |

## Where Overhaust works best / worst

**Works best (largest honest reduction):**
- Long conversations with lots of filler / repetition (e.g. *buried*: 76%, *coding*: repetition + chatter).
- Conversations where critical facts are stated with clear trigger phrasing ("we decided…", "the architecture is…", "X is still broken").

**Does not help (correctly reports 'already compact'):**
- Short inputs (*short*: 20 tokens) — metadata overhead exceeds any saving.
- Dense, unique, low-repetition conversations (*no_repetition*) — little to remove.
- Small conversations where the prepared context (task + knowledge + decisions) is naturally larger than the raw text.

## Current limitations (honest)

1. **Extraction is trigger-phrase based.** Plain declarative facts without a cue verb (e.g. *'ConnectionManager owns the socket lifecycle'*) are not extracted. Recall depends on phrasing.
2. **No historical decision chain.** In the contradiction case the *current* decision (PostgreSQL) is retained and ranked correctly, but the superseded MongoDB decision is dropped rather than kept as explicit history.
3. **Filename tokenization gap.** "Where is memory stored?" missed `memory_store.py` because 'stored' doesn't token-match 'memory_store'. Retrieval is lexical, not semantic.
4. **Near-duplicate dedup is exact-ish.** Reworded repetitions are only partially collapsed; true semantic dedup needs embeddings (deferred).
5. **Reduction % is estimated**, not measured against a provider's billed usage.
6. **`_get_relevant_files` in the context builder is still a placeholder** — the context package's `relevant_files` are illustrative; real file linkage flows through the separate project-index path used in the real-project test.

## Recommended algorithm changes (prioritized)

1. **Add a lightweight declarative-fact extractor** (subject-verb-object on `X is/are/uses Y`) to raise recall on plain statements without cue verbs.
2. **Retain superseded decisions as `stale` history** linked to the current decision, so the contradiction chain is queryable without being ranked equally.
3. **Tokenize identifiers on `_`/camelCase** in both content and queries so `memory_store` matches 'memory stored'.
4. **Wire `_get_relevant_files`** in the context builder to the real project index instead of the placeholder.
5. **Introduce optional local embeddings** behind the existing `RelevanceEngine` interface for semantic dedup + synonym matching, keeping the layered engine as the zero-dependency default.

_This report is generated by `scripts/evaluate.py` from live engine runs; re-run to refresh._
