"""Tests for persistent project index storage."""
import sys
import os
import tempfile
import time
from pathlib import Path

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from packages.memory.memory_store import MemoryStore
from services.ingestion.index_store import ProjectIndexStore
from services.ingestion.project_indexer import INDEX_EXTRACTOR_VERSION
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


def test_sync_records_extractor_version():
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
            _, report = idx_store.sync_project("p1", str(root))
            assert report["extractor_version"] == INDEX_EXTRACTOR_VERSION
            assert idx_store.stored_extractor_version("p1") == INDEX_EXTRACTOR_VERSION
            assert idx_store.extractor_version_is_current("p1")
        finally:
            os.unlink(db)


def test_stale_extractor_version_forces_full_reindex():
    """
    Regression: symbols extracted by an older extractor must not survive.

    Incremental sync compares file *content* hashes, so changing extraction
    rules leaves every file "unchanged" and silently preserves the old symbol
    table. This is what made a Dart private-method fix appear to have no
    effect — the index was never re-read. A fingerprint mismatch must force
    ``mode: full`` even though nothing on disk changed.
    """
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
            assert idx_store.sync_project("p1", str(root))[1]["mode"] == "unchanged"

            # Simulate an index written by different extraction rules.
            with store._connect() as conn:
                conn.execute(
                    "UPDATE project_index_meta SET extractor_version = ? "
                    "WHERE project_id = ?",
                    ("0:stalefingerprint", "p1"),
                )
                conn.commit()
            assert not idx_store.extractor_version_is_current("p1")

            index, report = idx_store.sync_project("p1", str(root))
            assert report["mode"] == "full"
            assert report["reason"] == "extractor_version_changed"
            assert index.files
            assert idx_store.extractor_version_is_current("p1")
        finally:
            os.unlink(db)


def test_missing_extractor_version_is_treated_as_stale():
    """Indexes written before fingerprinting existed must be rebuilt once."""
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
            with store._connect() as conn:
                conn.execute(
                    "UPDATE project_index_meta SET extractor_version = NULL "
                    "WHERE project_id = ?",
                    ("p1",),
                )
                conn.commit()
            assert idx_store.stored_extractor_version("p1") == ""
            _, report = idx_store.sync_project("p1", str(root))
            assert report["mode"] == "full"
            assert report["reason"] == "extractor_version_changed"
        finally:
            os.unlink(db)


def test_extractor_fingerprint_is_stable_and_rule_derived():
    """A fingerprint that changes per-process would force endless re-indexing."""
    from services.ingestion import project_indexer

    assert project_indexer._compute_extractor_fingerprint() == INDEX_EXTRACTOR_VERSION
    assert INDEX_EXTRACTOR_VERSION.startswith(
        f"{project_indexer._EXTRACTOR_REVISION}:"
    )
