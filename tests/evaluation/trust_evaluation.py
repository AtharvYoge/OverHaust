"""Deterministic trust evaluation scenarios (Phase 2C)."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from packages.memory.memory_store import MemoryStore
from packages.context.retrieval import search_project_knowledge
from packages.context.context_engine import ContextAssembler
from packages.knowledge.versioning import supersede


REPORT_PATH = Path(__file__).parent / "trust_evaluation_report.md"


def _run_scenarios():
    metrics = {
        "current_selected": 0,
        "superseded_excluded": 0,
        "provenance_present": 0,
        "confidence_preserved": 0,
        "false_certainty": 0,
        "insufficient_evidence": 0,
        "total_scenarios": 6,
    }
    notes = []

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        store.add_project("trust-p", "Trust Eval", "", "")
        asm = ContextAssembler(memory_store=store)

        # 1. Old vs new architecture (Firebase → Auth0)
        old_id = store.add_memory(
            "trust-p", "Authentication uses Firebase", "permanent", 0.85,
            {"knowledge_type": "decision", "confidence": 0.7, "status": "active",
             "provenance": "Conversation old", "source_ref": "Conversation old"},
        )
        supersede(
            store, "trust-p", old_id,
            "Authentication uses Auth0",
            confidence=0.95, provenance="User update",
        )
        r1 = search_project_knowledge("trust-p", "what auth provider", memory_store=store)
        if r1 and "Auth0" in r1[0]["content"]:
            metrics["current_selected"] += 1
        if not any("Firebase" in x["content"] for x in r1):
            metrics["superseded_excluded"] += 1

        # 2. Resolved bug vs active bug on fix query
        store.add_memory(
            "trust-p", "RESOLVED: WebSocket reconnect bug fixed in v2", "resolved", 0.7,
            {"knowledge_type": "resolved_issue", "status": "resolved", "confidence": 0.8},
        )
        store.add_memory(
            "trust-p", "WebSocket reconnect bug still open on mobile", "task", 0.9,
            {"knowledge_type": "open_issue", "status": "active", "confidence": 0.85},
        )
        r2 = search_project_knowledge("trust-p", "fix websocket reconnect bug", memory_store=store)
        if r2 and "still open" in r2[0]["content"]:
            metrics["current_selected"] += 1
        if not any("RESOLVED" in x["content"] for x in r2):
            metrics["superseded_excluded"] += 1

        # 3. High vs low confidence — trust ordering differs from relevance
        store.add_memory(
            "trust-p", "Database is PostgreSQL with pgvector optional", "permanent", 0.5,
            {"knowledge_type": "permanent_knowledge", "confidence": 0.95, "status": "active",
             "provenance": "Architecture doc", "source_ref": "Architecture doc"},
        )
        store.add_memory(
            "trust-p", "Database might be MongoDB maybe", "temporary", 0.5,
            {"knowledge_type": "permanent_knowledge", "confidence": 0.2, "status": "active"},
        )
        r3 = search_project_knowledge("trust-p", "database storage", memory_store=store)
        if len(r3) >= 2 and r3[0]["trust_score"] >= r3[1]["trust_score"]:
            metrics["confidence_preserved"] += 1

        # 4. File evidence vs conversation claim
        store.add_memory(
            "trust-p", "AuthService validates JWT tokens", "permanent", 0.8,
            {"knowledge_type": "permanent_knowledge", "source_type": "file",
             "source_ref": "src/auth/AuthService.ts", "provenance": "src/auth/AuthService.ts",
             "confidence": 0.9, "status": "active"},
        )
        r4 = search_project_knowledge("trust-p", "JWT validation", memory_store=store)
        if r4 and r4[0].get("provenance") == "src/auth/AuthService.ts":
            metrics["provenance_present"] += 1

        # 5. Missing evidence — empty project
        store.add_project("empty-p", "Empty", "", "")
        asm_empty = ContextAssembler(memory_store=store)
        ctx = asm_empty.assemble_context("empty-p", "quantum entanglement deployment strategy", max_knowledge_items=3)
        if ctx.insufficient_evidence:
            metrics["insufficient_evidence"] += 1

        # 6. Conflicting knowledge — supersession queryable
        old2 = store.add_memory(
            "trust-p", "Cache layer uses Redis", "permanent", 0.8,
            {"knowledge_type": "decision", "confidence": 0.7, "status": "active"},
        )
        new2 = supersede(store, "trust-p", old2, "Cache layer uses Memcached", confidence=0.9)
        old_mem = store.get_memory(old2)
        new_mem = store.get_memory(new2)
        if old_mem["metadata"]["superseded_by"] == new2 and new_mem["metadata"]["supersedes"] == old2:
            metrics["confidence_preserved"] += 1

        # false certainty: trust < 0.4 returned without low-trust reason
        for row in r3:
            if (row.get("trust_score") or 1) < 0.4:
                reasons = (row.get("metadata") or {}).get("trust", {}).get("reasons", [])
                if not any("low trust" in r.lower() or "Low confidence" in r for r in reasons):
                    metrics["false_certainty"] += 1

        notes.append(f"- current_selected: {metrics['current_selected']}/2 applicable")
        notes.append(f"- superseded/stale excluded: {metrics['superseded_excluded']}/2")
        notes.append(f"- provenance present: {metrics['provenance_present']}/1")
        notes.append(f"- confidence/links preserved: {metrics['confidence_preserved']}/2")
        notes.append(f"- insufficient_evidence detected: {metrics['insufficient_evidence']}/1")
        notes.append(f"- false_certainty count: {metrics['false_certainty']} (target 0)")

    finally:
        os.unlink(db)

    return metrics, notes


def write_report(metrics, notes):
    lines = [
        "# Trust Evaluation Report (Phase 2C)",
        "",
        "Deterministic scenarios — no LLM, no embeddings required.",
        "",
        "## Metrics",
        "",
    ]
    lines.extend(notes)
    lines.extend([
        "",
        "## Summary",
        "",
        f"Scenarios run: {metrics['total_scenarios']}",
        "",
        "Run: `python3 -m tests.evaluation.trust_evaluation`",
    ])
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main():
    metrics, notes = _run_scenarios()
    write_report(metrics, notes)
    print("\n".join(notes))
    assert metrics["false_certainty"] == 0, "false certainty detected"
    print(f"\nReport written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
