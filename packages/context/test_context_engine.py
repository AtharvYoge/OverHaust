"""
Tests for context engine functionality.
"""

import sys
import os
import tempfile
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from packages.context.context_engine import (
    KnowledgeExtractor, 
    ContextAssembler,
    ExtractedKnowledge,
    ContextPackage
)
from packages.memory.memory_store import MemoryStore
from packages.tokenization.token_estimator import TokenEstimator


def test_knowledge_extractor():
    """Test knowledge extraction functionality."""
    extractor = KnowledgeExtractor()
    
    # Test conversation content
    conversation = """
    We are building a project called Overhaust that helps AI agents be more efficient.
    We decided to use React and TypeScript for the frontend.
    The architecture uses a local-first approach with SQLite for storage.
    We prefer to use FastAPI for the backend because it's fast and has good documentation.
    There's an issue with the memory extraction being too slow.
    """
    
    knowledge_items = extractor.extract_knowledge(
        conversation, 
        "test-project-001", 
        "conversation", 
        "Team Discussion"
    )
    
    assert len(knowledge_items) > 0
    print(f"✓ Extracted {len(knowledge_items)} knowledge items")
    
    # Check that we extracted different types of knowledge
    knowledge_types = set(item.knowledge_type for item in knowledge_items)
    assert 'project_identity' in knowledge_types or 'architecture' in knowledge_types
    assert 'decision' in knowledge_types
    assert 'preference' in knowledge_types
    print("✓ Extracted multiple knowledge types")
    
    # Check importance scores
    for item in knowledge_items:
        assert 0.1 <= item.importance_score <= 1.0
    print("✓ All importance scores in valid range")


def test_context_assembler():
    """Test context assembly functionality."""
    # Create a temporary database for testing
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    try:
        # Setup memory store with test data
        memory_store = MemoryStore(db_path)
        
        # Add a test project
        project_id = memory_store.add_project(
            "test-project-001",
            "Overhaust",
            "AI memory optimization system",
            "/test/path"
        )
        
        # Add some test memories
        memory_store.add_memory(
            project_id,
            "We decided to use React and TypeScript for the frontend",
            memory_type="permanent",
            importance_score=0.9,
            metadata={
                "knowledge_type": "decision",
                "source_type": "conversation",
                "source_title": "Architecture Meeting"
            }
        )
        
        memory_store.add_memory(
            project_id,
            "The project is called Overhaust and helps AI agents be more efficient",
            memory_type="permanent",
            importance_score=0.8,
            metadata={
                "knowledge_type": "project_identity",
                "source_type": "conversation",
                "source_title": "Project Kickoff"
            }
        )
        
        # Setup token estimator
        token_estimator = TokenEstimator()
        
        # Create context assembler
        assembler = ContextAssembler(memory_store, token_estimator)
        
        # Assemble context for a task
        context = assembler.assemble_context(
            project_id,
            "How should we build the frontend?",
            max_knowledge_items=5
        )
        
        assert isinstance(context, ContextPackage)
        assert context.project_id == project_id
        assert context.task == "How should we build the frontend?"
        assert len(context.relevant_knowledge) > 0
        assert context.estimated_tokens > 0
        print("✓ Context package assembled successfully")
        
        # Check that we got relevant knowledge
        assert len(context.relevant_knowledge) >= 1
        # Should have the frontend decision
        frontend_decision_found = any(
            "React" in k.content and "TypeScript" in k.content 
            for k in context.relevant_knowledge
        )
        assert frontend_decision_found
        print("✓ Relevant frontend decision found in context")
        
    finally:
        # Clean up temporary file
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_context_package_properties():
    """Test ContextPackage properties and serialization."""
    knowledge_item = ExtractedKnowledge(
        id="test-001",
        project_id="test-project",
        source_type="conversation",
        source_title="Test Conversation",
        title="Test Knowledge",
        content="This is test knowledge content",
        knowledge_type="decision",
        importance_score=0.8,
        extracted_at="2026-08-17T12:00:00",
        metadata={"test": "data"},
        source_hash="abc123"
    )
    
    context = ContextPackage(
        id="context-001",
        project_id="test-project",
        task="Test task",
        relevant_knowledge=[knowledge_item],
        relevant_files=[],
        relevant_decisions=[knowledge_item],
        current_state={"state": "test"},
        relevant_memory=[],
        constraints=["Test constraint"],
        created_at="2026-08-17T12:00:00",
        estimated_tokens=50
    )
    
    # Test that we can access all properties
    assert context.id == "context-001"
    assert context.project_id == "test-project"
    assert context.task == "Test task"
    assert len(context.relevant_knowledge) == 1
    assert context.relevant_knowledge[0].content == "This is test knowledge content"
    assert context.estimated_tokens == 50
    print("✓ ContextPackage properties accessible")


if __name__ == "__main__":
    print("Running context engine tests...\n")
    
    test_knowledge_extractor()
    test_context_assembler()
    test_context_package_properties()
    
    print("\n✓ All context engine tests passed!")