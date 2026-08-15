"""
POC — Context Runtime Core

Proves that an LLM (via Emergent Universal Key) can:
  1) Analyze a large mixed project context (project files + conversation history + docs)
     into a strict, categorized JSON Context Cache.
  2) Given a new coding task, select only the relevant subset of the cached knowledge
     and produce an "AI-ready" optimized context block.

Run:
    cd /app/backend && python poc_context_runtime.py
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

from emergentintegrations.llm.chat import (  # noqa: E402
    LlmChat,
    UserMessage,
    TextDelta,
    StreamDone,
)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
if not EMERGENT_LLM_KEY:
    print("ERROR: EMERGENT_LLM_KEY not set in /app/backend/.env")
    sys.exit(1)

# Use a fast, cost-effective model for prototype analysis. Recommended default is gpt-5.4;
# we use gpt-5.4-mini for speed. Model can be swapped at runtime via env var.
POC_PROVIDER = os.environ.get("POC_PROVIDER", "openai")
POC_MODEL = os.environ.get("POC_MODEL", "gpt-5.4-mini")


# ---------- Sample "LabKOT" project context ----------

LABKOT_PROJECT = {
    "name": "LabKOT",
    "description": "Restaurant operations platform with Waiter, Billing, and Kitchen apps running over a local LAN with a Billing master.",
    "stack": ["Flutter", "Dart", "SQLite", "WebSocket", "Android"],
}

LABKOT_FILES = [
    ("lib/services/websocket_service.dart",
     "// Handles LAN WebSocket. Billing app is master, waiter/kitchen are clients.\n"
     "class WebSocketService {\n"
     "  Future<void> connect(String host, int port) async { /* ... */ }\n"
     "  Stream<Event> get events => _controller.stream;\n"
     "  void _reconnectLoop() { /* exponential backoff */ }\n"
     "}\n"),
    ("lib/services/database_service.dart",
     "// Local SQLite for offline-first ordering.\n"
     "class DatabaseService {\n"
     "  Future<void> upsertOrder(Order o) async {}\n"
     "  Future<List<Order>> pendingSync() async { return []; }\n"
     "}\n"),
    ("lib/repositories/order_repository.dart",
     "class OrderRepository {\n"
     "  final DatabaseService db; final WebSocketService ws;\n"
     "  Future<void> placeOrder(Order o) async { await db.upsertOrder(o); ws.send(o); }\n"
     "}\n"),
    ("lib/services/billing_service.dart", "// Runs only in Billing flavor. LAN master."),
    ("lib/services/kitchen_service.dart", "// Kitchen app: receives orders, updates status."),
    ("android/app/build.gradle", "flavorDimensions 'app'\nproductFlavors {\n  waiter {}\n  billing {}\n  kitchen {}\n}\n"),
    ("docs/architecture.md",
     "LabKOT is offline-first. SQLite is the source of truth locally. Billing app is LAN master.\n"
     "Waiter and Kitchen apps discover the Billing master via mDNS on port 4040.\n"
     "WebSocket is used for realtime sync. Payment integration is in progress.\n"),
    ("docs/marketing.md", "LabKOT helps restaurants run smoother. Marketing site copy. Not relevant to engineering."),
]


def _mk_conversation() -> List[Dict[str, str]]:
    """Simulate a large messy conversation history with repetition, resolved issues, rejected approaches, and noise."""
    msgs: List[Dict[str, str]] = []

    # Repeated architecture explanations (bloat)
    for i in range(6):
        msgs.append({"role": "user", "text": (
            f"[msg {i}] Reminder: LabKOT is a Flutter app. Billing app is LAN master. "
            "Waiter and Kitchen apps connect via WebSocket. SQLite is the local DB. "
            "Android flavors isolate the three apps."
        )})
        msgs.append({"role": "assistant", "text": (
            "Understood. LabKOT: Flutter/Dart, SQLite local, WebSocket over LAN, Billing master, "
            "3 Android flavors (waiter/billing/kitchen)."
        )})

    # Resolved bug
    msgs.append({"role": "user", "text": "Orders were being duplicated when the waiter app reconnected."})
    msgs.append({"role": "assistant", "text": (
        "Fixed. We deduped by client-generated UUID in OrderRepository.placeOrder and added an idempotency key on the WS receiver."
    )})
    msgs.append({"role": "user", "text": "Confirmed working."})

    # Rejected approach
    msgs.append({"role": "user", "text": "Should we switch from WebSocket to gRPC over LAN?"})
    msgs.append({"role": "assistant", "text": (
        "We evaluated gRPC but rejected it: TLS/cert distribution on unmanaged LAN is painful, "
        "WebSocket + JSON is simpler and already works. Sticking with WebSocket."
    )})

    # Irrelevant / noise
    msgs.append({"role": "user", "text": "Also, could you write me a poem about tomatoes?"})
    msgs.append({"role": "assistant", "text": "Sure — here's a short one: [poem elided]"})
    msgs.append({"role": "user", "text": "How do I set my Mac dock to auto-hide?"})
    msgs.append({"role": "assistant", "text": "System Settings → Desktop & Dock → Automatically hide and show the Dock."})

    # Open issue — the one we'll ask about
    msgs.append({"role": "user", "text": (
        "We still see the waiter app taking 30-60s to recover when it briefly loses LAN. "
        "Reconnect logic in WebSocketService seems slow."
    )})
    msgs.append({"role": "assistant", "text": (
        "Yeah — the exponential backoff starts at 5s and caps at 60s. We should shrink initial backoff, "
        "add a fast-path health ping on ConnectionHealth, and re-run mDNS discovery on failure."
    )})

    # Permanent decisions
    msgs.append({"role": "user", "text": "Confirm: SQLite is offline-first source of truth?"})
    msgs.append({"role": "assistant", "text": "Yes — SQLite is authoritative locally; sync to Billing master when online."})

    return msgs


def build_labkot_raw_context() -> Dict[str, Any]:
    return {
        "project": LABKOT_PROJECT,
        "files": [{"path": p, "content": c} for p, c in LABKOT_FILES],
        "documentation": [f for f in LABKOT_FILES if f[0].startswith("docs/")],
        "conversation": _mk_conversation(),
    }


# ---------- Token estimation (deterministic mock) ----------

def estimate_tokens(text: str) -> int:
    """Char/4 heuristic — clearly labeled 'estimated' in UI. Replaceable with real tokenizer later."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_raw_context_tokens(raw: Dict[str, Any]) -> Dict[str, int]:
    files_txt = "\n".join(f"{f['path']}\n{f['content']}" for f in raw.get("files", []))
    conv_txt = "\n".join(f"{m['role']}: {m['text']}" for m in raw.get("conversation", []))
    docs_txt = "\n".join(c for _, c in raw.get("documentation", []))
    return {
        "files": estimate_tokens(files_txt),
        "conversation": estimate_tokens(conv_txt),
        "documentation": estimate_tokens(docs_txt),
        "total": estimate_tokens(files_txt) + estimate_tokens(conv_txt) + estimate_tokens(docs_txt),
    }


