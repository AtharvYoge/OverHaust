# Phase 2C Implementation Report

**Date:** August 28, 2026  
**Scope:** Provenance-aware knowledge trust (versioning, supersession, trust scoring, abstention)  
**Constraint:** RelevanceEngine unchanged; trust applied as post-processor in retrieval

---

## Summary

Phase 2C separates **relevance** (“does this match?”) from **trust** (“should we rely on it?”). Memory metadata gains versioning and supersession links. Retrieval applies a deterministic trust layer after relevance scoring. Context assembly surfaces abstention signals when evidence is weak. Confidence was removed from hybrid fusion (Phase 2B) and moved exclusively to the trust layer.

**Tests:** 112 passing with `OVERHAUST_EMBEDDINGS=0` (22 new trust-related tests).

---

## Architecture

```
Query
  │
  ▼
RelevanceEngine (unchanged — keyword or hybrid)
  │
  ▼
ScoredMemory[]  (score = relevance only)
  │
  ▼
apply_trust()  — packages/knowledge/trust.py
  ├── exclude superseded
  ├── demote resolved on fix/bug queries
  ├── keep sole low-confidence source with explanation
  └── re-sort by relevance among trusted items
  │
  ▼
format_scored_results() + ContextAssembler + abstention check
```

---

## New modules

| Module | Purpose |
|--------|---------|
| `packages/knowledge/schema.py` | `normalize_metadata()`, `bump_version()` |
| `packages/knowledge/provenance.py` | `format_provenance()` — conversation/file/symbol/user |
| `packages/knowledge/trust.py` | `TrustResult`, `compute_trust()`, `apply_trust_to_scored()` |
| `packages/knowledge/versioning.py` | `supersede()` — link old→new without deletion |
| `packages/knowledge/abstention.py` | `assess_evidence()` — insufficient evidence signals |

---

## Metadata fields (JSON, backward compatible)

| Field | Default | Notes |
|-------|---------|-------|
| `version` | `1` | Bumped on content update |
| `status` | `active` | `active`, `stale`, `resolved`, `superseded` |
| `superseded_by` | `null` | ID of replacing memory |
| `supersedes` | `null` | ID of replaced memory |
| `source_ref` | from provenance/source_id | Machine pointer |
| `source_type` | `conversation` | `conversation`, `file`, `symbol`, `user` |
| `authority` | `ingestion` | `ingestion`, `user`, `indexer`, `agent` |
| `confidence` | not fabricated | Only when set by ingestion/user |

`normalize_metadata()` runs on every memory read/write.

---

## Trust formula (deterministic)

```
status_factor:  active=1.0, resolved=0.6, stale=0.4, superseded=0.0
freshness:      exp(-age_days/30) from updated_at
provenance_q:   1.0 if provenance+source_ref, 0.7 if one, 0.5 if neither
confidence:     metadata value (0.5 neutral for formula only if missing — labeled in reasons)

trust = 0.35×confidence + 0.25×freshness + 0.25×provenance_q + 0.15×status_factor
```

**Rules:**
- `superseded` → excluded from context by default
- `resolved` → excluded when query intent is fix/bug/error
- Sole low-trust candidate → included with `"Low confidence — only available source"`

Trust is **never merged into** `ScoredMemory.score`.

---

## API changes (additive)

### Search results (`/api/v1/search-knowledge`)

Each result now includes:
- `trust_score` — separate from `score` (relevance)
- `provenance` — display string
- `metadata.trust` — `{ score, status, confidence, fresh, reasons }`
- `metadata.relevance` — unchanged `{ score, reasons, methods }`

### Context (`/api/v1/get-context`)

New top-level fields:
- `insufficient_evidence: bool`
- `evidence_note: str`

Knowledge items include `metadata.trust` and formatted `metadata.provenance`.

### Supersede (`POST /api/v1/supersede-knowledge`)

```json
{
  "project_id": "...",
  "supersedes_memory_id": "...",
  "content": "...",
  "confidence": 0.95,
  "provenance": "optional"
}
```

### MCP

- `remember` accepts optional `supersedes_memory_id`
- Search/build_context responses include trust fields

---

## Hybrid fusion change (Phase 2B → 2C)

Confidence removed from relevance fusion. New default weights:

| Term | Weight |
|------|--------|
| keyword | 0.55 |
| semantic | 0.40 |
| freshness | 0.05 |

Confidence affects **trust only**, preserving relevance/trust separation.

---

## Abstention

`assess_evidence()` runs after trust-filtered retrieval in `ContextAssembler`:

| Condition | Signal |
|-----------|--------|
| No matches | `insufficient_evidence=true`, "Needs more information — no project knowledge matched" |
| Relevance &lt; 0.15 | `insufficient_evidence=true` |
| All results low trust | `evidence_note="Low confidence — only available source"` |

User-facing labels (docs): Relevant, Current, Source, Confidence, Needs more information.

---

## Evaluation

Run:

```bash
python3 -m tests.evaluation.trust_evaluation
```

Generates `tests/evaluation/trust_evaluation_report.md` with six deterministic scenarios:

1. Firebase → Auth0 supersession (current selected, old excluded)
2. Resolved vs active bug on fix query
3. High vs low confidence trust ordering
4. File provenance preserved
5. Empty project → insufficient evidence
6. Supersession links queryable

Measured metrics: current selected, superseded excluded, provenance present, confidence preserved, false-certainty count (target 0).

---

## Files changed

| Action | Path |
|--------|------|
| Create | `packages/knowledge/*.py` (5 modules + 4 test files) |
| Create | `packages/context/test_retrieval_trust.py` |
| Create | `tests/evaluation/trust_evaluation.py`, `trust_evaluation_report.md` |
| Modify | `packages/memory/memory_store.py` — normalize metadata, version bump |
| Modify | `packages/context/relevance.py` — trust fields on `ScoredMemory` |
| Modify | `packages/context/retrieval.py` — `apply_trust()`, enriched output |
| Modify | `packages/context/context_engine.py` — abstention on `ContextPackage` |
| Modify | `packages/retrieval/hybrid.py` — confidence removed from fusion |
| Modify | `packages/shared/config.py` — `get_trust_min()`, updated hybrid weights |
| Modify | `services/ingestion/conversation.py` — `source_ref`, `authority`, `version` |
| Modify | `services/api/main.py` — supersede endpoint, context fields |
| Modify | `services/mcp_server/server.py` — supersede on remember, trust in output |
| Modify | `packages/agent/autonomous_agent.py` — `supersede_knowledge()` |
| Modify | `.env.example` — `OVERHAUST_TRUST_MIN` |

---

## Verification

```bash
OVERHAUST_EMBEDDINGS=0 python3 -m pytest -v          # 112 passed
python3 -m tests.evaluation.trust_evaluation         # 6 scenarios
OVERHAUST_EMBEDDINGS=1 python3 -m tests.evaluation.retrieval_benchmark
python3 scripts/demo.py
cd apps/web && npm run build && python3 ../scripts/verify_frontend.py
```

---

## Limitations

- Supersession is manual (API/MCP) — no automatic contradiction detection during ingest
- Trust freshness uses `updated_at` only (no domain-specific TTL rules)
- No knowledge graph — relationships are metadata links only
- Resolved-issue exclusion uses query intent heuristics (fix/bug/error keywords)

---

## Phase 2D recommendation

Add a **knowledge graph** layer (`supersedes`, `contradicts`, `supports` edges) for multi-hop reasoning and automatic staleness propagation — building on the metadata links introduced here without changing the RelevanceEngine contract.
