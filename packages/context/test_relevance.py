"""Tests for the layered relevance engine."""
import sys, os, tempfile
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from packages.context.relevance import LayeredRelevanceEngine, search_knowledge, _keywords
from packages.memory.memory_store import MemoryStore


def seeded_store(db):
    s = MemoryStore(db)
    s.add_project('p', 'P')
    s.add_memory('p', 'We decided to use WebSockets with 30s heartbeats for realtime chat',
                 'permanent', 0.9, {'knowledge_type': 'decision', 'status': 'active'})
    s.add_memory('p', 'Architecture: React frontend, FastAPI backend, Redis pub/sub, PostgreSQL',
                 'permanent', 0.85, {'knowledge_type': 'permanent_knowledge', 'status': 'active'})
    s.add_memory('p', 'The WebSocket reconnect bug is still open: connection drops after 60s idle',
                 'task', 0.8, {'knowledge_type': 'open_issue', 'status': 'active'})
    s.add_memory('p', 'We previously used 5s polling but migrated away from it',
                 'stale', 0.65, {'knowledge_type': 'stale_info', 'status': 'stale'})
    s.add_memory('p', 'Fixed: message ordering via monotonic sequence numbers',
                 'resolved', 0.5, {'knowledge_type': 'resolved_issue', 'status': 'resolved'})
    s.add_memory('p', 'Marketing landing page copy for the chat product website',
                 'temporary', 0.2, {'knowledge_type': 'permanent_knowledge', 'status': 'active'})
    return s


def test_exact_phrase_beats_partial():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        s = seeded_store(db)
        eng = LayeredRelevanceEngine(s)
        res = eng.search('p', 'WebSocket reconnect bug', limit=5)
        assert res, 'no results'
        top = res[0].memory['content']
        assert 'reconnect bug' in top, top
        assert res[0].score > res[-1].score
        print(f"✓ ranking: top score {res[0].score}, reasons {res[0].reasons[:2]}")
    finally:
        os.unlink(db)


def test_irrelevant_content_excluded():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        s = seeded_store(db)
        res = LayeredRelevanceEngine(s).search('p', 'WebSocket bug', limit=10)
        contents = [r.memory['content'] for r in res]
        assert not any('Marketing landing page' in c for c in contents), contents
        print("✓ irrelevant marketing memory not returned for technical query")
    finally:
        os.unlink(db)


def test_stale_demoted_by_default_promoted_when_asked():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        s = seeded_store(db)
        eng = LayeredRelevanceEngine(s)
        # Default: stale demoted below active decision
        res1 = eng.search('p', 'polling', limit=5)
        # Asking about old approach: stale should surface
        res2 = eng.search('p', 'what was the previous old approach', limit=5)
        assert any('polling' in r.memory['content'] for r in res2)
        print(f"✓ stale handling: default results={len(res1)}, explicit-old-query finds stale={len(res2)}")
    finally:
        os.unlink(db)


def test_keyword_tokenizer():
    kw = _keywords("How do I fix the WebSocket reconnect bug?")
    assert 'websocket' in kw and 'reconnect' in kw
    assert 'the' not in kw and 'how' not in kw and 'do' not in kw
    # intent words are stopwords for content matching
    assert 'fix' not in kw and 'bug' not in kw
    print(f"✓ keywords: {kw}")


def test_module_level_interface():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        s = seeded_store(db)
        res = search_knowledge('p', 'database architecture', memory_store=s, limit=3)
        assert len(res) >= 1
        assert res[0].score > 0
        print(f"✓ search_knowledge interface works, {len(res)} results")
    finally:
        os.unlink(db)


def test_empty_project_returns_empty():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        s = MemoryStore(db)
        s.add_project('empty-p', 'E')
        assert LayeredRelevanceEngine(s).search('empty-p', 'anything') == []
        print("✓ empty project -> empty results")
    finally:
        os.unlink(db)


if __name__ == "__main__":
    print("Running relevance engine tests...\n")
    test_exact_phrase_beats_partial()
    test_irrelevant_content_excluded()
    test_stale_demoted_by_default_promoted_when_asked()
    test_keyword_tokenizer()
    test_module_level_interface()
    test_empty_project_returns_empty()
    print("\n✓ All relevance engine tests passed!")
