"""
Best-effort read of the Cursor local session store.

Headless runs keep request blobs, including the system prompt and hook
context, in `~/.cursor/chats/<hash>/<session>/store.db` plus `meta.json`.
The layout is not a documented schema. When the SQLite file can be opened
and scanned, injection verification uses it. When it cannot, verification
stays hook-log-only and is recorded that way.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from benchmarks.layer4.cursor_parse import OVERHAUST_MCP_TOOL_NAMES
from packages.integrations.interception import CONTEXT_MARKER


@dataclass
class StoreInspection:
    parseable: bool
    verification: str
    marker_present: Optional[bool] = None
    overhaust_tools: List[str] = field(default_factory=list)
    store_path: Optional[str] = None
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "parseable": self.parseable,
            "verification": self.verification,
            "marker_present": self.marker_present,
            "overhaust_tools": list(self.overhaust_tools),
            "store_path": self.store_path,
            "detail": self.detail,
        }


def _candidate_dirs(homes: Sequence[Path]) -> List[Path]:
    found: List[Path] = []
    for home in homes:
        if home is None:
            continue
        for relative in (
            Path(".cursor") / "chats",
            Path("chats"),
        ):
            root = home / relative
            if root.is_dir():
                found.append(root)
    return found


def _session_dirs(chats_root: Path, session_id: str) -> List[Path]:
    matches: List[Path] = []
    if not session_id:
        return matches
    try:
        children = list(chats_root.iterdir())
    except OSError:
        return matches
    for child in children:
        if not child.is_dir():
            continue
        direct = child / session_id
        if direct.is_dir():
            matches.append(direct)
        elif child.name == session_id:
            matches.append(child)
    return matches


def _read_sqlite_text(path: Path) -> str:
    uri = path.resolve().as_posix().replace("?", "%3F")
    connection = sqlite3.connect(f"file:{uri}?mode=ro", uri=True)
    try:
        try:
            connection.execute("PRAGMA query_only=ON")
        except sqlite3.Error:
            pass
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        chunks: List[str] = []
        for (name,) in tables:
            if not isinstance(name, str) or not name:
                continue
            quoted = '"' + name.replace('"', '""') + '"'
            try:
                rows = connection.execute(f"SELECT * FROM {quoted}").fetchall()
            except sqlite3.Error:
                continue
            for row in rows:
                for cell in row:
                    if isinstance(cell, str):
                        chunks.append(cell)
                    elif isinstance(cell, bytes):
                        chunks.append(cell.decode("utf-8", errors="replace"))
        if not tables:
            raise sqlite3.DatabaseError("no tables")
        return "\n".join(chunks)
    finally:
        connection.close()


def overhaust_tools_in_text(text: str) -> List[str]:
    """Tool-catalog hits only. A prose mention of a name is not enough."""
    found: List[str] = []
    if re.search(r'"(?:server|serverName|providerIdentifier)"\s*:\s*"overhaust"', text, re.I):
        found.append("server:overhaust")
    for name in sorted(OVERHAUST_MCP_TOOL_NAMES):
        pattern = rf'"(?:name|toolName|tool)"\s*:\s*"{re.escape(name)}"'
        if re.search(pattern, text):
            found.append(name)
    return found


def inspect_session_store(homes: Sequence[Path], session_id: Optional[str]) -> StoreInspection:
    """
    Scan chat stores for one Cursor session id.

    `verification` is `store+hook` when a store.db was read, otherwise
    `hook-log-only`.
    """
    if not session_id:
        return StoreInspection(
            parseable=False,
            verification="hook-log-only",
            detail="No Cursor session_id was parsed from stream-json, so the local store was not opened.",
        )
    candidates: List[Path] = []
    for chats_root in _candidate_dirs(homes):
        candidates.extend(_session_dirs(chats_root, session_id))
    if not candidates:
        return StoreInspection(
            parseable=False,
            verification="hook-log-only",
            detail=(
                f"No ~/.cursor/chats/*/{session_id} directory was found. "
                "Injection verification is hook-log-only."
            ),
        )
    errors: List[str] = []
    for directory in candidates:
        store = directory / "store.db"
        meta = directory / "meta.json"
        if not store.is_file():
            errors.append(f"{store} is missing")
            continue
        try:
            text = _read_sqlite_text(store)
        except sqlite3.Error as exc:
            errors.append(f"{store} is not a readable sqlite database ({exc})")
            continue
        except OSError as exc:
            errors.append(f"{store} could not be read ({exc})")
            continue
        if meta.is_file():
            try:
                text += "\n" + meta.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                errors.append(f"{meta} could not be read ({exc})")
        return StoreInspection(
            parseable=True,
            verification="store+hook",
            marker_present=CONTEXT_MARKER in text,
            overhaust_tools=overhaust_tools_in_text(text),
            store_path=str(store),
            detail="Scanned sqlite text columns and meta.json. This is not a documented Cursor schema.",
        )
    return StoreInspection(
        parseable=False,
        verification="hook-log-only",
        detail="Injection verification is hook-log-only. " + "; ".join(errors),
    )