# ---------- LLM prompts ----------

ANALYZE_SYSTEM = """You are the Context Runtime — an engine that turns a raw software project (files, docs, conversation history) into a compact, structured Project Knowledge Cache.

Your job is to extract ONLY durable, useful, non-redundant knowledge. Discard chit-chat, marketing, duplicate re-explanations, and noise. Preserve important decisions, resolved bugs, rejected approaches, and open issues distinctly.

Return STRICT JSON that matches this schema exactly (no prose, no markdown fences):

{
  "project_identity": {
    "type": "string (e.g. 'Restaurant operations platform')",
    "stack": ["string"],
    "purpose": "string",
    "architecture_summary": "string (2-4 sentences)"
  },
  "architecture": {
    "frontend": "string",
    "backend": "string",
    "database": "string",
    "authentication": "string",
    "networking": "string",
    "infrastructure": "string"
  },
  "components": [
    {"name": "string", "kind": "service|repository|module|class|widget", "purpose": "string"}
  ],
  "decisions": [
    {"title": "string", "rationale": "string"}
  ],
  "current_state": {
    "implemented": ["string"],
    "in_progress": ["string"],
    "known_issues": ["string"]
  },
  "conversation_memory": {
    "permanent_knowledge": ["string"],
    "temporary_task_context": ["string"],
    "resolved_issues": ["string"],
    "rejected_approaches": ["string"],
    "open_issues": ["string"]
  }
}

Rules:
- Output MUST be valid JSON parseable by json.loads.
- If a field has no info, use an empty string or empty array — never null.
- Be terse. Every bullet should be a single crisp sentence.
- Never invent facts not present in the input.
"""


