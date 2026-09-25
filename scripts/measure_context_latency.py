#!/usr/bin/env python3
"""
Phase 14 latency profiler for get-relevant-context.

Breaks down search, snippet retrieval, and full assembly latency.
Compares in-process cold/warm runs and optional HTTP API timing.

Usage:
  python3 scripts/measure_context_latency.py --project-id labkot
  python3 scripts/measure_context_latency.py --project-id labkot --http http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LABKOT_PROMPT = (
    "Add support for multiple kitchen printers and route each order "
    "to the appropriate printer."
)


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def measure_search(project_id: str, prompt: str, memory_store) -> Dict[str, Any]:
    from packages.context.retrieval import search_project_knowledge, search_project_knowledge_scored

    t0 = time.perf_counter()
    results = search_project_knowledge(project_id, prompt, memory_store=memory_store, limit=10)
    search_ms = _ms(t0)

    t1 = time.perf_counter()
    scored = search_project_knowledge_scored(
        project_id, prompt, memory_store=memory_store, limit=20,
    )
    scored_ms = _ms(t1)

    return {
        "search_latency_ms": search_ms,
        "scored_search_latency_ms": scored_ms,
        "result_count": len(results),
        "scored_count": len(scored),
    }


def measure_file_reads(project_id: str, prompt: str, memory_store) -> Dict[str, Any]:
    from packages.context.benchmark import simulate_naive_agent_exploration

    t0 = time.perf_counter()
    naive = simulate_naive_agent_exploration(
        project_id, prompt, memory_store=memory_store, search_limit=10,
    )
    total_ms = _ms(t0)
    return {
        "naive_total_latency_ms": total_ms,
        "files_read": naive["files_read"],
        "search_plus_disk_read_ms": naive["latency_ms"],
    }


def measure_assembly_runs(
    project_id: str,
    prompt: str,
    memory_store,
    runs: int = 3,
) -> Dict[str, Any]:
    from packages.context.agent_context import invoke_context_request

    timings: List[int] = []
    last_metrics: Dict[str, Any] = {}
    for _ in range(runs):
        t0 = time.perf_counter()
        response = invoke_context_request(project_id, prompt, memory_store=memory_store)
        wall_ms = _ms(t0)
        timings.append(wall_ms)
        last_metrics = {
            "metrics_latency_ms": response.metrics.latency_ms,
            "files_count": response.metrics.files_count,
            "symbols_count": response.metrics.symbols_count,
            "response_bytes": response.metrics.response_bytes,
        }

    return {
        "runs": runs,
        "wall_latency_ms": timings,
        "cold_wall_ms": timings[0] if timings else 0,
        "warm_wall_ms_avg": round(sum(timings[1:]) / max(len(timings) - 1, 1)),
        **last_metrics,
    }


def measure_http(
    base_url: str,
    project_id: str,
    prompt: str,
    runs: int = 2,
) -> Dict[str, Any]:
    import urllib.error
    import urllib.request

    url = f"{base_url.rstrip('/')}/api/v1/get-relevant-context"
    body = json.dumps({"project_id": project_id, "prompt": prompt}).encode("utf-8")
    timings: List[Dict[str, Any]] = []

    for i in range(runs):
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            http_ms = _ms(t0)
            metrics = payload.get("metrics", {})
            timings.append({
                "run": i + 1,
                "http_total_ms": http_ms,
                "context_assembly_ms": metrics.get("latency_ms"),
                "response_bytes": metrics.get("response_bytes"),
            })
        except urllib.error.URLError as exc:
            return {"error": str(exc), "url": url}

    return {
        "url": url,
        "runs": timings,
        "first_http_ms": timings[0]["http_total_ms"] if timings else None,
        "warm_http_ms": timings[-1]["http_total_ms"] if len(timings) > 1 else None,
    }


def measure_agent_init() -> Dict[str, Any]:
    """Measure OverhaustAgent singleton first-touch cost in a subprocess."""
    code = """
import time, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from packages.agent.autonomous_agent import get_overhaust_agent
t0 = time.perf_counter()
get_overhaust_agent()
init_ms = int((time.perf_counter() - t0) * 1000)
print(init_ms)
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=60,
    )
    if proc.returncode != 0:
        return {"error": proc.stderr.strip()}
    return {"agent_init_ms_subprocess": int(proc.stdout.strip())}


def run_profile(
    project_id: str,
    prompt: str,
    *,
    http_url: Optional[str] = None,
    memory_store=None,
) -> Dict[str, Any]:
    if memory_store is None:
        from packages.memory.memory_store import get_memory_store
        memory_store = get_memory_store()

    return {
        "project_id": project_id,
        "prompt": prompt,
        "search": measure_search(project_id, prompt, memory_store),
        "naive_file_reads": measure_file_reads(project_id, prompt, memory_store),
        "assembly": measure_assembly_runs(project_id, prompt, memory_store),
        "agent_init_subprocess": measure_agent_init(),
        "http": measure_http(http_url, project_id, prompt) if http_url else None,
        "interpretation": (
            "First in-process assembly run may include cold imports (tiktoken, retrieval). "
            "HTTP first request adds OverhaustAgent lazy init on top. "
            "Warm runs (~150-200ms) reflect steady-state context assembly."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile context API latency")
    parser.add_argument("--project-id", default="labkot")
    parser.add_argument("--prompt", default=LABKOT_PROMPT)
    parser.add_argument("--http", default="", help="Optional API base URL")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_profile(
        args.project_id,
        args.prompt,
        http_url=args.http or None,
    )

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"Project: {report['project_id']}")
    print(f"Prompt:  {report['prompt']}\n")

    s = report["search"]
    print("Search")
    print(f"  keyword search:       {s['search_latency_ms']} ms ({s['result_count']} hits)")
    print(f"  scored search:        {s['scored_search_latency_ms']} ms ({s['scored_count']} hits)")

    n = report["naive_file_reads"]
    print("\nNaive baseline (search + full file reads)")
    print(f"  total:                {n['naive_total_latency_ms']} ms")
    print(f"  files read:           {n['files_read']}")

    a = report["assembly"]
    print("\nOverHaust assembly (invoke_context_request)")
    print(f"  cold wall:            {a['cold_wall_ms']} ms")
    print(f"  warm wall avg:        {a['warm_wall_ms_avg']} ms")
    print(f"  metrics (last run):   {a['metrics_latency_ms']} ms")
    print(f"  response bytes:       {a['response_bytes']}")

    init = report["agent_init_subprocess"]
    if "agent_init_ms_subprocess" in init:
        print(f"\nAgent init (subprocess): {init['agent_init_ms_subprocess']} ms")

    if report.get("http"):
        h = report["http"]
        if "error" in h:
            print(f"\nHTTP: skipped ({h['error']})")
        else:
            print("\nHTTP API")
            for run in h["runs"]:
                print(
                    f"  run {run['run']}: http={run['http_total_ms']} ms "
                    f"assembly={run['context_assembly_ms']} ms"
                )

    print(f"\nNote: {report['interpretation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
