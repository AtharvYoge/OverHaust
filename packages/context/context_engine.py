"""
Context package for Overhaust.
Handles knowledge extraction, context assembly, and relevance determination.
"""

import re
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import hashlib
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExtractedKnowledge:
    """Represents extracted knowledge from a source."""
    id: str
    project_id: str
    source_type: str  # 'conversation', 'document', 'code', 'instruction'
    source_title: str
    title: str
    content: str
    knowledge_type: str  # 'identity', 'architecture', 'decision', 'state', 'issue', 'preference'
    importance_score: float  # 0.0 to 1.0
    extracted_at: str
    metadata: Dict[str, Any]
    source_hash: str  # Hash of original source for change detection


@dataclass
class ContextPackage:
    """Represents a compiled context package for AI consumption."""
    id: str
    project_id: str
    task: str
    relevant_knowledge: List[ExtractedKnowledge]
    relevant_files: List[Dict[str, Any]]
    relevant_decisions: List[ExtractedKnowledge]
    current_state: Dict[str, Any]
    relevant_memory: List[Dict[str, Any]]
    constraints: List[str]
    created_at: str
    estimated_tokens: int


class KnowledgeExtractor:
    """Extracts structured knowledge from various sources."""
    
    def __init__(self):
        self.knowledge_patterns = {
            'project_identity': [
                r'(?i)project\s*name\s*[:=]\s*([^\n]+)',
                r'(?i)this\s*project\s+is\s+([^\n]+)',
                r'(?i)we\s*are\s+building\s+([^\n]+)',
            ],
            'architecture': [
                r'(?i)architecture\s*[:=]\s*([^\n]+)',
                r'(?i)we\s*use\s+([^\n]+)\s+for\s+([^\n]+)',
                r'(?i)stack\s*[:=]\s*([^\n]+)',
            ],
            'decision': [
                r'(?i)we\s*decided\s+to\s+([^\n]+)',
                r'(?i)decision\s*[:=]\s*([^\n]+)',
                r'(?i)chosen\s+approach\s*[:=]\s*([^\n]+)',
            ],
            'issue': [
                r'(?i)problem\s*[:=]\s*([^\n]+)',
                r'(?i)issue\s*[:=]\s*([^\n]+)',
                r'(?i)bug\s*[:=]\s*([^\n]+)',
            ],
            'preference': [
                r'(?i)prefer\s+([^\n]+)',
                r'(?i)like\s+to\s+([^\n]+)',
                r'(?i)want\s+([^\n]+)',
            ]
        }
    
    def extract_knowledge(self, source_content: str, project_id: str, 
                         source_type: str = "conversation",
                         source_title: str = "Unknown Source") -> List[ExtractedKnowledge]:
        """
        Extract structured knowledge from source content.
        
        Args:
            source_content: The raw content to extract knowledge from
            project_id: ID of the project this knowledge belongs to
            source_type: Type of source ('conversation', 'document', 'code', 'instruction')
            source_title: Title or description of the source
            
        Returns:
            List of extracted knowledge items
        """
        extracted = []
        source_hash = hashlib.sha256(source_content.encode()).hexdigest()
        
        # Split content into chunks for processing
        chunks = self._split_into_chunks(source_content)
        
        for i, chunk in enumerate(chunks):
            chunk_knowledge = self._extract_from_chunk(
                chunk, project_id, source_type, f"{source_title} - Chunk {i+1}"
            )
            extracted.extend(chunk_knowledge)
        
        logger.info(f"Extracted {len(extracted)} knowledge items from {source_type}")
        return extracted
    
    def _split_into_chunks(self, content: str, chunk_size: int = 1000) -> List[str]:
        """Split content into overlapping chunks for better extraction."""
        if len(content) <= chunk_size:
            return [content]
        
        chunks = []
        start = 0
        while start < len(content):
            end = start + chunk_size
            # Try to break at sentence boundary
            if end < len(content):
                # Look for sentence endings near the boundary
                for i in range(end, max(end - 100, start), -1):
                    if content[i] in '.!?\n':
                        end = i + 1
                        break
            
            chunks.append(content[start:end])
            start = end - 100  # Overlap for context
            if start >= len(content):
                break
                
        return chunks
    
    def _extract_from_chunk(self, chunk: str, project_id: str, 
                           source_type: str, source_title: str) -> List[ExtractedKnowledge]:
        """Extract knowledge from a single chunk."""
        knowledge_items = []
        
        # Check each knowledge type pattern
        for knowledge_type, patterns in self.knowledge_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, chunk)
                for match in matches:
                    # Extract the matched content
                    matched_text = match.group(0).strip()
                    if len(match.groups()) > 0:
                        matched_text = match.group(1).strip()
                    
                    if len(matched_text) > 10:  # Filter out trivial matches
                        knowledge_id = hashlib.sha256(
                            f"{project_id}_{source_title}_{matched_text}".encode()
                        ).hexdigest()[:16]
                        
                        knowledge = ExtractedKnowledge(
                            id=knowledge_id,
                            project_id=project_id,
                            source_type=source_type,
                            source_title=source_title,
                            title=f"{knowledge_type.title()} from {source_title}",
                            content=matched_text,
                            knowledge_type=knowledge_type,
                            importance_score=self._calculate_importance(
                                knowledge_type, matched_text, chunk
                            ),
                            extracted_at=datetime.now().isoformat(),
                            metadata={
                                "source_chunk": chunk[:200] + "..." if len(chunk) > 200 else chunk,
                                "match_position": match.start()
                            },
                            source_hash=hashlib.sha256(chunk.encode()).hexdigest()
                        )
                        knowledge_items.append(knowledge)
        
        return knowledge_items
    
    def _calculate_importance(self, knowledge_type: str, text: str, 
                            full_context: str) -> float:
        """Calculate importance score for extracted knowledge."""
        base_score = 0.5
        
        # Adjust based on knowledge type
        type_weights = {
            'decision': 0.9,
            'architecture': 0.85,
            'project_identity': 0.8,
            'issue': 0.75,
            'preference': 0.6
        }
        
        score = type_weights.get(knowledge_type, base_score)
        
        # Boost for certain keywords
        high_importance_keywords = [
            'critical', 'important', 'must', 'required', 'essential',
            'key', 'core', 'main', 'primary'
        ]
        
        text_lower = text.lower()
        for keyword in high_importance_keywords:
            if keyword in text_lower:
                score = min(1.0, score + 0.1)
                break
        
        # Reduce for very short text
        if len(text) < 20:
            score *= 0.8
            
        return max(0.1, min(1.0, score))


