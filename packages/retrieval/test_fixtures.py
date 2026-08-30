"""Shared retrieval test fixtures for LabKOT-style projects."""
from pathlib import Path


def make_labkot_retrieval_tree(root: Path):
    """
    LabKOT fixture with domain kitchen/hardware code and generic Flutter noise.
    """
    (root / "src" / "kitchen").mkdir(parents=True)
    (root / "src" / "hardware").mkdir(parents=True)
    (root / "src" / "marketing").mkdir(parents=True)
    (root / "lib" / "generated").mkdir(parents=True)
    (root / "lib" / "theme").mkdir(parents=True)

    (root / "src" / "kitchen" / "order_service.ts").write_text(
        "import { generateKOT } from './kot_generator';\n"
        "import { notifyKitchen } from './notifications';\n\n"
        "export function createOrder(orderId: string) {\n"
        "  generateKOT(orderId);\n"
        "  notifyKitchen(orderId);\n"
        "}\n\n"
        "export function handleOrderPlaced(orderId: string) {\n"
        "  createOrder(orderId);\n"
        "}\n"
    )
    (root / "src" / "kitchen" / "kot_generator.ts").write_text(
        "export function generateKOT(orderId: string) {\n"
        "  return { orderId, items: [], printedAt: Date.now() };\n"
        "}\n"
    )
    (root / "src" / "kitchen" / "notifications.ts").write_text(
        "export function notifyKitchen(orderId: string) {\n"
        "  console.log('kitchen notified', orderId);\n"
        "}\n"
    )
    (root / "src" / "hardware" / "quikot_client.ts").write_text(
        "export function connectQuikotHardware(deviceId: string) {\n"
        "  return { deviceId, connected: true };\n"
        "}\n\n"
        "export function sendOrderToQuikotPrinter(orderId: string) {\n"
        "  connectQuikotHardware('printer-1');\n"
        "  return { orderId, printed: true };\n"
        "}\n"
    )
    (root / "lib" / "generated" / "plugin_registrant.dart").write_text(
        "class GeneratedPluginRegistrant {\n"
        "  static void registerWith() {}\n"
        "}\n"
    )
    (root / "lib" / "theme" / "app_theme.dart").write_text(
        "enum AppThemeMode { light, dark }\n\n"
        "class AppTheme {\n"
        "  AppTheme copyWith() { return this; }\n"
        "}\n"
    )
    (root / "src" / "marketing" / "page.tsx").write_text(
        "export function MarketingPage() {\n"
        "  return <div>Pricing and landing page copy</div>;\n"
        "}\n"
    )


def make_kot_flow_tree(root: Path):
    """Backward-compatible wrapper: kitchen flow without hardware/noise."""
    (root / "src" / "kitchen").mkdir(parents=True)
    (root / "src" / "marketing").mkdir(parents=True)

    (root / "src" / "kitchen" / "order_service.ts").write_text(
        "import { generateKOT } from './kot_generator';\n"
        "import { notifyKitchen } from './notifications';\n\n"
        "export function createOrder(orderId: string) {\n"
        "  generateKOT(orderId);\n"
        "  notifyKitchen(orderId);\n"
        "}\n"
    )
    (root / "src" / "kitchen" / "kot_generator.ts").write_text(
        "export function generateKOT(orderId: string) {\n"
        "  return { orderId, items: [], printedAt: Date.now() };\n"
        "}\n"
    )
    (root / "src" / "kitchen" / "notifications.ts").write_text(
        "export function notifyKitchen(orderId: string) {\n"
        "  console.log('kitchen notified', orderId);\n"
        "}\n"
    )
    (root / "src" / "marketing" / "page.tsx").write_text(
        "export function MarketingPage() {\n"
        "  return <div>Pricing and landing page copy</div>;\n"
        "}\n"
    )


def make_kot_tree(root: Path):
    """Backward-compatible wrapper: original index retrieval fixture."""
    (root / "src" / "kitchen").mkdir(parents=True)
    (root / "src" / "config").mkdir(parents=True)
    (root / "src" / "marketing").mkdir(parents=True)

    (root / "src" / "kitchen" / "order_flow.ts").write_text(
        "export function handleOrderReady(orderId: string) {\n"
        "  markOrderReady(orderId);\n"
        "  notifyKitchen(orderId);\n"
        "}\n"
        "export function markOrderReady(orderId: string) {\n"
        "  // update order status to ready\n"
        "}\n"
    )
    (root / "src" / "kitchen" / "kot_generator.ts").write_text(
        "export function generateKOT(orderId: string) {\n"
        "  return { orderId, items: [], printedAt: Date.now() };\n"
        "}\n"
    )
    (root / "src" / "kitchen" / "notifications.ts").write_text(
        "export function notifyKitchen(orderId: string) {\n"
        "  console.log('kitchen notified', orderId);\n"
        "}\n"
    )
    (root / "src" / "config" / "database.ts").write_text(
        "export function createDbConnection() {\n"
        "  return { url: 'sqlite://labkot.db' };\n"
        "}\n"
    )
    (root / "src" / "marketing" / "page.tsx").write_text(
        "export function MarketingPage() {\n"
        "  return <div>Pricing and landing page copy</div>;\n"
        "}\n"
    )


