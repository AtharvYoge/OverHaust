"""
Deterministic retrieval benchmark for Overhaust Phase 2B.

Measures real precision, coverage, latency, and token counts.
Run: python3 -m tests.evaluation.retrieval_benchmark
"""

import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from services.ingestion.conversation import ConversationIngestor
from packages.memory.memory_store import MemoryStore
from packages.context.context_engine import ContextAssembler
from packages.context.relevance import LayeredRelevanceEngine
from packages.tokenization.token_estimator import TokenEstimator
from packages.context.retrieval import search_project_knowledge, get_relevance_engine


@dataclass
class RetrievalScenario:
    id: str
    title: str
    conversation: str
    query: str  # paraphrased task (may differ from stored wording)
    expected_important: List[str] = field(default_factory=list)
    expected_irrelevant: List[str] = field(default_factory=list)


PARAPHRASE_SCENARIOS: List[RetrievalScenario] = [
    RetrievalScenario(
        id="paraphrase_websocket",
        title="Paraphrase: idle connection recovery",
        conversation=(
            "## User\n"
            "The WebSocket reconnect bug is still open: connection drops after 60s idle.\n\n"
            "## User\n"
            "We decided to use WebSocket heartbeats every 30 seconds.\n\n"
            "## User\n"
            "Marketing landing page copy and pricing tiers.\n"
        ),
        query="Fix idle connection recovery in realtime messaging",
        expected_important=["WebSocket", "heartbeat", "reconnect", "idle"],
        expected_irrelevant=["Marketing", "pricing"],
    ),
    RetrievalScenario(
        id="paraphrase_auth",
        title="Paraphrase: authentication architecture",
        conversation=(
            "## User\n"
            "We decided the auth architecture uses JWT access tokens with 15-minute expiry "
            "and refresh tokens in httpOnly cookies.\n\n"
            "## User\n"
            "The weather is nice today.\n"
        ),
        query="How does user login and session renewal work?",
        expected_important=["JWT", "refresh", "httpOnly", "token"],
        expected_irrelevant=["weather"],
    ),
    RetrievalScenario(
        id="paraphrase_database",
        title="Paraphrase: database decision",
        conversation=(
            "## User\n"
            "We decided to use PostgreSQL as our primary database for the application.\n\n"
            "## User\n"
            "Unrelated pizza discussion.\n"
        ),
        query="What persistence layer did we choose for data storage?",
        expected_important=["PostgreSQL"],
        expected_irrelevant=["pizza"],
    ),
]


@dataclass
class BenchmarkResult:
    scenario_id: str
    mode: str
    precision_at_k: float
    coverage: float
    irrelevant_hits: int
    top_k: int
    latency_ms_mean: float
    original_tokens: int
    prepared_tokens: int
    measured: bool = True


def _score_results(
    results: List[Dict[str, Any]],
    expected: List[str],
    irrelevant: List[str],
):
    """Human-reviewed substring matching (same approach as evaluation harness)."""
    haystack = "\n".join(r.get("content", "").lower() for r in results)
    hits = sum(1 for e in expected if e.lower() in haystack)
    coverage = (hits / len(expected) * 100) if expected else 100.0
    top_k = len(results)
    relevant_results = sum(
        1 for r in results
        if any(e.lower() in r.get("content", "").lower() for e in expected)
    )
    precision = (relevant_results / top_k * 100) if top_k else 0.0
    irr = sum(
        1 for r in results
        if any(i.lower() in r.get("content", "").lower() for i in irrelevant)
    )
    return precision, coverage, irr


def run_scenario(
    scenario: RetrievalScenario,
    mode: str,
    estimator: TokenEstimator,
) -> BenchmarkResult:
    os.environ["OVERHAUST_EMBEDDINGS"] = "1" if mode == "hybrid" else "0"

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name

    try:
        store = MemoryStore(db)
        store.add_project(scenario.id, scenario.title, "", "")
        ing = ConversationIngestor(estimator)
        result = ing.ingest_text(scenario.conversation, f"conv-{scenario.id}")
        ing.store_result(result, scenario.id, store)

        latencies: List[float] = []
        results = []
        for _ in range(3):
            t0 = time.perf_counter()
            results = search_project_knowledge(
                scenario.id, scenario.query, memory_store=store, limit=5
            )
            latencies.append((time.perf_counter() - t0) * 1000)

        haystack = "\n".join(r.get("content", "").lower() for r in results)
        precision, coverage, irr = _score_results(
            results, scenario.expected_important, scenario.expected_irrelevant
        )

        asm = ContextAssembler(store, estimator)
        ctx = asm.assemble_context(scenario.id, scenario.query, max_knowledge_items=5)
        prepared = estimator.estimate_tokens(
            "\n".join(k.content for k in ctx.relevant_knowledge)
        )

        return BenchmarkResult(
            scenario_id=scenario.id,
            mode=mode,
            precision_at_k=round(precision, 1),
            coverage=round(coverage, 1),
            irrelevant_hits=irr,
            top_k=len(results),
            latency_ms_mean=round(sum(latencies) / len(latencies), 2),
            original_tokens=result.original_tokens,
            prepared_tokens=prepared,
        )
    finally:
        if os.path.exists(db):
            os.unlink(db)


def generate_report(results: List[BenchmarkResult]) -> str:
    lines = [
        "# Retrieval Benchmark Report (Phase 2B)",
        "",
        "All metrics are **measured** from the real engine (not fabricated).",
        "",
        "| Scenario | Mode | Precision@k | Coverage | Irrelevant | Latency ms | Orig tokens | Prepared tokens |",
        "|----------|------|-------------|----------|------------|------------|-------------|-----------------|",
    ]
    for r in results:
        lines.append(
            f"| {r.scenario_id} | {r.mode} | {r.precision_at_k}% | {r.coverage}% | "
            f"{r.irrelevant_hits} | {r.latency_ms_mean} | {r.original_tokens} | {r.prepared_tokens} |"
        )
    lines.extend([
        "",
        "## Methodology",
        "",
        "- **Precision@k**: fraction of top-k results that contain at least one expected term",
        "- **Coverage**: fraction of expected_important items found in top-k",
        "- **Latency**: mean of 3 search calls (ms), includes embed-on-demand for hybrid",
        "- **Tokens**: tiktoken estimates (not provider billing)",
        "",
        "## Notes",
        "",
        "- Keyword-only: `OVERHAUST_EMBEDDINGS=0`",
        "- Hybrid: `OVERHAUST_EMBEDDINGS=1` with fastembed",
        "- Paraphrase queries intentionally differ from stored memory wording",
    ])
    return "\n".join(lines)


def main():
    estimator = TokenEstimator()
    results: List[BenchmarkResult] = []

    hybrid_available = False
    try:
        from packages.retrieval.embeddings import FastEmbedProvider
        from packages.shared.config import get_embedding_model
        prov = FastEmbedProvider(get_embedding_model())
        hybrid_available = prov.is_available
    except Exception:
        pass

    for scenario in PARAPHRASE_SCENARIOS:
        results.append(run_scenario(scenario, "keyword", estimator))
        if hybrid_available:
            results.append(run_scenario(scenario, "hybrid", estimator))
        else:
            print(f"Skipping hybrid for {scenario.id}: fastembed unavailable")

    report = generate_report(results)
    out_path = os.path.join(os.path.dirname(__file__), "retrieval_benchmark_report.md")
    with open(out_path, "w") as f:
        f.write(report)
    print(report)
    print(f"\nReport written to {out_path}")


if __name__ == "__main__":
    main()
