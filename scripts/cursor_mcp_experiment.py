#!/usr/bin/env python3
"""
Cursor MCP token-reduction experiment support.

Compares compact OverHaust get_relevant_context against a simulated naïve
full-file exploration baseline.

This does NOT measure Cursor's hidden model token count. Cursor does not
expose that. Distinguish:

  1. OverHaust context size (this script)
  2. Repository exploration / tool activity (manual Cursor session comparison)
  3. Actual model token usage (only if Cursor exposes it; currently not)

CONTROL: Cursor Agent without calling get_relevant_context (explores via Glob/Grep/Read)
OVERHAUST: alwaysApply rule → MCP get_relevant_context first, then gap-only exploration

Usage:
  python3 scripts/cursor_mcp_experiment.py
  python3 scripts/cursor_mcp_experiment.py --project-id overhaust --prompt "Where is get_relevant_context assembled?"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.context.benchmark import run_agent_benchmark  # noqa: E402
from packages.context.agent_context import resolve_project_id  # noqa: E402
from packages.memory.memory_store import get_memory_store  # noqa: E402
from packages.shared.config import (  # noqa: E402
    get_context_max_evidence,
    get_context_max_files,
    get_context_max_symbols,
)

DEFAULT_PROMPT = (
    "Trace how OverHaust handles an incoming context request, from the API "
    "entry point through retrieval, ranking, evidence gating, snippet "
    "selection, and final context assembly."
)


def _slim(condition: dict) -> dict:
    return {k: v for k, v in condition.items() if k != "payload"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Cursor MCP context-size experiment")
    parser.add_argument("--project-id", default="overhaust")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--root-path", default=str(ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    store = get_memory_store()
    project_id = args.project_id
    resolved = resolve_project_id(args.root_path, memory_store=store)
    if resolved and project_id and resolved != project_id:
        print(
            f"WARNING: root_path resolves to {resolved}, expected {project_id}",
            file=sys.stderr,
        )
    if not store.get_project(project_id):
        print(f"ERROR: project {project_id} is not registered", file=sys.stderr)
        return 1

    report = run_agent_benchmark(project_id, args.prompt, memory_store=store)
    report["cursor_protocol"] = {
        "control": "Cursor Agent without OverHaust MCP retrieval (repo tools only)",
        "overhaust": (
            "alwaysApply rule → MCP get_relevant_context → compact context → "
            "gap-only Glob/Grep/Read"
        ),
        "budgets": {
            "max_files": get_context_max_files(),
            "max_symbols": get_context_max_symbols(),
            "max_evidence": get_context_max_evidence(),
        },
        "cannot_prove": [
            "Cursor hidden model token counts",
            "That hookSpecificOutput.additionalContext reached the Cursor Agent",
            "Automatic reduction in Glob/Grep/Read without a paired live session log",
        ],
        "resolved_project_id": resolved,
    }

    if args.json:
        slim = dict(report)
        slim["baseline_fair"] = _slim(report["baseline_fair"])
        slim["overhaust"] = _slim(report["overhaust"])
        print(json.dumps(slim, indent=2, default=str))
        return 0

    oh = report["overhaust"]
    naive = report["baseline_fair"]
    red = report["fair_reduction"]
    print(f"project_id: {project_id}")
    print(f"resolved_from_root: {resolved}")
    print("")
    print("OVERHAUST compact context")
    print(f"  files={oh['files_read']} symbols={oh.get('symbols_count', 0)}")
    print(f"  approx_source_lines={oh['approx_source_lines']}")
    print(f"  response_bytes={oh['response_bytes']}")
    print(f"  estimated_context_tokens={oh['estimated_context_tokens']} (tiktoken, not Cursor billing)")
    print(f"  code_flow_included={oh.get('code_flow_included')} steps={oh.get('code_flow_steps', 0)}")
    print(f"  latency_ms={oh['latency_ms']}")
    print("")
    print("CONTROL simulation (naïve full-file reads of top hits)")
    print(f"  files={naive['files_read']} lines={naive['approx_source_lines']}")
    print(f"  response_bytes={naive['response_bytes']}")
    print(f"  estimated_context_tokens={naive['estimated_context_tokens']}")
    print("")
    print("Size reduction vs naïve full-file baseline (not Cursor model tokens)")
    print(f"  tokens_pct={red['tokens_vs_naive_full_files_pct']}")
    print(f"  bytes_pct={red['bytes_vs_naive_full_files_pct']}")
    print("")
    print("Not measured: Cursor Agent Glob/Grep/Read counts, Cursor model tokens.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
