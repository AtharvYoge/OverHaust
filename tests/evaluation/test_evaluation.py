"""
Behavioural evaluation tests (pytest) — assert the engine handles the hard
cases from the real-world validation brief. These complement the metric
harness with explicit correctness assertions.
"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.ingestion.conversation import ConversationIngestor
from packages.memory.memory_store import MemoryStore
from packages.context.context_engine import ContextAssembler
from packages.context.relevance import LayeredRelevanceEngine
from tests.evaluation.harness import run_all, product_reduction_message


def _setup(conversation, pid):
    db = tempfile.NamedTemporaryFile(suffix='.db', delete=False).name
    store = MemoryStore(db)
    store.add_project(pid, pid)
    ing = ConversationIngestor()
    res = ing.ingest_text(conversation, pid)
    ing.store_result(res, pid, store)
    return store, db


def test_product_reduction_message_rule():
    # never claim savings when prepared >= original
    assert product_reduction_message(100, 150) == "This input is already compact."
    assert product_reduction_message(100, 100) == "This input is already compact."
    assert "reduction: 50.0%" in product_reduction_message(100, 50)
    print("✓ product rule: no negative savings claim")


def test_contradiction_prefers_current_decision():
    conv = ("## User\nWe decided to use PostgreSQL.\n\n"
            "## User\nActually we switched to MongoDB.\n\n"
            "## User\nMongoDB caused problems.\n\n"
            "## User\nWe switched back to PostgreSQL and that is final.\n")
    store, db = _setup(conv, "contra")
    try:
        results = LayeredRelevanceEngine(store).search("contra", "what database should I use", limit=10)
        contents = " ".join(r.memory['content'].lower() for r in results)
        assert 'postgresql' in contents, "current decision (Postgres) must be present"
        # Postgres should rank at/above Mongo when both present
        pg = next((i for i, r in enumerate(results) if 'postgresql' in r.memory['content'].lower()), 99)
        mongo = next((i for i, r in enumerate(results) if 'mongodb' in r.memory['content'].lower()), 99)
        assert pg <= mongo, f"Postgres (idx {pg}) should rank >= Mongo (idx {mongo})"
        print(f"✓ contradiction: Postgres ranked at/above Mongo (pg={pg}, mongo={mongo})")
    finally:
        os.unlink(db)


def test_stale_rest_vs_websocket():
    conv = ("## User\nWe are using REST for the API.\n\n"
            "## User\nWe migrated from REST to WebSockets for realtime.\n")
    store, db = _setup(conv, "stale")
    try:
        results = LayeredRelevanceEngine(store).search("stale", "implement the WebSocket handler", limit=10)
        assert results, "should retrieve something"
        top = results[0].memory['content'].lower()
        assert 'websocket' in top, f"WebSocket should rank first, got: {top}"
        print("✓ stale: WebSocket prioritized over REST for a WebSocket task")
    finally:
        os.unlink(db)


def test_resolved_issue_not_surfaced_for_unrelated_task():
    conv = ("## User\nLogin is broken, users can't sign in.\n\n"
            "## User\nFixed the login bug, it was an expired OAuth secret.\n\n"
            "## User\nThe pagination on the dashboard is still broken.\n")
    store, db = _setup(conv, "resolved")
    try:
        results = LayeredRelevanceEngine(store).search("resolved", "add a CSV export feature", limit=10)
        # the resolved login bug must NOT appear as a top active issue
        for r in results[:2]:
            meta = r.memory.get('metadata') or {}
            content = r.memory['content'].lower()
            if 'login' in content:
                assert meta.get('status') == 'resolved', "login bug must be marked resolved if surfaced"
        print("✓ resolved: old login bug not surfaced as active for unrelated task")
    finally:
        os.unlink(db)


def test_buried_information_retrieved():
    filler = "## User\njust checking in\n\n## Assistant\nall good\n\n" * 30
    buried = ("## User\nImportant: we decided the authentication architecture uses "
              "JWT access tokens with 15-minute expiry and refresh tokens in httpOnly cookies.\n")
    conv = filler + buried + filler
    store, db = _setup(conv, "buried")
    try:
        results = LayeredRelevanceEngine(store).search("buried", "how does authentication work", limit=5)
        contents = " ".join(r.memory['content'].lower() for r in results)
        assert 'jwt' in contents, "buried JWT decision must be retrieved"
        print("✓ buried: critical JWT decision retrieved from ~60 filler messages")
    finally:
        os.unlink(db)


def test_full_suite_no_regressions():
    """The metric harness must run and retention must stay high."""
    results = run_all()
    assert len(results) == 10
    avg_ret = sum(r.retention_pct for r in results) / len(results)
    assert avg_ret >= 90.0, f"retention regressed to {avg_ret}%"
    # every 'compact' verdict must be honest
    for r in results:
        if not r.prepared_is_smaller:
            assert r.product_message == "This input is already compact."
    print(f"✓ full suite: {len(results)} scenarios, avg retention {avg_ret:.1f}%")


if __name__ == "__main__":
    test_product_reduction_message_rule()
    test_contradiction_prefers_current_decision()
    test_stale_rest_vs_websocket()
    test_resolved_issue_not_surfaced_for_unrelated_task()
    test_buried_information_retrieved()
    test_full_suite_no_regressions()
    print("\n✓ All evaluation behaviour tests passed!")
