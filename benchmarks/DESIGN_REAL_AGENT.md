# Design note — real-agent benchmark extension (Phase 2)

## A. Current architecture (before this phase)

Layer 1 only under `benchmarks/`: synthetic context-size comparison, TokenCounter,
ingest hooks, 5 LabKOT tasks. No tool traces, multi-size repos, rubrics, break-even,
or real-model protocol.

## B. What was missing

Provider-neutral traces; Layer 2 simulator; Layer 3/4 ingest; SMALL/MEDIUM/LARGE;
adversarial tasks; AnswerRubric; p25/p75/CI; break-even scaffolding; matrix;
reproducibility metadata; A/B/C/D/E report sections.

## C. Files added/extended

- `trace.py`, `sim_agent.py`, `repos.py`, `providers.py`, `experiment.py`
- `breakeven.py`, `matrix.py`, `report.py`, `repro.py`
- `REAL_AGENT_PROTOCOL.md`, `tasks/adversarial/*`, `test_real_agent.py`
- Extended: `schemas.py`, `evaluate.py`, `metrics.py`, `run.py`, `README.md`

## D. Measurement methodology

- **Layer 2:** identical `RepoTools` (search/read/list); OverHaust condition only
  adds `invoke_context_request()` context first. Tokens = estimated transcript size.
- **Layer 3/4:** exact tokens only via ingest / future `ModelProvider`; never invented.
- Reductions computed only within one token kind; correctness via pre-defined rubrics.

## E. Threats to validity

Layer 2 ≠ real model tool choice; substring search ≠ IDE search; tiny fixtures can
invert savings; indexing cost omitted unless measured; CI unreliable for small n.

## F. Explicitly untouched

`packages/context/*`, `packages/retrieval/*`, `invoke_context_request` behaviour,
`interception.py`, `hook_io.py`, existing host integrations.