SELECT_SYSTEM = """You are the Context Runtime — you select only the pieces of a Project Knowledge Cache that are relevant to a specific coding task, and assemble an AI-ready context block.

You will receive:
  - the full Context Cache (JSON)
  - a task description

Return STRICT JSON matching:

{
  "relevant": {
    "components": ["string (component names)"],
    "architecture_keys": ["string (keys from architecture that matter)"],
    "decisions": ["string (decision titles)"],
    "conversation_memory": ["string (short labels of memory items included)"]
  },
  "ignored": {
    "components": ["string"],
    "architecture_keys": ["string"],
    "decisions": ["string"],
    "conversation_memory": ["string"]
  },
  "assembled_context": "string — a compact, well-formatted, copy-pasteable context block containing only the relevant knowledge, in Markdown"
}

Rules:
- Output MUST be valid JSON. No prose outside JSON. No markdown fences around the JSON.
- The assembled_context itself may contain Markdown headings and lists.
- Aim for the smallest useful context (typically < 2000 tokens).
- Never invent facts absent from the cache.
"""


# ---------- LLM helpers ----------

async def _stream_to_text(chat: LlmChat, prompt: str) -> str:
    """Stream a full response and concatenate. Used because playbook says stream_message is default.
    We accumulate to a string since we need the complete JSON."""
    buf: List[str] = []
    async for ev in chat.stream_message(UserMessage(text=prompt)):
        if isinstance(ev, TextDelta):
            buf.append(ev.content)
        elif isinstance(ev, StreamDone):
            break
    return "".join(buf)


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_json_fences(s: str) -> str:
    s = s.strip()
    s = _JSON_FENCE_RE.sub("", s).strip()
    # If model wrapped with a leading/trailing sentence, try to find outermost braces
    if not s.startswith("{"):
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1:
            s = s[start : end + 1]
    return s


def _parse_json_strict(raw: str) -> Dict[str, Any]:
    cleaned = _strip_json_fences(raw)
    return json.loads(cleaned)


async def analyze_context(raw: Dict[str, Any], session_id: str = "poc-analyze") -> Dict[str, Any]:
    """Call LLM to produce Context Cache from raw project context."""
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=ANALYZE_SYSTEM,
    ).with_model(POC_PROVIDER, POC_MODEL)

    payload_lines: List[str] = []
    p = raw["project"]
    payload_lines.append(f"# Project\nName: {p['name']}\nDescription: {p['description']}\nStack: {', '.join(p['stack'])}\n")

    payload_lines.append("# Files")
    for f in raw["files"]:
        payload_lines.append(f"\n## {f['path']}\n```\n{f['content']}\n```")

    payload_lines.append("\n# Conversation History")
    for i, m in enumerate(raw["conversation"]):
        payload_lines.append(f"[{i}] {m['role']}: {m['text']}")

    prompt = "\n".join(payload_lines) + "\n\nReturn ONLY the JSON cache. No prose. No markdown fences."
    raw_out = await _stream_to_text(chat, prompt)
    return _parse_json_strict(raw_out)


async def select_relevant_context(
    cache: Dict[str, Any], task: str, session_id: str = "poc-select"
) -> Dict[str, Any]:
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=SELECT_SYSTEM,
    ).with_model(POC_PROVIDER, POC_MODEL)

    prompt = (
        "# Context Cache (JSON)\n"
        f"{json.dumps(cache, indent=2)}\n\n"
        "# Task\n"
        f"{task}\n\n"
        "Return ONLY the JSON result. No prose. No markdown fences."
    )
    raw_out = await _stream_to_text(chat, prompt)
    return _parse_json_strict(raw_out)


# ---------- Validation ----------

REQUIRED_CACHE_KEYS = [
    "project_identity",
    "architecture",
    "components",
    "decisions",
    "current_state",
    "conversation_memory",
]

REQUIRED_MEMORY_KEYS = [
    "permanent_knowledge",
    "temporary_task_context",
    "resolved_issues",
    "rejected_approaches",
    "open_issues",
]