class ContextAssembler:
    """Assembles context packages for AI consumption based on project knowledge and task.
    Uses the layered relevance engine; every selection carries an explanation."""

    def __init__(self, memory_store=None, token_estimator=None):
        from packages.memory.memory_store import get_memory_store
        from packages.tokenization.token_estimator import TokenEstimator
        from packages.context.relevance import LayeredRelevanceEngine

        self.memory_store = memory_store or get_memory_store()
        self.token_estimator = token_estimator or TokenEstimator()
        self.knowledge_extractor = KnowledgeExtractor()
        self.relevance = LayeredRelevanceEngine(self.memory_store)
    
    def assemble_context(self, project_id: str, task: str, 
                        max_knowledge_items: int = 10,
                        max_files: int = 5) -> ContextPackage:
        """
        Assemble a context package for a given project and task.
        
        Args:
            project_id: ID of the project
            task: The current task or question
            max_knowledge_items: Maximum knowledge items to include
            max_files: Maximum files to include
            
        Returns:
            ContextPackage with relevant information
        """
        # Get project information
        project = self.memory_store.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        # Get relevant memories/knowledge
        relevant_knowledge = self._get_relevant_knowledge(
            project_id, task, max_knowledge_items
        )
        
        # Get relevant files (placeholder - would integrate with file system)
        relevant_files = self._get_relevant_files(project_id, task, max_files)
        
        # Extract decisions from knowledge
        relevant_decisions = [
            k for k in relevant_knowledge 
            if k.knowledge_type == 'decision'
        ]
        
        # Get current state
        current_state = self._get_current_state(project_id)
        
        # Get relevant memory (general memories)
        relevant_memory = self._get_relevant_memory(project_id, task, 5)
        
        # Identify constraints
        constraints = self._identify_constraints(relevant_knowledge, task)
        
        # Create context package
        context_id = hashlib.sha256(
            f"{project_id}_{task}_{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]
        
        # Estimate tokens for the context package
        context_text = self._context_to_text({
            'task': task,
            'knowledge': [k.content for k in relevant_knowledge],
            'files': [f.get('path', '') for f in relevant_files],
            'decisions': [d.content for d in relevant_decisions],
            'state': current_state,
            'constraints': constraints
        })
        
        estimated_tokens = self.token_estimator.estimate_tokens(context_text)
        
        context_package = ContextPackage(
            id=context_id,
            project_id=project_id,
            task=task,
            relevant_knowledge=relevant_knowledge,
            relevant_files=relevant_files,
            relevant_decisions=relevant_decisions,
            current_state=current_state,
            relevant_memory=relevant_memory,
            constraints=constraints,
            created_at=datetime.now().isoformat(),
            estimated_tokens=estimated_tokens
        )
        
        logger.info(f"Assembled context package {context_id} for project {project_id}")
        return context_package
    
    def _get_relevant_knowledge(self, project_id: str, task: str,
                               limit: int) -> List[ExtractedKnowledge]:
        """Get knowledge relevant to the task via the layered relevance engine.
        Returns items ranked by relevance score with explanations attached
        in metadata['relevance']."""
        scored = self.relevance.search(project_id, task, limit=limit)
        items: List[ExtractedKnowledge] = []
        for sm in scored:
            mem = sm.memory
            meta = dict(mem.get('metadata') or {})
            meta['relevance'] = {'score': sm.score, 'reasons': sm.reasons}
            knowledge = ExtractedKnowledge(
                id=mem['id'],
                project_id=mem['project_id'],
                source_type=meta.get('source_type', 'memory'),
                source_title=meta.get('provenance', meta.get('source_id', 'Memory')),
                title=meta.get('title', f"Knowledge from {mem['id']}"),
                content=mem['content'],
                knowledge_type=meta.get('knowledge_type', 'general'),
                importance_score=mem['importance_score'],
                extracted_at=str(mem['created_at']),
                metadata=meta,
                source_hash=mem.get('source_hash', '')
            )
            items.append(knowledge)
        return items
    
    def _get_relevant_files(self, project_id: str, task: str, 
                           limit: int) -> List[Dict[str, Any]]:
        """Get files relevant to the task (placeholder implementation)."""
        # In a real implementation, this would scan the project directory
        # and use file content analysis to find relevant files
        return [
            {
                "id": f"file-{i}",
                "path": f"src/component-{i}.tsx",
                "name": f"Component {i}",
                "relevance_score": 0.9 - (i * 0.1),
                "last_modified": datetime.now().isoformat()
            }
            for i in range(min(limit, 3))
        ]
    
    def _get_current_state(self, project_id: str) -> Dict[str, Any]:
        """Get current state of the project."""
        # Get recent memories that indicate current state
        recent_memories = self.memory_store.get_project_memories(
            project_id, 
            memory_types=['task', 'state'],
            min_importance=0.5,
            limit=5
        )
        
        state = {
            "last_updated": datetime.now().isoformat(),
            "active_issues": [],
            "recent_decisions": [],
            "current_focus": ""
        }
        
        for mem in recent_memories:
            if mem.get('metadata', {}).get('knowledge_type') == 'issue':
                state["active_issues"].append(mem['content'])
            elif mem.get('metadata', {}).get('knowledge_type') == 'decision':
                state["recent_decisions"].append(mem['content'])
        
        return state
    
    def _get_relevant_memory(self, project_id: str, task: str, 
                           limit: int) -> List[Dict[str, Any]]:
        """Get general relevant memories."""
        return self.memory_store.search_memories(project_id, task, limit=limit)
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text for search."""
        # Simple keyword extraction - remove common words and extract meaningful terms
        common_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those'
        }
        
        # Extract words (alphanumeric sequences)
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        
        # Filter out common words and short words
        keywords = [w for w in words if w not in common_words and len(w) > 3]
        
        # Count frequency and return most common
        from collections import Counter
        word_freq = Counter(keywords)
        return [word for word, _ in word_freq.most_common(10)]
    
    def _identify_constraints(self, knowledge_items: List[ExtractedKnowledge], 
                            task: str) -> List[str]:
        """Identify constraints from knowledge and task."""
        constraints = []
        
        # Look for constraint-indicating language in knowledge
        constraint_patterns = [
            r'(?i)must\s+([^\n]+)',
            r'(?i)should\s+([^\n]+)',
            r'(?i)cannot\s+([^\n]+)',
            r'(?i)limited\s+to\s+([^\n]+)',
            r'(?i)requirement\s*[:=]\s*([^\n]+)',
            r'(?i)constraint\s*[:=]\s*([^\n]+)'
        ]
        
        all_text = task + " " + " ".join([k.content for k in knowledge_items])
        
        for pattern in constraint_patterns:
            matches = re.finditer(pattern, all_text)
            for match in matches:
                constraint = match.group(0).strip()
                if len(constraint) > 10:
                    constraints.append(constraint)
        
        return list(set(constraints))[:5]  # Limit and deduplicate
    
    def _context_to_text(self, context_dict: Dict) -> str:
        """Convert context dictionary to text for token estimation."""
        def format_value(val):
            if isinstance(val, dict):
                return json.dumps(val)
            elif isinstance(val, list):
                return ", ".join([format_value(item) for item in val])
            else:
                return str(val)
        
        parts = []
        for key, value in context_dict.items():
            parts.append(f"{key}: {format_value(value)}")
        
        return "\n".join(parts)


# Global instances
knowledge_extractor = KnowledgeExtractor()
context_assembler = ContextAssembler()


def get_knowledge_extractor() -> KnowledgeExtractor:
    """Get the global knowledge extractor."""
    return knowledge_extractor


def get_context_assembler() -> ContextAssembler:
    """Get the global context assembler."""
    return context_assembler