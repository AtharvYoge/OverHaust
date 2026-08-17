"""
Tests for memory store functionality.
"""

import sys
import os
import tempfile
import shutil
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from packages.memory.memory_store import MemoryStore, get_memory_store


def test_memory_store_basic():
    """Test basic memory store operations."""
    # Create a temporary database for testing
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    try:
        store = MemoryStore(db_path)
        
        # Test adding a project
        project_id = store.add_project(
            "test-project-001", 
            "Test Project", 
            "A test project for memory store",
            "/tmp/test-project"
        )
        assert project_id == "test-project-001"
        print("✓ Project added successfully")
        
        # Test getting project
        project = store.get_project(project_id)
        assert project is not None
        assert project['name'] == "Test Project"
        print("✓ Project retrieved successfully")
        
        # Test adding memory
        memory_content = "This is a test memory about user preferences."
        memory_id = store.add_memory(
            project_id,
            memory_content,
            memory_type="permanent",
            importance_score=0.9,
            metadata={"category": "preferences", "source": "user_interview"}
        )
        assert len(memory_id) == 16  # SHA256 hash truncated to 16 chars
        print("✓ Memory added successfully")
        
        # Test getting memory
        memory = store.get_memory(memory_id)
        assert memory is not None
        assert memory['content'] == memory_content
        assert memory['memory_type'] == "permanent"
        assert memory['importance_score'] == 0.9
        print("✓ Memory retrieved successfully")
        
        # Test searching memories
        memories = store.search_memories(project_id, "test memory", limit=5)
        assert len(memories) == 1
        assert memories[0]['id'] == memory_id
        print("✓ Memory search successful")
        
        # Test updating memory
        updated_content = "This is an updated test memory about user preferences."
        success = store.update_memory(
            memory_id,
            content=updated_content,
            importance_score=0.95
        )
        assert success
        updated_memory = store.get_memory(memory_id)
        assert updated_memory is not None
        assert updated_memory['content'] == updated_content
        assert updated_memory['importance_score'] == 0.95
        print("✓ Memory update successful")
        
        # Test getting project memories
        project_memories = store.get_project_memories(project_id, min_importance=0.8)
        assert len(project_memories) == 1
        assert project_memories[0]['id'] == memory_id
        print("✓ Project memories retrieval successful")
        
    finally:
        # Clean up temporary file
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_global_memory_store():
    """Test the global memory store instance."""
    store = get_memory_store()
    assert isinstance(store, MemoryStore)
    print("✓ Global memory store accessible")


if __name__ == "__main__":
    print("Running memory store tests...\n")
    
    test_memory_store_basic()
    test_global_memory_store()
    
    print("\n✓ All memory store tests passed!")