"""
Knowledge supersession — newer knowledge replaces older without deletion.
"""

from typing import Any, Dict, Optional

from packages.knowledge.schema import normalize_metadata
from packages.knowledge.provenance import format_provenance


def supersede(
    memory_store,
    project_id: str,
    old_memory_id: str,
    new_content: str,
    *,
    memory_type: str = "permanent",
    importance_score: float = 0.85,
    confidence: Optional[float] = None,
    provenance: Optional[str] = None,
    source_type: str = "user",
    authority: str = "user",
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Create new memory that supersedes an older one.

    Old memory: status=superseded, superseded_by=new_id (content preserved).
    New memory: status=active, supersedes=old_id.
    """
    old = memory_store.get_memory(old_memory_id)
    if old is None:
        raise ValueError(f"Memory {old_memory_id} not found")
    if old["project_id"] != project_id:
        raise ValueError(f"Memory {old_memory_id} does not belong to project {project_id}")

    old_meta = normalize_metadata(old.get("metadata"))
    new_meta = normalize_metadata(metadata or {})
    new_meta.update({
        "status": "active",
        "version": 1,
        "supersedes": old_memory_id,
        "superseded_by": None,
        "source_type": source_type,
        "authority": authority,
        "knowledge_type": new_meta.get("knowledge_type") or old_meta.get("knowledge_type", "decision"),
    })
    if confidence is not None:
        new_meta["confidence"] = confidence
    if provenance:
        new_meta["provenance"] = provenance
        new_meta["source_ref"] = provenance
    elif old_meta.get("provenance"):
        new_meta.setdefault("provenance", format_provenance(old_meta))

    new_id = memory_store.add_memory(
        project_id, new_content, memory_type, importance_score, new_meta
    )

    old_meta["status"] = "superseded"
    old_meta["superseded_by"] = new_id
    memory_store.update_memory(old_memory_id, metadata=old_meta)

    return new_id
