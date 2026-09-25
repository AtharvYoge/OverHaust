"""
Layer 3 — strict experiment contract, pairing, OpenAI-compatible runner.

Does not modify production OverHaust context/retrieval/integrations.
"""

from benchmarks.layer3.contract import ExperimentContract, FieldPresence
from benchmarks.layer3.pairing import PairValidationResult, validate_layer3_pair
from benchmarks.layer3.states import RunState

__all__ = [
    "ExperimentContract",
    "FieldPresence",
    "PairValidationResult",
    "RunState",
    "validate_layer3_pair",
]
