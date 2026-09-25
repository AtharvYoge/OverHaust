"""Tests for register/index lifecycle helpers and multi-repo ops."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from packages.memory.memory_store import MemoryStore
from packages.retrieval.index_retrieval import _stable_index_id, index_hit_to_memory
from services.ingestion.project_lifecycle import ensure_project_indexed
from services.ingestion.test_project_indexer import make_tree


def test_ensure_project_indexed_repeated_and_isolated():
    with tempfile.TemporaryDirectory() as tmp:
        root_a = Path(tmp) / "a"
        root_b = Path(tmp) / "b"
        root_a.mkdir()
        root_b.mkdir()
        make_tree(root_a)
        (root_b / "only_b.py").write_text("def only_b():\n    return True\n")
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
            db = t.name
        try:
            store = MemoryStore(db)
            first = ensure_project_indexed(
                "life-a", str(root_a), name="A", memory_store=store
            )
            second = ensure_project_indexed(
                "life-a", str(root_a), name="A", memory_store=store
            )
            other = ensure_project_indexed(
                "life-b", str(root_b), name="B", memory_store=store
            )
            assert first["mode"] == "full"
            assert second["mode"] == "unchanged"
            assert other["project_id"] == "life-b"
            assert first["health"]["ok"] is True
            assert other["resolved_project_id"] == "life-b"

            # Duplicate root with different id fails.
            try:
                ensure_project_indexed(
                    "life-c", str(root_a), name="C", memory_store=store
                )
                assert False, "expected ValueError"
            except ValueError:
                pass
        finally:
            os.unlink(db)


def test_stable_index_ids_differ_across_projects():
    class _File:
        path = "src/app.ts"
        imports = []
        symbols = []

    class _Sym:
        name = "main"
        kind = "function"
        line = 1

    a = index_hit_to_memory("proj-a", _File(), symbol=_Sym())
    b = index_hit_to_memory("proj-b", _File(), symbol=_Sym())
    assert a["id"] != b["id"]
    assert a["id"] == _stable_index_id("proj-a", "symbol", "src/app.ts", "main")
    assert b["id"] == _stable_index_id("proj-b", "symbol", "src/app.ts", "main")
