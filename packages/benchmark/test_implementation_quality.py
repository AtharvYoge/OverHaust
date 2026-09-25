"""Tests for Phase 15 implementation quality evaluation."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from packages.benchmark.implementation_quality import evaluate_repo
from packages.memory.memory_store import MemoryStore
from packages.retrieval.test_fixtures import make_dart_flow_tree
from services.ingestion.index_store import ProjectIndexStore


@pytest.fixture
def temp_store():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    store = MemoryStore(tmp.name)
    yield store
    if os.path.exists(tmp.name):
        os.unlink(tmp.name)


def test_evaluate_existing_dart_fixture(temp_store):
    tmpdir = tempfile.mkdtemp()
    root = Path(tmpdir)
    make_dart_flow_tree(root)
    store = temp_store
    store.add_project("eval-p", "Eval", "", str(root))
    ProjectIndexStore(store).sync_project("eval-p", str(root))
    try:
        report = evaluate_repo(root, agent_completed=False)
        assert "KitchenPrintService" in report.architecture_patterns
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
