"""LabKOT demo project data for one-click seeding."""
from __future__ import annotations

from typing import Any, Dict, List


LABKOT_PROJECT: Dict[str, Any] = {
    "name": "LabKOT",
    "description": "Restaurant operations platform with Waiter, Billing, and Kitchen apps running over a local LAN with a Billing master.",
    "stack": ["Flutter", "Dart", "SQLite", "WebSocket", "Android"],
}


LABKOT_FILES: List[Dict[str, str]] = [
    {
        "name": "lib/services/websocket_service.dart",
        "content": (
            "// Handles LAN WebSocket. Billing app is master, waiter/kitchen are clients.\n"
            "class WebSocketService {\n"
            "  final ConnectionHealth _health = ConnectionHealth();\n"
            "  Future<void> connect(String host, int port) async { /* ... */ }\n"
            "  Stream<Event> get events => _controller.stream;\n"
            "  // Exponential backoff — initial 5s, max 60s. Retries via mDNS.\n"
            "  void _reconnectLoop() { /* exponential backoff */ }\n"
            "}\n"
        ),
    },
    {
        "name": "lib/services/database_service.dart",
        "content": (
            "// Local SQLite for offline-first ordering.\n"
            "class DatabaseService {\n"
            "  Future<void> upsertOrder(Order o) async {}\n"
            "  Future<List<Order>> pendingSync() async { return []; }\n"
            "}\n"
        ),
    },
    {
        "name": "lib/repositories/order_repository.dart",
        "content": (
            "class OrderRepository {\n"
            "  final DatabaseService db; final WebSocketService ws;\n"
            "  Future<void> placeOrder(Order o) async {\n"
            "    // Idempotency: client-generated UUID.\n"
            "    await db.upsertOrder(o); ws.send(o);\n"
            "  }\n"
            "}\n"
        ),
    },
    {
        "name": "lib/services/billing_service.dart",
        "content": "// Runs only in Billing flavor. Acts as LAN master. Emits mDNS on port 4040.",
    },
    {
        "name": "lib/services/kitchen_service.dart",
        "content": "// Kitchen app: receives orders, updates status via WebSocket.",
    },
    {
        "name": "android/app/build.gradle",
        "content": (
            "flavorDimensions 'app'\n"
            "productFlavors {\n  waiter {}\n  billing {}\n  kitchen {}\n}\n"
        ),
    },
]

LABKOT_DOCS: List[Dict[str, str]] = [
    {
        "name": "architecture.md",
        "content": (
            "LabKOT is offline-first. SQLite is the source of truth locally.\n"
            "Billing app is LAN master.\n"
            "Waiter and Kitchen apps discover the Billing master via mDNS on port 4040.\n"
            "WebSocket is used for realtime sync. Payment integration is in progress.\n"
        ),
    },
    {
        "name": "marketing.md",
        "content": "LabKOT helps restaurants run smoother. Marketing site copy — not relevant to engineering.",
    },
]


