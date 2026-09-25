"""Deterministic context quality tests for agent validation."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from packages.context.agent_context import (
    assemble_agent_context,
    invoke_context_request,
    resolve_project_id,
)
from packages.context.benchmark import run_agent_benchmark
from packages.memory.memory_store import MemoryStore
from packages.retrieval.test_index_retrieval import make_kot_tree
from packages.shared.config import (
    get_context_max_evidence,
    get_context_max_files,
    get_context_max_symbols,
)


@pytest.fixture
def temp_store():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    store = MemoryStore(tmp.name)
    yield store
    if os.path.exists(tmp.name):
        os.unlink(tmp.name)


def _index_fixture(store, project_id="quality-p"):
    tmpdir = tempfile.mkdtemp()
    root = Path(tmpdir)
    make_kot_tree(root)
    store.add_project(project_id, "Quality", "", str(root))
    from services.ingestion.index_store import ProjectIndexStore

    ProjectIndexStore(store).sync_project(project_id, str(root))
    return tmpdir, project_id


def test_implementation_context_includes_relevant_symbols(temp_store):
    tmpdir, pid = _index_fixture(temp_store)
    try:
        result = assemble_agent_context(
            pid,
            "Add support for multiple kitchen printers",
            memory_store=temp_store,
        )
        paths = " ".join(f["path"] for f in result.relevant_files).lower()
        symbols = " ".join(s["name"] for s in result.relevant_symbols).lower()
        combined = paths + " " + symbols
        assert "kot" in combined or "kitchen" in combined or "print" in combined
        assert not result.insufficient_evidence
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_implementation_prefers_lib_over_test(temp_store):
    tmpdir, pid = _index_fixture(temp_store)
    try:
        result = assemble_agent_context(
            pid,
            "Add support for multiple kitchen printers",
            memory_store=temp_store,
        )
        if result.relevant_files:
            first = result.relevant_files[0]["path"]
            assert not first.startswith("test/")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_irrelevant_prompt_abstains(temp_store):
    tmpdir, pid = _index_fixture(temp_store)
    try:
        result = assemble_agent_context(
            pid,
            "How does Stripe billing webhook integration work?",
            memory_store=temp_store,
        )
        assert result.insufficient_evidence
        assert result.relevant_files == []
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_context_remains_bounded(temp_store):
    tmpdir, pid = _index_fixture(temp_store)
    try:
        result = invoke_context_request(
            pid,
            "Where is the KOT generated?",
            memory_store=temp_store,
            max_files=20,
            max_symbols=30,
        )
        assert len(result.relevant_files) <= get_context_max_files()
        assert len(result.relevant_symbols) <= get_context_max_symbols()
        assert len(result.evidence) <= get_context_max_evidence()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_selective_flow_implementation_vs_process(temp_store):
    tmpdir, pid = _index_fixture(temp_store)
    try:
        impl = assemble_agent_context(
            pid,
            "Add support for multiple kitchen printers",
            memory_store=temp_store,
        )
        assert impl.metrics.code_flow_included is False

        flow = assemble_agent_context(
            pid,
            "Where does a food order reach the kitchen?",
            memory_store=temp_store,
        )
        assert flow.metrics.code_flow_included is True
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_project_resolution(temp_store):
    tmpdir, pid = _index_fixture(temp_store)
    try:
        root = temp_store.get_project(pid)["root_path"]
        assert resolve_project_id(root, memory_store=temp_store) == pid
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_fair_benchmark_reports_reduction(temp_store):
    tmpdir, pid = _index_fixture(temp_store)
    try:
        report = run_agent_benchmark(
            pid,
            "Where is the KOT generated?",
            memory_store=temp_store,
            search_limit=5,
        )
        assert "baseline_fair" in report
        assert "overhaust" in report
        assert report["fair_reduction"]["tokens_vs_naive_full_files_pct"] is not None
        assert report["baseline_fair"]["files_read"] >= 1
        assert report["overhaust"]["files_read"] >= 1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
