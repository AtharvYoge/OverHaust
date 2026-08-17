"""
Autonomous agent package for Overhaust.
Implements an AI agent that can interact with the Overhaust system to
understand tasks, retrieve relevant context, and update knowledge.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from packages.context.context_engine import (
    get_context_assembler,
    ContextPackage
)
from packages.memory.memory_store import (
    get_memory_store,
    MemoryStore
)
from packages.tokenization.token_estimator import (
    TokenEstimator,
    estimate_tokens
)

logger = logging.getLogger(__name__)


@dataclass
class AgentAction:
    """Represents an action taken by the agent."""
    action_type: str  # 'search_memory', 'get_context', 'update_memory', etc.
    description: str
    parameters: Dict[str, Any]
    result: Any
    timestamp: str
    success: bool


class OverhaustAgent:
    """
    An autonomous agent that operates within the Overhaust system.
    
    The agent can:
    - Understand user tasks
    - Retrieve relevant project context
    - Update project memory with new learnings
    - Detect and mark stale knowledge
    - Report its actions and decisions
    """
    
    def __init__(self, 
                 agent_id: str = "overhaust-agent-001",
                 memory_store: Optional[MemoryStore] = None,
                 token_estimator: Optional[TokenEstimator] = None):
        """
        Initialize the agent.
        
        Args:
            agent_id: Unique identifier for this agent instance
            memory_store: Memory store instance (uses global if not provided)
            token_estimator: Token estimator instance (uses global if not provided)
        """
        self.agent_id = agent_id
        self.memory_store = memory_store or get_memory_store()
        self.token_estimator = token_estimator or TokenEstimator()
        # Build assembler with same stores so injected test doubles are respected
        from packages.context.context_engine import ContextAssembler
        self.context_assembler = ContextAssembler(self.memory_store, self.token_estimator)
        
        # Action history for this agent session
        self.action_history: List[AgentAction] = []
        
        logger.info(f"Initialized OverhaustAgent {self.agent_id}")
    
    def _record_action(self, action_type: str, description: str, 
                      parameters: Dict[str, Any], result: Any, success: bool = True):
        """Record an action in the agent's history."""
        action = AgentAction(
            action_type=action_type,
            description=description,
            parameters=parameters,
            result=result,
            timestamp=datetime.now().isoformat(),
            success=success
        )
        self.action_history.append(action)
        logger.debug(f"Recorded action: {action_type} - {description}")
    
    def understand_task(self, task_description: str) -> Dict[str, Any]:
        """
        Analyze and understand a user task.
        
        Args:
            task_description: The user's task or question
            
        Returns:
            Dictionary with task analysis
        """
        # Simple task understanding - in a real system this might use NLP
        keywords = self._extract_keywords(task_description)
        task_type = self._classify_task_type(task_description)
        
        analysis = {
            "original_task": task_description,
            "keywords": keywords,
            "task_type": task_type,
            "complexity": self._estimate_complexity(task_description),
            "required_knowledge_types": self._infer_required_knowledge_types(task_description)
        }
        
        self._record_action(
            "understand_task",
            f"Analyzed task: {task_description[:50]}...",
            {"task_description": task_description},
            analysis
        )
        
        return analysis
    
    def get_project_context(self, project_id: str, task: str, 
                           max_knowledge_items: int = 10) -> ContextPackage:
        """
        Retrieve relevant context for a project and task.
        
        Args:
            project_id: ID of the project
            task: The current task or question
            max_knowledge_items: Maximum knowledge items to include
            
        Returns:
            ContextPackage with relevant information
        """
        context = self.context_assembler.assemble_context(
            project_id, task, max_knowledge_items=max_knowledge_items
        )
        
        self._record_action(
            "get_project_context",
            f"Retrieved context for project {project_id} and task: {task[:30]}...",
            {
                "project_id": project_id,
                "task": task,
                "max_knowledge_items": max_knowledge_items
            },
            {
                "context_id": context.id,
                "knowledge_items": len(context.relevant_knowledge),
                "estimated_tokens": context.estimated_tokens
            }
        )
        
        return context
    
    def search_project_knowledge(self, project_id: str, query: str, 
                                limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for specific knowledge in a project.
        
        Args:
            project_id: ID of the project
            query: Search query
            limit: Maximum results to return
            
        Returns:
            List of matching knowledge items
        """
        results = self.memory_store.search_memories(project_id, query, limit=limit)
        
        self._record_action(
            "search_project_knowledge",
            f"Searched project {project_id} for: {query}",
            {"project_id": project_id, "query": query, "limit": limit},
            {"results_count": len(results)}
        )
        
        return results
    
    def get_relevant_context(self, project_id: str, task: str) -> Dict[str, Any]:
        """
        Get a simplified relevant context for quick consumption.
        
        Args:
            project_id: ID of the project
            task: The current task or question
            
        Returns:
            Dictionary with key context information
        """
        context = self.get_project_context(project_id, task, max_knowledge_items=5)
        
        # Extract the most important information
        relevant_knowledge = [
            {
                "id": k.id,
                "content": k.content,
                "type": k.knowledge_type,
                "importance": k.importance_score
            }
            for k in context.relevant_knowledge
        ]
        
        relevant_decisions = [
            {
                "id": d.id,
                "content": d.content,
                "importance": d.importance_score
            }
            for d in context.relevant_decisions
        ]
        
        result = {
            "task": context.task,
            "project_id": context.project_id,
            "relevant_knowledge": relevant_knowledge,
            "relevant_decisions": relevant_decisions,
            "current_state": context.current_state,
            "constraints": context.constraints,
            "estimated_tokens": context.estimated_tokens,
            "context_id": context.id
        }
        
        self._record_action(
            "get_relevant_context",
            f"Got relevant context for project {project_id}",
            {"project_id": project_id, "task": task},
            {"knowledge_count": len(relevant_knowledge),
             "decision_count": len(relevant_decisions),
             "tokens": context.estimated_tokens}
        )
        
        return result
    
    def read_document(self, project_id: str, document_path: str) -> Optional[str]:
        """
        Read a document from the project (placeholder - would integrate with file system).
        
        Args:
            project_id: ID of the project
            document_path: Path to the document within the project
            
        Returns:
            Document content as string, or None if not found/error
        """
        # This is a placeholder implementation
        # In a real system, this would read from the actual file system
        # or a document management system
        
        # For now, we'll check if we have this document in memory
        memories = self.memory_store.search_memories(
            project_id, 
            f"document:{document_path}", 
            limit=1
        )
        
        if memories:
            content = memories[0].get('content', '')
            self._record_action(
                "read_document",
                f"Read document {document_path} from memory",
                {"project_id": project_id, "document_path": document_path},
                {"content_length": len(content) if content else 0}
            )
            return content if content else None
        
        # If not in memory, return None (would normally read from file system)
        self._record_action(
            "read_document",
            f"Attempted to read document {document_path} (not found in memory)",
            {"project_id": project_id, "document_path": document_path},
            None,
            success=False
        )
        return None
    
    def update_memory(self, project_id: str, content: str, 
                     memory_type: str = "temporary",
                     importance_score: float = 0.5,
                     metadata: Optional[Dict] = None) -> str:
        """
        Update project memory with new information.
        
        Args:
            project_id: ID of the project
            content: The information to remember
            memory_type: Type of memory ('permanent', 'temporary', 'task', 'resolved', 'stale')
            importance_score: Importance score from 0.0 to 1.0
            metadata: Additional metadata
            
        Returns:
            Memory ID of the created/updated memory
        """
        memory_id = self.memory_store.add_memory(
            project_id, content, memory_type, importance_score, metadata
        )
        
        self._record_action(
            "update_memory",
            f"Updated memory in project {project_id}",
            {
                "project_id": project_id,
                "content_preview": content[:100] + "..." if len(content) > 100 else content,
                "memory_type": memory_type,
                "importance_score": importance_score
            },
            {"memory_id": memory_id}
        )
        
        return memory_id
    
    def mark_resolved(self, project_id: str, issue_description: str) -> str:
        """
        Mark an issue as resolved in the project memory.
        
        Args:
            project_id: ID of the project
            issue_description: Description of the issue that was resolved
            
        Returns:
            Memory ID of the resolution record
        """
        resolution_content = f"RESOLVED: {issue_description}"
        memory_id = self.update_memory(
            project_id,
            resolution_content,
            memory_type="resolved",
            importance_score=0.8,
            metadata={
                "issue": issue_description,
                "resolution_date": datetime.now().isoformat(),
                "knowledge_type": "resolution"
            }
        )
        
        self._record_action(
            "mark_resolved",
            f"Marked issue as resolved in project {project_id}",
            {"project_id": project_id, "issue": issue_description},
            {"memory_id": memory_id}
        )
        
        return memory_id
    
    def mark_stale(self, memory_id: str, reason: str = "") -> bool:
        """
        Mark a memory as stale (no longer relevant).
        Preserves existing metadata, merges stale flags.
        """
        existing = self.memory_store.get_memory(memory_id)
        if existing is None:
            return False
        merged_meta = dict(existing.get('metadata') or {})
        merged_meta.update({
            "stale": True,
            "stale_reason": reason,
            "stale_date": datetime.now().isoformat()
        })
        success = self.memory_store.update_memory(
            memory_id,
            importance_score=0.1,
            metadata=merged_meta
        )
        
        self._record_action(
            "mark_stale",
            f"Marked memory {memory_id} as stale",
            {"memory_id": memory_id, "reason": reason},
            {"success": success}
        )
        
        return success
    
    def estimate_context(self, context_package: ContextPackage) -> Dict[str, int]:
        """
        Estimate token usage for a context package.
        
        Args:
            context_package: The context package to estimate
            
        Returns:
            Dictionary with token estimates
        """
        # Convert context to text for estimation
        context_text = self._context_package_to_text(context_package)
        tokens = self.token_estimator.estimate_tokens(context_text)
        
        result = {
            "estimated_tokens": tokens,
            "context_id": context_package.id,
            "project_id": context_package.project_id
        }
        
        self._record_action(
            "estimate_context",
            f"Estimated tokens for context {context_package.id}",
            {"context_id": context_package.id},
            result
        )
        
        return result
    
    def build_context(self, project_id: str, task: str, 
                     max_knowledge_items: int = 10) -> ContextPackage:
        """
        Build an optimized context package for a task.
        This is an alias for get_project_context with a focus on optimization.
        
        Args:
            project_id: ID of the project
            task: The current task or question
            max_knowledge_items: Maximum knowledge items to include
            
        Returns:
            Optimized ContextPackage
        """
        context = self.get_project_context(project_id, task, max_knowledge_items)
        
        self._record_action(
            "build_context",
            f"Built optimized context for project {project_id}",
            {
                "project_id": project_id,
                "task": task,
                "max_knowledge_items": max_knowledge_items
            },
            {
                "context_id": context.id,
                "knowledge_items": len(context.relevant_knowledge),
                "estimated_tokens": context.estimated_tokens
            }
        )
        
        return context
    
    def get_action_history(self, limit: int = 10) -> List[AgentAction]:
        """
        Get the agent's action history.
        
        Args:
            limit: Maximum number of actions to return
            
        Returns:
            List of recent actions
        """
        return self.action_history[-limit:] if limit > 0 else self.action_history
    
    # Helper methods
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text."""
        import re
        common_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those'
        }
        
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        keywords = [w for w in words if w not in common_words and len(w) > 3]
        
        # Return unique keywords
        return list(dict.fromkeys(keywords))[:10]
    
    def _classify_task_type(self, task: str) -> str:
        """Classify the type of task."""
        task_lower = task.lower()
        if any(word in task_lower for word in ['fix', 'bug', 'error', 'issue', 'problem']):
            return 'troubleshooting'
        elif any(word in task_lower for word in ['build', 'create', 'implement', 'add']):
            return 'development'
        elif any(word in task_lower for word in ['explain', 'understand', 'learn', 'what']):
            return 'learning'
        elif any(word in task_lower for word in ['review', 'check', 'audit', 'inspect']):
            return 'review'
        else:
            return 'general'
    
    def _estimate_complexity(self, task: str) -> str:
        """Estimate task complexity."""
        # Simple heuristic based on length and keywords
        length_factor = min(len(task) / 100, 2.0)  # Normalize length
        keyword_indicators = len([w for w in ['complex', 'difficult', 'hard', 'challenging', 
                                              'simple', 'easy', 'straightforward'] 
                                 if w in task.lower()])
        
        if length_factor > 1.5 or keyword_indicators > 0:
            if any(w in task.lower() for w in ['complex', 'difficult', 'hard', 'challenging']):
                return 'high'
            elif any(w in task.lower() for w in ['simple', 'easy', 'straightforward']):
                return 'low'
            else:
                return 'medium'
        else:
            return 'low'
    
    def _infer_required_knowledge_types(self, task: str) -> List[str]:
        """Infer what types of knowledge might be needed for this task."""
        task_lower = task.lower()
        knowledge_types = []
        
        if any(word in task_lower for word in ['how', 'architecture', 'structure', 'design']):
            knowledge_types.append('architecture')
        if any(word in task_lower for word in ['decision', 'chose', 'selected', 'approach']):
            knowledge_types.append('decision')
        if any(word in task_lower for word in ['bug', 'issue', 'problem', 'error']):
            knowledge_types.append('issue')
        if any(word in task_lower for word in ['prefer', 'like', 'want', 'need']):
            knowledge_types.append('preference')
        if any(word in task_lower for word in ['what is', 'define', 'meaning']):
            knowledge_types.append('project_identity')
        
        # Default to general if none detected
        if not knowledge_types:
            knowledge_types = ['general']
        
        return knowledge_types
    
    def _context_package_to_text(self, context_package: ContextPackage) -> str:
        """Convert a context package to text for token estimation."""
        sections = []
        
        sections.append(f"TASK: {context_package.task}")
        
        if context_package.relevant_knowledge:
            sections.append("RELEVANT KNOWLEDGE:")
            for k in context_package.relevant_knowledge:
                sections.append(f"- [{k.knowledge_type}] {k.content}")
        
        if context_package.relevant_decisions:
            sections.append("RELEVANT DECISIONS:")
            for d in context_package.relevant_decisions:
                sections.append(f"- {d.content}")
        
        if context_package.current_state:
            sections.append("CURRENT STATE:")
            for key, value in context_package.current_state.items():
                sections.append(f"- {key}: {value}")
        
        if context_package.constraints:
            sections.append("CONSTRAINTS:")
            for constraint in context_package.constraints:
                sections.append(f"- {constraint}")
        
        return "\n".join(sections)


# Global agent instance (optional)
default_agent = None


def get_overhaust_agent(agent_id: str = "overhaust-agent-001") -> OverhaustAgent:
    """
    Get or create the default Overhaust agent.
    
    Args:
        agent_id: ID for the agent instance
        
    Returns:
        OverhaustAgent instance
    """
    global default_agent
    if default_agent is None or default_agent.agent_id != agent_id:
        default_agent = OverhaustAgent(agent_id)
    return default_agent