#!/usr/bin/env python3
"""Simulate the full Overhaust user flow via the real API."""
import json, sys, urllib.request, urllib.error

BASE = "http://localhost:8000"

def call(endpoint, data=None):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(BASE + endpoint, data=body, method="POST" if data else "GET",
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())
    except Exception as e:
        return {"error": str(e)}

print("=== Overhaust End-to-End User Flow ===\n")

# STEP 1: User lands on Overhaust (implicit — we start at step 2)

# STEP 2: Create project + paste conversation + process
print("STEP 2: Create project and ingest conversation")
r = call("/api/v1/projects", {"project_id": "demo-e2e", "name": "Demo Project"})
print(f"  project: {r}")
conv = """## User
The project is a chat app. Architecture: React, FastAPI, Redis, Postgres.

## Assistant
Got it.

## User
We decided to use WebSockets. We rejected SSE.

## Assistant
ok

## User
The reconnect bug is still broken. Currently working on heartbeat recovery.

## User
thanks!
"""
r = call("/api/v1/ingest-conversation", {"project_id": "demo-e2e", "content": conv, "store": True})
print(f"  ingestion: {r['original_tokens']} -> {r['structured_tokens']} tokens ({r['reduction_percent']}% estimated reduction)")
print(f"  breakdown: {r['breakdown']}")
print(f"  stored: {len(r['stored_memory_ids'])} memories\n")

# STEP 3: Show the result (already shown above)

# STEP 4: Show what was remembered
print("STEP 4: What your AI remembers")
for cat, tokens in r["breakdown"].items():
    simple = {
        "permanent_knowledge": "Important information",
        "decision": "Important decisions",
        "current_task": "What you're working on",
        "open_issue": "Open issues",
        "resolved_issue": "Problems you've solved",
        "stale_info": "Outdated info (removed)",
    }.get(cat, cat)
    print(f"  {simple}: {tokens} tokens")
print()

# STEP 5-6: Ask what user is working on + prepare context
print("STEP 5-6: Prepare context for task")
task = "Fix the WebSocket reconnect bug"
r2 = call("/api/v1/get-context", {"project_id": "demo-e2e", "task": task, "max_knowledge_items": 10})
print(f"  task: {task}")
print(f"  context_id: {r2.get('context_id')}")
print(f"  estimated_tokens: {r2.get('estimated_tokens')}")
print(f"  knowledge_items: {len(r2.get('relevant_knowledge', []))}")
print(f"  decisions: {len(r2.get('relevant_decisions', []))}")
print(f"  constraints: {r2.get('constraints', [])}")
print()

# STEP 7: Output
print("STEP 7: Ready for AI")
orig = r["original_tokens"]
prep = r2.get("estimated_tokens", 0)
pct = (orig - prep) / orig * 100 if orig else 0
print(f"  Original: {orig} estimated tokens")
print(f"  Prepared: {prep} estimated tokens")
print(f"  Potential reduction: {pct:.1f}% (Estimated)")
print()

# STEP 9: Verify persistence
print("STEP 9: Verify local memory persistence")
r3 = call("/api/v1/search-knowledge", {"project_id": "demo-e2e", "query": "", "limit": 100})
print(f"  Stored memories: {len(r3['results'])}")
for m in r3["results"][:3]:
    print(f"    - {m['content'][:70]}")
print()
print("=== Demo flow complete ===")
print("Total flow: paste -> ingest -> show reduction -> prepare context -> copy for AI")
print("All data persisted locally — survives page refresh.")
