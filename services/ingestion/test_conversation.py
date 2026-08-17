"""Tests for conversation ingestion and compression."""
import sys, os, json, tempfile
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from services.ingestion.conversation import (
    ConversationIngestor, ConversationParser, MessageClassifier,
    compression_report, Message,
)
from packages.memory.memory_store import MemoryStore


SAMPLE_MD = """# Conversation

## User
Hi, can you help me with my project?

## Assistant
Of course! What are you working on?

## User
The project is a real-time chat application. Architecture: React frontend, FastAPI backend, Redis pub/sub for message fan-out, PostgreSQL for persistence.

## Assistant
Got it. What are you working on right now?

## User
Currently working on fixing the WebSocket reconnect bug. The connection drops after 60s idle and never recovers.

## Assistant
Have you considered heartbeats?

## User
We decided to use WebSocket heartbeats every 30s. We rejected server-sent events because proxies buffer them.

## Assistant
Good choice.

## User
Also, we previously used polling every 5 seconds, but that's no longer the approach.

## Assistant
Understood.

## User
The rate limiter is still broken after the Redis migration. Need to fix that next week.

## Assistant
Let me know if you need help with the rate limiter.

## User
Fixed: the message ordering issue. The fix was adding a monotonic sequence number per channel.

## Assistant
Great!

## User
thanks!
"""


def test_parse_markdown():
    p = ConversationParser()
    msgs = p.parse(SAMPLE_MD, "conv-1")
    assert len(msgs) == 15, f"expected 15 messages, got {len(msgs)}"
    assert msgs[0].role == 'user'
    assert msgs[1].role == 'assistant'
    assert 'WebSocket reconnect bug' in msgs[4].content
    print(f"✓ markdown parse: {len(msgs)} messages")


def test_parse_json_messages():
    p = ConversationParser()
    raw = json.dumps([
        {"role": "user", "content": "We decided to use Postgres"},
        {"role": "assistant", "content": "Noted."},
        {"role": "user", "content": "The login page is broken"},
    ])
    msgs = p.parse(raw, "conv-json")
    assert len(msgs) == 3
    assert msgs[0].role == 'user'
    print("✓ json parse")


def test_parse_chatgpt_export():
    p = ConversationParser()
    raw = json.dumps({
        "mapping": {
            "a": {"create_time": 2, "message": {"author": {"role": "assistant"}, "content": {"parts": ["Answer here"]}}},
            "b": {"create_time": 1, "message": {"author": {"role": "user"}, "content": {"parts": ["Question here"]}}},
        }
    })
    msgs = p.parse(raw, "conv-gpt")
    assert len(msgs) == 2
    assert msgs[0].role == 'user' and msgs[0].content == 'Question here'
    assert msgs[1].role == 'assistant'
    print("✓ chatgpt export parse (sorted by time)")


def test_classification_categories():
    ing = ConversationIngestor()
    result = ing.ingest_text(SAMPLE_MD, "conv-1")
    cats = {m.category for m in result.memories}
    assert 'permanent_knowledge' in cats, cats
    assert 'decision' in cats
    assert 'current_task' in cats or 'open_issue' in cats
    assert 'stale_info' in cats
    assert 'resolved_issue' in cats
    assert 'irrelevant' in cats
    print(f"✓ classification categories: {sorted(cats)}")
    print(f"  stats: {result.stats}")


def test_duplicate_detection():
    ing = ConversationIngestor()
    dup = SAMPLE_MD + "\n## User\nThe project is a real-time chat application. Architecture: React frontend, FastAPI backend, Redis pub/sub for message fan-out, PostgreSQL for persistence.\n"
    r1 = ing.ingest_text(SAMPLE_MD, "c1")
    r2 = ing.ingest_text(dup, "c2")
    assert r2.duplicate_messages >= 1
    print(f"✓ duplicates detected: {r2.duplicate_messages}")


def test_provenance():
    ing = ConversationIngestor()
    result = ing.ingest_text(SAMPLE_MD, "conv-17")
    for m in result.memories:
        if m.category == 'decision':
            assert m.conversation_id == 'conv-17'
            assert m.message_index >= 0
            assert 'Conversation conv-17, Message #' in m.provenance
            print(f"✓ provenance: {m.provenance} -> {m.content[:60]}")
            return
    raise AssertionError("no decision found to check provenance")


def test_compression_report_honest():
    ing = ConversationIngestor()
    result = ing.ingest_text(SAMPLE_MD * 20, "big-conv")  # ~280 messages
    rep = compression_report(result)
    assert rep['original_tokens'] > rep['structured_tokens']
    assert rep['reduction_percent'] > 0
    assert rep['estimated'] is True
    assert 'permanent_knowledge' in rep['breakdown']
    print(f"✓ compression: {rep['original_tokens']} -> {rep['structured_tokens']} tokens "
          f"({rep['reduction_percent']}% estimated reduction, {rep['duplicate_messages']} dup msgs)")
    print(f"  breakdown: {rep['breakdown']}")


def test_store_result_with_provenance():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        store.add_project('proj-conv', 'Conv Test')
        ing = ConversationIngestor()
        result = ing.ingest_text(SAMPLE_MD, "conv-99")
        ids = ing.store_result(result, 'proj-conv', store)
        assert len(ids) > 0
        # verify provenance survives the store round-trip
        mems = store.search_memories('proj-conv', 'WebSocket', limit=5)
        assert len(mems) >= 1
        meta = mems[0]['metadata']
        assert meta['source_id'] == 'conv-99'
        assert 'message_index' in meta
        assert 'Conversation conv-99' in meta['provenance']
        # irrelevant chatter not stored
        all_mems = store.get_project_memories('proj-conv', limit=100)
        assert not any(m['content'].lower().strip() == 'thanks!' for m in all_mems)
        print(f"✓ stored {len(ids)} memories with provenance, chatter excluded")
    finally:
        os.unlink(db)


def test_contradictory_and_stale_flagged():
    convo = """## User
We decided to use MongoDB for everything.

## Assistant
Noted.

## User
Update: we no longer use MongoDB. Migrated from MongoDB to Postgres last sprint. We decided to use Postgres instead.
"""
    ing = ConversationIngestor()
    result = ing.ingest_text(convo, "contradict")
    stale = [m for m in result.memories if m.category == 'stale_info']
    decisions = [m for m in result.memories if m.category == 'decision']
    assert len(stale) >= 1, "stale not detected"
    assert any('Postgres' in d.content for d in decisions)
    print(f"✓ stale+decision: stale={len(stale)}, decisions={len(decisions)}")


def test_malformed_input():
    ing = ConversationIngestor()
    assert ing.ingest_text("", "empty").message_count == 0
    assert ing.ingest_text("{not json", "bad").message_count >= 0
    r = ing.ingest_text("hello world, no markers at all", "plain")
    assert r.message_count == 1
    print("✓ malformed input handled")


if __name__ == "__main__":
    print("Running conversation ingestion tests...\n")
    test_parse_markdown()
    test_parse_json_messages()
    test_parse_chatgpt_export()
    test_classification_categories()
    test_duplicate_detection()
    test_provenance()
    test_compression_report_honest()
    test_store_result_with_provenance()
    test_contradictory_and_stale_flagged()
    test_malformed_input()
    print("\n✓ All conversation ingestion tests passed!")
