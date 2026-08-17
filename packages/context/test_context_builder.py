"""Tests for the upgraded context builder (relevance-driven, explainable)."""
import sys, os, tempfile
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from packages.context.context_engine import ContextAssembler
from packages.memory.memory_store import MemoryStore


def build_seeded(db):
    s = MemoryStore(db)
    s.add_project('chat-proj', 'Realtime Chat')
    s.add_memory('chat-proj',
        'We decided to use WebSockets with 30s heartbeats for realtime chat. We rejected SSE because proxies buffer it.',
        'permanent', 0.9, {'knowledge_type': 'decision', 'status': 'active',
                            'provenance': 'Conversation 3, Message #42'})
    s.add_memory('chat-proj',
        'Architecture: React frontend, FastAPI backend, Redis pub/sub for fan-out, PostgreSQL persistence.',
        'permanent', 0.85, {'knowledge_type': 'permanent_knowledge', 'status': 'active'})
    s.add_memory('chat-proj',
        'The WebSocket reconnect bug is still open: the connection drops after 60s of idle and never recovers.',
        'task', 0.85, {'knowledge_type': 'open_issue', 'status': 'active'})
    s.add_memory('chat-proj',
        'ConnectionManager in src/ws/manager.ts owns socket lifecycle; HeartbeatService sends pings.',
        'permanent', 0.8, {'knowledge_type': 'permanent_knowledge', 'status': 'active'})
    s.add_memory('chat-proj',
        'Marketing landing page copy: headline, subheadline, pricing tiers for the chat product.',
        'temporary', 0.2, {'knowledge_type': 'permanent_knowledge', 'status': 'active'})
    s.add_memory('chat-proj',
        'Fixed: avatar upload 500 error. The fix was setting correct multipart boundary.',
        'resolved', 0.5, {'knowledge_type': 'resolved_issue', 'status': 'resolved'})
    return s


def test_selection_has_explanations():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        s = build_seeded(db)
        asm = ContextAssembler(s)
        ctx = asm.assemble_context('chat-proj', 'Fix the WebSocket reconnect bug', max_knowledge_items=6)
        assert len(ctx.relevant_knowledge) >= 2
        for k in ctx.relevant_knowledge:
            rel = k.metadata.get('relevance')
            assert rel and 'score' in rel and 'reasons' in rel, f"missing explanation on {k.id}"
        top_contents = [k.content for k in ctx.relevant_knowledge]
        assert any('reconnect bug' in c for c in top_contents)
        assert any('WebSocket' in c for c in top_contents)
        print("✓ selections explained; bug + websocket knowledge at top")
        for k in ctx.relevant_knowledge[:3]:
            print(f"  - {k.metadata['relevance']['score']}: {k.content[:60]}")
    finally:
        os.unlink(db)


def test_irrelevant_excluded():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        s = build_seeded(db)
        asm = ContextAssembler(s)
        ctx = asm.assemble_context('chat-proj', 'Fix the WebSocket reconnect bug', max_knowledge_items=10)
        contents = [k.content for k in ctx.relevant_knowledge]
        assert not any('Marketing landing page' in c for c in contents), contents
        assert not any('avatar upload' in c for c in contents), "resolved+unrelated should not rank"
        print("✓ marketing + unrelated-resolved excluded from bug-fix context")
    finally:
        os.unlink(db)


def test_minimum_useful_not_minimum():
    """Aggressive truncation must not drop the critical open issue.
    The engine should include the bug memory even with a small limit."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        s = build_seeded(db)
        asm = ContextAssembler(s)
        ctx = asm.assemble_context('chat-proj', 'Fix the WebSocket reconnect bug', max_knowledge_items=2)
        contents = [k.content for k in ctx.relevant_knowledge]
        # With only 2 slots, the top-2 must still be the most task-relevant items
        assert any('reconnect bug' in c for c in contents), \
            f"critical issue dropped under compression: {contents}"
        print("✓ minimum-useful: critical issue survives small limit")
    finally:
        os.unlink(db)


def test_deterministic_ranking():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        s = build_seeded(db)
        asm = ContextAssembler(s)
        a = asm.assemble_context('chat-proj', 'Fix the WebSocket reconnect bug', max_knowledge_items=5)
        b = asm.assemble_context('chat-proj', 'Fix the WebSocket reconnect bug', max_knowledge_items=5)
        assert [k.id for k in a.relevant_knowledge] == [k.id for k in b.relevant_knowledge]
        print("✓ ranking deterministic across runs")
    finally:
        os.unlink(db)


if __name__ == "__main__":
    print("Running context builder tests...\n")
    test_selection_has_explanations()
    test_irrelevant_excluded()
    test_minimum_useful_not_minimum()
    test_deterministic_ranking()
    print("\n✓ All context builder tests passed!")
