#!/usr/bin/env python3
"""Validate compact LabKOT context for the multi-printer implementation prompt."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROMPT = (
    "Add support for multiple kitchen printers and route each order "
    "to the appropriate printer."
)
PROJECT_ID = "labkot"
RELEVANCE_KEYWORDS = ("print", "printer", "kitchen", "kot", "order", "route")


def _collect_paths(payload: dict) -> str:
    parts = []
    for file_item in payload.get("relevant_files", []):
        parts.append(file_item.get("path", ""))
    for sym in payload.get("relevant_symbols", []):
        parts.append(sym.get("file", ""))
        parts.append(sym.get("name", ""))
    parts.append(payload.get("context", ""))
    return " ".join(parts).lower()


def main() -> int:
    from packages.context.agent_context import invoke_context_request
    from packages.shared.config import (
        get_context_max_evidence,
        get_context_max_files,
        get_context_max_symbols,
    )
    from services.mcp_server.server import OverhaustMCPServer

    result = invoke_context_request(PROJECT_ID, PROMPT)
    payload = result.to_dict()

    print("=== assemble_agent_context ===")
    print(f"summary: {payload['summary']}")
    print(f"confidence: {payload['confidence']}")
    print(f"code_flow_included: {payload['metrics']['code_flow_included']}")
    print(f"files={payload['metrics']['files_count']} "
          f"symbols={payload['metrics']['symbols_count']} "
          f"latency={payload['metrics']['latency_ms']}ms")
    print("\nTop files:")
    for f in payload.get("relevant_files", [])[:5]:
        print(f"  - {f.get('path')} (score={f.get('relevance_score')})")
    print("\nTop symbols:")
    for s in payload.get("relevant_symbols", [])[:5]:
        print(f"  - {s.get('file')}:{s.get('line')} {s.get('name')}")

    combined = _collect_paths(payload)
    if not any(kw in combined for kw in RELEVANCE_KEYWORDS):
        print("\nFAIL: context lacks kitchen/print related paths or symbols")
        return 1

    if payload["metrics"]["code_flow_included"]:
        print("\nFAIL: code flow should not run for implementation prompt (auto mode)")
        return 1

    max_files = get_context_max_files()
    max_symbols = get_context_max_symbols()
    max_evidence = get_context_max_evidence()
    if len(payload.get("relevant_files", [])) > max_files:
        print(f"\nFAIL: files exceed budget {max_files}")
        return 1
    if len(payload.get("relevant_symbols", [])) > max_symbols:
        print(f"\nFAIL: symbols exceed budget {max_symbols}")
        return 1
    if len(payload.get("evidence", [])) > max_evidence:
        print(f"\nFAIL: evidence exceeds budget {max_evidence}")
        return 1

    srv = OverhaustMCPServer()
    mcp_result = srv._tool_get_relevant_context({
        "project_id": PROJECT_ID,
        "prompt": PROMPT,
    })
    mcp_payload = json.loads(mcp_result.content[0].text)
    if "error" in mcp_payload:
        print(f"\nFAIL: MCP error: {mcp_payload['error']}")
        return 1
    if not mcp_payload.get("context"):
        print("\nFAIL: MCP returned empty context")
        return 1

    print("\n=== MCP get_relevant_context ===")
    print(f"metrics: {mcp_payload.get('metrics')}")
    print("\nPASS: LabKOT context validation succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
