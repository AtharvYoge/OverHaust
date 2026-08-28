"""Tests for persistent project index storage."""
import sys
import os
import tempfile
import time
from pathlib import Path

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from packages.memory.memory_store import MemoryStore
from services.ingestion.index_store import ProjectIndexStore
from services.ingestion.test_project_indexer import make_tree


def test_persist_and_reload_index():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "proj"
        root.mkdir()
        make_tree(root)
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
            db = t.name
        try:
            store = MemoryStore(db)
            store.add_project("p1", "Demo", "", str(root))
            idx_store = ProjectIndexStore(store)
            index, report = idx_store.sync_project("p1", str(root))
            assert report["mode"] == "full"
            assert len(index.files) >= 5

            loaded = idx_store.load_index("p1")
            assert loaded is not None
            assert len(loaded.files) == len(index.files)
            assert loaded.total_tokens == index.total_tokens
        finally:
            os.unlink(db)


def test_incremental_sync_skips_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "proj"
        root.mkdir()
        make_tree(root)
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
            db = t.name
        try:
            store = MemoryStore(db)
            store.add_project("p1", "Demo", "", str(root))
            idx_store = ProjectIndexStore(store)
            idx_store.sync_project("p1", str(root))
            _, report = idx_store.sync_project("p1", str(root))
            assert report["mode"] == "unchanged"
        finally:
            os.unlink(db)


def test_incremental_detects_modified_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "proj"
        root.mkdir()
        make_tree(root)
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as t:
            db = t.name
        try:
            store = MemoryStore(db)
            store.add_project("p1", "Demo", "", str(root))
            idx_store = ProjectIndexStore(store)
            idx_store.sync_project("p1", str(root))
            time.sleep(0.05)
            (root / "src" / "app.ts").write_text(
                (root / "src" / "app.ts").read_text() + "\nexport function patched() {}\n"
            )
            _, report = idx_store.sync_project("p1", str(root))
            assert report["mode"] == "incremental"
            assert "src/app.ts" in report["modified"]
        finally:
            os.unlink(db)
