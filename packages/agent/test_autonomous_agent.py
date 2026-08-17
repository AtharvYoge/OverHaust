"""
Tests for the autonomous agent functionality.
"""

import sys
import os
import tempfile
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from packages.agent.autonomous_agent import (
    OverhaustAgent,
    get_overhaust_agent,
    AgentAction
)
from packages.memory.memory_store import MemoryStore
from packages.context.context_engine import ContextAssembler
from packages.tokenization.token_estimator import TokenEstimator


def test_agent_initialization():
    """Test agent initialization."""
    agent = OverhaustAgent("test-agent-001")
    assert agent.agent_id == "test-agent-001"
    assert agent.memory_store is not None
    assert agent.token_estimator is not None
    assert agent.context_assembler is not None
    assert len(agent.action_history) == 0
    print("✓ Agent initialized successfully")


def test_task_understanding():
    """Test task understanding functionality."""
    agent = OverhaustAgent("test-agent-002")
    
    # Test different task types
    fix_task = "Fix the login bug in the authentication system"
    analysis = agent.understand_task(fix_task)
    
    assert analysis["original_task"] == fix_task
    assert analysis["task_type"] == "troubleshooting"
    assert isinstance(analysis["keywords"], list)
    assert len(analysis["keywords"]) > 0
    assert analysis["complexity"] in ["low", "medium", "high"]
    print("✓ Task understanding works for troubleshooting")
    
    # Test development task
    build_task = "Create a new React component for user profile"
    analysis2 = agent.understand_task(build_task)
    assert analysis2["task_type"] == "development"
    print("✓ Task understanding works for development")
    
    # Test learning task
    learn_task = "Explain how the memory system works"
    analysis3 = agent.understand_task(learn_task)
    assert analysis3["task_type"] == "learning"
    print("✓ Task understanding works for learning")


def test_agent_memory_operations():
    """Test agent memory operations."""
    # Create a temporary database for testing
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    try:
        memory_store = MemoryStore(db_path)
        token_estimator = TokenEstimator()
        context_assembler = ContextAssembler(memory_store, token_estimator)
        
        agent = OverhaustAgent(
            "test-agent-003",
            memory_store=memory_store,
            token_estimator=token_estimator
        )
        
        # Add a test project
        project_id = memory_store.add_project(
            "test-project-001",
            "Overhaust Test",
            "A test project",
            "/test/path"
        )
        
        # Test updating memory
        memory_id = agent.update_memory(
            project_id,
            "We decided to use PostgreSQL for the database",
            memory_type="permanent",
            importance_score=0.9,
            metadata={"decision_type": "database", "meeting": "architecture"}
        )
        
        assert len(memory_id) == 16
        print("✓ Agent can update memory")
        
        # Test marking resolved
        resolution_id = agent.mark_resolved(
            project_id,
            "Fixed the database connection timeout issue"
        )
        
        assert len(resolution_id) == 16
        print("✓ Agent can mark issues as resolved")
        
        # Test marking stale
        stale_success = agent.mark_stale(memory_id, "Decision was revised")
        assert stale_success
        print("✓ Agent can mark memories as stale")
        
    finally:
        # Clean up temporary file
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_agent_context_retrieval():
    """Test agent context retrieval."""
    # Create a temporary database for testing
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    try:
        memory_store = MemoryStore(db_path)
        token_estimator = TokenEstimator()
        context_assembler = ContextAssembler(memory_store, token_estimator)
        
        agent = OverhaustAgent(
            "test-agent-004",
            memory_store=memory_store,
            token_estimator=token_estimator
        )
        
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
        
        # Test getting project context
        context = agent.get_project_context(
            project_id,
            "How should we build the frontend?",
            max_knowledge_items=5
        )
        
        assert context.project_id == project_id
        assert context.task == "How should we build the frontend?"
        assert len(context.relevant_knowledge) > 0
        assert context.estimated_tokens > 0
        print("✓ Agent can retrieve project context")
        
        # Test getting relevant context (simplified)
        relevant_context = agent.get_relevant_context(
            project_id,
            "What technology should we use for frontend?"
        )
        
        assert relevant_context["project_id"] == project_id
        assert "relevant_knowledge" in relevant_context
        assert "estimated_tokens" in relevant_context
        print("✓ Agent can get relevant context")
        
    finally:
        # Clean up temporary file
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_agent_action_history():
    """Test agent action history tracking."""
    agent = OverhaustAgent("test-agent-005")
    
    # Perform some actions
    agent.understand_task("Test task")
    agent.get_project_context("test-project", "Test context")
    
    history = agent.get_action_history(5)
    assert len(history) == 2
    assert history[0].action_type == "understand_task"
    assert history[1].action_type == "get_project_context"
    assert all(action.success for action in history)
    print("✓ Agent action history tracked correctly")


def test_global_agent():
    """Test the global agent function."""
    agent1 = get_overhaust_agent("global-test-001")
    agent2 = get_overhaust_agent("global-test-001")
    
    # Should return the same instance
    assert agent1 is agent2
    assert agent1.agent_id == "global-test-001"
    
    # Different ID should create new instance
    agent3 = get_overhaust_agent("global-test-002")
    assert agent3 is not agent1
    assert agent3.agent_id == "global-test-002"
    
    print("✓ Global agent function works correctly")


if __name__ == "__main__":
    print("Running autonomous agent tests...\n")
    
    test_agent_initialization()
    test_task_understanding()
    test_agent_memory_operations()
    test_agent_context_retrieval()
    test_agent_action_history()
    test_global_agent()
    
    print("\n✓ All autonomous agent tests passed!")