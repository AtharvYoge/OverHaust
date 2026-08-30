"""Tests for deterministic code-flow retrieval."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from packages.memory.memory_store import MemoryStore
from services.ingestion.index_store import ProjectIndexStore
from packages.retrieval.code_flow import (
    build_index_lookups,
    is_allowed_reason,
    resolve_import,
    scored_hit_to_flow_step,
    trace_code_flow,
)
from packages.context.relevance import ScoredMemory
from packages.retrieval.index_ranking import is_generic_symbol
from packages.context.retrieval import trace_code_flow as unified_trace
from packages.retrieval.test_fixtures import (
    make_dart_flow_tree,
    make_kot_flow_tree,
    make_labkot_retrieval_tree,
)


def _setup_flow_index(db_path: str, *, full: bool = False):
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    if full:
        make_labkot_retrieval_tree(root)
        project_id = "labkot-rank-flow"
    else:
        make_kot_flow_tree(root)
        project_id = "labkot-flow"
    store = MemoryStore(db_path)
    store.add_project(project_id, "LabKOT Flow", "", str(root))
    idx_store = ProjectIndexStore(store)
    index, _ = idx_store.sync_project(project_id, str(root))
    return store, index, str(root), project_id, tmp


def _setup_dart_flow_index(db_path: str):
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    make_dart_flow_tree(root)
    project_id = "dart-flow"
    store = MemoryStore(db_path)
    store.add_project(project_id, "Dart Flow", "", str(root))
    idx_store = ProjectIndexStore(store)
    index, _ = idx_store.sync_project(project_id, str(root))
    return store, index, str(root), project_id, tmp


def _edge_types(result):
    return [s.edge_type for s in result.steps]


def _has_typed_edge(result, edge_type: str) -> bool:
    return any(s.edge_type == edge_type for s in result.steps)


def _first_seed_symbol(result):
    if not result.steps:
        return ""
    return result.steps[0].symbol

    if not result.steps:
        return ""
    return result.steps[0].symbol


def test_import_resolver_relative():
    indexed = {
        "src/kitchen/notifications.ts",
        "src/kitchen/order_service.ts",
    }
    resolved = resolve_import(
        "src/kitchen/order_service.ts",
        "./notifications",
        indexed,
    )
    assert resolved == "src/kitchen/notifications.ts"


def test_resolve_import_parent_dir():
    indexed = {
        "lib/models/foo.dart",
        "lib/services/example.dart",
    }
    resolved = resolve_import(
        "lib/services/example.dart",
        "../models/foo.dart",
        indexed,
    )
    assert resolved == "lib/models/foo.dart"


def test_resolve_import_bare_relative_dart():
    indexed = {
        "lib/services/example.dart",
        "lib/services/order_service.dart",
    }
    resolved = resolve_import(
        "lib/services/example.dart",
        "order_service.dart",
        indexed,
    )
    assert resolved == "lib/services/order_service.dart"


def test_trace_relevance_matches_search_scale():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        _, index, _, pid, tmp = _setup_flow_index(db)
        file_record = next(
            f for f in index.files
            if f.path == "src/kitchen/kot_generator.ts"
        )
        symbol = next(s for s in file_record.symbols if s.name == "generateKOT")
        memory = {
            "id": "hybrid-seed",
            "project_id": pid,
            "content": "generateKOT",
            "metadata": {
                "record_type": "indexed_symbol",
                "file_path": file_record.path,
                "symbol_name": symbol.name,
            },
        }
        scored = ScoredMemory(
            memory=memory,
            score=0.8058,
            reasons=["hybrid result"],
            retrieval_methods=["index_keyword", "index_hybrid"],
        )

        step = scored_hit_to_flow_step(scored, "KOT generated", pid, index)

        assert step is not None
        assert step.relevance_score == pytest.approx(0.8058)
        assert step.relevance_score != pytest.approx(0.8058 / 8.0)
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_flow_finds_kot_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, root, pid, tmp = _setup_flow_index(db, full=True)
        result = trace_code_flow(
            pid,
            "Where is the KOT generated?",
            index,
            memory_store=store,
            root_path=root,
        )
        symbols = [s.symbol for s in result.steps]
        assert "generateKOT" in symbols
        assert not is_generic_symbol(_first_seed_symbol(result), result.steps[0].file)
        assert not result.insufficient_evidence
        assert all(is_allowed_reason(s.reason) for s in result.steps)
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_origin_generation_summary_excludes_callers():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, root, pid, tmp = _setup_flow_index(db)
        result = trace_code_flow(
            pid,
            "Where is the KOT generated?",
            index,
            memory_store=store,
            root_path=root,
            max_steps=6,
        )
        assert result.flow_intent == "origin_generation"
        assert "generateKOT" in result.summary
        assert "createOrder" not in result.summary
        assert result.summary == "generateKOT"
        assert not any(
            s.edge_type in ("caller", "same_file_caller") for s in result.process_steps
        )
        assert all(s.direction in ("", "forward") for s in result.process_steps[1:])
        assert not any(
            s.edge_type in ("caller", "same_file_caller") for s in result.steps
        )
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_trace_does_not_abstain_on_good_seed():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, root, pid, tmp = _setup_flow_index(db, full=True)
        result = trace_code_flow(
            pid,
            "How does a food order reach the kitchen?",
            index,
            memory_store=store,
            root_path=root,
            max_steps=6,
        )
        symbols = [s.symbol for s in result.steps]
        files = [s.file for s in result.steps]
        assert "createOrder" in symbols or any("order_service" in f for f in files)
        assert any(sym in symbols for sym in ("generateKOT", "notifyKitchen"))
        assert not any("marketing" in f for f in files)
        assert not is_generic_symbol(_first_seed_symbol(result), result.steps[0].file)
        assert result.insufficient_evidence is False
        assert result.steps[0].relevance_score >= 0.15
        assert len(result.steps) > 1
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_trace_walks_multiple_steps():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, root, pid, tmp = _setup_flow_index(db, full=True)
        result = trace_code_flow(
            pid,
            "How does a food order reach the kitchen?",
            index,
            memory_store=store,
            root_path=root,
            max_steps=6,
        )
        assert len(result.steps) > 1
        assert _has_typed_edge(result, "import") or _has_typed_edge(result, "direct_call") or _has_typed_edge(result, "constructor")
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_flow_after_order_placed():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, root, pid, tmp = _setup_flow_index(db, full=True)
        result = trace_code_flow(
            pid,
            "What happens after an order is placed?",
            index,
            memory_store=store,
            root_path=root,
            max_steps=6,
        )
        symbols = [s.symbol for s in result.steps]
        assert any(
            s in symbols for s in ("handleOrderPlaced", "createOrder")
        )
        assert not is_generic_symbol(_first_seed_symbol(result), result.steps[0].file)
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_flow_quikot_hardware():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, root, pid, tmp = _setup_flow_index(db, full=True)
        result = trace_code_flow(
            pid,
            "How does the app communicate with QuiKOT hardware?",
            index,
            memory_store=store,
            root_path=root,
            max_steps=6,
        )
        symbols = [s.symbol for s in result.steps]
        files = [s.file for s in result.steps]
        assert any(
            "connectQuikotHardware" in s or "quikot" in f.lower()
            for s, f in zip(symbols + [""], files)
        )
        assert not is_generic_symbol(_first_seed_symbol(result), result.steps[0].file)
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_flow_stops_on_weak_evidence():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, root, pid, tmp = _setup_flow_index(db)
        result = trace_code_flow(
            pid,
            "xyzzy plugh completely unrelated nonsense query",
            index,
            memory_store=store,
            root_path=root,
        )
        assert result.insufficient_evidence or len(result.steps) <= 1
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_flow_no_invented_edges():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, root, pid, tmp = _setup_flow_index(db)
        result = trace_code_flow(
            pid,
            "order kitchen KOT flow",
            index,
            memory_store=store,
            root_path=root,
            max_steps=6,
        )
        for step in result.steps:
            assert is_allowed_reason(step.reason) or step.edge_type, step.reason
            assert step.file
            assert 0.0 <= step.relevance_score <= 1.0
            assert 0.0 <= step.trust_score <= 1.0
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_unified_trace_wrapper():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, _, _, pid, tmp = _setup_flow_index(db)
        payload = unified_trace(
            pid,
            "Where is the KOT generated?",
            memory_store=store,
        )
        assert payload["project_id"] == pid
        assert payload["summary"]
        assert payload["steps"]
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_build_index_lookups_exports():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        _, index, _, _, tmp = _setup_flow_index(db)
        lookups = build_index_lookups(index)
        assert "generateKOT" in lookups["exports_by_name"]
        assert lookups["files_by_path"]["src/kitchen/kot_generator.ts"]
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_dart_flow_excludes_build():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, root, pid, tmp = _setup_dart_flow_index(db)
        result = trace_code_flow(
            pid,
            "How does a food order reach the kitchen?",
            index,
            memory_store=store,
            root_path=root,
            max_steps=6,
        )
        symbols = [s.symbol for s in result.steps]
        assert "build" not in symbols
        assert result.steps[0].file.startswith("lib/services/")
        assert _has_typed_edge(result, "direct_call") or _has_typed_edge(result, "constructor")
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_dart_kot_flow_extends_from_build_kot_text():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, root, pid, tmp = _setup_dart_flow_index(db)
        result = trace_code_flow(
            pid,
            "Where is the KOT generated?",
            index,
            memory_store=store,
            root_path=root,
            max_steps=6,
        )
        symbols = [s.symbol for s in result.steps]
        assert "buildKotText" in symbols
        assert "buildText" in symbols
        process_rest = result.process_steps[1:]
        assert process_rest, "origin query should continue downstream from the generator"
        assert all(s.direction == "forward" for s in process_rest)
        assert not any(
            s.edge_type in ("caller", "same_file_caller") for s in process_rest
        )
        assert result.steps[0].edge_type == "query_match"
        assert all(s.edge_type for s in result.steps)
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_dart_quikot_service_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, root, pid, tmp = _setup_dart_flow_index(db)
        result = trace_code_flow(
            pid,
            "How does the app communicate with QuiKOT hardware?",
            index,
            memory_store=store,
            root_path=root,
            max_steps=6,
        )
        symbols = [s.symbol for s in result.steps]
        files = [s.file for s in result.steps]
        assert any(
            "deliver" in s or "QuikotDeviceManagementService" in s or "send" in s
            for s in symbols
        ) or any("hardware" in f and "service" in f for f in files)
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_dart_flow_typed_evidence_fields():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, root, pid, tmp = _setup_dart_flow_index(db)
        result = trace_code_flow(
            pid,
            "order kitchen flow",
            index,
            memory_store=store,
            root_path=root,
            max_steps=4,
        )
        for step in result.steps:
            assert step.edge_type
            assert step.evidence or step.edge_type == "query_match"
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
