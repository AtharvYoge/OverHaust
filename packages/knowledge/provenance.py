"""
Human-readable provenance formatting for knowledge sources.
"""

from typing import Any, Dict

from packages.knowledge.schema import normalize_metadata


def format_provenance(meta: Dict[str, Any]) -> str:
    """
    Return a concise provenance string for users (no internal DB details).

    Examples:
      - Conversation abc123, Message #4
      - src/auth/AuthService.ts
      - src/ws/manager.ts (ConnectionManager)
      - User-provided knowledge
    """
    m = normalize_metadata(meta)
    existing = m.get("provenance")
    if existing and not existing.startswith("Conversation ") and m.get("source_type") != "conversation":
        # Prefer explicit non-conversation provenance when set
        if m.get("source_type") in ("file", "symbol", "user"):
            pass
        elif len(str(existing)) > 3:
            return str(existing)

    source_type = m.get("source_type", "memory")
    source_ref = m.get("source_ref") or m.get("source_id") or ""

    if source_type == "conversation":
        conv_id = m.get("source_id") or source_ref
        msg_idx = m.get("message_index")
        if msg_idx is not None and conv_id:
            return f"Conversation {conv_id}, Message #{msg_idx}"
        if conv_id:
            return f"Conversation {conv_id}"
        if existing:
            return str(existing)
        return "Unknown source"

    if source_type == "file":
        path = source_ref or existing or "Unknown file"
        return str(path)

    if source_type == "symbol":
        path = m.get("file_path") or source_ref or "Unknown file"
        symbol = m.get("symbol_name") or m.get("symbol")
        if symbol:
            return f"{path} ({symbol})"
        return str(path)

    if source_type == "user":
        return "User-provided knowledge"

    if existing:
        return str(existing)
    if source_ref:
        return str(source_ref)
    return "Unknown source"