def make_dart_flow_tree(root: Path):
    """Dart fixture mirroring LabKOT widget/service/hardware patterns."""
    (root / "lib" / "widgets" / "kitchen").mkdir(parents=True)
    (root / "lib" / "models" / "hardware").mkdir(parents=True)
    (root / "lib" / "models").mkdir(parents=True, exist_ok=True)
    (root / "lib" / "services" / "printing" / "adapters" / "usb").mkdir(parents=True)
    (root / "lib" / "services" / "hardware").mkdir(parents=True, exist_ok=True)
    (root / "lib" / "services" / "printing").mkdir(parents=True, exist_ok=True)

    (root / "lib" / "models" / "order_status.dart").write_text(
        "enum OrderStatus { newOrder, preparing, ready }\n"
    )
    (root / "lib" / "widgets" / "kitchen" / "order_status_buttons.dart").write_text(
        "import '../../models/order_status.dart';\n\n"
        "class OrderStatusButtons {\n"
        "  const OrderStatusButtons({required this.currentStatus});\n"
        "  final OrderStatus currentStatus;\n\n"
        "  Widget build(BuildContext context) {\n"
        "    return Row(children: []);\n"
        "  }\n"
        "}\n"
    )
    (root / "lib" / "widgets" / "kitchen" / "kitchen_order_card.dart").write_text(
        "import '../../models/order_status.dart';\n"
        "import 'order_status_buttons.dart';\n\n"
        "class KitchenOrderCard {\n"
        "  const KitchenOrderCard({required this.orderStatus});\n"
        "  final OrderStatus orderStatus;\n\n"
        "  Widget build(BuildContext context) {\n"
        "    return OrderStatusButtons(currentStatus: orderStatus);\n"
        "  }\n"
        "}\n"
    )
    (root / "lib" / "services" / "printing" / "kitchen_print_document_builder.dart").write_text(
        "class KitchenPrintDocumentBuilder {\n"
        "  const KitchenPrintDocumentBuilder();\n"
        "  String buildText(String orderId) {\n"
        "    return 'KOT $orderId';\n"
        "  }\n"
        "}\n"
    )
    (root / "lib" / "services" / "printing" / "kitchen_print_service.dart").write_text(
        "import 'kitchen_print_document_builder.dart';\n\n"
        "class KitchenPrintService {\n"
        "  static final KitchenPrintService instance = KitchenPrintService();\n"
        "  final KitchenPrintDocumentBuilder _documentBuilder = "
        "const KitchenPrintDocumentBuilder();\n\n"
        "  String buildKotText(String orderId) {\n"
        "    return _documentBuilder.buildText(orderId);\n"
        "  }\n\n"
        "  Future<void> enqueueRoutedJobsForOrder(String orderId) async {\n"
        "    buildKotText(orderId);\n"
        "  }\n"
        "}\n"
    )
    (root / "lib" / "services" / "order_service.dart").write_text(
        "import '../models/hardware/quikot_protocol.dart';\n"
        "import 'printing/kitchen_print_service.dart';\n"
        "import 'hardware/quikot_device_management_service.dart';\n\n"
        "class OrderService {\n"
        "  Future<void> addOrder(String orderId) async {\n"
        "    await KitchenPrintService.instance.enqueueRoutedJobsForOrder(orderId);\n"
        "  }\n\n"
        "  Future<void> _deliverPaidReceipt(String orderId) async {\n"
        "    await completePayment(orderId);\n"
        "    await QuikotDeviceManagementService.instance.deliver("
        "QuikotProtocolMessage(id: orderId));\n"
        "  }\n\n"
        "  Future<void> completePayment(String orderId) async {}\n\n"
        "  Future<void> markFoodDelivered(String orderId) async {\n"
        "    await _markFoodDeliveredInternal(orderId);\n"
        "  }\n\n"
        "  Future<void> _markFoodDeliveredInternal(String orderId) async {}\n"
        "}\n"
    )
    (root / "lib" / "models" / "hardware" / "quikot_protocol.dart").write_text(
        "class QuikotProtocolMessage {\n"
        "  const QuikotProtocolMessage({required this.id});\n"
        "  final String id;\n"
        "}\n"
    )
    (root / "lib" / "services" / "hardware" / "quikot_device_adapter.dart").write_text(
        "import '../../models/hardware/quikot_protocol.dart';\n\n"
        "abstract class QuikotDeviceAdapter {\n"
        "  Future<void> send(QuikotProtocolMessage message);\n"
        "}\n"
    )
    (root / "lib" / "services" / "hardware" / "quikot_device_management_service.dart").write_text(
        "import 'quikot_device_adapter.dart';\n"
        "import '../../models/hardware/quikot_protocol.dart';\n\n"
        "class QuikotDeviceManagementService {\n"
        "  static final QuikotDeviceManagementService instance = "
        "QuikotDeviceManagementService();\n"
        "  QuikotDeviceAdapter? adapter;\n\n"
        "  Future<void> deliver(QuikotProtocolMessage message) async {\n"
        "    await adapter!.send(message);\n"
        "  }\n"
        "}\n"
    )
    (root / "lib" / "services" / "printing" / "adapters" / "usb" / "platform_usb_printer_port.dart").write_text(
        "import 'package:flutter/services.dart';\n\n"
        "class PlatformUsbPrinterPort {\n"
        "  PlatformUsbPrinterPort({MethodChannel? channel})\n"
        "    : _channel = channel ?? const MethodChannel('labkot/usb_printer');\n"
        "  final MethodChannel _channel;\n\n"
        "  Future<bool> isSupported() async {\n"
        "    return await _channel.invokeMethod<bool>('isSupported') ?? false;\n"
        "  }\n"
        "}\n"
    )


