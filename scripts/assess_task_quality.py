#!/usr/bin/env python3
"""
Phase 14 read/plan task quality assessment for LabKOT multi-printer task.

Evaluates whether OverHaust context (and naïve baseline) surface the files,
symbols, and architectural cues needed to implement the task — without
running a live coding agent or modifying the repository.

Usage:
  python3 scripts/assess_task_quality.py --project-id labkot
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LABKOT_PROMPT = (
    "Add support for multiple kitchen printers and route each order "
    "to the appropriate printer."
)

# Expected implementation locus for this controlled task (LabKOT fixture + real index).
EXPECTED_FILES = {
    "lib/services/printing/kitchen_print_service.dart",
    "lib/services/printing/kitchen_print_router.dart",
}
EXPECTED_SYMBOLS = {
    "KitchenPrintService",
    "KitchenPrintRoute",
}
OPTIONAL_SYMBOLS = {
    "enableKitchenPrinterWithDefault",
    "KitchenPrintJob",
}
ARCHITECTURE_CUES = (
    "route",
    "router",
    "printer",
    "kitchen",
    "order",
    "print",
)


def _normalize_path(path: str) -> str:
    return (path or "").replace("\\", "/").lstrip("/")


def _score_paths(paths: Set[str]) -> Dict[str, Any]:
    normalized = {_normalize_path(p) for p in paths}
    matched = {p for p in EXPECTED_FILES if p in normalized}
    missing = EXPECTED_FILES - matched
    return {
        "matched_files": sorted(matched),
        "missing_files": sorted(missing),
        "files_score_pct": round(len(matched) / max(len(EXPECTED_FILES), 1) * 100, 1),
    }


def _score_symbols(symbols: Set[str]) -> Dict[str, Any]:
    matched = {s for s in EXPECTED_SYMBOLS if s in symbols}
    optional = {s for s in OPTIONAL_SYMBOLS if s in symbols}
    missing = EXPECTED_SYMBOLS - matched
    return {
        "matched_symbols": sorted(matched),
        "optional_symbols": sorted(optional),
        "missing_symbols": sorted(missing),
        "symbols_score_pct": round(len(matched) / max(len(EXPECTED_SYMBOLS), 1) * 100, 1),
    }


def _score_architecture(text: str) -> Dict[str, Any]:
    lower = (text or "").lower()
    cues_found = [c for c in ARCHITECTURE_CUES if c in lower]
    return {
        "architecture_cues_found": cues_found,
        "architecture_score_pct": round(len(cues_found) / len(ARCHITECTURE_CUES) * 100, 1),
    }


def _extract_plan_signals(context_text: str) -> Dict[str, Any]:
    """Heuristic plan completeness from context text (read/plan proxy)."""
    lower = context_text.lower()
    signals = {
        "mentions_service": "kitchen_print_service" in lower or "kitchenprintservice" in lower,
        "mentions_router": "kitchen_print_router" in lower or "kitchenprintroute" in lower,
        "mentions_routing": "route" in lower,
        "mentions_multiple_printers": "multiple" in lower or "printer" in lower,
        "mentions_order": "order" in lower,
    }
    passed = sum(1 for v in signals.values() if v)
    return {
        "plan_signals": signals,
        "plan_score_pct": round(passed / len(signals) * 100, 1),
    }


def assess_condition(
    label: str,
    paths: List[str],
    symbols: List[str],
    context_text: str,
) -> Dict[str, Any]:
    path_score = _score_paths(set(paths))
    symbol_score = _score_symbols(set(symbols))
    arch_score = _score_architecture(context_text)
    plan_score = _extract_plan_signals(context_text)

    composite = round(
        (
            path_score["files_score_pct"]
            + symbol_score["symbols_score_pct"]
            + arch_score["architecture_score_pct"]
            + plan_score["plan_score_pct"]
        )
        / 4,
        1,
    )

    return {
        "label": label,
        "paths": paths,
        "symbols": symbols,
        "path_quality": path_score,
        "symbol_quality": symbol_score,
        "architecture_quality": arch_score,
        "plan_quality": plan_score,
        "composite_quality_score_pct": composite,
        "task_completable_read_plan": (
            path_score["files_score_pct"] >= 100
            and symbol_score["symbols_score_pct"] >= 100
            and plan_score["plan_score_pct"] >= 60
        ),
    }


def run_assessment(project_id: str, prompt: str, memory_store=None) -> Dict[str, Any]:
    from packages.context.agent_context import invoke_context_request
    from packages.context.benchmark import simulate_naive_agent_exploration
    from packages.context.benchmark import measure_overhaust_context
    from packages.tokenization.token_estimator import TokenEstimator

    if memory_store is None:
        from packages.memory.memory_store import get_memory_store
        memory_store = get_memory_store()

    naive = simulate_naive_agent_exploration(project_id, prompt, memory_store=memory_store)
    overhaust = measure_overhaust_context(project_id, prompt, memory_store=memory_store)
    payload = overhaust["payload"]

    # Build naive context text from full files (fair comparison content)
    from services.ingestion.index_store import ProjectIndexStore
    from packages.context.benchmark import _read_full_file

    root = ProjectIndexStore(memory_store).get_project_root(project_id) or ""
    naive_parts: List[str] = []
    for path in naive["paths"]:
        content = _read_full_file(root, path) if root else None
        if content:
            naive_parts.append(f"// FILE: {path}\n{content}")
    naive_context = "\n\n".join(naive_parts)

    oh_context = payload.get("context", "")
    oh_symbols = [s.get("name", "") for s in payload.get("relevant_symbols", [])]

    naive_assessment = assess_condition(
        "naive_full_files",
        naive["paths"],
        _extract_symbols_from_text(naive_context),
        naive_context,
    )
    oh_assessment = assess_condition(
        "overhaust_compact",
        overhaust["paths"],
        oh_symbols,
        oh_context,
    )

    estimator = TokenEstimator()
    return {
        "project_id": project_id,
        "prompt": prompt,
        "assessment_mode": "read_plan_proxy",
        "note": (
            "Scores whether context surfaces correct files/symbols/architecture for the task. "
            "Does NOT execute a live coding agent or modify the repository."
        ),
        "naive": {
            **naive_assessment,
            "estimated_context_tokens": naive["estimated_context_tokens"],
            "latency_ms": naive["latency_ms"],
        },
        "overhaust": {
            **oh_assessment,
            "estimated_context_tokens": overhaust["estimated_context_tokens"],
            "latency_ms": overhaust["latency_ms"],
        },
        "quality_parity": (
            oh_assessment["composite_quality_score_pct"]
            >= naive_assessment["composite_quality_score_pct"] - 5
        ),
        "token_reduction_pct": round(
            (1 - overhaust["estimated_context_tokens"] / max(naive["estimated_context_tokens"], 1))
            * 100,
            2,
        ),
    }


def _extract_symbols_from_text(text: str) -> List[str]:
    found: Set[str] = set()
    for sym in EXPECTED_SYMBOLS | OPTIONAL_SYMBOLS:
        if sym in text:
            found.add(sym)
    for match in re.finditer(r"class\s+(\w+)", text):
        found.add(match.group(1))
    return sorted(found)


def main() -> int:
    parser = argparse.ArgumentParser(description="Assess read/plan task quality")
    parser.add_argument("--project-id", default="labkot")
    parser.add_argument("--prompt", default=LABKOT_PROMPT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_assessment(args.project_id, args.prompt)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"Project: {report['project_id']}")
    print(f"Mode:    {report['assessment_mode']}\n")

    for key in ("naive", "overhaust"):
        c = report[key]
        print(f"{c['label'].upper()}")
        print(f"  composite quality: {c['composite_quality_score_pct']}%")
        print(f"  files matched:       {c['path_quality']['matched_files']}")
        print(f"  symbols matched:     {c['symbol_quality']['matched_symbols']}")
        print(f"  plan signals:        {c['plan_quality']['plan_signals']}")
        print(f"  tokens (est.):       ~{c['estimated_context_tokens']}")
        print(f"  latency:             {c['latency_ms']} ms")
        print(f"  read/plan viable:    {c['task_completable_read_plan']}\n")

    print(f"Quality parity (OverHaust within 5% of naive): {report['quality_parity']}")
    print(f"Token reduction: {report['token_reduction_pct']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
