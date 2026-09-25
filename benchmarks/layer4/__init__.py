"""
Layer 4 — real coding-agent session instrumentation.

Measures isolated agent sessions (Codex CLI first). It does not change
Layer 3, retrieval, or the production context seam. OverHaust context
reaches the agent only through the existing host integration.
"""

from benchmarks.layer4.schema import Layer4SessionResult, MetricFigure

PROTOCOL_VERSION = "layer4-protocol-v1"
SCHEMA_VERSION = "layer4-session-v1"
RUN_SCHEMA_VERSION = "layer4-run-v1"
TARGET_CODEX_VERSION = "0.146.0"

__all__ = [
    "PROTOCOL_VERSION",
    "SCHEMA_VERSION",
    "RUN_SCHEMA_VERSION",
    "TARGET_CODEX_VERSION",
    "Layer4SessionResult",
    "MetricFigure",
]
