"""
Register + index lifecycle helpers for multi-repository use.

Context requests load the persisted index only; operators call these helpers
(or REST ``/api/v1/index-project``) when the tree needs a refresh.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


def ensure_project_indexed(
    project_id: str,
    root_path: str,
    *,
    name: Optional[str] = None,
    description: str = "",
    force_full: bool = False,
    memory_store=None,
) -> Dict[str, Any]:
    """
    Register (or update) a project and run ``sync_project``.

    Safe to re-run: same ``project_id`` updates root; a different project_id
    claiming the same root raises ``ValueError``.
    """
    from packages.memory.memory_store import get_memory_store
    from services.ingestion.index_store import ProjectIndexStore

    if memory_store is None:
        memory_store = get_memory_store()

    repo = str(Path(root_path).expanduser().resolve())
    existing = memory_store.get_project(project_id)
    newly_registered = existing is None
    display_name = name or (existing or {}).get("name") or project_id
    desc = description or (existing or {}).get("description") or ""

    index_store = ProjectIndexStore(memory_store)
    owner = index_store.resolve_project_id(repo)
    if owner and owner != project_id:
        raise ValueError(
            f"Repository {repo} is already registered as project {owner}"
        )

    memory_store.add_project(project_id, display_name, desc, repo)
    index, report = index_store.sync_project(
        project_id, repo, force_full=force_full
    )
    resolved = index_store.resolve_project_id(repo)
    health = index_store.index_health(project_id)
    return {
        "project_id": project_id,
        "root_path": repo,
        "newly_registered": newly_registered,
        "resolved_project_id": resolved,
        "indexed": True,
        "mode": report.get("mode"),
        "file_count": report.get("file_count", len(index.files)),
        "sync": report,
        "health": health,
    }
