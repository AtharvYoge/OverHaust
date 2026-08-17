"""Tests for the agent runtime (goal-directed loop + action log)."""
import sys, os, tempfile
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from packages.agent.runtime import AgentRuntime
from packages.agent.autonomous_agent import OverhaustAgent
from packages.memory.memory_store import MemoryStore


def seeded(db):
    s = MemoryStore(db)
    s.add_project('chat', 'Chat App')
    s.add_memory('chat', 'We decided to use WebSockets with 30s heartbeats',
                 'permanent', 0.9, {'knowledge_type': 'decision', 'status': 'active'})
    s.add_memory('chat', 'Architecture: React + FastAPI + Redis + Postgres',
                 'permanent', 0.85, {'knowledge_type': 'permanent_knowledge', 'status': 'active'})
    s.add_memory('chat', 'The WebSocket reconnect bug is still open',
                 'task', 0.85, {'knowledge_type': 'open_issue', 'status': 'active'})
    return s


def test_run_produces_action_log_and_context():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        s = seeded(db)
        agent = OverhaustAgent('rt-agent', memory_store=s)
        rt = AgentRuntime(agent)
        res = rt.run('chat', 'Fix the WebSocket reconnect bug')
        assert res.context_id is not None
        assert res.estimated_tokens > 0
        assert res.knowledge_items >= 2
        rendered = res.render_log()
        assert 'Analyzing task' in rendered
        assert 'Searching project knowledge' in rendered
        assert 'Built optimized context' in rendered
        assert 'Context ready' in rendered
        # No chain-of-thought leakage: entries are terse
        assert all(len(e.detail) < 200 for e in res.action_log)
        print("✓ run produced action log + context")
        print(res.render_log())
    finally:
        os.unlink(db)


def test_gap_detection_on_thin_project():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        s = MemoryStore(db)
        s.add_project('thin', 'Thin Project')
        # only one memory, no open issues / decisions
        s.add_memory('thin', 'The project uses Python', 'permanent', 0.5,
                     {'knowledge_type': 'permanent_knowledge', 'status': 'active'})
        agent = OverhaustAgent('rt-agent-2', memory_store=s)
        res = AgentRuntime(agent).run('thin', 'Fix the login bug')
        assert len(res.gaps) >= 1, f"expected gaps, got {res.gaps}"
        assert any('open-issue' in g for g in res.gaps)
        print(f"✓ gaps detected: {res.gaps}")
    finally:
        os.unlink(db)


def test_missing_project_aborts_cleanly():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        s = MemoryStore(db)
        agent = OverhaustAgent('rt-agent-3', memory_store=s)
        res = AgentRuntime(agent).run('ghost', 'anything')
        assert res.context_id is None
        assert res.gaps == ['project not found']
        print("✓ ghost project handled cleanly")
    finally:
        os.unlink(db)


def test_learning_updates_memory():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        s = seeded(db)
        agent = OverhaustAgent('rt-agent-4', memory_store=s)
        before = len(s.get_project_memories('chat', limit=100))
        res = AgentRuntime(agent).run('chat', 'Fix the WebSocket reconnect bug',
                                      learn_from_result=True)
        after = len(s.get_project_memories('chat', limit=100))
        assert res.memory_updates, "no memory update recorded"
        assert after == before + 1
        focus = [m for m in s.get_project_memories('chat', limit=100)
                 if 'Current focus' in m['content']]
        assert len(focus) == 1
        print("✓ agent learned: task focus written to memory")
    finally:
        os.unlink(db)


if __name__ == "__main__":
    print("Running agent runtime tests...\n")
    test_run_produces_action_log_and_context()
    test_gap_detection_on_thin_project()
    test_missing_project_aborts_cleanly()
    test_learning_updates_memory()
    print("\n✓ All agent runtime tests passed!")
