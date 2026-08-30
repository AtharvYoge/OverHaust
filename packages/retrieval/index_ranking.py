"""
Intent-aware ranking adjustments for project index retrieval.

Penalizes generic boilerplate symbols/paths and boosts domain-specific hits
for architecture and code-flow queries. Applied as a relevance post-processor
before trust — never invents evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from packages.context.relevance import ScoredMemory, _keywords
from packages.shared.config import get_index_generic_penalty, get_index_weak_kw_threshold

_FLOW_PHRASES = (
    "how does",
    "what happens",
    "where is",
    "where are",
    "communicate with",
    "after",
    "reach",
    "flow",
    "path",
    "what service",
    "sent to",
    "marked ready",
    "when a",
)

_ARCH_PHRASES = (
    "architecture",
    "structure",
    "module",
    "component",
    "stack",
    "design",
)

_GENERIC_SYMBOL_NAMES = frozenset({
    "copyWith",
    "registerWith",
    "AppThemeMode",
})

_FLOW_TRAVERSAL_EXCLUDED = frozenset({
    "build",
    "copyWith",
    "toString",
    "hashCode",
    "noSuchMethod",
    "runtimeType",
    "initState",
    "dispose",
    "didUpdateWidget",
    "createState",
    "didChangeDependencies",
    "deactivate",
    "reassemble",
    "setState",
    "==",
})

_GENERIC_PATH_MARKERS = (
    "/generated/",
    ".g.dart",
    "/l10n/",
    "/theme/",
    "plugin_registrant",
    "app_theme",
)

_DOMAIN_PATH_FOLDERS = (
    "kitchen/",
    "hardware/",
    "order",
)

_SHORT_PATH_TOKENS = frozenset({"app", "lib", "src", "api", "ui"})

_SERVICE_PATH_MARKERS = (
    "/services/",
    "/service/",
    "/domain/",
    "/use_cases/",
    "/usecases/",
    "/controllers/",
    "/repositories/",
    "/adapters/",
    "/transport/",
    "/handlers/",
    "/providers/",
    "/application/",
    "/core/",
    "/backend/",
)

_UI_PATH_MARKERS = (
    "/widgets/",
    "/widget/",
    "/screens/",
    "/screen/",
    "/views/",
    "/view/",
    "/components/",
    "/component/",
    "/pages/",
    "/page/",
    "/ui/",
)

_MODEL_PATH_MARKERS = (
    "/models/",
    "/model/",
    "/dto/",
    "/dtos/",
    "/entities/",
    "/entity/",
    "/types/",
    "/schemas/",
    "/schema/",
    "/data/",
)

_SERVICE_CLASS_SUFFIXES = (
    "Service",
    "Manager",
    "Controller",
    "Repository",
    "Handler",
    "UseCase",
    "Interactor",
    "Gateway",
    "Coordinator",
)

_OPERATION_VERBS = (
    "add",
    "create",
    "enqueue",
    "send",
    "deliver",
    "process",
    "update",
    "handle",
    "cancel",
    "print",
    "notify",
    "place",
    "route",
    "sync",
    "publish",
    "dispatch",
    "execute",
    "connect",
    "pair",
    "discover",
    "mark",
    "ready",
    "void",
    "submit",
    "commit",
    "save",
    "load",
    "fetch",
    "push",
    "pull",
    "broadcast",
    "emit",
    "trigger",
    "invoke",
    "call",
)

_NEGATIVE_OPERATION_MARKERS = (
    "void",
    "cancel",
    "delete",
    "remove",
    "abort",
    "rollback",
)

_FORWARD_FLOW_QUERY_TERMS = frozenset({
    "reach",
    "placed",
    "place",
    "sent",
    "after",
    "flow",
    "happen",
    "happens",
})

_INGRESS_OPERATION_VERBS = (
    "add",
    "create",
    "place",
    "enqueue",
    "send",
    "route",
    "submit",
    "dispatch",
    "accept",
    "receive",
    "generate",
    "build",
    "print",
)

_STATE_CHANGE_SEGMENTS = frozenset({
    "update",
    "mark",
    "status",
    "set",
    "change",
    "notify",
    "ready",
    "delivered",
    "void",
    "cancel",
})

_HARDWARE_QUERY_TERMS = frozenset({
    "hardware",
    "device",
    "devices",
    "adapter",
    "transport",
    "bluetooth",
    "printer",
    "usb",
})

# Max structural adjustment on normalized 0–1 relevance scale for flow seeds.
_MAX_FLOW_STRUCTURAL_BONUS = 0.36
_MAX_FLOW_STRUCTURAL_PENALTY = 0.14


@dataclass
class QueryIntent:
    kind: str
    flow: bool
    architecture: bool
    domain_terms: List[str] = field(default_factory=list)


def detect_query_intent(query: str) -> QueryIntent:
    """Detect flow/architecture intent and extract domain terms from query."""
    q_lower = (query or "").strip().lower()
    flow = any(p in q_lower for p in _FLOW_PHRASES)
    architecture = any(p in q_lower for p in _ARCH_PHRASES)

    if flow and architecture:
        kind = "flow"
    elif flow:
        kind = "flow"
    elif architecture:
        kind = "architecture"
    else:
        kind = "general"

    domain_terms = _keywords(query)
    return QueryIntent(
        kind=kind,
        flow=flow,
        architecture=architecture,
        domain_terms=domain_terms,
    )


def is_generic_symbol(name: str, file_path: str) -> bool:
    """True for boilerplate/generated symbol names."""
    if not name:
        return False
    if name in _GENERIC_SYMBOL_NAMES:
        return True
    if name.endswith("Registrant") or name.endswith("GeneratedPluginRegistrant"):
        return True
    if name.startswith("_$"):
        return True
    if is_generic_path(file_path):
        return True
    return False


def is_generic_path(file_path: str) -> bool:
    """True for generated/theme/l10n paths unlikely to answer flow queries."""
    path_lower = (file_path or "").replace("\\", "/").lower()
    return any(m in path_lower for m in _GENERIC_PATH_MARKERS)


def is_flow_traversal_excluded_symbol(
    name: str,
    file_path: str = "",
    kind: str = "",
) -> bool:
    """Symbols excluded from code-flow neighbor traversal (not from search)."""
    if not name:
        return False
    if name in _FLOW_TRAVERSAL_EXCLUDED:
        return True
    if is_generic_symbol(name, file_path):
        return True
    if kind == "platform_channel" and name.startswith("invoke:"):
        return False
    return False


def flow_path_adjustment(intent: QueryIntent, file_path: str) -> float:
    """Boost/penalty for flow walk neighbor ranking by file path layer."""
    if not (intent.flow or intent.architecture):
        return 0.0
    path_lower = (file_path or "").replace("\\", "/").lower()
    adj = 0.0
    if "/services/" in path_lower or "/providers/" in path_lower:
        adj += 20.0
    if "/models/" in path_lower:
        adj -= 15.0
    if "/widgets/" in path_lower or "/screens/" in path_lower:
        adj -= 10.0
    for folder in _DOMAIN_PATH_FOLDERS:
        if folder.rstrip("/") in path_lower:
            adj += 5.0
    return adj


def classify_code_layer(
    file_path: str,
    symbol_name: str = "",
    symbol_kind: str = "",
) -> str:
    """
    Classify an indexed hit into a structural code layer.

    Returns one of: service, transport, ui, model, unknown
    """
    path_lower = (file_path or "").replace("\\", "/").lower()
    sym = symbol_name or ""
    kind = (symbol_kind or "").lower()

    if kind == "platform_channel" or "/transport/" in path_lower:
        return "transport"
    if any(m in path_lower for m in _SERVICE_PATH_MARKERS):
        return "service"
    if any(m in path_lower for m in _UI_PATH_MARKERS):
        return "ui"
    if any(m in path_lower for m in _MODEL_PATH_MARKERS):
        return "model"
    if sym.endswith(_SERVICE_CLASS_SUFFIXES):
        return "service"
    if kind in ("class", "enum", "interface", "struct") and not sym.endswith(_SERVICE_CLASS_SUFFIXES):
        if any(m in path_lower for m in ("/lib/", "/src/")) and "service" in sym.lower():
            return "service"
    return "unknown"


def _normalized_hit_relevance(sm: ScoredMemory) -> float:
    """Normalize index hit score to 0–1 for fair flow seed comparison."""
    methods = set(sm.retrieval_methods or [])
    if methods.intersection({"index_hybrid", "index_semantic"}):
        return max(0.0, min(sm.score, 1.0))
    raw = sm.score
    if raw <= 0:
        return 0.0
    return min(raw / 8.0, 1.0)


def _symbol_has_operation_verb(symbol_name: str, verb: str) -> bool:
    """True when verb is a distinct operation in symbol_name (not a substring)."""
    if not symbol_name:
        return False
    name_lower = symbol_name.lower()
    if name_lower == verb:
        return True
    segments = _camel_segments(symbol_name)
    if verb in segments:
        return True
    if name_lower.startswith(verb) and len(name_lower) > len(verb):
        nxt = name_lower[len(verb)]
        if not nxt.isalpha() or nxt.isupper():
            return True
    return False


def operation_verb_bonus(symbol_name: str, query_terms: List[str]) -> float:
    """Boost symbols whose names suggest callable domain operations."""
    if not symbol_name:
        return 0.0
    boost = 0.0
    for verb in _OPERATION_VERBS:
        if _symbol_has_operation_verb(symbol_name, verb):
            boost += 0.035
    for term in query_terms:
        tl = term.lower()
        if len(tl) < 3:
            continue
        if tl in _OPERATION_VERBS and _symbol_has_operation_verb(symbol_name, tl):
            boost += 0.05
    return min(boost, 0.12)


def _service_class_bonus(symbol_name: str, symbol_kind: str) -> float:
    if not symbol_name:
        return 0.0
    boost = 0.0
    if symbol_name.endswith(_SERVICE_CLASS_SUFFIXES):
        boost += 0.06
    if symbol_kind in ("function", "platform_channel"):
        boost += 0.03
    return boost


def _negative_operation_penalty(symbol_name: str, query_terms: List[str]) -> float:
    """Penalize destructive ops when the query does not ask about them."""
    if not symbol_name:
        return 0.0
    q_lower = {t.lower() for t in query_terms}
    sym_lower = symbol_name.lower()
    if any(t in q_lower for t in _NEGATIVE_OPERATION_MARKERS):
        return 0.0
    if any(marker in sym_lower for marker in _NEGATIVE_OPERATION_MARKERS):
        return 0.14
    return 0.0


def _query_mentions_operation(query_terms: List[str], verb: str) -> bool:
    """True when a query term refers to an operation verb (handles delivers/placed/etc.)."""
    q_lower = {t.lower() for t in query_terms}
    state_query = bool(
        q_lower.intersection({"marked", "when", "happens", "status", "ready"})
    )
    for term in query_terms:
        tl = term.lower()
        if tl == verb:
            return True
        if tl.startswith(verb) and len(tl) > len(verb):
            if state_query and tl.endswith("ed") and tl not in ("placed",):
                continue
            return True
        if tl.endswith("s") and tl[:-1] == verb:
            return True
        if tl.endswith("es") and tl[:-2] == verb:
            return True
        if tl.endswith("ed") and (tl[:-2] == verb or tl[:-1] == verb):
            if state_query and tl not in ("placed",):
                continue
            return True
        if tl.endswith("ing") and tl[:-3] == verb:
            return True
    return False


def _query_operation_terms(query_terms: List[str]) -> set:
    """Expand query terms to referenced operation verbs."""
    found = set()
    for verb in _OPERATION_VERBS:
        if _query_mentions_operation(query_terms, verb):
            found.add(verb)
    return found


_TRANSPORT_OPERATION_VERBS = frozenset({
    "deliver",
    "send",
    "push",
    "dispatch",
    "publish",
    "connect",
    "pair",
    "discover",
    "broadcast",
    "emit",
})


_WORKFLOW_MODIFIER_SEGMENTS = frozenset({
    "paid",
    "internal",
    "workflow",
    "helper",
    "receipt",
    "status",
    "history",
    "latest",
    "pending",
})


def _symbol_is_public_operation_name(symbol_name: str, verb: str) -> bool:
    """True when symbol is a public callable whose primary name is the operation verb."""
    if not symbol_name or symbol_name.startswith("_"):
        return False
    if symbol_name.lower() == verb:
        return True
    segments = _camel_segments(symbol_name)
    if not segments or segments[0] != verb:
        return False
    if len(segments) == 1:
        return True
    if len(segments) == 2 and segments[1] not in _WORKFLOW_MODIFIER_SEGMENTS:
        return True
    return False


def _is_operational_forward_query(intent: QueryIntent) -> bool:
    """True for forward/delivery-style operational flow queries (seed ranking only)."""
    if not (intent.flow or intent.architecture):
        return False
    q_lower = {t.lower() for t in intent.domain_terms}
    if q_lower.intersection(_FORWARD_FLOW_QUERY_TERMS):
        return True
    ops = _query_operation_terms(intent.domain_terms)
    if ops.intersection(_INGRESS_OPERATION_VERBS):
        return True
    if ops.intersection(_TRANSPORT_OPERATION_VERBS):
        return True
    return False


def _query_targets_hardware_layer(intent: QueryIntent) -> bool:
    q_lower = {t.lower() for t in intent.domain_terms}
    if q_lower.intersection(_HARDWARE_QUERY_TERMS):
        return True
    transport_ops = _query_operation_terms(intent.domain_terms) & _TRANSPORT_OPERATION_VERBS
    return bool(transport_ops) and bool(q_lower.intersection({"data", "device", "devices"}))


def _private_workflow_operation_penalty(
    intent: QueryIntent,
    symbol_name: str,
    symbol_kind: str,
) -> float:
    """
    Penalize private helpers that embed a requested operation verb but are not
    the public operation entry point (e.g. _verbWorkflow vs verb).
    """
    if not symbol_name.startswith("_"):
        return 0.0
    if symbol_kind not in ("function", "platform_channel", ""):
        return 0.0
    if not _is_operational_forward_query(intent):
        return 0.0
    ops = _query_operation_terms(intent.domain_terms)
    if not ops:
        return 0.0
    for verb in ops:
        if _symbol_has_operation_verb(symbol_name, verb) and not _symbol_is_public_operation_name(
            symbol_name.lstrip("_"), verb
        ):
            return 0.16
    return 0.0


def _public_operation_match_bonus(
    intent: QueryIntent,
    symbol_name: str,
    symbol_kind: str,
) -> float:
    """Boost public callables whose name exactly matches a requested operation verb."""
    if symbol_kind not in ("function", "platform_channel", ""):
        return 0.0
    bonus = 0.0
    for verb in _query_operation_terms(intent.domain_terms):
        if _symbol_is_public_operation_name(symbol_name, verb):
            bonus += 0.08
    return min(bonus, 0.08)


def _flow_entry_point_adjustment(
    intent: QueryIntent,
    file_path: str,
    symbol_name: str,
    symbol_kind: str,
) -> float:
    """Boost ingress callables and penalize state-change symbols for flow seeds."""
    if not (intent.flow or intent.architecture):
        return 0.0
    q_lower = {t.lower() for t in intent.domain_terms}
    path_lower = (file_path or "").replace("\\", "/").lower()
    sym = symbol_name or ""
    kind = (symbol_kind or "").lower()
    adj = 0.0

    if kind == "class":
        adj -= 0.12
    elif kind in ("function", "platform_channel"):
        adj += 0.06

    forward_flow = bool(q_lower.intersection(_FORWARD_FLOW_QUERY_TERMS))
    if forward_flow:
        if any(_symbol_has_operation_verb(sym, verb) for verb in _INGRESS_OPERATION_VERBS):
            adj += 0.12
        segments = set(_camel_segments(sym))
        if segments.intersection(_STATE_CHANGE_SEGMENTS) and not q_lower.intersection(
            _STATE_CHANGE_SEGMENTS
        ):
            adj -= 0.10

    for verb in _query_operation_terms(intent.domain_terms):
        if _symbol_is_public_operation_name(sym, verb):
            adj += 0.14
        elif sym.startswith("_") and _symbol_has_operation_verb(sym, verb):
            adj -= 0.10
        elif verb in sym.lower() and not _symbol_has_operation_verb(sym, verb):
            adj -= 0.08

    if _query_targets_hardware_layer(intent):
        if "/hardware/" in path_lower or "/adapters/" in path_lower:
            adj += 0.08
        elif (
            _query_operation_terms(intent.domain_terms)
            and sym.startswith("_")
            and "/order" in path_lower
            and "/hardware/" not in path_lower
            and "/adapters/" not in path_lower
        ):
            adj -= 0.12

    return adj


def _query_context_bonus(
    intent: QueryIntent,
    file_path: str,
    symbol_name: str,
) -> float:
    """Extra seed boost from query terms + path/symbol alignment (generic)."""
    if not (intent.flow or intent.architecture):
        return 0.0
    path_lower = (file_path or "").lower()
    sym_lower = (symbol_name or "").lower()
    q_lower = {t.lower() for t in intent.domain_terms}
    boost = 0.0

    if _query_targets_hardware_layer(intent):
        if "/hardware/" in path_lower or "/adapters/" in path_lower:
            boost += 0.08
        if any(t in sym_lower for t in ("adapter", "device", "transport")):
            boost += 0.06
        for verb in _query_operation_terms(intent.domain_terms):
            if _symbol_is_public_operation_name(symbol_name, verb):
                boost += 0.16
            elif (
                _symbol_has_operation_verb(symbol_name, verb)
                and "/hardware/" in path_lower
                and not symbol_name.startswith("_")
            ):
                boost += 0.10
            elif (
                classify_code_layer(file_path, symbol_name, "") == "service"
                and not _symbol_has_operation_verb(symbol_name, verb)
                and "/hardware/" not in path_lower
                and "/adapters/" not in path_lower
            ):
                boost -= 0.10

    if "printer" in q_lower or "print" in q_lower:
        if "/printing/" in path_lower or "print" in sym_lower:
            boost += 0.06

    if "ready" in q_lower and "ready" in sym_lower:
        boost += 0.05

    if "kitchen" in q_lower and "order" in q_lower:
        if any(v in sym_lower for v in ("addorder", "enqueue", "place", "create")):
            boost += 0.10
        if "/printing/" in path_lower and "enqueue" in sym_lower:
            boost += 0.08

    return min(boost, 0.22)


def flow_seed_score(query: str, sm: ScoredMemory) -> float:
    """
    Rank code-flow entry points: relevance plus bounded structural bonuses.

    Does not replace sm.score (relevance); used only for seed ordering.
    """
    intent = detect_query_intent(query)
    meta = sm.memory.get("metadata") or {}
    sym = meta.get("symbol_name") or ""
    path = meta.get("file_path") or meta.get("source_ref") or ""
    kind = meta.get("symbol_kind") or ""
    record_type = meta.get("record_type") or ""

    relevance = _normalized_hit_relevance(sm)
    structural = 0.0

    if intent.flow or intent.architecture:
        layer = classify_code_layer(path, sym, kind)
        if layer == "service":
            structural += 0.20
        elif layer == "transport":
            structural += 0.13
        elif layer == "ui":
            structural -= 0.14
        elif layer == "model":
            structural -= 0.10

        structural += operation_verb_bonus(sym, intent.domain_terms)
        structural += _service_class_bonus(sym, kind)
        structural += _query_context_bonus(intent, path, sym)
        structural += _flow_entry_point_adjustment(intent, path, sym, kind)
        structural -= _negative_operation_penalty(sym, intent.domain_terms)
        structural -= _private_workflow_operation_penalty(intent, sym, kind)

        domain_boost = domain_symbol_boost(intent.domain_terms, sym, path)
        if layer in ("service", "transport"):
            structural += domain_boost * 0.14
        elif layer in ("ui", "model"):
            structural += domain_boost * 0.03
        else:
            structural += domain_boost * 0.08

        if record_type == "indexed_symbol" and layer in ("service", "transport"):
            structural += 0.04
        if is_generic_symbol(sym, path):
            structural -= 0.18
        path_lower = (path or "").replace("\\", "/").lower()
        if "/test/" in path_lower or "/tests/" in path_lower or "/integration_test/" in path_lower:
            structural -= 0.22

    structural = max(
        -_MAX_FLOW_STRUCTURAL_PENALTY,
        min(_MAX_FLOW_STRUCTURAL_BONUS, structural),
    )
    extra = _public_operation_match_bonus(intent, sym, kind)
    q_lower = {t.lower() for t in intent.domain_terms}
    forward_flow = bool(q_lower.intersection(_FORWARD_FLOW_QUERY_TERMS))
    state_focused = bool(q_lower.intersection(_STATE_CHANGE_SEGMENTS))
    if forward_flow and kind in ("function", "platform_channel"):
        if state_focused:
            segments = set(_camel_segments(sym))
            if segments.intersection(q_lower.intersection(_STATE_CHANGE_SEGMENTS)):
                extra += 0.05
        else:
            if any(_symbol_has_operation_verb(sym, verb) for verb in _INGRESS_OPERATION_VERBS):
                extra += 0.05
            segments = set(_camel_segments(sym))
            if segments.intersection(_STATE_CHANGE_SEGMENTS) and not q_lower.intersection(
                _STATE_CHANGE_SEGMENTS
            ):
                extra -= 0.05
    return relevance + structural + extra


def rank_flow_seed_candidates(
    query: str,
    candidates: List[ScoredMemory],
) -> List[ScoredMemory]:
    """Sort candidates for code-flow seed selection (not normal search)."""
    if not candidates:
        return []

    intent = detect_query_intent(query)
    if not (intent.flow or intent.architecture):
        return sorted(candidates, key=lambda sm: sm.score, reverse=True)

    def sort_key(sm: ScoredMemory):
        meta = sm.memory.get("metadata") or {}
        sym = meta.get("symbol_name") or ""
        ops = _query_operation_terms(intent.domain_terms)
        exact_op = 1 if any(_symbol_is_public_operation_name(sym, verb) for verb in ops) else 0
        return (flow_seed_score(query, sm), _normalized_hit_relevance(sm), exact_op)

    return sorted(candidates, key=sort_key, reverse=True)


def flow_seed_score_breakdown(query: str, sm: ScoredMemory) -> dict:
    """Explain flow seed ranking components (for diagnostics/tests)."""
    meta = sm.memory.get("metadata") or {}
    sym = meta.get("symbol_name") or ""
    path = meta.get("file_path") or ""
    kind = meta.get("symbol_kind") or ""
    relevance = _normalized_hit_relevance(sm)
    total = flow_seed_score(query, sm)
    return {
        "symbol": sym,
        "file_path": path,
        "layer": classify_code_layer(path, sym, kind),
        "relevance": relevance,
        "flow_seed_score": total,
        "structural_bonus": total - relevance,
    }


def _camel_segments(name: str) -> List[str]:
    parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|[0-9]+", name or "")
    return [p.lower() for p in parts if len(p) >= 2]


def domain_symbol_boost(
    query_terms: List[str],
    symbol_name: str,
    file_path: str = "",
) -> float:
    """Boost when symbol name contains query domain terms as camelCase segments."""
    if not query_terms or not symbol_name:
        return 0.0
    segments = set(_camel_segments(symbol_name))
    path_lower = (file_path or "").lower()
    boost = 0.0
    for term in query_terms:
        tl = term.lower()
        if len(tl) < 3:
            continue
        if tl in segments:
            boost += 0.8
        elif len(tl) <= 3:
            continue
        elif any(tl in seg or seg in tl for seg in segments if len(seg) >= 3):
            boost += 0.5
        elif tl in symbol_name.lower():
            boost += 0.6
        elif tl in path_lower:
            boost += 0.3
    return min(boost, 1.5)


def _domain_path_boost(intent: QueryIntent, file_path: str, query_terms: List[str]) -> float:
    if not (intent.flow or intent.architecture):
        return 0.0
    path_lower = (file_path or "").lower()
    boost = 0.0
    for folder in _DOMAIN_PATH_FOLDERS:
        if folder.rstrip("/") in path_lower:
            boost += 0.3
    for term in query_terms:
        if len(term) >= 4 and term.lower() in path_lower:
            boost += 0.2
    return min(boost, 0.6)


def adjust_index_score(
    query: str,
    intent: QueryIntent,
    file_path: str,
    symbol_name: Optional[str],
    base_score: float,
    reasons: List[str],
    *,
    path_only_match: bool,
    is_config: bool = False,
) -> Tuple[float, List[str]]:
    """Apply deterministic penalties and domain boosts to a base keyword score."""
    if base_score <= 0:
        return 0.0, reasons

    score = base_score
    out = list(reasons)
    sym = symbol_name or ""

    if is_generic_symbol(sym, file_path) or is_generic_path(file_path):
        penalty = get_index_generic_penalty()
        score *= penalty
        out.append("penalized: generic symbol/path")

    if is_config and (intent.flow or intent.architecture):
        score *= 0.5
        out.append("penalized: config file for flow query")

    if path_only_match:
        domain_hits = sum(
            1 for t in intent.domain_terms
            if len(t) >= 3 and t.lower() in (file_path or "").lower()
        )
        sym_match = sym and any(
            t.lower() in sym.lower() for t in intent.domain_terms if len(t) >= 3
        )
        if not sym_match and domain_hits < 2:
            score = 0.0
            out.append("filtered: weak path-only match")
        else:
            score *= 0.4
            out.append("demoted: path-only match")

    boost = domain_symbol_boost(intent.domain_terms, sym, file_path)
    if boost > 0:
        score += boost
        out.append(f"domain boost +{boost:.1f}")

    path_boost = _domain_path_boost(intent, file_path, intent.domain_terms)
    if path_boost > 0:
        score += path_boost
        out.append(f"path domain boost +{path_boost:.1f}")

    return max(score, 0.0), out


def weak_keyword_query(keyword_hits: List[ScoredMemory]) -> bool:
    """True when raw keyword scores are too weak to trust normalization."""
    if not keyword_hits:
        return True
    max_raw = max(h.score for h in keyword_hits)
    return max_raw < get_index_weak_kw_threshold()


def hybrid_weights_for_query(query: str, keyword_hits: List[ScoredMemory]) -> dict:
    """Return fusion weights; favor semantic when keywords are weak."""
    from packages.shared.config import get_hybrid_weights

    intent = detect_query_intent(query)
    if not weak_keyword_query(keyword_hits):
        return get_hybrid_weights()
    if intent.flow or intent.architecture:
        return {"keyword": 0.30, "semantic": 0.65, "freshness": 0.05}
    return {"keyword": 0.40, "semantic": 0.55, "freshness": 0.05}


def rank_index_candidates(
    query: str,
    candidates: List[ScoredMemory],
) -> List[ScoredMemory]:
    """Re-sort index hits with domain tie-breaking after score adjustments."""
    if not candidates:
        return []

    intent = detect_query_intent(query)

    def sort_key(sm: ScoredMemory):
        meta = sm.memory.get("metadata") or {}
        sym = meta.get("symbol_name") or ""
        path = meta.get("file_path") or meta.get("source_ref") or ""
        generic = is_generic_symbol(sym, path)
        domain = domain_symbol_boost(intent.domain_terms, sym, path)
        return (sm.score, domain, 0 if generic else 1)

    ranked = sorted(candidates, key=sort_key, reverse=True)
    return ranked


def seed_tiebreak_score(query: str, sm: ScoredMemory) -> float:
    """Backward-compatible alias for code-flow seed ranking."""
    return flow_seed_score(query, sm)