def make_flow_beam_tree(root: Path):
    """
    Generic Dart fixture for Phase 2E beam-search / bidirectional flow tests.

    Covers order routing, caller chains, adapter boundaries, printer pipeline,
    and import traps with a stronger direct-call alternative.
    """
    (root / "lib" / "services" / "order").mkdir(parents=True)
    (root / "lib" / "services" / "kitchen").mkdir(parents=True)
    (root / "lib" / "services" / "hardware" / "adapters").mkdir(parents=True)
    (root / "lib" / "services" / "printing").mkdir(parents=True)
    (root / "lib" / "models").mkdir(parents=True)

    (root / "lib" / "models" / "order_item.dart").write_text(
        "class OrderItem {\n"
        "  const OrderItem({required this.name});\n"
        "  final String name;\n"
        "}\n"
    )
    (root / "lib" / "services" / "kitchen" / "kitchen_router.dart").write_text(
        "class KitchenRouter {\n"
        "  Future<void> sendToKitchen(String orderId) async {}\n"
        "}\n"
    )
    (root / "lib" / "services" / "order" / "order_flow.dart").write_text(
        "import '../kitchen/kitchen_router.dart';\n"
        "import '../../models/order_item.dart';\n\n"
        "class OrderFlowService {\n"
        "  final KitchenRouter _router = KitchenRouter();\n\n"
        "  Future<void> createOrder(String orderId) async {\n"
        "    await routeOrder(orderId);\n"
        "  }\n\n"
        "  Future<void> routeOrder(String orderId) async {\n"
        "    final item = OrderItem(name: orderId);\n"
        "    await _router.sendToKitchen(item.name);\n"
        "  }\n"
        "}\n"
    )
    (root / "lib" / "services" / "order" / "checkout.dart").write_text(
        "import 'order_flow.dart';\n\n"
        "class CheckoutService {\n"
        "  Future<void> submitOrder(String orderId) async {\n"
        "    await checkout(orderId);\n"
        "  }\n\n"
        "  Future<void> checkout(String orderId) async {\n"
        "    await OrderFlowService().createOrder(orderId);\n"
        "  }\n"
        "}\n"
    )
    (root / "lib" / "models" / "hardware").mkdir(parents=True)
    (root / "lib" / "models" / "hardware" / "device_protocol.dart").write_text(
        "class DeviceProtocol {\n"
        "  List<int> encode(String payload) => payload.codeUnits;\n"
        "}\n"
    )
    (root / "lib" / "services" / "hardware" / "adapters" / "device_adapter.dart").write_text(
        "import '../../../models/hardware/device_protocol.dart';\n\n"
        "class DeviceAdapter {\n"
        "  final DeviceProtocol _protocol = DeviceProtocol();\n\n"
        "  Future<void> send(String payload) async {\n"
        "    final bytes = _protocol.encode(payload);\n"
        "    await transportWrite(bytes);\n"
        "  }\n\n"
        "  Future<void> transportWrite(List<int> bytes) async {}\n"
        "}\n"
    )
    (root / "lib" / "services" / "hardware" / "device_service.dart").write_text(
        "import 'adapters/device_adapter.dart';\n\n"
        "class DeviceService {\n"
        "  final DeviceAdapter _adapter = DeviceAdapter();\n\n"
        "  Future<void> deliver(String payload) async {\n"
        "    await _adapter.send(payload);\n"
        "  }\n"
        "}\n"
    )
    (root / "lib" / "services" / "printing" / "print_pipeline.dart").write_text(
        "class PrintPipeline {\n"
        "  Future<void> enqueue(String orderId) async {\n"
        "    final doc = buildDocument(orderId);\n"
        "    await printerSend(doc);\n"
        "  }\n\n"
        "  String buildDocument(String orderId) => 'DOC:$orderId';\n\n"
        "  Future<void> printerSend(String doc) async {}\n"
        "}\n"
    )
