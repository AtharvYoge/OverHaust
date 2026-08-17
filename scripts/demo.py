#!/usr/bin/env python3
"""
Demonstration script for Overhaust.
Shows the core functionality of the memory store, agent, and context engine.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from packages.memory.memory_store import get_memory_store
from packages.agent.autonomous_agent import get_overhaust_agent
from packages.context.context_engine import get_context_assembler
from packages.tokenization.token_estimator import TokenEstimator

def main():
    print("=== Overhaust Demonstration ===\n")
    
    # Initialize core components
    memory_store = get_memory_store()
    agent = get_overhaust_agent("demo-agent-001")
    context_assembler = get_context_assembler()
    token_estimator = TokenEstimator()
    
    # Step 1: Add a test project
    print("1. Adding a test project...")
    project_id = memory_store.add_project(
        "demo-project-001",
        "Overhaust Demo Project",
        "A demonstration project showing Overhaust capabilities",
        "/tmp/demo-project"
    )
    print(f"   Project added with ID: {project_id}\n")
    
    # Step 2: Add some memories to the project
    print("2. Adding memories to the project...")
    
    # Add a decision memory
    decision_id = memory_store.add_memory(
        project_id,
        "We decided to use React and TypeScript for the frontend because of the strong ecosystem and developer experience.",
        memory_type="permanent",
        importance_score=0.9,
        metadata={
            "knowledge_type": "decision",
            "source_type": "conversation",
            "source_title": "Architecture Meeting",
            "category": "frontend"
        }
    )
    print(f"   Added decision memory: {decision_id}")
    
    # Add a project identity memory
    identity_id = memory_store.add_memory(
        project_id,
        "Overhaust is an AI memory and efficiency layer that helps reduce redundant processing in AI agents.",
        memory_type="permanent",
        importance_score=0.95,
        metadata={
            "knowledge_type": "project_identity",
            "source_type": "document",
            "source_title": "Project README",
            "category": "overview"
        }
    )
    print(f"   Added identity memory: {identity_id}")
    
    # Add a preference memory
    preference_id = memory_store.add_memory(
        project_id,
        "We prefer to use FastAPI for the backend due to its high performance and automatic API documentation.",
        memory_type="permanent",
        importance_score=0.85,
        metadata={
            "knowledge_type": "preference",
            "source_type": "conversation",
            "source_title": "Backend Discussion",
            "category": "backend"
        }
    )
    print(f"   Added preference memory: {preference_id}\n")
    
    # Step 3: Demonstrate task understanding
    print("3. Demonstrating task understanding...")
    task = "How should we build the frontend for Overhaust?"
    analysis = agent.understand_task(task)
    print(f"   Task: {task}")
    print(f"   Task type: {analysis['task_type']}")
    print(f"   Keywords: {analysis['keywords']}")
    print(f"   Complexity: {analysis['complexity']}")
    print(f"   Required knowledge types: {analysis['required_knowledge_types']}\n")
    
    # Step 4: Demonstrate context retrieval
    print("4. Demonstrating context retrieval...")
    context = agent.get_project_context(
        project_id,
        task,
        max_knowledge_items=5
    )
    print(f"   Context ID: {context.id}")
    print(f"   Project ID: {context.project_id}")
    print(f"   Task: {context.task}")
    print(f"   Number of relevant knowledge items: {len(context.relevant_knowledge)}")
    print(f"   Number of relevant decisions: {len(context.relevant_decisions)}")
    print(f"   Estimated tokens for context: {context.estimated_tokens}")
    
    if context.relevant_knowledge:
        print("   Relevant knowledge:")
        for k in context.relevant_knowledge[:3]:  # Show first 3
            print(f"     - [{k.knowledge_type}] {k.content[:100]}{'...' if len(k.content) > 100 else ''}")
    print()
    
    # Step 5: Demonstrate token estimation
    print("5. Demonstrating token estimation...")
    
    # Original text (simulating a large conversation)
    original_text = """
    We are building a project called Overhaust that helps AI agents be more efficient.
    We decided to use React and TypeScript for the frontend.
    The architecture uses a local-first approach with SQLite for storage.
    We prefer to use FastAPI for the backend because it's fast and has good documentation.
    We decided to use React and TypeScript for the frontend because of the strong ecosystem and developer experience.
    We prefer to use FastAPI for the backend due to its high performance and automatic API documentation.
    There's an issue with the memory extraction being too slow.
    We are building a project called Overhaust that helps AI agents be more efficient.
    We decided to use React and TypeScript for the frontend.
    The architecture uses a local-first approach with SQLite for storage.
    We prefer to use FastAPI for the backend because it's fast and has good documentation.
    We decided to use React and TypeScript for the frontend because of the strong ecosystem and developer experience.
    We prefer to use FastAPI for the backend due to its high performance and automatic API documentation.
    There's an issue with the memory extraction being too slow.
    """ * 3  # Repeat to make it longer
    
    # Optimized text (what Overhaust would provide)
    optimized_text = """
    Overhaust Project Info:
    - Frontend: React and TypeScript (chosen for ecosystem and developer experience)
    - Backend: FastAPI (chosen for performance and automatic documentation)
    - Storage: Local-first with SQLite
    - Current Task: How should we build the frontend for Overhaust?
    - Relevant Decision: Use React and TypeScript for frontend
    """
    
    reduction = token_estimator.estimate_reduction(original_text, optimized_text)
    print(f"   Original text length: {len(original_text)} characters")
    print(f"   Optimized text length: {len(optimized_text)} characters")
    print(f"   Original estimated tokens: {reduction['original_tokens']}")
    print(f"   Optimized estimated tokens: {reduction['optimized_tokens']}")
    print(f"   Tokens saved: {reduction['saved_tokens']}")
    print(f"   Reduction percentage: {reduction['reduction_percent']}%\n")
    
    # Step 6: Demonstrate agent actions
    print("6. Demonstrating agent action history...")
    history = agent.get_action_history(10)
    print(f"   Agent {agent.agent_id} has performed {len(history)} actions:")
    for i, action in enumerate(history, 1):
        print(f"     {i}. {action.action_type}: {action.description}")
    print()
    
    print("=== Demonstration Complete ===")
    print("Overhaust successfully:")
    print("  - Stored project knowledge and memories")
    print("  - Understood user tasks and extracted relevant information")
    print("  - Assembled context with relevant knowledge and decisions")
    print("  - Estimated token usage and showed potential savings")
    print("  - Tracked agent actions for transparency and auditability")

if __name__ == "__main__":
    main()