"""
Safe observability for agent hook integrations.

Never logs full prompts or source snippets by default.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("overhaust.integration")


def _debug_enabled() -> bool:
    return os.getenv("OVERHAUST_INTEGRATION_DEBUG", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def prompt_hash(prompt: str) -> str:
    """SHA-256 prefix for correlation without storing the full prompt."""
    digest = hashlib.sha256((prompt or "").encode("utf-8")).hexdigest()
    return digest[:12]


@dataclass
class InterceptionDebugReport:
    prompt_length: int = 0
    prompt_hash: str = ""
    project_id: str = ""
    relevant_files: List[str] = field(default_factory=list)
    relevant_symbols: List[str] = field(default_factory=list)
    context_bytes: int = 0
    estimated_context_tokens: int = 0
    estimated_naive_tokens: Optional[int] = None
    reduction_pct: Optional[float] = None
    latency_ms: int = 0
    code_flow_used: bool = False
    insufficient_evidence: bool = False
    injection_mode: str = "codex_additional_context"
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def emit_debug_report(report: InterceptionDebugReport) -> None:
    """Write structured debug JSON to stderr (and optional file)."""
    if not _debug_enabled() and not report.error:
        return

    payload = report.to_dict()
    line = json.dumps(payload, separators=(",", ":"))

    if _debug_enabled():
        print(line, file=__import__("sys").stderr, flush=True)

    debug_file = os.getenv("OVERHAUST_INTEGRATION_DEBUG_FILE", "").strip()
    if debug_file:
        path = os.path.expanduser(debug_file)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    if report.error:
        logger.warning(
            "integration_debug project_id=%s error=%s latency_ms=%d",
            report.project_id or "-",
            report.error,
            report.latency_ms,
        )
