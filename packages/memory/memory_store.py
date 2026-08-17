"""
Memory package for Overhaust.
Handles storage, retrieval, and management of project knowledge and memories.
"""

import sqlite3
import json
import hashlib
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)


class MemoryStore:
    """Handles persistent storage of memories and project knowledge."""
    
    def __init__(self, db_path: str = "/Users/atharv11/Desktop/overhaust/overhaust_memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize the SQLite database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    memory_type TEXT NOT NULL,  -- 'permanent', 'temporary', 'task', 'resolved', 'stale'
                    importance_score REAL DEFAULT 0.5,  -- 0.0 to 1.0
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 0,
                    metadata TEXT,  -- JSON string for additional data
                    source_hash TEXT  -- Hash of source content for change detection
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    root_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_extractions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    extraction_type TEXT NOT NULL,  -- 'conversation', 'document', 'code', etc.
                    source_content TEXT NOT NULL,
                    extracted_knowledge TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects (id)
                )
            """)
            
            # Create indices for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_project_id ON memories(project_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance_score)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_updated ON memories(updated_at)")
            
            conn.commit()
    
    def _generate_id(self, content: str) -> str:
        """Generate a unique ID based on content hash."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _generate_source_hash(self, content: str) -> str:
        """Generate hash of source content for change detection."""
        return hashlib.sha256(content.encode()).hexdigest()
    
    def add_memory(self, project_id: str, content: str, memory_type: str = "temporary",
                   importance_score: float = 0.5, metadata: Optional[Dict] = None) -> str:
        """
        Add a new memory to the store.
        
        Args:
            project_id: ID of the project this memory belongs to
            content: The memory content
            memory_type: Type of memory ('permanent', 'temporary', 'task', 'resolved', 'stale')
            importance_score: Importance score from 0.0 to 1.0
            metadata: Additional metadata as dictionary
            
        Returns:
            Memory ID
        """
        memory_id = self._generate_id(content)
        source_hash = self._generate_source_hash(content)
        metadata_json = json.dumps(metadata) if metadata else None
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO memories 
                (id, project_id, content, memory_type, importance_score, metadata, source_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (memory_id, project_id, content, memory_type, importance_score, metadata_json, source_hash))
            conn.commit()
        
        logger.info(f"Added memory {memory_id} to project {project_id}")
        return memory_id
    
    def get_memory(self, memory_id: str) -> Optional[Dict]:
        """Retrieve a memory by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM memories WHERE id = ?
            """, (memory_id,))
            row = cursor.fetchone()
            
            if row:
                memory = dict(row)
                # Update access tracking
                self._update_access(memory_id)
                return memory
            return None
    
    def search_memories(self, project_id: str, query: str = "", 
                       memory_type: Optional[str] = None,
                       limit: int = 10) -> List[Dict]:
        """
        Search memories for a project.
        
        Args:
            project_id: Project to search in
            query: Text search query (simple LIKE for now)
            memory_type: Filter by memory type
            limit: Maximum results to return
            
        Returns:
            List of matching memories
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            sql = """
                SELECT * FROM memories 
                WHERE project_id = ?
            """
            params = [project_id]
            
            if query:
                sql += " AND content LIKE ?"
                params.append(f"%{query}%")
            
            if memory_type:
                sql += " AND memory_type = ?"
                params.append(memory_type)
            
            sql += " ORDER BY importance_score DESC, updated_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
            
            memories = []
            for row in rows:
                memory = dict(row)
                # Parse metadata JSON if present
                if memory['metadata']:
                    try:
                        memory['metadata'] = json.loads(memory['metadata'])
                    except json.JSONDecodeError:
                        memory['metadata'] = {}
                memories.append(memory)
                
                # Update access tracking
                self._update_access(memory['id'])
            
            return memories
    
    def update_memory(self, memory_id: str, content: Optional[str] = None,
                     importance_score: Optional[float] = None,
                     metadata: Optional[Dict] = None) -> bool:
        """Update an existing memory."""
        updates = []
        params = []
        
        if content is not None:
            updates.append("content = ?")
            params.append(content)
            updates.append("source_hash = ?")  # Update source hash when content changes
            params.append(self._generate_source_hash(content))
        
        if importance_score is not None:
            updates.append("importance_score = ?")
            params.append(importance_score)
        
        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata))
        
        if not updates:
            return False
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(memory_id)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(f"""
                UPDATE memories 
                SET {', '.join(updates)}
                WHERE id = ?
            """, params)
            conn.commit()
            
            return cursor.rowcount > 0
    
    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def _update_access(self, memory_id: str):
        """Update access tracking for a memory."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE memories 
                SET accessed_at = CURRENT_TIMESTAMP,
                    access_count = access_count + 1
                WHERE id = ?
            """, (memory_id,))
            conn.commit()
    
    def get_project_memories(self, project_id: str, 
                           memory_types: Optional[List[str]] = None,
                           min_importance: float = 0.0,
                           limit: int = 50) -> List[Dict]:
        """Get all memories for a project with optional filtering."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            sql = """
                SELECT * FROM memories 
                WHERE project_id = ? AND importance_score >= ?
            """
            params = [project_id, min_importance]
            
            if memory_types:
                placeholders = ",".join(["?"] * len(memory_types))
                sql += f" AND memory_type IN ({placeholders})"
                params.extend(memory_types)
            
            sql += " ORDER BY importance_score DESC, updated_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
            
            memories = []
            for row in rows:
                memory = dict(row)
                if memory['metadata']:
                    try:
                        memory['metadata'] = json.loads(memory['metadata'])
                    except json.JSONDecodeError:
                        memory['metadata'] = {}
                memories.append(memory)
            
            return memories
    
    def add_project(self, project_id: str, name: str, description: str = "",
                   root_path: str = "", metadata: Optional[Dict] = None) -> str:
        """Add a new project to the store."""
        metadata_json = json.dumps(metadata) if metadata else None
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO projects 
                (id, name, description, root_path, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (project_id, name, description, root_path, metadata_json))
            conn.commit()
        
        return project_id
    
    def get_project(self, project_id: str) -> Optional[Dict]:
        """Get project information."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
            row = cursor.fetchone()
            
            if row:
                project = dict(row)
                if project['metadata']:
                    try:
                        project['metadata'] = json.loads(project['metadata'])
                    except json.JSONDecodeError:
                        project['metadata'] = {}
                return project
            return None
    
    def cleanup_stale_memories(self, max_age_days: int = 30) -> int:
        """Remove memories older than max_age_days that aren't permanent or high importance."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM memories 
                WHERE memory_type != 'permanent' 
                AND importance_score < 0.7
                AND updated_at < datetime('now', '-' || ? || ' days')
            """, (str(max_age_days),))  # Fixed: convert int to string for SQL parameter
            conn.commit()
            return cursor.rowcount


# Global memory store instance
memory_store = MemoryStore()


def get_memory_store() -> MemoryStore:
    """Get the global memory store instance."""
    return memory_store