"""
Persistent local embedding storage in SQLite.

Stores vectors linked to memory_id + content_hash — no duplicate content.
"""

import json
import sqlite3
from typing import Dict, List, Optional, Tuple, Any
import logging

logger = logging.getLogger(__name__)


class EmbeddingStore:
    """CRUD for memory_embeddings table."""

    def __init__(self, memory_store):
        self.store = memory_store
        self._ensure_table()

    def _ensure_table(self):
        with self.store._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_embeddings (
                    memory_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_embeddings_project "
                "ON memory_embeddings(project_id)"
            )
            conn.commit()

    def get(self, memory_id: str, model_id: str) -> Optional[Tuple[str, List[float]]]:
        """Return (content_hash, vector) or None."""
        with self.store._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT content_hash, embedding FROM memory_embeddings "
                "WHERE memory_id = ? AND model_id = ?",
                (memory_id, model_id),
            ).fetchone()
        if not row:
            return None
        try:
            vector = json.loads(row["embedding"])
        except (json.JSONDecodeError, TypeError):
            return None
        return row["content_hash"], vector

    def upsert(
        self,
        memory_id: str,
        project_id: str,
        model_id: str,
        content_hash: str,
        vector: List[float],
    ) -> None:
        blob = json.dumps(vector)
        with self.store._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO memory_embeddings
                (memory_id, project_id, model_id, content_hash, embedding, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (memory_id, project_id, model_id, content_hash, blob))
            conn.commit()

    def delete_for_memory(self, memory_id: str) -> None:
        with self.store._connect() as conn:
            conn.execute(
                "DELETE FROM memory_embeddings WHERE memory_id = ?",
                (memory_id,),
            )
            conn.commit()

    def list_for_project(
        self, project_id: str, model_id: str
    ) -> List[Dict[str, Any]]:
        """All stored embeddings for a project (for brute-force search)."""
        with self.store._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT memory_id, content_hash, embedding FROM memory_embeddings "
                "WHERE project_id = ? AND model_id = ?",
                (project_id, model_id),
            ).fetchall()
        out = []
        for row in rows:
            try:
                vector = json.loads(row["embedding"])
            except (json.JSONDecodeError, TypeError):
                continue
            out.append({
                "memory_id": row["memory_id"],
                "content_hash": row["content_hash"],
                "vector": vector,
            })
        return out
