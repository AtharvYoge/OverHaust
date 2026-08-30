"""Tests for service-layer code-flow seed ranking."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from packages.memory.memory_store import MemoryStore
from services.ingestion.index_store import ProjectIndexStore
from packages.context.relevance import ScoredMemory
from packages.retrieval.code_flow import collect_seed_hits, trace_code_flow
from packages.context.retrieval import apply_trust
from packages.retrieval.index_retrieval import search_index_records
from packages.retrieval.index_ranking import (
    classify_code_layer,
    flow_seed_score,
    rank_flow_seed_candidates,
)
from packages.retrieval.test_fixtures import make_dart_flow_tree


def _hit(symbol_name: str, file_path: str, score: float, kind: str = "function") -> ScoredMemory:
    return ScoredMemory(
        memory={
            "metadata": {
                "record_type": "indexed_symbol",
                "symbol_name": symbol_name,
                "symbol_kind": kind,
                "file_path": file_path,
            }
        },
        score=score,
        reasons=[],
        retrieval_methods=["index_hybrid"],
    )


def _setup_dart_flow(db_path: str):
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    make_dart_flow_tree(root)
    store = MemoryStore(db_path)
    store.add_project("dart-seed", "Dart Seed", "", str(root))
    idx_store = ProjectIndexStore(store)
    index, _ = idx_store.sync_project("dart-seed", str(root))
    return store, index, str(root), tmp


def test_classify_code_layer_paths():
    assert classify_code_layer("lib/services/order_service.dart", "addOrder", "function") == "service"
    assert classify_code_layer("lib/widgets/kitchen/kitchen_order_card.dart", "KitchenOrderCard", "class") == "ui"
    assert classify_code_layer("lib/models/order_status.dart", "OrderStatus", "enum") == "model"
    assert classify_code_layer(
        "lib/services/printing/adapters/usb/platform_usb_printer_port.dart",
        "channel:labkot/usb_printer",
        "platform_channel",
    ) == "transport"


def test_flow_seed_prefers_service_over_widget():
    widget = ScoredMemory(
        memory={
            "metadata": {
                "record_type": "indexed_symbol",
                "symbol_name": "KitchenOrderCard",
                "symbol_kind": "class",
                "file_path": "lib/widgets/kitchen/kitchen_order_card.dart",
            }
        },
        score=0.82,
        reasons=[],
        retrieval_methods=["index_hybrid"],
    )
    service = ScoredMemory(
        memory={
            "metadata": {
                "record_type": "indexed_symbol",
                "symbol_name": "addOrder",
                "symbol_kind": "function",
                "file_path": "lib/services/order_service.dart",
            }
        },
        score=0.58,
        reasons=[],
        retrieval_methods=["index_hybrid"],
    )
    ranked = rank_flow_seed_candidates(
        "How does a food order reach the kitchen?",
        [widget, service],
    )
    assert ranked[0].memory["metadata"]["symbol_name"] == "addOrder"
    assert flow_seed_score(
        "How does a food order reach the kitchen?", service
    ) > flow_seed_score("How does a food order reach the kitchen?", widget)


def test_flow_seed_prefers_deliver_over_mark_food_delivered():
    deliver = _hit(
        "deliver",
        "lib/services/hardware/quikot_device_management_service.dart",
        0.85,
    )
    mark_delivered = _hit(
        "markFoodDelivered",
        "lib/services/order_service.dart",
        0.95,
    )
    ranked = rank_flow_seed_candidates(
        "What service delivers data to QuiKOT?",
        [mark_delivered, deliver],
    )
    assert ranked[0].memory["metadata"]["symbol_name"] == "deliver"


def test_flow_seed_prefers_public_deliver_over_private_deliver_helper():
    deliver = _hit(
        "deliver",
        "lib/services/hardware/quikot_device_management_service.dart",
        0.80,
    )
    private_helper = _hit(
        "_deliverPaidReceipt",
        "lib/services/order_service.dart",
        0.92,
    )
    ranked = rank_flow_seed_candidates(
        "What service delivers data to QuiKOT?",
        [private_helper, deliver],
    )
    assert ranked[0].memory["metadata"]["symbol_name"] == "deliver"
    assert flow_seed_score(
        "What service delivers data to QuiKOT?", deliver
    ) > flow_seed_score("What service delivers data to QuiKOT?", private_helper)


def test_flow_seed_prefers_add_order_over_create_order_interface():
    create_iface = _hit(
        "createOrder",
        "lib/services/order/order_backend.dart",
        0.94,
        kind="function",
    )
    add_order = _hit(
        "addOrder",
        "lib/services/order_service.dart",
        0.94,
    )
    ranked = rank_flow_seed_candidates(
        "How is a food order added and sent to the kitchen?",
        [create_iface, add_order],
    )
    assert ranked[0].memory["metadata"]["symbol_name"] == "addOrder"


def test_flow_seed_prefers_state_handler_for_marked_delivered_query():
    deliver = _hit(
        "deliver",
        "lib/services/hardware/quikot_device_management_service.dart",
        0.90,
    )
    mark_delivered = _hit(
        "markFoodDelivered",
        "lib/services/order_service.dart",
        0.88,
    )
    private_mark = _hit(
        "_markFoodDeliveredInternal",
        "lib/services/order_service.dart",
        0.82,
    )
    ranked = rank_flow_seed_candidates(
        "What happens when food is marked delivered?",
        [deliver, mark_delivered, private_mark],
    )
    assert ranked[0].memory["metadata"]["symbol_name"] == "markFoodDelivered"


def test_flow_seed_private_helper_can_win_for_state_change_query():
    private_ready = _hit(
        "_markReadyInternal",
        "lib/services/kitchen/kitchen_queue_service.dart",
        0.93,
    )
    add_order = _hit(
        "addOrder",
        "lib/services/order_service.dart",
        0.90,
    )
    ranked = rank_flow_seed_candidates(
        "What happens when a kitchen order is marked ready?",
        [add_order, private_ready],
    )
    assert ranked[0].memory["metadata"]["symbol_name"] == "_markReadyInternal"


def test_flow_seed_prefers_add_order_over_update_kitchen_status():
    update = ScoredMemory(
        memory={
            "metadata": {
                "record_type": "indexed_symbol",
                "symbol_name": "updateKitchenStatus",
                "symbol_kind": "function",
                "file_path": "lib/services/order_service.dart",
            }
        },
        score=0.95,
        reasons=[],
        retrieval_methods=["index_hybrid"],
    )
    add_order = ScoredMemory(
        memory={
            "metadata": {
                "record_type": "indexed_symbol",
                "symbol_name": "addOrder",
                "symbol_kind": "function",
                "file_path": "lib/services/order_service.dart",
            }
        },
        score=0.91,
        reasons=[],
        retrieval_methods=["index_hybrid"],
    )
    ranked = rank_flow_seed_candidates(
        "How does a food order reach the kitchen?",
        [update, add_order],
    )
    assert ranked[0].memory["metadata"]["symbol_name"] == "addOrder"


def test_flow_seed_weak_service_does_not_beat_strong_irrelevant():
    widget = ScoredMemory(
        memory={
            "metadata": {
                "record_type": "indexed_symbol",
                "symbol_name": "KitchenOrderCard",
                "symbol_kind": "class",
                "file_path": "lib/widgets/kitchen/kitchen_order_card.dart",
            }
        },
        score=0.95,
        reasons=[],
        retrieval_methods=["index_hybrid"],
    )
    weak_service = ScoredMemory(
        memory={
            "metadata": {
                "record_type": "indexed_symbol",
                "symbol_name": "loadConfig",
                "symbol_kind": "function",
                "file_path": "lib/services/config_loader.dart",
            }
        },
        score=0.05,
        reasons=[],
        retrieval_methods=["index_keyword"],
    )
    ranked = rank_flow_seed_candidates("How does a food order reach the kitchen?", [widget, weak_service])
    assert ranked[0].memory["metadata"]["symbol_name"] == "KitchenOrderCard"


def test_flow_seed_prefers_ready_handler_for_marked_ready_query():
    add_order = ScoredMemory(
        memory={
            "metadata": {
                "record_type": "indexed_symbol",
                "symbol_name": "addOrder",
                "symbol_kind": "function",
                "file_path": "lib/services/order_service.dart",
            }
        },
        score=0.91,
        reasons=[],
        retrieval_methods=["index_hybrid"],
    )
    ready_queue = ScoredMemory(
        memory={
            "metadata": {
                "record_type": "indexed_symbol",
                "symbol_name": "readyQueueForWaiter",
                "symbol_kind": "function",
                "file_path": "lib/services/kitchen/kitchen_queue_service.dart",
            }
        },
        score=0.88,
        reasons=[],
        retrieval_methods=["index_hybrid"],
    )
    ranked = rank_flow_seed_candidates(
        "What happens when a kitchen order is marked ready?",
        [add_order, ready_queue],
    )
    assert ranked[0].memory["metadata"]["symbol_name"] == "readyQueueForWaiter"


def test_dart_fixture_seed_order_to_kitchen():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, root, tmp = _setup_dart_flow(db)
        query = "How does a food order reach the kitchen?"
        raw = search_index_records("dart-seed", query, index, limit=12, memory_store=store)
        trusted = apply_trust(raw, query)
        seeds = collect_seed_hits(trusted, query)
        assert seeds
        top_sym = seeds[0].memory["metadata"]["symbol_name"]
        top_path = seeds[0].memory["metadata"]["file_path"]
        assert classify_code_layer(top_path, top_sym, "") == "service"
        assert "/services/" in top_path
        assert top_sym in ("addOrder", "enqueueRoutedJobsForOrder") or "Order" in top_sym

        result = trace_code_flow("dart-seed", query, index, store, root_path=root, max_steps=6)
        assert "/services/" in result.steps[0].file
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_dart_fixture_seed_quikot_deliver():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, root, tmp = _setup_dart_flow(db)
        query = "What service delivers data to QuiKOT?"
        raw = search_index_records("dart-seed", query, index, limit=36, memory_store=store)
        trusted = apply_trust(raw, query)
        seeds = collect_seed_hits(trusted, query)
        assert seeds
        top_sym = seeds[0].memory["metadata"]["symbol_name"]
        top_path = seeds[0].memory["metadata"]["file_path"]
        assert top_sym == "deliver"
        assert "/hardware/" in top_path

        result = trace_code_flow("dart-seed", query, index, store, root_path=root, max_steps=6)
        assert result.steps
        assert result.steps[0].symbol == "deliver"
        assert "/hardware/" in result.steps[0].file
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_dart_fixture_seed_quikot_deliver_embeddings_on():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    prev = os.environ.get("OVERHAUST_EMBEDDINGS")
    os.environ["OVERHAUST_EMBEDDINGS"] = "1"
    try:
        store, index, root, tmp = _setup_dart_flow(db)
        query = "What service delivers data to QuiKOT?"
        result = trace_code_flow("dart-seed", query, index, store, root_path=root, max_steps=6)
        assert result.steps
        assert result.steps[0].symbol == "deliver"
    finally:
        if prev is None:
            os.environ.pop("OVERHAUST_EMBEDDINGS", None)
        else:
            os.environ["OVERHAUST_EMBEDDINGS"] = prev
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


test_dart_fixture_seed_quikot_deliver_embeddings_on.__pytestmark__ = pytest.mark.embeddings


def test_dart_fixture_seed_quikot_deliver_communication_query():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, root, tmp = _setup_dart_flow(db)
        query = "How does the app communicate with QuiKOT hardware?"
        raw = search_index_records("dart-seed", query, index, limit=12, memory_store=store)
        trusted = apply_trust(raw, query)
        seeds = collect_seed_hits(trusted, query)
        top_sym = seeds[0].memory["metadata"]["symbol_name"]
        top_path = seeds[0].memory["metadata"]["file_path"]
        assert "deliver" in top_sym or "QuikotDeviceManagementService" in top_sym
        assert classify_code_layer(top_path, top_sym, "") == "service"
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_dart_fixture_kot_keeps_build_kot_text():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        db = t.name
    tmp = None
    try:
        store, index, root, tmp = _setup_dart_flow(db)
        query = "Where is the KOT generated?"
        raw = search_index_records("dart-seed", query, index, limit=12, memory_store=store)
        trusted = apply_trust(raw, query)
        seeds = collect_seed_hits(trusted, query)
        top_sym = seeds[0].memory["metadata"]["symbol_name"]
        assert top_sym == "buildKotText"
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