def _make_conversation() -> str:
    lines: List[str] = []

    # A ton of repeated architecture explanations (real conversations bloat like this)
    for i in range(60):
        lines.append(
            f"[{i*2}] user: Quick reminder about our system \u2014 LabKOT is a Flutter mobile suite for restaurants. "
            "The Billing app runs as the LAN master and Waiter + Kitchen apps connect to it via WebSocket. "
            "SQLite is our local, offline-first source of truth so orders never get lost if the LAN drops. "
            "Android product flavors let us build three isolated apps from a single codebase (waiter, billing, kitchen). "
            "Discovery happens over mDNS on port 4040. This is important background before we discuss the ticket."
        )
        lines.append(
            f"[{i*2+1}] assistant: Got it \u2014 LabKOT: Flutter/Dart clients, SQLite locally authoritative, WebSocket sync over LAN, "
            "Billing app as the LAN master exposed via mDNS on port 4040, three Android flavors "
            "(waiter/billing/kitchen) built from one codebase, offline-first with reconciliation when the master is reachable. "
            "Ready to look at the specific issue."
        )

    # More repetition with slightly different phrasing (still redundant)
    for i in range(40):
        lines.append(
            f"[bg-{i}] user: One more thing about our stack \u2014 we chose Flutter because we needed one codebase across Android tablets. "
            "SQLite is baked into every app instance. The Billing device is always the master because it holds the printer + the payment terminal. "
            "Waiter tablets and Kitchen displays are just clients. WebSocket keeps everyone in sync in real-time."
        )
        lines.append(
            f"[bg-{i}r] assistant: Understood. Flutter for cross-Android portability, SQLite locally on every device, "
            "Billing hosts printer + payment, waiter/kitchen tablets are pure clients, WebSocket for realtime, mDNS for discovery."
        )

    # Resolved bug (should end up in resolved_issues)
    lines += [
        "[bug-1] user: We had a bad bug last week \u2014 orders were being duplicated whenever the waiter app briefly disconnected and reconnected. "
        "The kitchen would receive two copies of every order that fell during the reconnection window.",
        "[bug-1r] assistant: We fixed that. Root cause was that OrderRepository.placeOrder was writing to SQLite AND sending over WebSocket, "
        "and when the reconnect flushed the outbox, in-flight orders sent again. Fix: client-generated UUID as the order id, "
        "and an idempotency key check on the WebSocket receiver side. Deployed to all flavors two days ago.",
        "[bug-1c] user: Confirmed the duplicates are gone across all three restaurants running the pilot.",
        "[bug-2] user: Kitchen display was flickering when a lot of orders came in fast.",
        "[bug-2r] assistant: Diagnosed as unnecessary rebuilds. Wrapped OrderTile widgets in const and moved the timer into a ChangeNotifier. Solved.",
        "[bug-3] user: Bill printer would randomly stop working after 4+ hours uptime.",
        "[bug-3r] assistant: USB serial buffer overflow \u2014 added a periodic flush + reopen once/hour. Solved.",
    ]

    # Rejected approaches
    lines += [
        "[rej-1] user: Should we switch from WebSocket to gRPC over LAN for better typing and streaming?",
        "[rej-1r] assistant: We evaluated gRPC but rejected it. Reason: TLS/certificate distribution on unmanaged restaurant LANs is painful. "
        "WebSocket + JSON is simpler, already works, and lets us debug with any browser. Sticking with WebSocket.",
        "[rej-2] user: Could we use Firestore for sync instead of a LAN master?",
        "[rej-2r] assistant: Rejected. Rural restaurants have unreliable internet and we already commit to offline-first. "
        "A LAN master with SQLite is exactly the right shape. Firestore is off the table.",
        "[rej-3] user: What if we rewrote the Kitchen app in native Android for perf?",
        "[rej-3r] assistant: Rejected \u2014 not enough performance benefit to justify two codebases. Flutter is fine on Kitchen tablets.",
    ]

    # Noise / marketing / off-topic (should be ignored)
    for i in range(20):
        lines += [
            f"[noise-{i}a] user: Also, unrelated \u2014 could you write me a short poem about tomatoes?",
            f"[noise-{i}ar] assistant: Sure: 'Red round fruit / basil's silent partner / summer on my plate.'",
            f"[noise-{i}b] user: How do I set my Mac dock to auto-hide?",
            f"[noise-{i}br] assistant: System Settings \u2192 Desktop & Dock \u2192 Automatically hide and show the Dock.",
            f"[noise-{i}c] user: What's the weather in Bangalore today?",
            f"[noise-{i}cr] assistant: I don't have live weather. Try weather.com or the built-in widget.",
        ]

    # Marketing bloat
    for i in range(15):
        lines += [
            f"[mkt-{i}] user: For the LabKOT landing page \u2014 tagline ideas please. Enterprise ready, restaurant grade, blah blah.",
            f"[mkt-{i}r] assistant: Try: 'One tap. Every ticket.' or 'Front-of-house, in sync.' Marketing copy \u2014 not engineering critical.",
        ]

    # The important OPEN issue \u2014 what we'll ask about later
    lines += [
        "[open-1] user: We still have one nagging thing. When the waiter app briefly loses LAN (someone kicks a cable, or "
        "the AP hiccups), it takes 30\u201360 seconds for the waiter tablet to reconnect and start receiving updates from Billing. "
        "The reconnect logic in WebSocketService starts backoff at 5 seconds and caps at 60. That's too slow for a busy service.",
        "[open-1r] assistant: Yes \u2014 the exponential backoff is too conservative for LAN recovery. Suggested fix: shrink initial backoff to 250ms, "
        "cap at 5s, add a fast-path health ping via ConnectionHealth so we detect recovery within a couple of seconds, "
        "and re-run mDNS discovery on failure in case the Billing master IP changed. This is still open.",
        "[open-2] user: Also open: the Payment integration \u2014 we've integrated with the terminal SDK but the tip flow "
        "still needs UX polish and we're not billing per-transaction yet. Not urgent but tracked.",
    ]

    # Permanent knowledge
    lines += [
        "[perm-1] user: Confirm again: SQLite is our offline-first source of truth on every device.",
        "[perm-1r] assistant: Correct. SQLite is authoritative locally. Sync to the Billing master when reachable. Permanent architectural decision.",
        "[perm-2] user: And Billing acts as the LAN master because it owns the printer and the payment terminal \u2014 permanent.",
        "[perm-2r] assistant: Confirmed permanent.",
    ]

    return "\n".join(lines)


LABKOT_CONVERSATION = _make_conversation()


def labkot_sources() -> List[Dict[str, str]]:
    """Returns the demo context sources in the shape expected by /projects/:id/contexts."""
    out: List[Dict[str, str]] = []
    for f in LABKOT_FILES:
        out.append({"type": "file", "name": f["name"], "content": f["content"]})
    for d in LABKOT_DOCS:
        out.append({"type": "documentation", "name": d["name"], "content": d["content"]})
    out.append({"type": "conversation", "name": "Full conversation history", "content": LABKOT_CONVERSATION})
    return out
