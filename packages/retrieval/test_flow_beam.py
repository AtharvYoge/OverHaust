"""Phase 2E tests: beam search, path scoring, bidirectional evidence."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from packages.memory.memory_store import MemoryStore
from services.ingestion.index_store import ProjectIndexStore
from packages.retrieval.code_flow import (
    build_caller_index,
    build_index_lookups,
    enrich_lookups,
    trace_code_flow,
)
from packages.retrieval.dart_evidence import (
    EDGE_ADAPTER_BOUNDARY,
    EDGE_CALLER,
    EDGE_DIRECT_CALL,
    EDGE_IMPORT,
    EDGE_QUERY_MATCH,
    EDGE_SAME_FILE_CALLER,
)
from packages.retrieval.flow_graph import (
    PartialFlowPath,
    backward_edge_allowed,
    classify_flow_traversal_intent,
    direction_is_coherent,
    query_asks_about_generation,
    score_flow_path,
    should_expand_backward,
)
from packages.retrieval.test_fixtures import make_dart_flow_tree, make_flow_beam_tree, make_kot_flow_tree


def _setup(project_id: str, fixture_fn):
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    fixture_fn(root)
    db = tempfile.mktemp(suffix=".db")
    store = MemoryStore(db)
    store.add_project(project_id, "Flow Beam", "", str(root))
    idx = ProjectIndexStore(store)
    index, _ = idx.sync_project(project_id, str(root))
    return store, index, str(root), db, tmp


def _symbols(result):
    return [s.symbol for s in result.steps]


def _edge_types(result):
    return [s.edge_type for s in result.steps]


def test_flow_intent_forward_process():
    intent = classify_flow_traversal_intent("How does a food order reach the kitchen?")
    assert intent.kind == "forward_process"
    assert intent.prefer_forward


def test_flow_intent_hardware():
    intent = classify_flow_traversal_intent("How does the app communicate with device hardware?")
    assert intent.kind == "hardware_transport"


def test_caller_index_builds_reverse_edges():
    db = tempfile.mktemp(suffix=".db")
    tmp = None
    try:
        store, index, root, db, tmp = _setup("caller-idx", make_flow_beam_tree)
        lookups = enrich_lookups(root, build_index_lookups(index))
        callers = lookups["callers_by_target"]
        assert ("lib/services/order/order_flow.dart", "createOrder") in callers
        edge_types = {e.edge_type for e in callers[("lib/services/order/order_flow.dart", "createOrder")]}
        assert EDGE_CALLER in edge_types or EDGE_SAME_FILE_CALLER in edge_types
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_beam_prefers_direct_call_over_import_trap():
    db = tempfile.mktemp(suffix=".db")
    tmp = None
    try:
        store, index, root, db, tmp = _setup("beam-order", make_flow_beam_tree)
        result = trace_code_flow(
            "beam-order",
            "How does an order reach the kitchen?",
            index,
            memory_store=store,
            root_path=root,
            max_steps=5,
        )
        symbols = _symbols(result)
        assert "createOrder" in symbols or "routeOrder" in symbols
        assert "sendToKitchen" in symbols
        import_count = sum(1 for s in result.steps if s.edge_type == EDGE_IMPORT)
        assert import_count <= 1
        assert EDGE_DIRECT_CALL in _edge_types(result)
        assert result.path_score > 0
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_beam_adapter_boundary_chain():
    db = tempfile.mktemp(suffix=".db")
    tmp = None
    try:
        store, index, root, db, tmp = _setup("beam-device", make_flow_beam_tree)
        result = trace_code_flow(
            "beam-device",
            "How does DeviceService deliver payload via the adapter?",
            index,
            memory_store=store,
            root_path=root,
            max_steps=6,
        )
        symbols = _symbols(result)
        assert "deliver" in symbols
        assert "send" in symbols or "transportWrite" in symbols
        assert any(
            s.edge_type in (EDGE_DIRECT_CALL, EDGE_ADAPTER_BOUNDARY)
            for s in result.steps[1:]
        )
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_beam_printer_pipeline():
    db = tempfile.mktemp(suffix=".db")
    tmp = None
    try:
        store, index, root, db, tmp = _setup("beam-print", make_flow_beam_tree)
        result = trace_code_flow(
            "beam-print",
            "How does PrintPipeline enqueue print jobs?",
            index,
            memory_store=store,
            root_path=root,
            max_steps=5,
        )
        symbols = _symbols(result)
        assert "enqueue" in symbols or "PrintPipeline" in symbols
        assert "buildDocument" in symbols or "printerSend" in symbols
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_dart_fixture_end_to_end_kitchen():
    db = tempfile.mktemp(suffix=".db")
    tmp = None
    try:
        store, index, root, db, tmp = _setup("dart-beam", make_dart_flow_tree)
        result = trace_code_flow(
            "dart-beam",
            "How does a food order reach the kitchen?",
            index,
            memory_store=store,
            root_path=root,
            max_steps=6,
        )
        symbols = _symbols(result)
        assert result.steps[0].file.startswith("lib/services/")
        assert "enqueueRoutedJobsForOrder" in symbols or "buildKotText" in symbols
        assert "build" not in symbols
        assert len(result.process_steps) >= 2
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_path_scoring_penalizes_import_chain():
    from packages.retrieval.code_flow import FlowStep

    intent = classify_flow_traversal_intent("order kitchen flow")
    strong_path = [
        FlowStep("a.dart", "createOrder", "function", 1, "query match", 0.9, 0.8, "query_match"),
        FlowStep("a.dart", "routeOrder", "function", 2, "direct_call", 0.7, 0.8, EDGE_DIRECT_CALL),
        FlowStep("b.dart", "sendToKitchen", "function", 3, "direct_call", 0.7, 0.8, EDGE_DIRECT_CALL),
    ]
    import_path = [
        FlowStep("a.dart", "createOrder", "function", 1, "query match", 0.9, 0.8, "query_match"),
        FlowStep("m.dart", "OrderItem", "class", 2, "import", 0.6, 0.8, EDGE_IMPORT),
        FlowStep("m2.dart", "OtherModel", "class", 3, "import", 0.6, 0.8, EDGE_IMPORT),
    ]
    assert score_flow_path(strong_path, "order kitchen", intent) > score_flow_path(
        import_path, "order kitchen", intent
    )


def test_function_body_span_does_not_bleed_into_next_method():
    from packages.retrieval.dart_evidence import _symbol_body_span

    source = (
        "class S {\n"
        "  Future<void> reprintFromHistory(String id) {\n"
        "    return _history.reprintKot(id);\n"
        "  }\n\n"
        "  OrderModel? _orderFromJob() {\n"
        "    return OrderModel(orderId: '1', tableNumber: 1, items: []);\n"
        "  }\n\n"
        "  Future<void> restoreFromStore() async {}\n"
        "}\n"
    )
    start, end = _symbol_body_span(source, "lib/s.dart", "reprintFromHistory")
    scoped = "\n".join(source.splitlines()[start - 1 : end])
    assert "OrderModel(" not in scoped


def test_short_function_body_excludes_later_sibling_calls():
    from packages.retrieval.dart_evidence import find_source_edges

    class _Sym:
        def __init__(self, name, kind="function", line=1, exported=True):
            self.name = name
            self.kind = kind
            self.line = line
            self.exported = exported

    source = (
        "class TicketPipeline {\n"
        "  String buildTicket(\n"
        "    String id, {\n"
        "    int? width,\n"
        "  }) {\n"
        "    return _builder.buildText(id);\n"
        "  }\n\n"
        "  Future<void> enqueueForTicket(String id) async {\n"
        "    await enqueueJobsForTicket(id);\n"
        "  }\n\n"
        "  Future<void> enqueueJobsForTicket(String id) async {}\n"
        "}\n"
    )
    lookups = {
        "symbols_by_file": {
            "lib/ticket_pipeline.dart": [
                _Sym("buildTicket", "function", 2),
                _Sym("enqueueForTicket", "function", 10),
                _Sym("enqueueJobsForTicket", "function", 14),
            ]
        }
    }
    reachable = [
        ("lib/ticket_pipeline.dart", _Sym("buildTicket", "function", 2), "same"),
        ("lib/ticket_pipeline.dart", _Sym("enqueueForTicket", "function", 10), "same"),
        ("lib/ticket_pipeline.dart", _Sym("enqueueJobsForTicket", "function", 14), "same"),
        ("lib/ticket_builder.dart", _Sym("buildText", "function", 1), "import"),
    ]
    edges = find_source_edges(
        source,
        "lib/ticket_pipeline.dart",
        reachable,
        current_symbol="buildTicket",
        lookups=lookups,
    )
    targets = {e.target_symbol for e in edges if e.edge_type == EDGE_DIRECT_CALL}
    assert "buildText" in targets
    assert "enqueueJobsForTicket" not in targets


def test_origin_generation_skips_backward_when_forward_exists():
    intent = classify_flow_traversal_intent("Where is the ticket generated?")
    assert intent.kind == "origin_generation"
    assert not should_expand_backward(intent, 0, has_strong_forward=False)
    assert not should_expand_backward(intent, 0, has_strong_forward=True)
    hw = classify_flow_traversal_intent("How does the app communicate with device hardware?")
    assert hw.kind == "hardware_transport"
    assert should_expand_backward(hw, 0, has_strong_forward=False)
    assert not should_expand_backward(hw, 0, has_strong_forward=True)


def test_origin_generation_uses_forward_pipeline():
    db = tempfile.mktemp(suffix=".db")
    tmp = None
    try:
        store, index, root, db, tmp = _setup("origin-fwd", make_dart_flow_tree)
        result = trace_code_flow(
            "origin-fwd",
            "Where is the KOT generated?",
            index,
            memory_store=store,
            root_path=root,
            max_steps=6,
        )
        symbols = _symbols(result)
        assert "buildKotText" in symbols
        assert "buildText" in symbols
        process_rest = result.process_steps[1:]
        assert all(s.direction == "forward" for s in process_rest)
        assert not any(
            s.edge_type in (EDGE_CALLER, EDGE_SAME_FILE_CALLER) for s in process_rest
        )
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def test_origin_generation_kot_summary_excludes_callers():
    db = tempfile.mktemp(suffix=".db")
    tmp_dir = None
    try:
        tmp_dir = tempfile.mkdtemp()
        root = Path(tmp_dir)
        make_kot_flow_tree(root)
        store = MemoryStore(db)
        store.add_project("origin-kot", "Origin KOT", "", str(root))
        index, _ = ProjectIndexStore(store).sync_project("origin-kot", str(root))
        result = trace_code_flow(
            "origin-kot",
            "Where is the KOT generated?",
            index,
            memory_store=store,
            root_path=str(root),
            max_steps=6,
        )
        assert result.flow_intent == "origin_generation"
        assert "generateKOT" in result.summary
        assert "createOrder" not in result.summary
        assert result.summary == "generateKOT"
        assert not any(
            s.edge_type in (EDGE_CALLER, EDGE_SAME_FILE_CALLER) for s in result.steps
        )
    finally:
        os.unlink(db)
        if tmp_dir:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


def test_result_includes_path_metadata():
    db = tempfile.mktemp(suffix=".db")
    tmp = None
    try:
        store, index, root, db, tmp = _setup("meta", make_dart_flow_tree)
        from packages.retrieval.code_flow import code_flow_result_to_dict

        result = trace_code_flow(
            "meta",
            "Where is the KOT generated?",
            index,
            memory_store=store,
            root_path=root,
        )
        payload = code_flow_result_to_dict(result)
        assert payload["flow_intent"]
        assert "path_score" in payload
        assert payload["process_steps"]
        assert payload["static_evidence_disclaimer"]
        for step in payload["steps"]:
            assert "path_role" in step
            assert "direction" in step
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Direction coherence
# ---------------------------------------------------------------------------


def _partial(*directions, edge=EDGE_DIRECT_CALL):
    """Build a PartialFlowPath whose edges have the given directions."""
    from packages.retrieval.code_flow import FlowStep

    steps = [
        FlowStep("lib/services/a.dart", "seed", "function", 1, "query match",
                 0.9, 0.8, EDGE_QUERY_MATCH)
    ]
    for i, direction in enumerate(directions):
        step = FlowStep(
            "lib/services/a.dart", f"s{i}", "function", i + 2, "edge",
            0.7, 0.8, edge,
        )
        step.direction = direction
        steps.append(step)
    return PartialFlowPath(steps=steps, score=0.0)


def test_seed_alone_has_no_committed_direction():
    assert _partial().committed_direction == ""


def test_first_edge_fixes_the_committed_direction():
    assert _partial("forward").committed_direction == "forward"
    assert _partial("backward").committed_direction == "backward"
    # The commitment comes from the first edge, not the most recent one.
    assert _partial("backward", "backward").committed_direction == "backward"


def test_direction_coherence_rejects_mixed_paths():
    """
    Regression: `A -> B <- C -> D` renders as a four-step process while
    actually describing three unrelated relationships. Once a path commits to
    a direction, later steps must agree with it.
    """
    assert direction_is_coherent("forward", _partial())
    assert direction_is_coherent("backward", _partial())
    assert direction_is_coherent("forward", _partial("forward"))
    assert not direction_is_coherent("backward", _partial("forward"))
    assert not direction_is_coherent("forward", _partial("backward"))
    # An unset direction is treated as forward rather than as a wildcard.
    assert not direction_is_coherent("", _partial("backward"))


def test_backward_edge_blocked_after_forward_commitment():
    origin = classify_flow_traversal_intent("Where is the KOT generated?")
    assert not backward_edge_allowed(EDGE_CALLER, _partial(), origin)
    assert not backward_edge_allowed(EDGE_CALLER, _partial("forward"), origin)
    assert not backward_edge_allowed(EDGE_CALLER, _partial("backward"), origin)


def test_backward_edge_requires_absent_forward_egress():
    """
    Origin-generation paths never admit caller edges. Hardware transport still
    uses callers only when the current node has no strong forward egress.
    """
    origin = classify_flow_traversal_intent("Where is the KOT generated?")
    assert not backward_edge_allowed(
        EDGE_CALLER, _partial(), origin, has_strong_forward=False
    )
    assert not backward_edge_allowed(
        EDGE_CALLER, _partial(), origin, has_strong_forward=True
    )
    hw = classify_flow_traversal_intent("How does the app communicate with device hardware?")
    assert backward_edge_allowed(
        EDGE_CALLER, _partial(), hw, has_strong_forward=False
    )
    assert not backward_edge_allowed(
        EDGE_CALLER, _partial(), hw, has_strong_forward=True
    )


def test_non_caller_edges_bypass_backward_policy():
    origin = classify_flow_traversal_intent("Where is the KOT generated?")
    assert backward_edge_allowed(
        EDGE_DIRECT_CALL, _partial("forward"), origin, has_strong_forward=True
    )


def test_forward_intents_never_admit_caller_edges():
    intent = classify_flow_traversal_intent("What happens after an order is placed?")
    assert intent.kind == "forward_process"
    assert not backward_edge_allowed(EDGE_CALLER, _partial(), intent)
    assert not backward_edge_allowed(EDGE_SAME_FILE_CALLER, _partial(), intent)


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------


def test_bare_interrogative_is_not_an_origin_signal():
    """
    Regression: "Where are orders sent to the kitchen printer?" was classified
    origin_generation because the origin phrase list contained the bare
    interrogative "where are". It is a delivery question. Origin intent now
    requires a generation verb, so the interrogative cannot hijack traversal
    policy.
    """
    delivery = "Where are orders sent to the kitchen printer?"
    assert not query_asks_about_generation(delivery)
    assert classify_flow_traversal_intent(delivery).kind != "origin_generation"

    for phrasing in (
        "Where is the KOT generated?",
        "Where is the receipt created?",
        "Where is the payload constructed?",
        "Which class defines the order model?",
    ):
        assert query_asks_about_generation(phrasing), phrasing
        assert classify_flow_traversal_intent(phrasing).kind == "origin_generation"


def test_generation_stems_match_inflections():
    for phrasing in ("generate", "generates", "generated", "generation"):
        assert query_asks_about_generation(f"Where is the ticket {phrasing}?")


def test_traced_paths_never_alternate_direction():
    """End-to-end: a rendered path must tell exactly one causal story."""
    queries = (
        "How does a food order reach the kitchen?",
        "Where is the KOT generated?",
        "Where are orders sent to the kitchen printer?",
        "How does the app communicate with device hardware?",
    )
    db = tempfile.mktemp(suffix=".db")
    tmp = None
    try:
        store, index, root, db, tmp = _setup("coherence", make_dart_flow_tree)
        for query in queries:
            result = trace_code_flow(
                "coherence", query, index,
                memory_store=store, root_path=root, max_steps=6,
            )
            directions = {
                (s.direction or "forward") for s in result.steps[1:]
            }
            assert len(directions) <= 1, (query, [s.symbol for s in result.steps])
    finally:
        os.unlink(db)
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
