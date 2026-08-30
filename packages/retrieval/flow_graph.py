"""
Evidence graph abstractions and path scoring for code-flow reconstruction.

In-memory only — no graph database. Used by code_flow beam search.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

from packages.context.relevance import _keywords
from packages.retrieval.dart_evidence import (
    EDGE_ADAPTER_BOUNDARY,
    EDGE_CALLER,
    EDGE_CONSTRUCTOR,
    EDGE_DIRECT_CALL,
    EDGE_EXPORT,
    EDGE_IMPORT,
    EDGE_INHERITANCE,
    EDGE_PLATFORM_CHANNEL,
    EDGE_QUERY_MATCH,
    EDGE_SAME_FILE_CALLER,
    MEDIUM_EDGE_TYPES,
    STRONG_EDGE_TYPES,
    WEAK_EDGE_TYPES,
)
from packages.retrieval.index_ranking import classify_code_layer, is_flow_traversal_excluded_symbol

# Generic destination tags inferred from query + indexed metadata (not project-specific).
_DESTINATION_MARKERS: Dict[str, FrozenSet[str]] = {
    "kitchen": frozenset({"kitchen", "kot", "cook", "chef", "prep", "food"}),
    "printer": frozenset({"printer", "print", "printing", "escpos", "receipt", "ticket"}),
    "transport": frozenset({"transport", "adapter", "bluetooth", "usb", "serial", "socket"}),
    "device": frozenset({"device", "hardware", "quikot", "esp32", "peripheral"}),
    "database": frozenset({"database", "db", "sqlite", "postgres", "storage", "persist"}),
    "api": frozenset({"api", "backend", "network", "http", "rest", "graphql"}),
    "ui": frozenset({"widget", "screen", "view", "page", "ui", "display"}),
    "notification": frozenset({"notify", "notification", "alert", "push", "broadcast"}),
    "queue": frozenset({"queue", "job", "enqueue", "worker", "pipeline"}),
    "external": frozenset({"external", "third", "integration", "webhook"}),
}

# Stems, so generate/generates/generated/generation all match without a stemmer.
# An interrogative like "where is" is deliberately *not* an origin signal on its
# own — see query_asks_about_generation().
_GENERATION_STEMS = (
    "generat",
    "creat",
    "defin",
    "construct",
    "instantiat",
    "produc",
    "originat",
    "origin",
    "build",
    "built",
    "assembl",
)

_FORWARD_PHRASES = (
    "what happens after",
    "after an",
    "after a",
    "reach",
    "how does",
    "how is",
    "sent to",
    "flow",
    "happen",
    "happens",
)

_DELIVERY_PHRASES = (
    "sent to",
    "reach",
    "deliver",
    "delivers",
    "dispatch",
    "route",
    "transmit",
)

_HARDWARE_PHRASES = (
    "hardware",
    "device",
    "communicate",
    "bluetooth",
    "usb",
    "adapter",
    "transport",
)

_STATE_PHRASES = (
    "marked ready",
    "becomes ready",
    "state",
    "status",
    "ready",
    "marked",
)

_ADAPTER_PATH_MARKERS = ("/adapters/", "/adapter/", "/transport/", "/hardware/")
_ADAPTER_SYMBOL_MARKERS = ("adapter", "protocol", "transport", "gateway", "client")
_TRANSPORT_METHODS = frozenset({"send", "deliver", "write", "transmit", "publish", "encode"})

EDGE_STRENGTH: Dict[str, float] = {
    EDGE_DIRECT_CALL: 1.0,
    EDGE_CONSTRUCTOR: 0.92,
    EDGE_ADAPTER_BOUNDARY: 0.90,
    EDGE_PLATFORM_CHANNEL: 0.88,
    EDGE_INHERITANCE: 0.78,
    EDGE_CALLER: 0.68,
    EDGE_SAME_FILE_CALLER: 0.62,
    EDGE_QUERY_MATCH: 0.55,
    EDGE_EXPORT: 0.38,
    EDGE_IMPORT: 0.28,
}

# Per-step cost of a caller (backward) edge. Any question that names a direction
# — what happens next, where something is produced, how data reaches hardware —
# is answered badly by reverse causality, so backward steps must lose to forward
# evidence wherever forward evidence exists. They stay *possible* rather than
# forbidden: when a seed has no downstream egress, "what reaches this" is the
# only honest answer available.
_BACKWARD_STEP_PENALTY_DIRECTED = 0.35
_BACKWARD_STEP_PENALTY_GENERAL = 0.10


def backward_step_penalty(intent_kind: str) -> float:
    """Score cost for one backward step under the given intent."""
    if not intent_kind or intent_kind == "general":
        return _BACKWARD_STEP_PENALTY_GENERAL
    return _BACKWARD_STEP_PENALTY_DIRECTED


@dataclass
class FlowTraversalIntent:
    """Generic traversal intent derived from query phrasing."""

    kind: str = "general"
    prefer_forward: bool = True
    prefer_backward: bool = False
    destination_tags: Set[str] = field(default_factory=set)


@dataclass
class PartialFlowPath:
    """A candidate path during beam search."""

    steps: List[Any]
    score: float
    weak_edges: int = 0
    strong_edges: int = 0
    import_edges: int = 0

    @property
    def current(self):
        return self.steps[-1]

    @property
    def committed_direction(self) -> str:
        """
        Direction this path has already committed to, or "" while undecided.

        The seed carries no relationship, so the first edge after it fixes the
        story the path is telling: downstream ("what this reaches") or upstream
        ("what reaches this").
        """
        for step in self.steps[1:]:
            direction = getattr(step, "direction", "forward") or "forward"
            return direction
        return ""

    def visited_keys(self) -> Set[Tuple[str, str]]:
        return {(s.file, s.symbol or "") for s in self.steps}


def direction_is_coherent(next_direction: str, partial: PartialFlowPath) -> bool:
    """
    True when adding a step of ``next_direction`` keeps one causal story.

    A path that alternates forward and backward edges reads as a sequence but
    is not one: ``A → B ← C → D`` renders as a four-step process while actually
    describing three unrelated relationships. Once a direction is committed,
    every later step must agree with it.
    """
    committed = partial.committed_direction
    if not committed:
        return True
    return (next_direction or "forward") == committed


def query_asks_about_generation(query: str) -> bool:
    """
    True when the question is about where something is *produced*.

    A bare interrogative is not enough. "Where are orders sent to the printer?"
    and "Where is the KOT generated?" both open with "where", but only the second
    asks about origin — the first is a delivery question. Requiring a generation
    verb keeps the interrogative from hijacking traversal policy.
    """
    q_lower = (query or "").strip().lower()
    return any(stem in q_lower for stem in _GENERATION_STEMS)


def classify_flow_traversal_intent(query: str) -> FlowTraversalIntent:
    """Classify how traversal should expand (generic, not project-specific)."""
    q_lower = (query or "").strip().lower()
    terms = set(_keywords(query))
    destinations: Set[str] = set()

    for tag, markers in _DESTINATION_MARKERS.items():
        if terms.intersection(markers) or any(m in q_lower for m in markers):
            destinations.add(tag)

    if query_asks_about_generation(query):
        return FlowTraversalIntent(
            kind="origin_generation",
            prefer_forward=True,
            prefer_backward=True,
            destination_tags=destinations,
        )
    if any(p in q_lower for p in _STATE_PHRASES):
        return FlowTraversalIntent(
            kind="state_transition",
            prefer_forward=True,
            prefer_backward=False,
            destination_tags=destinations,
        )
    if (
        any(p in q_lower for p in _HARDWARE_PHRASES)
        or destinations.intersection({"device", "transport"})
    ):
        return FlowTraversalIntent(
            kind="hardware_transport",
            prefer_forward=True,
            prefer_backward=True,
            destination_tags=destinations or {"device", "transport"},
        )
    if any(p in q_lower for p in _FORWARD_PHRASES):
        return FlowTraversalIntent(
            kind="forward_process",
            prefer_forward=True,
            prefer_backward=True,
            destination_tags=destinations,
        )
    if any(p in q_lower for p in _DELIVERY_PHRASES):
        return FlowTraversalIntent(
            kind="delivery_destination",
            prefer_forward=True,
            prefer_backward=True,
            destination_tags=destinations,
        )
    return FlowTraversalIntent(
        kind="general",
        prefer_forward=True,
        prefer_backward=False,
        destination_tags=destinations,
    )


def edge_strength(edge_type: str) -> float:
    return EDGE_STRENGTH.get(edge_type, 0.3)


def is_strong_edge(edge_type: str) -> bool:
    return edge_type in STRONG_EDGE_TYPES or edge_type in {
        EDGE_ADAPTER_BOUNDARY,
        EDGE_CALLER,
        EDGE_SAME_FILE_CALLER,
    }


def is_weak_edge(edge_type: str) -> bool:
    return edge_type in WEAK_EDGE_TYPES


def is_medium_edge(edge_type: str) -> bool:
    return edge_type in MEDIUM_EDGE_TYPES


def detect_adapter_boundary(
    source_file: str,
    source_symbol: str,
    source_kind: str,
    target_file: str,
    target_symbol: str,
    target_kind: str,
    base_edge_type: str,
) -> bool:
    """True when edge crosses a service→adapter/protocol/transport boundary."""
    if base_edge_type not in (EDGE_DIRECT_CALL, EDGE_CONSTRUCTOR, EDGE_PLATFORM_CHANNEL):
        return False

    src_path = (source_file or "").lower()
    tgt_path = (target_file or "").lower()
    tgt_sym = (target_symbol or "").lower()

    src_layer = classify_code_layer(source_file, source_symbol, source_kind)
    tgt_layer = classify_code_layer(target_file, target_symbol, target_kind)

    if tgt_layer == "transport" or target_kind == "platform_channel":
        return True
    if any(m in tgt_path for m in _ADAPTER_PATH_MARKERS):
        return True
    if any(m in tgt_sym for m in _ADAPTER_SYMBOL_MARKERS):
        return True
    if tgt_sym in _TRANSPORT_METHODS and src_layer in ("service", "unknown"):
        return True
    if src_layer == "service" and any(m in tgt_path for m in ("/adapters/", "/hardware/")):
        return True
    return False


def destination_relevance(
    query: str,
    file_path: str,
    symbol: str,
    symbol_kind: str,
    intent: FlowTraversalIntent,
) -> float:
    """Score how close a step is to query-implied destinations (0–1)."""
    if not intent.destination_tags:
        return 0.0

    path_lower = (file_path or "").lower()
    sym_lower = (symbol or "").lower()
    layer = classify_code_layer(file_path, symbol, symbol_kind)
    score = 0.0

    tag_path_hints = {
        "kitchen": ("/kitchen/", "kitchen", "kot"),
        "printer": ("/printing/", "print", "printer", "escpos"),
        "transport": ("/transport/", "/adapters/", "adapter", "transport"),
        "device": ("/hardware/", "device", "quikot"),
        "database": ("/data/", "/db/", "database", "persist"),
        "api": ("/network/", "/api/", "backend", "client"),
        "ui": ("/widgets/", "/screens/", "/ui/"),
        "notification": ("notify", "notification", "alert"),
        "queue": ("queue", "job", "enqueue"),
        "external": ("external", "integration", "webhook"),
    }

    for tag in intent.destination_tags:
        hints = tag_path_hints.get(tag, ())
        if any(h in path_lower or h in sym_lower for h in hints):
            score += 0.35
        if tag == "kitchen" and layer == "service" and any(v in sym_lower for v in ("order", "kitchen", "kot", "enqueue")):
            score += 0.2
        if tag in ("printer", "transport", "device") and layer in ("service", "transport"):
            score += 0.15

    return min(score, 1.0)


def classify_step_path_role(
    step,
    intent: FlowTraversalIntent,
    *,
    is_seed: bool = False,
) -> str:
    """Classify step as process, supporting, or context evidence."""
    if is_seed or step.edge_type == EDGE_QUERY_MATCH:
        return "process"

    layer = classify_code_layer(step.file, step.symbol, step.symbol_type)
    edge = step.edge_type or ""

    if edge in WEAK_EDGE_TYPES and layer == "model":
        return "supporting"
    if getattr(step, "direction", "forward") == "backward" and intent.kind in (
        "forward_process",
        "delivery_destination",
        "origin_generation",
        "hardware_transport",
    ):
        return "supporting"
    if layer == "ui" and intent.kind != "general":
        return "context"
    if is_strong_edge(edge):
        if layer in ("service", "transport") or edge in (
            EDGE_ADAPTER_BOUNDARY,
            EDGE_PLATFORM_CHANNEL,
        ):
            return "process"
    if layer == "model":
        return "supporting"
    if edge in WEAK_EDGE_TYPES:
        return "supporting"
    return "process"


def score_flow_path(
    steps: List[Any],
    query: str,
    intent: FlowTraversalIntent,
) -> float:
    """Score a complete or partial path (higher is better)."""
    if not steps:
        return 0.0

    score = steps[0].relevance_score * 1.5
    score += steps[0].trust_score * 0.2

    strong = 0
    weak = 0
    imports = 0
    dest_hits = 0.0
    roles = []

    for i, step in enumerate(steps):
        role = classify_step_path_role(step, intent, is_seed=(i == 0))
        roles.append(role)
        if i == 0:
            continue

        strength = edge_strength(step.edge_type)
        score += strength * 0.18
        score += step.relevance_score * 0.08
        score += step.trust_score * 0.05

        dest = destination_relevance(
            query, step.file, step.symbol, step.symbol_type, intent
        )
        dest_hits += dest
        score += dest * 0.14

        if is_strong_edge(step.edge_type):
            strong += 1
        if is_weak_edge(step.edge_type):
            weak += 1
            score -= 0.07
        if step.edge_type == EDGE_IMPORT:
            imports += 1
            score -= 0.05

        if getattr(step, "direction", "forward") == "backward":
            score -= backward_step_penalty(intent.kind)

        layer = classify_code_layer(step.file, step.symbol, step.symbol_type)
        if layer == "model" and intent.kind in (
            "forward_process",
            "delivery_destination",
            "hardware_transport",
        ):
            score -= 0.06
        if is_flow_traversal_excluded_symbol(step.symbol, step.file, step.symbol_type):
            score -= 0.2

        if role == "context":
            score -= 0.08
        elif role == "supporting":
            score -= 0.04

    score += min(dest_hits, 0.5)

    if imports >= 2 and strong == 0:
        score -= 0.3
    if weak >= 3 and strong == 0:
        score -= 0.25
    if intent.kind in ("forward_process", "delivery_destination"):
        edge_types = [s.edge_type for s in steps[1:]]
        directions = [getattr(s, "direction", "forward") for s in steps[1:]]
        if EDGE_IMPORT in edge_types and any(
            d == "backward" for d in directions
        ):
            score -= 0.45

    keys = [(s.file, s.symbol or "") for s in steps]
    repeats = len(keys) - len(set(keys))
    score -= repeats * 0.18

    process_count = sum(1 for r in roles if r == "process")
    if process_count >= 2:
        score += 0.1

    # Convergence hint: reward transport/service layers late in path for delivery queries
    if intent.kind in ("delivery_destination", "hardware_transport", "forward_process"):
        tail = steps[-3:] if len(steps) >= 3 else steps
        for step in tail:
            layer = classify_code_layer(step.file, step.symbol, step.symbol_type)
            if layer in ("service", "transport") and is_strong_edge(step.edge_type):
                score += 0.06

    return score


def should_expand_backward(
    intent: FlowTraversalIntent,
    depth: int,
    has_strong_forward: bool = False,
) -> bool:
    """Allow caller expansion when query intent or depth warrants it.

    Origin-generation queries walk downstream only — never expand callers.
    Hardware queries prefer the downstream pipeline; backward callers are only
    a fallback when the current node has no strong forward edges.
    """
    if not intent.prefer_backward:
        return False
    if intent.kind in ("forward_process", "delivery_destination"):
        return False
    if intent.kind == "origin_generation":
        return False
    if intent.kind == "hardware_transport":
        return not has_strong_forward
    return False


def backward_edge_allowed(
    edge_type: str,
    partial: PartialFlowPath,
    intent: FlowTraversalIntent,
    *,
    has_strong_forward: bool = False,
) -> bool:
    """
    Caller edges are allowed only when justified by intent/path state.

    ``has_strong_forward`` is the caller's knowledge of whether the current node
    has downstream egress. It is a parameter rather than something re-derived
    here because only the discovery layer can see the node's outgoing edges;
    an earlier version called ``should_expand_backward()`` without it, which
    defaulted the flag to ``False`` and made the "backward is a fallback only"
    policy unenforceable at this call site.
    """
    if edge_type not in (EDGE_CALLER, EDGE_SAME_FILE_CALLER):
        return True
    if not intent.prefer_backward:
        return False
    if intent.kind in ("forward_process", "delivery_destination"):
        return False
    if intent.kind == "origin_generation":
        return False
    # A downstream commitment cannot be reconciled with an upstream step.
    if not direction_is_coherent("backward", partial):
        return False
    if has_strong_forward:
        return False
    from packages.retrieval.index_ranking import classify_code_layer

    current = partial.current
    layer = classify_code_layer(current.file, current.symbol, current.symbol_type)
    if layer in ("model", "ui"):
        return False
    if intent.kind == "hardware_transport":
        return True
    return partial.strong_edges < 2
