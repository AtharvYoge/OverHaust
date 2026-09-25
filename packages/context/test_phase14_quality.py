"""Phase 14 regression tests for task quality assessment."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from packages.memory.memory_store import MemoryStore
from packages.retrieval.test_fixtures import make_dart_flow_tree
from scripts.assess_task_quality import run_assessment


@pytest.fixture
def temp_store():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    store = MemoryStore(tmp.name)
    yield store
    if os.path.exists(tmp.name):
        os.unlink(tmp.name)


def _index_fixture(store, project_id="phase14-p"):
    tmpdir = tempfile.mkdtemp()
    root = Path(tmpdir)
    make_dart_flow_tree(root)
    store.add_project(project_id, "Phase14", "", str(root))
    from services.ingestion.index_store import ProjectIndexStore

    ProjectIndexStore(store).sync_project(project_id, str(root))
    return tmpdir, project_id


def test_task_quality_overhaust_viable(temp_store):
    tmpdir, pid = _index_fixture(temp_store)
    try:
        report = run_assessment(
            pid,
            "Add support for multiple kitchen printers",
            memory_store=temp_store,
        )
        oh = report["overhaust"]
        paths = " ".join(oh["paths"]).lower()
        symbols = " ".join(oh["symbols"]).lower()
        assert "kitchen" in paths or "kitchen" in symbols or "print" in paths
        assert oh["composite_quality_score_pct"] >= 50
        assert report["token_reduction_pct"] is not None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
