"""Tests for intent-aware index ranking and retrieval quality."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from packages.memory.memory_store import MemoryStore
from services.ingestion.index_store import ProjectIndexStore
from packages.retrieval.index_retrieval import search_index_keyword, search_index_records
from packages.retrieval.index_ranking import (
    detect_query_intent,
    is_generic_symbol,
    hybrid_weights_for_query,
)
from packages.retrieval.test_fixtures import make_labkot_retrieval_tree


def _top_symbol_or_path(hits):
    if not hits:
        return "", ""
    meta = hits[0].memory.get("metadata") or {}
    return meta.get("symbol_name") or "", meta.get("file_path") or ""


def _setup_retrieval_index(db_path: str):
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    make_labkot_retrieval_tree(root)
    store = MemoryStore(db_path)
    store.add_project("labkot-rank", "LabKOT Rank", "", str(root))
    idx_store = ProjectIndexStore(store)
    index, _ = idx_store.sync_project("labkot-rank", str(root))
    return store, index, str(root), tmp


def _hit_labels(hits):
    labels = []
    for h in hits:
        meta = h.memory.get("metadata") or {}
        sym = meta.get("symbol_name") or ""
        path = meta.get("file_path") or ""
        labels.append(sym or path)
    return labels


def test_generic_symbol_penalty_unit():
    assert is_generic_symbol("copyWith", "lib/theme/app_theme.dart")
    assert is_generic_symbol("registerWith", "lib/generated/plugin_registrant.dart")
    assert is_generic_symbol("AppThemeMode", "lib/theme/app_theme.dart")
    assert is_generic_symbol("GeneratedPluginRegistrant", "lib/generated/plugin_registrant.dart")
    assert not is_generic_symbol("generateKOT", "src/kitchen/kot_generator.ts")


def test_detect_flow_intent():
    intent = detect_query_intent("How does a food order reach the kitchen?")
    assert intent.flow is True
    assert "order" in intent.domain_terms or "food" in intent.domain_terms


def test_kot_query_prefers_generator():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        _, index, _, tmp = _setup_retrieval_index(db)
        hits = search_index_keyword("labkot-rank", "Where is the KOT generated?", index, limit=8)
        labels = _hit_labels(hits)
        assert labels
        assert not any("copyWith" in l or "registerWith" in l for l in labels[:3])
        top_sym, top_path = _top_symbol_or_path(hits)
        assert "generateKOT" in top_sym or "kot_generator" in top_path
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_order_flow_to_kitchen():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        _, index, _, tmp = _setup_retrieval_index(db)
        hits = search_index_keyword(
            "labkot-rank",
            "How does a food order reach the kitchen?",
            index,
            limit=8,
        )
        labels = _hit_labels(hits)
        assert not any("marketing" in l or "app_theme" in l for l in labels[:3])
        assert any(
            "createOrder" in l or "notifyKitchen" in l or "kitchen" in l
            for l in labels[:4]
        )
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_after_order_placed():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        _, index, _, tmp = _setup_retrieval_index(db)
        hits = search_index_keyword(
            "labkot-rank",
            "What happens after an order is placed?",
            index,
            limit=8,
        )
        labels = _hit_labels(hits)
        assert not any("copyWith" in l or "registerWith" in l for l in labels[:3])
        assert any(
            "handleOrderPlaced" in l or "createOrder" in l or "order_service" in l
            for l in labels[:4]
        )
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_quikot_hardware():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        _, index, _, tmp = _setup_retrieval_index(db)
        hits = search_index_keyword(
            "labkot-rank",
            "How does the app communicate with QuiKOT hardware?",
            index,
            limit=8,
        )
        labels = _hit_labels(hits)
        assert not any(
            "AppThemeMode" in l or "registerWith" in l or "copyWith" in l
            for l in labels[:3]
        )
        assert any(
            "connectQuikotHardware" in l or "quikot" in l.lower()
            for l in labels[:4]
        )
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_weak_keyword_uses_semantic_weights():
    intent = detect_query_intent("How does ticket printing work in the kitchen area?")
    assert intent.flow
    w = hybrid_weights_for_query("How does ticket printing work?", [])
    assert w["semantic"] > w["keyword"]


@pytest.mark.embeddings
def test_weak_keyword_semantic_boost():
    os.environ["OVERHAUST_EMBEDDINGS"] = "1"
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, _, tmp = _setup_retrieval_index(db)
        from packages.retrieval.embeddings import reset_embedding_provider
        reset_embedding_provider()
        hits = search_index_records(
            "labkot-rank",
            "ticket printing workflow for kitchen orders",
            index,
            limit=5,
            memory_store=store,
        )
        labels = _hit_labels(hits)
        assert labels
        assert not any("registerWith" in l or "copyWith" in l for l in labels[:2])
    finally:
        os.environ.pop("OVERHAUST_EMBEDDINGS", None)
        from packages.retrieval.embeddings import reset_embedding_provider
        reset_embedding_provider()
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