def validate_cache(cache: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errs: List[str] = []
    for k in REQUIRED_CACHE_KEYS:
        if k not in cache:
            errs.append(f"missing cache key: {k}")
    mem = cache.get("conversation_memory", {})
    for k in REQUIRED_MEMORY_KEYS:
        if k not in mem:
            errs.append(f"missing memory bucket: {k}")
    if not isinstance(cache.get("components", []), list):
        errs.append("components must be a list")
    if not isinstance(cache.get("decisions", []), list):
        errs.append("decisions must be a list")
    return (len(errs) == 0, errs)


def validate_selection(sel: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errs: List[str] = []
    for k in ["relevant", "ignored", "assembled_context"]:
        if k not in sel:
            errs.append(f"missing selection key: {k}")
    if not isinstance(sel.get("assembled_context", ""), str):
        errs.append("assembled_context must be a string")
    return (len(errs) == 0, errs)


# ---------- Runner ----------

async def main() -> int:
    print("=" * 70)
    print("Context Runtime POC")
    print(f"Provider: {POC_PROVIDER}  Model: {POC_MODEL}")
    print("=" * 70)

    raw = build_labkot_raw_context()
    raw_tokens = estimate_raw_context_tokens(raw)
    print(f"\n[1] Raw context estimated tokens: {raw_tokens}")

    print("\n[2] Calling LLM to build Context Cache ...")
    try:
        cache = await analyze_context(raw)
    except json.JSONDecodeError as e:
        print(f"FAIL — JSON parse error building cache: {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"FAIL — analyze_context raised: {type(e).__name__}: {e}")
        return 1

    ok, errs = validate_cache(cache)
    if not ok:
        print("FAIL — cache validation errors:")
        for e in errs:
            print(f"  - {e}")
        print("\nCache content:")
        print(json.dumps(cache, indent=2)[:2000])
        return 1
    print("  ✓ Cache JSON valid and covers all 6 categories + 5 memory buckets")

    cache_json = json.dumps(cache)
    cache_tokens = estimate_tokens(cache_json)
    reduction = 1.0 - (cache_tokens / max(1, raw_tokens["total"]))
    print(f"  Cache estimated tokens: {cache_tokens}")
    print(f"  Reduction vs raw: {reduction * 100:.1f}%")

    # Show samples
    print("\n  Sample — Project Identity:")
    print("   ", cache["project_identity"])
    print("\n  Sample — Decisions ({}):".format(len(cache["decisions"])))
    for d in cache["decisions"][:3]:
        print("   -", d)
    print("\n  Sample — Rejected Approaches:")
    for r in cache["conversation_memory"]["rejected_approaches"]:
        print("   -", r)
    print("\n  Sample — Open Issues:")
    for o in cache["conversation_memory"]["open_issues"]:
        print("   -", o)

    # Task selection
    task = (
        "Fix the WebSocket reconnection issue when the waiter app temporarily loses "
        "connection to the billing master. Reconnect currently takes 30-60s."
    )
    print(f"\n[3] Selecting relevant context for task:\n    {task!r}")
    try:
        sel = await select_relevant_context(cache, task)
    except json.JSONDecodeError as e:
        print(f"FAIL — JSON parse error in selection: {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"FAIL — select_relevant_context raised: {type(e).__name__}: {e}")
        return 1

    ok, errs = validate_selection(sel)
    if not ok:
        print("FAIL — selection validation errors:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("  ✓ Selection JSON valid")

    relevant = sel["relevant"]
    ignored = sel["ignored"]
    print("\n  Relevant components:", relevant.get("components"))
    print("  Ignored components: ", ignored.get("components"))
    print("  Relevant decisions:  ", relevant.get("decisions"))

    assembled = sel["assembled_context"]
    assembled_tokens = estimate_tokens(assembled)
    print(f"\n  Assembled context estimated tokens: {assembled_tokens}")
    print(f"  vs raw total {raw_tokens['total']} — reduction: "
          f"{(1 - assembled_tokens / max(1, raw_tokens['total'])) * 100:.1f}%")
    print("\n  Assembled context (first 800 chars):")
    print("  " + assembled[:800].replace("\n", "\n  "))

    print("\n" + "=" * 70)
    print("POC RESULT: SUCCESS ✓")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
