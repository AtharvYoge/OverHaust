"""Unit tests for Dart/static evidence extraction."""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from packages.retrieval.dart_evidence import (
    EDGE_CONSTRUCTOR,
    EDGE_DIRECT_CALL,
    EDGE_IMPORT,
    EDGE_INHERITANCE,
    find_same_file_callers,
    find_source_edges,
    is_definition_line,
    strip_comments,
)
from services.ingestion.project_indexer import ProjectIndexer


class _Sym:
    def __init__(self, name, kind="function", line=1, exported=True):
        self.name = name
        self.kind = kind
        self.line = line
        self.exported = exported


def test_is_definition_line_build():
    assert is_definition_line("  Widget build(BuildContext context) {", "build")
    assert not is_definition_line("    return OrderStatusButtons(currentStatus: s);", "build")


def test_strip_comments():
    src = "foo(); // bar\n/* baz */ qux();"
    cleaned = strip_comments(src)
    assert "bar" not in cleaned
    assert "baz" not in cleaned
    assert "foo()" in cleaned


def test_direct_call_with_receiver():
    source = (
        "class S {\n"
        "  void enqueue() {\n"
        "    service.buildKotText('1');\n"
        "  }\n"
        "}\n"
    )
    reachable = [
        ("lib/services/printing/kitchen_print_service.dart", _Sym("buildKotText"), "import"),
    ]
    edges = find_source_edges(source, "lib/services/order_service.dart", reachable)
    calls = [e for e in edges if e.edge_type == EDGE_DIRECT_CALL]
    assert any(e.target_symbol == "buildKotText" for e in calls)


def test_constructor_edge():
    source = (
        "class Card {\n"
        "  Widget render() {\n"
        "    return OrderStatusButtons(currentStatus: status);\n"
        "  }\n"
        "}\n"
    )
    reachable = [
        ("lib/widgets/kitchen/order_status_buttons.dart", _Sym("OrderStatusButtons", "class"), "import"),
    ]
    edges = find_source_edges(source, "lib/widgets/kitchen/kitchen_order_card.dart", reachable)
    assert any(e.edge_type == EDGE_CONSTRUCTOR and e.target_symbol == "OrderStatusButtons" for e in edges)


def test_build_not_matched_as_call():
    source = (
        "class W {\n"
        "  Widget build(BuildContext context) {\n"
        "    return Row();\n"
        "  }\n"
        "}\n"
    )
    reachable = [("same.dart", _Sym("build", "function", 2), "same_file")]
    edges = find_source_edges(source, "same.dart", reachable)
    assert not any(e.target_symbol == "build" for e in edges)


def test_same_file_callers():
    source = (
        "class KitchenPrintService {\n"
        "  String buildKotText(String orderId) {\n"
        "    return _documentBuilder.buildText(orderId);\n"
        "  }\n"
        "  Future<void> enqueueRoutedJobsForOrder(String orderId) async {\n"
        "    buildKotText(orderId);\n"
        "  }\n"
        "}\n"
    )
    reachable = [
        ("lib/services/printing/kitchen_print_service.dart", _Sym("buildKotText", "function", 2), "same"),
        ("lib/services/printing/kitchen_print_service.dart", _Sym("enqueueRoutedJobsForOrder", "function", 6), "same"),
        ("lib/services/printing/kitchen_print_document_builder.dart", _Sym("buildText", "function"), "import"),
    ]
    edges = find_same_file_callers(
        source,
        "lib/services/printing/kitchen_print_service.dart",
        "buildKotText",
        reachable,
    )
    assert any(e.target_symbol == "enqueueRoutedJobsForOrder" for e in edges)


def test_inheritance_edge():
    source = "class Foo extends Bar {\n}\n"
    reachable = [("lib/bar.dart", _Sym("Bar", "class"), "import")]
    edges = find_source_edges(source, "lib/foo.dart", reachable)
    assert any(e.edge_type == EDGE_INHERITANCE and e.target_symbol == "Bar" for e in edges)


def test_named_param_body_does_not_include_later_method():
    from packages.retrieval.dart_evidence import _symbol_body_span

    source = (
        "class Pipeline {\n"
        "  String buildTicket(\n"
        "    String id, {\n"
        "    int? width,\n"
        "  }) {\n"
        "    return _builder.buildText(id);\n"
        "  }\n\n"
        "  Future<void> enqueueForTicket(String id) async {\n"
        "    await enqueueJobsForTicket(id);\n"
        "  }\n"
        "}\n"
    )
    start, end = _symbol_body_span(source, "lib/pipeline.dart", "buildTicket")
    scoped = "\n".join(source.splitlines()[start - 1 : end])
    assert "buildText" in scoped
    assert "enqueueJobsForTicket" not in scoped


def test_dart_indexer_platform_channel():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "port.dart").write_text(
            "import 'package:flutter/services.dart';\n"
            "class P {\n"
            "  final MethodChannel _channel = const MethodChannel('labkot/usb_printer');\n"
            "  Future<void> go() => _channel.invokeMethod('open');\n"
            "}\n"
        )
        idx = ProjectIndexer().index_project(str(root), "p")
        syms = {s.name: s.kind for f in idx.files for s in f.symbols}
        assert "channel:labkot/usb_printer" in syms
        assert syms["channel:labkot/usb_printer"] == "platform_channel"
        assert "invoke:open" in syms
