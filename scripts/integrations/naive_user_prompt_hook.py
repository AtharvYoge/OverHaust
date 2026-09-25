#!/usr/bin/env python3
"""
Naïve-agent UserPromptSubmit hook — injects full top-hit file contents.

Simulates a coding agent that searches then reads entire relevant files.
Used for Phase 15 write-task benchmark (naïve condition only).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.context.benchmark import simulate_naive_agent_exploration  # noqa: E402
from packages.context.agent_context import resolve_project_id  # noqa: E402
from packages.integrations.hook_io import (  # noqa: E402
    format_empty_hook_output,
    format_hook_output,
    parse_hook_input,
)
from packages.tokenization.token_estimator import TokenEstimator

NAIVE_MARKER = "<!-- naive-agent-context -->"


def _format_naive_context(combined_text: str) -> str:
    text = (combined_text or "").strip()
    if not text:
        return ""
    return f"{NAIVE_MARKER}\n\n## Repository context (full top-hit files)\n{text}"


def main() -> int:
    raw = sys.stdin.read()
    try:
        hook_input = parse_hook_input(raw)
        from packages.memory.memory_store import get_memory_store

        memory_store = get_memory_store()
        project_id = (
            hook_input.project_id_override
            or resolve_project_id(hook_input.cwd, memory_store=memory_store)
        )
        if not project_id:
            print(format_empty_hook_output(), end="", flush=True)
            return 0

        t0 = time.perf_counter()
        naive = simulate_naive_agent_exploration(
            project_id,
            hook_input.prompt,
            memory_store=memory_store,
        )
        from services.ingestion.index_store import ProjectIndexStore
        from packages.context.benchmark import _read_full_file

        root = ProjectIndexStore(memory_store).get_project_root(project_id) or ""
        parts = []
        for path in naive["paths"]:
            content = _read_full_file(root, path) if root else None
            if content:
                parts.append(f"// FILE: {path}\n{content}")
        combined = "\n\n".join(parts)
        additional = _format_naive_context(combined)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        if os.getenv("OVERHAUST_INTEGRATION_DEBUG", "").strip().lower() in {"1", "true", "yes"}:
            estimator = TokenEstimator()
            debug = {
                "hook": "naive_full_files",
                "project_id": project_id,
                "relevant_files": naive["paths"],
                "context_bytes": len(additional.encode("utf-8")),
                "estimated_context_tokens": estimator.estimate_tokens(additional),
                "estimated_naive_tokens": naive["estimated_context_tokens"],
                "latency_ms": latency_ms,
            }
            line = json.dumps(debug)
            print(line, file=sys.stderr)
            debug_file = os.getenv("OVERHAUST_INTEGRATION_DEBUG_FILE", "").strip()
            if debug_file:
                with open(debug_file, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")

        print(format_hook_output(additional), end="", flush=True)
        return 0
    except Exception:
        print(format_empty_hook_output(), end="", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
