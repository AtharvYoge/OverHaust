"""
Layer-3 run states and aggregation buckets.

Failed / incomplete / unpaired runs are never silently dropped.
"""

from __future__ import annotations

from enum import Enum


class RunState(str, Enum):
    SUCCESS = "SUCCESS"
    API_ERROR = "API_ERROR"
    TOOL_ERROR = "TOOL_ERROR"
    TIMEOUT = "TIMEOUT"
    MODEL_ERROR = "MODEL_ERROR"
    INCOMPLETE = "INCOMPLETE"
    CORRECTNESS_UNEVALUABLE = "CORRECTNESS_UNEVALUABLE"
    CANCELLED = "CANCELLED"


PRIMARY_ANALYSIS_STATES = frozenset({RunState.SUCCESS})
SEPARATE_REPORT_STATES = frozenset({
    RunState.API_ERROR,
    RunState.TOOL_ERROR,
    RunState.TIMEOUT,
    RunState.MODEL_ERROR,
    RunState.INCOMPLETE,
    RunState.CORRECTNESS_UNEVALUABLE,
    RunState.CANCELLED,
})
