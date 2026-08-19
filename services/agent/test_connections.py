"""Tests for the agent connection architecture."""
import sys, os, json, tempfile
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from services.agent.connections import (
    ConnectionRegistry, LocalAgentConnection, APIConnection,
    IDEConfigAdapter, ConnectionStatus, default_registry,
)
from packages.memory.memory_store import MemoryStore


def test_local_connection_run():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
        db = t.name
    try:
        store = MemoryStore(db)
        store.add_project('c', 'C')
        store.add_memory('c', 'We decided to use WebSockets', 'permanent', 0.9,
                         {'knowledge_type': 'decision', 'status': 'active'})
        conn = LocalAgentConnection(memory_store=store)
        assert conn.info.status == ConnectionStatus.AVAILABLE
        res = conn.handle('run', {'project_id': 'c', 'task': 'what websocket decision?'})
        assert 'action_log' in res
        assert 'Analyzing task' in res['action_log']
        res2 = conn.handle('search_memory', {'project_id': 'c', 'query': 'websocket'})
        assert len(res2) >= 1
        print("✓ local connection run + search")
    finally:
        os.unlink(db)


def test_registry_lists_statuses():
    with tempfile.TemporaryDirectory() as tmp:
        reg = default_registry(project_root=tmp)
        infos = reg.list_connections()
        by_id = {i.id: i for i in infos}
        assert by_id['local-agent'].status == ConnectionStatus.AVAILABLE
        assert by_id['mcp'].status == ConnectionStatus.AVAILABLE
        assert by_id['api'].status == ConnectionStatus.AVAILABLE
        assert by_id['ide-cursor'].status == ConnectionStatus.COMING_SOON
        assert by_id['ide-windsurf'].status == ConnectionStatus.COMING_SOON
        print(f"✓ registry: {[(i.id, i.status.value) for i in infos]}")


def test_registry_blocks_unavailable():
    reg = ConnectionRegistry()
    adapter = IDEConfigAdapter('cursor')
    reg.register_ide(adapter)
    try:
        reg.handle('ide-cursor', 'anything', {})
        raise AssertionError("should have raised")
    except (KeyError, RuntimeError):
        print("✓ coming_soon adapter not callable via handle()")


def test_ide_config_generation_and_merge():
    with tempfile.TemporaryDirectory() as tmp:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        adapter = IDEConfigAdapter('cursor', project_root=project_root)
        cfg = adapter.generate_config()
        server = cfg['mcpServers']['overhaust']
        assert server['args'] == ['-m', 'services.mcp_server.server']
        assert server['env']['PYTHONPATH'] == project_root
        target = os.path.join(tmp, 'mcp.json')
        # pre-existing config with another server must be preserved
        with open(target, 'w') as f:
            json.dump({'mcpServers': {'other': {'command': 'x'}}, 'theme': 'dark'}, f)
        path = adapter.write_config(target)
        merged = json.load(open(path))
        assert 'overhaust' in merged['mcpServers']
        assert 'other' in merged['mcpServers']
        assert merged['theme'] == 'dark'
        print("✓ IDE config generated and merged non-destructively")


def test_api_connection_methods():
    conn = APIConnection('http://localhost:9')  # nothing listening
    assert conn.info.status == ConnectionStatus.AVAILABLE
    try:
        conn.handle('health', {})
        raise AssertionError("should have raised ConnectionError")
    except (ConnectionError, OSError):
        print("✓ API connection reports unreachable host as ConnectionError")


if __name__ == "__main__":
    print("Running connection architecture tests...\n")
    test_local_connection_run()
    test_registry_lists_statuses()
    test_registry_blocks_unavailable()
    test_ide_config_generation_and_merge()
    test_api_connection_methods()
    print("\n✓ All connection architecture tests passed!")
