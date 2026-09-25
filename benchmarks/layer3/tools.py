"""
Canonical Layer-3 tool set. Both conditions receive identical tools.
OverHaust does NOT lose repository tools; baseline does NOT get OverHaust context.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from benchmarks.layer3.prompts import stable_json_hash

# OpenAI-compatible function schemas (canonical order matters for hashing).
CANONICAL_TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories under a relative path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path (default '.')"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full contents of a repository file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_text",
            "description": "Substring search across source files; returns path/line/text hits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_hits": {"type": "integer", "default": 20},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_repo",
            "description": "Repository-wide search alias for search_text (same behaviour).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_hits": {"type": "integer", "default": 20},
                },
                "required": ["query"],
            },
        },
    },
]


def tool_set_hash(specs: Optional[List[Dict[str, Any]]] = None) -> str:
    return stable_json_hash(specs if specs is not None else CANONICAL_TOOL_SPECS)


_SOURCE_SUFFIXES = {".ts", ".tsx", ".dart", ".py", ".js", ".md", ".json", ".yaml", ".yml"}


class RepoToolExecutor:
    """Executes the canonical tool set against a fixed repository root."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def _safe(self, rel: str) -> Path:
        rel = (rel or ".").replace("\\", "/").lstrip("/")
        if ".." in rel.split("/"):
            raise ValueError("path escape rejected")
        full = (self.root / rel).resolve()
        full.relative_to(self.root)
        return full

    def list_dir(self, path: str = ".") -> str:
        p = self._safe(path) if path not in ("", ".") else self.root
        if not p.is_dir():
            return json.dumps({"error": "not a directory", "path": path})
        entries = sorted(
            e.name + ("/" if e.is_dir() else "") for e in p.iterdir()
        )
        return json.dumps({"path": path or ".", "entries": entries})

    def read_file(self, path: str) -> str:
        text = self._safe(path).read_text(encoding="utf-8", errors="replace")
        return text

    def search_text(self, query: str, max_hits: int = 20) -> str:
        q = (query or "").strip()
        if not q:
            return json.dumps({"hits": []})
        hits: List[Dict[str, Any]] = []
        q_lower = q.lower()
        for path in self.root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _SOURCE_SUFFIXES:
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            rel = str(path.relative_to(self.root)).replace("\\", "/")
            for i, line in enumerate(lines, 1):
                if q_lower in line.lower():
                    hits.append({"path": rel, "line": i, "text": line.strip()[:200]})
                    if len(hits) >= max_hits:
                        return json.dumps({"hits": hits})
        return json.dumps({"hits": hits})

    def dispatch(self, name: str, arguments: Dict[str, Any]) -> str:
        if name == "list_dir":
            return self.list_dir(arguments.get("path", "."))
        if name == "read_file":
            return self.read_file(arguments["path"])
        if name in {"search_text", "search_repo"}:
            return self.search_text(
                arguments.get("query", ""),
                int(arguments.get("max_hits", 20)),
            )
        return json.dumps({"error": f"unknown tool {name}"})
