"""
Evaluation harness for Overhaust — measures the REAL engine, no fabrication.

For each scenario:
  1. ingest conversation -> structured memory (measured tokens, dedup)
  2. store into an isolated project
  3. build context for the scenario task (measured tokens)
  4. score retention/removal against human-authored ground truth

Metrics are labelled by provenance:
  - measured   : token counts from tiktoken via the engine
  - estimated  : reduction % derived from measured tokens (tiktoken != billing)
  - human-reviewed : ground-truth expectation lists in scenarios.py
"""

import sys
import os
import tempfile
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.ingestion.conversation import ConversationIngestor, compression_report
from packages.memory.memory_store import MemoryStore
from packages.context.context_engine import ContextAssembler
from packages.tokenization.token_estimator import TokenEstimator
from tests.evaluation.scenarios import Scenario, SCENARIOS


@dataclass
class ScenarioResult:
    id: str
    title: str
    task: str
    # measured
    original_tokens: int
    structured_tokens: int
    prepared_tokens: int
    duplicate_messages: int
    message_count: int
    # estimated
    structured_reduction_pct: float      # original -> structured
    prepared_reduction_pct: float        # original -> prepared context
    prepared_is_smaller: bool
    product_message: str                 # what the UI would honestly show
    # human-reviewed retention/removal
    important_retained: List[str] = field(default_factory=list)
    important_lost: List[str] = field(default_factory=list)
    retention_pct: float = 0.0
    irrelevant_removed: List[str] = field(default_factory=list)
    irrelevant_leaked: List[str] = field(default_factory=list)
    removal_pct: float = 0.0
    decisions_found: List[str] = field(default_factory=list)
    decisions_missed: List[str] = field(default_factory=list)
    open_issues_found: List[str] = field(default_factory=list)
    open_issues_missed: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    notes: str = ""


def product_reduction_message(original: int, prepared: int) -> str:
    """The honest product rule: never claim savings when prepared >= original."""
    if prepared >= original:
        return "This input is already compact."
    pct = (original - prepared) / original * 100
    return f"Estimated context reduction: {pct:.1f}%"


def _haystack_from_memories(memories) -> str:
    # Only count memories the product actually STORES (irrelevant is dropped
    # by store_result), so removal metrics reflect real behaviour.
    return "\n".join(m.content.lower() for m in memories if m.category != 'irrelevant')


def _context_haystack(ctx) -> str:
    parts = [k.content.lower() for k in ctx.relevant_knowledge]
    parts += [d.content.lower() for d in ctx.relevant_decisions]
    parts += [c.lower() for c in ctx.constraints]
    return "\n".join(parts)


def evaluate_scenario(scenario: Scenario, estimator: TokenEstimator) -> ScenarioResult:
    ingestor = ConversationIngestor(estimator)
    result = ingestor.ingest_text(scenario.conversation, scenario.id)
    report = compression_report(result, estimator)

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        store.add_project(scenario.id, scenario.title)
        ingestor.store_result(result, scenario.id, store)

        assembler = ContextAssembler(store, estimator)
        ctx = assembler.assemble_context(scenario.id, scenario.task, max_knowledge_items=12)

        original = report['original_tokens']
        structured = report['structured_tokens']
        prepared = ctx.estimated_tokens

        # --- retention: important info present in stored memory OR prepared context
        stored_hay = _haystack_from_memories(result.memories)
        ctx_hay = _context_haystack(ctx)
        combined_hay = stored_hay + "\n" + ctx_hay

        retained, lost = [], []
        for imp in scenario.expected_important:
            if imp.lower() in combined_hay:
                retained.append(imp)
            else:
                lost.append(imp)
        retention_pct = (len(retained) / len(scenario.expected_important) * 100
                         if scenario.expected_important else 100.0)

        # --- removal: irrelevant info should NOT be in stored memory
        removed, leaked = [], []
        for irr in scenario.expected_irrelevant:
            if irr.lower() in stored_hay:
                leaked.append(irr)
            else:
                removed.append(irr)
        removal_pct = (len(removed) / len(scenario.expected_irrelevant) * 100
                       if scenario.expected_irrelevant else 100.0)

        # --- decisions / open issues found in stored memory
        dec_found = [d for d in scenario.expected_decisions if d.lower() in stored_hay]
        dec_missed = [d for d in scenario.expected_decisions if d.lower() not in stored_hay]
        oi_found = [o for o in scenario.expected_open_issues if o.lower() in stored_hay]
        oi_missed = [o for o in scenario.expected_open_issues if o.lower() not in stored_hay]

        failures = []
        if lost:
            failures.append(f"LOST important info: {lost}")
        if leaked:
            failures.append(f"LEAKED irrelevant info: {leaked}")
        if dec_missed:
            failures.append(f"MISSED decisions: {dec_missed}")
        if oi_missed:
            failures.append(f"MISSED open issues: {oi_missed}")

        return ScenarioResult(
            id=scenario.id, title=scenario.title, task=scenario.task,
            original_tokens=original, structured_tokens=structured,
            prepared_tokens=prepared,
            duplicate_messages=report['duplicate_messages'],
            message_count=report['message_count'],
            structured_reduction_pct=round((original - structured) / original * 100, 1) if original else 0.0,
            prepared_reduction_pct=round((original - prepared) / original * 100, 1) if original else 0.0,
            prepared_is_smaller=prepared < original,
            product_message=product_reduction_message(original, prepared),
            important_retained=retained, important_lost=lost,
            retention_pct=round(retention_pct, 1),
            irrelevant_removed=removed, irrelevant_leaked=leaked,
            removal_pct=round(removal_pct, 1),
            decisions_found=dec_found, decisions_missed=dec_missed,
            open_issues_found=oi_found, open_issues_missed=oi_missed,
            failures=failures, notes=scenario.notes,
        )
    finally:
        if os.path.exists(db):
            os.unlink(db)


def run_all(scenarios: Optional[List[Scenario]] = None) -> List[ScenarioResult]:
    estimator = TokenEstimator()
    scenarios = scenarios or SCENARIOS
    return [evaluate_scenario(s, estimator) for s in scenarios]


def aggregate(results: List[ScenarioResult]) -> Dict[str, Any]:
    """Compute honest aggregate stats. Only count scenarios where reduction
    actually happened for reduction stats; report compact-input count separately."""
    reductions = [r.prepared_reduction_pct for r in results if r.prepared_is_smaller]
    retentions = [r.retention_pct for r in results]
    removals = [r.removal_pct for r in results if r.irrelevant_removed or r.irrelevant_leaked]

    def _median(xs):
        if not xs:
            return 0.0
        s = sorted(xs)
        n = len(s)
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

    return {
        'scenario_count': len(results),
        'compact_inputs': sum(1 for r in results if not r.prepared_is_smaller),
        'reduced_inputs': len(reductions),
        'avg_reduction': round(sum(reductions) / len(reductions), 1) if reductions else None,
        'median_reduction': round(_median(reductions), 1) if reductions else None,
        'best_reduction': max(reductions) if reductions else None,
        'worst_reduction': min(reductions) if reductions else None,
        'avg_retention': round(sum(retentions) / len(retentions), 1) if retentions else 0.0,
        'avg_removal': round(sum(removals) / len(removals), 1) if removals else None,
        'total_failures': sum(1 for r in results if r.failures),
    }
