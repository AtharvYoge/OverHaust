"""
Persistent project index storage in SQLite.

Reuses ProjectIndexer diff/apply logic to avoid rescanning unchanged files.
Does not store file contents — only metadata, symbols, and imports.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from services.ingestion.project_indexer import (
    INDEX_EXTRACTOR_VERSION,
    ProjectIndexer,
    ProjectIndex,
    FileIndex,
    Symbol,
    PathSecurityError,
)

logger = logging.getLogger(__name__)


class ProjectIndexStore:
    """Load, save, and incrementally sync project indexes in SQLite."""

    def __init__(self, memory_store):
        self.store = memory_store
        self.indexer = ProjectIndexer()
        self._ensure_tables()

    def _ensure_tables(self):
        with self.store._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_index_meta (
                    project_id TEXT PRIMARY KEY,
                    root_path TEXT NOT NULL,
                    indexed_at TEXT NOT NULL,
                    total_tokens INTEGER DEFAULT 0,
                    stats TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_index_files (
                    project_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    extension TEXT,
                    size INTEGER,
                    sha256 TEXT,
                    token_count INTEGER,
                    imports TEXT,
                    exports TEXT,
                    is_config INTEGER DEFAULT 0,
                    line_count INTEGER DEFAULT 0,
                    PRIMARY KEY (project_id, path)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_index_symbols (
                    project_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    line INTEGER DEFAULT 0,
                    exported INTEGER DEFAULT 0,
                    PRIMARY KEY (project_id, file_path, name, kind)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pif_project ON project_index_files(project_id)"
            )
            # Added after initial release; existing databases need the column.
            try:
                conn.execute(
                    "ALTER TABLE project_index_meta ADD COLUMN extractor_version TEXT"
                )
            except sqlite3.OperationalError:
                pass
            conn.commit()

    def load_index(self, project_id: str) -> Optional[ProjectIndex]:
        """Load a persisted index or None if never indexed."""
        meta = self._load_meta(project_id)
        if meta is None:
            return None
        files = self._load_files(project_id)
        if not files:
            return None
        deps = {f.path: f.imports for f in files if f.imports}
        stats = json.loads(meta.get("stats") or "{}")
        return ProjectIndex(
            project_id=project_id,
            root_path=meta["root_path"],
            files=files,
            indexed_at=meta["indexed_at"],
            total_tokens=int(meta.get("total_tokens") or 0),
            dependencies=deps,
            stats=stats,
        )

    def save_index(self, index: ProjectIndex) -> None:
        """Persist a full project index snapshot."""
        with self.store._connect() as conn:
            conn.execute(
                "DELETE FROM project_index_symbols WHERE project_id = ?",
                (index.project_id,),
            )
            conn.execute(
                "DELETE FROM project_index_files WHERE project_id = ?",
                (index.project_id,),
            )
            conn.execute("""
                INSERT OR REPLACE INTO project_index_meta
                (project_id, root_path, indexed_at, total_tokens, stats,
                 extractor_version)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                index.project_id,
                index.root_path,
                index.indexed_at,
                index.total_tokens,
                json.dumps(index.stats),
                INDEX_EXTRACTOR_VERSION,
            ))
            for f in index.files:
                conn.execute("""
                    INSERT INTO project_index_files
                    (project_id, path, extension, size, sha256, token_count,
                     imports, exports, is_config, line_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    index.project_id, f.path, f.extension, f.size, f.sha256,
                    f.token_count, json.dumps(f.imports), json.dumps(f.exports),
                    1 if f.is_config else 0, f.line_count,
                ))
                for sym in f.symbols:
                    conn.execute("""
                        INSERT INTO project_index_symbols
                        (project_id, file_path, name, kind, line, exported)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        index.project_id, f.path, sym.name, sym.kind,
                        sym.line, 1 if sym.exported else 0,
                    ))
            conn.commit()

    def stored_extractor_version(self, project_id: str) -> str:
        """Extractor fingerprint a persisted index was built with ('' if none)."""
        meta = self._load_meta(project_id)
        if not meta:
            return ""
        return meta.get("extractor_version") or ""

    def extractor_version_is_current(self, project_id: str) -> bool:
        """False when persisted symbols predate the current extraction rules."""
        return self.stored_extractor_version(project_id) == INDEX_EXTRACTOR_VERSION

    def sync_project(
        self, project_id: str, root_path: str, force_full: bool = False
    ) -> Tuple[ProjectIndex, Dict[str, Any]]:
        """
        Incrementally sync on-disk project with persisted index.

        Returns (updated_index, sync_report) where sync_report includes
        diff details and whether a full scan was performed.

        A stale extractor fingerprint forces a full re-scan: content hashes
        cannot detect that the extraction rules themselves changed, so an
        incremental pass would keep symbols the current extractor would no
        longer produce (or would now produce for the first time).
        """
        normalized_root = str(Path(root_path).expanduser().resolve())
        stale_extractor = not self.extractor_version_is_current(project_id)
        previous = (
            None if (force_full or stale_extractor) else self.load_index(project_id)
        )

        if previous is None or previous.root_path != normalized_root:
            index = self.indexer.index_project(normalized_root, project_id)
            self.save_index(index)
            return index, {
                "mode": "full",
                "reason": "extractor_version_changed" if stale_extractor else "",
                "added": [f.path for f in index.files],
                "modified": [],
                "deleted": [],
                "renamed": [],
                "file_count": len(index.files),
                "extractor_version": INDEX_EXTRACTOR_VERSION,
            }

        diff = self.indexer.diff_project(previous, normalized_root)
        unchanged = (
            not diff["added"] and not diff["modified"]
            and not diff["deleted"] and not diff["renamed"]
        )
        if unchanged:
            return previous, {
                "mode": "unchanged",
                "added": [], "modified": [], "deleted": [], "renamed": [],
                "file_count": len(previous.files),
                "extractor_version": INDEX_EXTRACTOR_VERSION,
            }

        index = self.indexer.apply_diff(previous, diff, normalized_root)
        self.save_index(index)
        return index, {
            "mode": "incremental",
            "added": diff["added"],
            "modified": diff["modified"],
            "deleted": diff["deleted"],
            "renamed": diff["renamed"],
            "file_count": len(index.files),
            "extractor_version": INDEX_EXTRACTOR_VERSION,
        }

    def load_index_or_none(self, project_id: str) -> Optional[ProjectIndex]:
        """Load persisted index without syncing/rescanning."""
        return self.load_index(project_id)

    def get_project_root(self, project_id: str) -> Optional[str]:
        """Return indexed root path from meta, or project root_path fallback."""
        meta = self._load_meta(project_id)
        if meta and meta.get("root_path"):
            return meta["root_path"]
        project = self.store.get_project(project_id)
        if project:
            return project.get("root_path") or project.get("project_root") or None
        return None

    def get_index_for_context(self, project_id: str, root_path: str) -> Optional[ProjectIndex]:
        """Load persisted index or perform initial sync if root_path is set."""
        if not root_path:
            return None
        try:
            normalized = str(Path(root_path).expanduser().resolve())
            index, _report = self.sync_project(project_id, normalized)
            return index
        except PathSecurityError:
            raise
        except Exception as exc:
            logger.warning("Index sync failed for %s: %s", project_id, exc)
            return self.load_index(project_id)

    # ------------------------------------------------------------------

    def _load_meta(self, project_id: str) -> Optional[Dict[str, Any]]:
        with self.store._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM project_index_meta WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            return dict(row) if row else None

    def _load_files(self, project_id: str) -> List[FileIndex]:
        with self.store._connect() as conn:
            conn.row_factory = sqlite3.Row
            file_rows = conn.execute(
                "SELECT * FROM project_index_files WHERE project_id = ? ORDER BY path",
                (project_id,),
            ).fetchall()
            sym_rows = conn.execute(
                "SELECT * FROM project_index_symbols WHERE project_id = ?",
                (project_id,),
            ).fetchall()

        syms_by_path: Dict[str, List[Symbol]] = {}
        for s in sym_rows:
            syms_by_path.setdefault(s["file_path"], []).append(Symbol(
                name=s["name"], kind=s["kind"], file_path=s["file_path"],
                line=int(s["line"]), exported=bool(s["exported"]),
            ))

        files: List[FileIndex] = []
        for row in file_rows:
            files.append(FileIndex(
                path=row["path"],
                extension=row["extension"] or "",
                size=int(row["size"] or 0),
                sha256=row["sha256"] or "",
                token_count=int(row["token_count"] or 0),
                symbols=syms_by_path.get(row["path"], []),
                imports=json.loads(row["imports"] or "[]"),
                exports=json.loads(row["exports"] or "[]"),
                is_config=bool(row["is_config"]),
                line_count=int(row["line_count"] or 0),
            ))
        return files
