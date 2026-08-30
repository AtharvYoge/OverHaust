"""
Deterministic code-flow retrieval over persisted project index metadata.

Builds an evidence-backed path from a natural-language question by:
1. Retrieving relevant indexed symbols/files (existing index search)
2. Picking a service-layer entry point via flow seed scoring
3. Beam-searching multiple candidate paths over typed edges
4. Scoring paths holistically (edge strength, destination relevance, weak-import penalty)

Limitations (by design — never invent relationships):
- Import resolution is relative-path only; external modules are skipped
- Call edges require optional disk reads and static pattern matching
- Path order reflects static evidence, not proven runtime execution order
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from packages.context.relevance import ScoredMemory
from packages.knowledge.abstention import RELEVANCE_SUFFICIENT
from packages.knowledge.trust import compute_trust
from packages.retrieval.dart_evidence import (
    EDGE_ADAPTER_BOUNDARY,
    EDGE_CALLER,
    EDGE_EXPORT,
    EDGE_IMPORT,
    EDGE_QUERY_MATCH,
    EDGE_SAME_FILE_CALLER,
    EDGE_TEXTUAL,
    STRONG_EDGE_TYPES,
    WEAK_EDGE_TYPES,
    EdgeEvidence,
    edge_priority,
    find_same_file_callers,
    find_source_edges,
)
from packages.retrieval.flow_graph import (
    PartialFlowPath,
    backward_edge_allowed,
    classify_flow_traversal_intent,
    classify_step_path_role,
    detect_adapter_boundary,
    direction_is_coherent,
    is_strong_edge,
    is_weak_edge,
    score_flow_path,
    should_expand_backward,
)
from packages.retrieval.index_retrieval import (
    build_index_search_text,
    index_hit_to_memory,
    score_index_record,
)
from packages.shared.config import (
    flow_read_calls_enabled,
    get_flow_beam_width,
    get_flow_max_steps,
    get_flow_min_relevance,
    get_flow_seed_search_limit,
)

# Raw index keyword scores typically land in 0–8; normalize for thresholds/display.
_RELEVANCE_NORM = 8.0

_ALLOWED_REASON_PREFIXES = (
    "query match",
    "imports ",
    "exports ",
    "calls ",
    "import",
    "export",
    "direct_call",
    "constructor",
    "inheritance",
    "platform_channel",
    "adapter_boundary",
    "caller",
    "same_file_caller",
)


@dataclass
class FlowStep:
    file: str
    symbol: str
    symbol_type: str
    line: int
    reason: str
    relevance_score: float
    trust_score: float
    edge_type: str = ""
    evidence: str = ""
    edge_line: int = 0
    path_role: str = "process"
    direction: str = "forward"


@dataclass
class CodeFlowResult:
    project_id: str
    query: str
    steps: List[FlowStep] = field(default_factory=list)
    summary: str = ""
    insufficient_evidence: bool = False
    evidence_note: str = ""
    flow_intent: str = "general"
    path_score: float = 0.0
    process_steps: List[FlowStep] = field(default_factory=list)
    supporting_steps: List[FlowStep] = field(default_factory=list)


def normalize_relevance(raw_score: float) -> float:
    """Map raw index keyword score to 0–1 range."""
    if raw_score <= 0:
        return 0.0
    return min(raw_score / _RELEVANCE_NORM, 1.0)


def relevance_for_scored_hit(scored: ScoredMemory) -> float:
    """Return a flow relevance score on the shared 0–1 scale."""
    methods = set(scored.retrieval_methods or [])
    if methods.intersection({"index_hybrid", "index_semantic"}):
        return max(0.0, min(scored.score, 1.0))
    return normalize_relevance(scored.score)


def build_index_lookups(index) -> Dict[str, Any]:
    """Build in-memory lookup tables from a loaded ProjectIndex."""
    files_by_path: Dict[str, Any] = {}
    symbols_by_file: Dict[str, List[Any]] = {}
    exports_by_name: Dict[str, List[Tuple[str, Any]]] = {}

    for file_record in getattr(index, "files", []) or []:
        path = getattr(file_record, "path", "")
        if not path:
            continue
        files_by_path[path] = file_record
        syms = list(getattr(file_record, "symbols", []) or [])
        symbols_by_file[path] = syms
        for sym in syms:
            if getattr(sym, "exported", False):
                exports_by_name.setdefault(getattr(sym, "name", ""), []).append((path, sym))

    indexed_paths = set(files_by_path.keys())
    return {
        "files_by_path": files_by_path,
        "symbols_by_file": symbols_by_file,
        "exports_by_name": exports_by_name,
        "indexed_paths": indexed_paths,
        "callers_by_target": {},
    }


def build_caller_index(
    root_path: str,
    lookups: Dict[str, Any],
) -> Dict[Tuple[str, str], List[EdgeEvidence]]:
    """Reverse caller map: (callee_file, callee_symbol) -> static caller edges."""
    callers: Dict[Tuple[str, str], List[EdgeEvidence]] = {}
    if not flow_read_calls_enabled() or not root_path:
        return callers

    from packages.retrieval.dart_evidence import EDGE_CONSTRUCTOR, EDGE_DIRECT_CALL

    for file_path in lookups["files_by_path"]:
        source = _read_source(root_path, file_path)
        if not source:
            continue
        reachable = _reachable_symbols(file_path, lookups)
        symbols = [
            s
            for s in lookups["symbols_by_file"].get(file_path, [])
            if getattr(s, "kind", "") in ("function", "platform_channel")
        ]
        for sym in symbols:
            caller_name = getattr(sym, "name", "")
            if not caller_name:
                continue
            for edge in find_source_edges(
                source,
                file_path,
                reachable,
                current_symbol=caller_name,
                lookups=lookups,
            ):
                if edge.edge_type not in (EDGE_DIRECT_CALL, EDGE_CONSTRUCTOR):
                    continue
                callee_key = (edge.target_file, edge.target_symbol)
                rev = EdgeEvidence(
                    edge_type=EDGE_CALLER,
                    target_file=file_path,
                    target_symbol=caller_name,
                    target_kind=getattr(sym, "kind", "function"),
                    line=edge.line,
                    evidence=(
                        f"{caller_name}() calls {edge.target_symbol}() "
                        f"(static evidence at line {edge.line})"
                    ),
                    direction="backward",
                    source_symbol=caller_name,
                    source_file=file_path,
                )
                callers.setdefault(callee_key, []).append(rev)

        for sym in symbols:
            callee_name = getattr(sym, "name", "")
            if not callee_name:
                continue
            for edge in find_same_file_callers(
                source, file_path, callee_name, reachable
            ):
                callee_key = (file_path, callee_name)
                callers.setdefault(callee_key, []).append(edge)

    return callers


def enrich_lookups(root_path: str, lookups: Dict[str, Any]) -> Dict[str, Any]:
    """Attach derived traversal indexes (callers) to lookup tables."""
    if not lookups.get("callers_by_target") and root_path:
        lookups["callers_by_target"] = build_caller_index(root_path, lookups)
    return lookups


def resolve_import(
    importer_path: str,
    import_str: str,
    indexed_paths: Set[str],
) -> Optional[str]:
    """
    Resolve a relative import string to an indexed file path.

    Bare ``*.dart`` imports are relative to their importing file. Other bare
    module names and absolute paths are treated as external and skipped.
    """
    imp = (import_str or "").strip().replace("\\", "/")
    is_dart_relative = imp.endswith(".dart") and not imp.startswith(
        ("package:", "dart:", "/")
    )
    if not imp or (not imp.startswith(".") and not is_dart_relative):
        return None

    importer = PurePosixPath(importer_path)
    base = importer.parent
    target = posixpath.normpath((base / imp).as_posix())
    if target == ".." or target.startswith("../") or target.startswith("/"):
        return None

    if target in indexed_paths:
        return target

    stem = target
    extensions = sorted({PurePosixPath(p).suffix for p in indexed_paths if PurePosixPath(p).suffix})
    for ext in extensions:
        candidate = stem + ext
        if candidate in indexed_paths:
            return candidate

    for path in indexed_paths:
        p = PurePosixPath(path)
        if p.with_suffix("").as_posix() == stem or p.as_posix() == stem:
            return path

    return None


def _step_key(file: str, symbol: str) -> Tuple[str, str]:
    return (file, symbol or "")


def format_flow_summary(steps: List[FlowStep]) -> str:
    """Human-readable arrow chain from symbol names (fallback to file basename)."""
    labels: List[str] = []
    for step in steps:
        if step.symbol:
            labels.append(step.symbol)
        else:
            labels.append(PurePosixPath(step.file).stem or step.file)
    return " → ".join(labels)


def _reason_for_edge(edge: EdgeEvidence, import_str: str = "") -> str:
    if edge.edge_type == EDGE_IMPORT:
        return f"import {import_str or edge.target_file}"
    if edge.edge_type == EDGE_EXPORT:
        return f"export {edge.target_symbol}"
    return edge.edge_type


def _score_step(
    query: str,
    project_id: str,
    file_record,
    symbol=None,
    indexed_at: str = "",
) -> Tuple[float, float, FlowStep]:
    """Score one candidate step and return raw score, trust, and FlowStep shell."""
    search_text = build_index_search_text(file_record, symbol)
    path = getattr(file_record, "path", "")
    raw, _ = score_index_record(query, search_text, path)
    relevance = normalize_relevance(raw)

    mem = index_hit_to_memory(
        project_id,
        file_record,
        symbol=symbol,
        indexed_at=indexed_at,
    )
    trust = compute_trust(mem, query).score

    if symbol is not None:
        sym_name = getattr(symbol, "name", "")
        sym_kind = getattr(symbol, "kind", "symbol")
        sym_line = getattr(symbol, "line", 0)
    else:
        sym_name = ""
        sym_kind = "file"
        sym_line = 0

    return raw, trust, FlowStep(
        file=path,
        symbol=sym_name,
        symbol_type=sym_kind,
        line=sym_line,
        reason="",
        relevance_score=relevance,
        trust_score=trust,
    )


def scored_hit_to_flow_step(
    sm: ScoredMemory,
    query: str,
    project_id: str,
    index,
    reason: str = "query match",
) -> Optional[FlowStep]:
    """Convert a trusted index ScoredMemory hit into a FlowStep."""
    meta = sm.memory.get("metadata") or {}
    record_type = meta.get("record_type")
    if record_type not in ("indexed_symbol", "indexed_file"):
        return None

    path = meta.get("file_path") or meta.get("source_ref") or ""
    if not path:
        return None

    lookups = build_index_lookups(index)
    file_record = lookups["files_by_path"].get(path)
    if file_record is None:
        return None

    symbol = None
    if record_type == "indexed_symbol":
        sym_name = meta.get("symbol_name", "")
        for sym in lookups["symbols_by_file"].get(path, []):
            if getattr(sym, "name", "") == sym_name:
                symbol = sym
                break

    _, trust, step = _score_step(
        query,
        project_id,
        file_record,
        symbol=symbol,
        indexed_at=getattr(index, "indexed_at", "") or "",
    )
    step.reason = reason
    step.edge_type = EDGE_QUERY_MATCH
    step.evidence = f"Index search matched query for {step.symbol or path}"
    step.relevance_score = relevance_for_scored_hit(sm)
    step.trust_score = trust
    return step


def collect_seed_hits(scored_hits: List[ScoredMemory], query: str = "") -> List[ScoredMemory]:
    """Return index hits ranked for code-flow entry-point selection."""
    from packages.retrieval.index_ranking import rank_flow_seed_candidates

    symbol_hits: List[ScoredMemory] = []
    file_hits: List[ScoredMemory] = []

    for sm in scored_hits:
        meta = sm.memory.get("metadata") or {}
        rt = meta.get("record_type")
        if rt == "indexed_symbol":
            symbol_hits.append(sm)
        elif rt == "indexed_file":
            file_hits.append(sm)

    if query:
        if symbol_hits:
            return rank_flow_seed_candidates(query, symbol_hits)
        return rank_flow_seed_candidates(query, file_hits)

    symbol_hits.sort(key=lambda s: s.score, reverse=True)
    file_hits.sort(key=lambda s: s.score, reverse=True)
    return symbol_hits + file_hits


def _reachable_symbols(
    file_path: str,
    lookups: Dict[str, Any],
) -> List[Tuple[str, Any, str]]:
    """Symbols reachable from file_path: same-file + resolved import exports."""
    out: List[Tuple[str, Any, str]] = []
    files_by_path = lookups["files_by_path"]
    indexed_paths = lookups["indexed_paths"]

    file_record = files_by_path.get(file_path)
    if file_record is None:
        return out

    for sym in lookups["symbols_by_file"].get(file_path, []):
        out.append((file_path, sym, "same_file"))

    for imp in getattr(file_record, "imports", []) or []:
        resolved = resolve_import(file_path, imp, indexed_paths)
        if not resolved:
            continue
        for sym in lookups["symbols_by_file"].get(resolved, []):
            if getattr(sym, "exported", False):
                out.append((resolved, sym, f"import:{imp}"))

    return out


def _read_source(root_path: str, file_path: str) -> Optional[str]:
    try:
        full = Path(root_path) / file_path
        return full.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _should_skip_neighbor(step: FlowStep) -> bool:
    from packages.retrieval.index_ranking import is_flow_traversal_excluded_symbol

    if step.edge_type == EDGE_TEXTUAL:
        return True
    if is_flow_traversal_excluded_symbol(
        step.symbol, step.file, step.symbol_type
    ):
        return True
    return False


def _neighbor_sort_key(step: FlowStep, query: str) -> Tuple[float, float, float]:
    from packages.retrieval.index_ranking import detect_query_intent, flow_path_adjustment

    intent = detect_query_intent(query)
    path_adj = flow_path_adjustment(intent, step.file)
    return (
        float(edge_priority(step.edge_type)),
        path_adj,
        step.relevance_score,
    )


def _edge_passes_gate(step: FlowStep, min_relevance: float) -> bool:
    if step.edge_type in STRONG_EDGE_TYPES:
        return True
    if step.edge_type in (EDGE_CALLER, EDGE_SAME_FILE_CALLER, EDGE_ADAPTER_BOUNDARY):
        return step.relevance_score >= min_relevance * 0.5
    if step.edge_type in WEAK_EDGE_TYPES:
        return step.relevance_score >= min_relevance
    return step.relevance_score >= min_relevance


def _emit_edge_step(
    edge: EdgeEvidence,
    query: str,
    project_id: str,
    lookups: Dict[str, Any],
    indexed_at: str,
    import_str: str = "",
    source_step: Optional[FlowStep] = None,
) -> Optional[FlowStep]:
    target_file = lookups["files_by_path"].get(edge.target_file)
    if target_file is None:
        return None

    symbol = None
    if edge.target_symbol:
        for sym in lookups["symbols_by_file"].get(edge.target_file, []):
            if getattr(sym, "name", "") == edge.target_symbol:
                symbol = sym
                break

    _, _, step = _score_step(
        query,
        project_id,
        target_file,
        symbol=symbol,
        indexed_at=indexed_at,
    )
    edge_type = edge.edge_type
    if source_step and detect_adapter_boundary(
        source_step.file,
        source_step.symbol,
        source_step.symbol_type,
        edge.target_file,
        edge.target_symbol,
        edge.target_kind,
        edge_type,
    ):
        edge_type = EDGE_ADAPTER_BOUNDARY
    step.edge_type = edge_type
    step.evidence = edge.evidence
    step.edge_line = edge.line
    step.reason = _reason_for_edge(edge, import_str)
    step.direction = edge.direction or "forward"
    if symbol is not None:
        step.line = getattr(symbol, "line", step.line)
    return step


def _select_implementable_seed(
    seed_hits: List[ScoredMemory],
    query: str,
    project_id: str,
    index,
    lookups: Dict[str, Any],
    root_path: str,
    traversal_intent,
) -> Optional[FlowStep]:
    """
    Prefer a seed symbol with forward direct-call egress over declaration-only hits.

    Applies only when multiple indexed symbols share a name (e.g. interface vs impl).
    Otherwise trust flow_seed_score ordering from collect_seed_hits.
    """
    from packages.retrieval.dart_evidence import EDGE_DIRECT_CALL
    from packages.retrieval.index_ranking import flow_seed_score

    candidates: List[Tuple[float, int, FlowStep]] = []
    for hit in seed_hits[:8]:
        step = scored_hit_to_flow_step(hit, query, project_id, index, reason="query match")
        if step is None:
            continue
        partial = PartialFlowPath(steps=[step], score=0.0)
        forward_calls = sum(
            1
            for n in discover_neighbors(
                step,
                query,
                project_id,
                index,
                lookups,
                root_path,
                traversal_intent,
                partial,
            )
            if n.edge_type == EDGE_DIRECT_CALL and n.direction == "forward"
        )
        candidates.append((flow_seed_score(query, hit), forward_calls, step))

    if not candidates:
        return None

    by_symbol: Dict[str, List[Tuple[float, int, FlowStep]]] = {}
    for item in candidates:
        sym = item[2].symbol or ""
        by_symbol.setdefault(sym, []).append(item)

    finalists: List[Tuple[float, int, FlowStep]] = []
    for group in by_symbol.values():
        if len(group) > 1:
            with_calls = [item for item in group if item[1] > 0]
            if with_calls:
                finalists.append(max(with_calls, key=lambda item: (item[0], item[1])))
            else:
                finalists.append(max(group, key=lambda item: item[0]))
        else:
            finalists.append(group[0])

    best = max(finalists, key=lambda item: (item[0], item[1]))
    return best[2]


def discover_neighbors(
    current: FlowStep,
    query: str,
    project_id: str,
    index,
    lookups: Dict[str, Any],
    root_path: str,
    traversal_intent=None,
    partial: Optional[PartialFlowPath] = None,
) -> Iterator[FlowStep]:
    """Yield candidate next steps with typed evidence-backed edges."""
    from packages.retrieval.flow_graph import FlowTraversalIntent

    if traversal_intent is None:
        traversal_intent = classify_flow_traversal_intent(query)

    file_path = current.file
    file_record = lookups["files_by_path"].get(file_path)
    if file_record is None:
        return

    from packages.retrieval.index_ranking import classify_code_layer

    current_layer = classify_code_layer(
        current.file, current.symbol, current.symbol_type
    )
    if traversal_intent.kind in ("forward_process", "delivery_destination"):
        if current_layer == "model":
            return
        if partial and partial.import_edges >= 1 and partial.strong_edges == 0:
            # Do not extend import-only chains without a forward call.
            return

    indexed_at = getattr(index, "indexed_at", "") or ""
    indexed_paths = lookups["indexed_paths"]
    seen_local: Set[Tuple[str, str, str]] = set()
    strong_steps: List[FlowStep] = []
    weak_steps: List[FlowStep] = []

    def collect_step(step: Optional[FlowStep]) -> None:
        if step is None or _should_skip_neighbor(step):
            return
        key = (step.file, step.symbol, step.edge_type)
        if key in seen_local:
            return
        seen_local.add(key)
        if is_weak_edge(step.edge_type):
            weak_steps.append(step)
        else:
            strong_steps.append(step)

    # Source-based forward edges (calls, constructors, inheritance, platform).
    if flow_read_calls_enabled() and root_path:
        source = _read_source(root_path, file_path)
        if source:
            reachable = _reachable_symbols(file_path, lookups)
            symbols_to_scan: List[str] = []
            if current.symbol_type in ("class", "enum", "interface", "struct"):
                symbols_to_scan = [
                    getattr(s, "name", "")
                    for s in lookups["symbols_by_file"].get(file_path, [])
                    if getattr(s, "kind", "") in ("function", "platform_channel")
                    and getattr(s, "name", "")
                ]
            elif current.symbol:
                symbols_to_scan = [current.symbol]

            for scan_sym in symbols_to_scan:
                for edge in find_source_edges(
                    source,
                    file_path,
                    reachable,
                    current_symbol=scan_sym,
                    lookups=lookups,
                ):
                    if current.symbol and edge.target_symbol == current.symbol:
                        continue
                    step = _emit_edge_step(
                        edge,
                        query,
                        project_id,
                        lookups,
                        indexed_at,
                        source_step=current,
                    )
                    if step:
                        step.direction = "forward"
                        collect_step(step)

    # Reverse caller edges from pre-built index.
    has_strong_forward = any(
        (s.direction or "forward") == "forward" and s.edge_type in STRONG_EDGE_TYPES
        for s in strong_steps
    )
    # A path that has already stepped downstream is telling a "what this reaches"
    # story; appending a caller would answer a different question mid-sequence.
    # Skip the work entirely rather than emitting candidates the beam must reject.
    backward_coherent = direction_is_coherent("backward", partial) if partial else True
    if current.symbol and backward_coherent and should_expand_backward(
        traversal_intent,
        len(partial.steps) - 1 if partial else 0,
        has_strong_forward=has_strong_forward,
    ):
        callers_by_target = lookups.get("callers_by_target", {})
        for edge in callers_by_target.get((file_path, current.symbol), []):
            if partial and not backward_edge_allowed(
                edge.edge_type,
                partial,
                traversal_intent,
                has_strong_forward=has_strong_forward,
            ):
                continue
            step = _emit_edge_step(
                edge,
                query,
                project_id,
                lookups,
                indexed_at,
                source_step=current,
            )
            if step:
                step.direction = "backward"
                collect_step(step)

    # Import edges — supporting evidence only; never bridge unrelated components on forward queries.
    allow_imports = True
    if traversal_intent.kind in ("forward_process", "delivery_destination"):
        if not strong_steps:
            allow_imports = False
        elif partial and partial.import_edges >= 1:
            allow_imports = False
    if allow_imports:
        for imp in getattr(file_record, "imports", []) or []:
            resolved = resolve_import(file_path, imp, indexed_paths)
            if not resolved:
                continue
            target = lookups["files_by_path"].get(resolved)
            if target is None:
                continue
            exported = [
                s for s in lookups["symbols_by_file"].get(resolved, [])
                if getattr(s, "exported", False)
            ]
            if exported:
                for sym in exported:
                    edge = EdgeEvidence(
                        edge_type=EDGE_IMPORT,
                        target_file=resolved,
                        target_symbol=getattr(sym, "name", ""),
                        target_kind=getattr(sym, "kind", "symbol"),
                        line=getattr(sym, "line", 0),
                        evidence=f"{file_path} imports {imp} for {getattr(sym, 'name', '')}",
                        import_str=imp,
                    )
                    step = _emit_edge_step(
                        edge, query, project_id, lookups, indexed_at, imp, current
                    )
                    if step:
                        step.direction = "forward"
                        collect_step(step)
            else:
                edge = EdgeEvidence(
                    edge_type=EDGE_IMPORT,
                    target_file=resolved,
                    target_symbol="",
                    target_kind="file",
                    line=0,
                    evidence=f"{file_path} imports {imp}",
                    import_str=imp,
                )
                step = _emit_edge_step(
                    edge, query, project_id, lookups, indexed_at, imp, current
                )
                if step:
                    step.direction = "forward"
                    collect_step(step)

    if strong_steps:
        for step in strong_steps:
            yield step
    else:
        for step in weak_steps:
            yield step


def _beam_search_trace(
    first: FlowStep,
    query: str,
    project_id: str,
    index,
    lookups: Dict[str, Any],
    root_path: str,
    max_steps: int,
    min_relevance: float,
    traversal_intent,
) -> Tuple[List[FlowStep], float]:
    """Expand multiple candidate paths and return the highest-scoring path."""
    beam_width = get_flow_beam_width()
    first.path_role = "process"
    first.direction = "forward"
    initial = PartialFlowPath(
        steps=[first],
        score=score_flow_path([first], query, traversal_intent),
    )
    beam = [initial]

    for _ in range(max(0, max_steps - 1)):
        expansions: List[PartialFlowPath] = []
        for partial in beam:
            visited = partial.visited_keys()
            for neighbor in discover_neighbors(
                partial.current,
                query,
                project_id,
                index,
                lookups,
                root_path,
                traversal_intent,
                partial,
            ):
                nkey = _step_key(neighbor.file, neighbor.symbol)
                if nkey in visited:
                    continue
                if not _edge_passes_gate(neighbor, min_relevance):
                    continue
                if not direction_is_coherent(
                    getattr(neighbor, "direction", "forward"), partial
                ):
                    continue
                if not backward_edge_allowed(neighbor.edge_type, partial, traversal_intent):
                    continue
                neighbor.path_role = classify_step_path_role(
                    neighbor, traversal_intent
                )
                new_steps = partial.steps + [neighbor]
                expansions.append(
                    PartialFlowPath(
                        steps=new_steps,
                        score=score_flow_path(new_steps, query, traversal_intent),
                        weak_edges=partial.weak_edges
                        + (1 if is_weak_edge(neighbor.edge_type) else 0),
                        strong_edges=partial.strong_edges
                        + (1 if is_strong_edge(neighbor.edge_type) else 0),
                        import_edges=partial.import_edges
                        + (1 if neighbor.edge_type == EDGE_IMPORT else 0),
                    )
                )
        if not expansions:
            break
        expansions.sort(key=lambda p: p.score, reverse=True)
        beam = expansions[:beam_width]

    best = max(beam, key=lambda p: p.score)
    return best.steps, best.score


def trace_code_flow(
    project_id: str,
    query: str,
    index,
    memory_store=None,
    *,
    max_steps: Optional[int] = None,
    min_relevance: Optional[float] = None,
    root_path: Optional[str] = None,
) -> CodeFlowResult:
    """
    Trace a short code-flow evidence path for a project question.

    Uses existing index search for seeds and walks typed import/call edges only.
    """
    if index is None or not getattr(index, "files", None):
        return CodeFlowResult(
            project_id=project_id,
            query=query,
            insufficient_evidence=True,
            evidence_note="Needs more information — no project index available.",
        )

    max_steps = max_steps if max_steps is not None else get_flow_max_steps()
    min_relevance = min_relevance if min_relevance is not None else get_flow_min_relevance()

    from packages.retrieval.index_retrieval import search_index_records
    from packages.context.retrieval import apply_trust

    raw_hits = search_index_records(
        project_id,
        query,
        index,
        limit=get_flow_seed_search_limit(),
        memory_store=memory_store,
    )
    trusted = apply_trust(raw_hits, query)
    seed_hits = collect_seed_hits(trusted, query)

    if not seed_hits:
        return CodeFlowResult(
            project_id=project_id,
            query=query,
            insufficient_evidence=True,
            evidence_note="Needs more information — no indexed code matched this question.",
        )

    best_seed = seed_hits[0]
    first = scored_hit_to_flow_step(best_seed, query, project_id, index, reason="query match")
    if first is None:
        return CodeFlowResult(
            project_id=project_id,
            query=query,
            insufficient_evidence=True,
            evidence_note="Needs more information — no indexed code matched this question.",
        )

    if first.relevance_score < RELEVANCE_SUFFICIENT:
        return CodeFlowResult(
            project_id=project_id,
            query=query,
            steps=[first],
            summary=format_flow_summary([first]),
            insufficient_evidence=True,
            evidence_note="Needs more information — nothing relevant was found in project memory.",
        )

    if root_path is None and memory_store is not None:
        from services.ingestion.index_store import ProjectIndexStore
        root_path = ProjectIndexStore(memory_store).get_project_root(project_id) or getattr(index, "root_path", "")

    lookups = build_index_lookups(index)
    enrich_lookups(root_path or "", lookups)
    traversal_intent = classify_flow_traversal_intent(query)

    refined = _select_implementable_seed(
        seed_hits,
        query,
        project_id,
        index,
        lookups,
        root_path or "",
        traversal_intent,
    )
    if refined is not None:
        first = refined

    steps, path_score = _beam_search_trace(
        first,
        query,
        project_id,
        index,
        lookups,
        root_path or "",
        max_steps,
        min_relevance,
        traversal_intent,
    )

    for i, step in enumerate(steps):
        step.path_role = classify_step_path_role(
            step, traversal_intent, is_seed=(i == 0)
        )

    process_steps = [s for s in steps if s.path_role == "process"]
    supporting_steps = [s for s in steps if s.path_role != "process"]

    if traversal_intent.kind == "origin_generation":
        result_steps = process_steps
    else:
        result_steps = steps

    insufficient = False
    evidence_note = ""
    if first.trust_score < 0.55 and all(s.trust_score < 0.55 for s in steps):
        evidence_note = "Low confidence — only available source"
    if not any(is_strong_edge(s.edge_type) for s in steps[1:]):
        evidence_note = (
            evidence_note
            + " Static evidence only — path uses weak or import edges where stronger call evidence was not found."
        ).strip()

    return CodeFlowResult(
        project_id=project_id,
        query=query,
        steps=result_steps,
        summary=format_flow_summary(result_steps),
        insufficient_evidence=insufficient,
        evidence_note=evidence_note,
        flow_intent=traversal_intent.kind,
        path_score=path_score,
        process_steps=process_steps,
        supporting_steps=supporting_steps,
    )


def code_flow_result_to_dict(result: CodeFlowResult) -> Dict[str, Any]:
    """JSON-serializable dict for API/MCP responses."""
    return {
        "project_id": result.project_id,
        "query": result.query,
        "summary": result.summary,
        "steps": [asdict(s) for s in result.steps],
        "process_steps": [asdict(s) for s in result.process_steps],
        "supporting_steps": [asdict(s) for s in result.supporting_steps],
        "flow_intent": result.flow_intent,
        "path_score": round(result.path_score, 4),
        "insufficient_evidence": result.insufficient_evidence,
        "evidence_note": result.evidence_note,
        "static_evidence_disclaimer": (
            "Path order reflects static source evidence, not proven runtime execution order."
        ),
    }


def is_allowed_reason(reason: str) -> bool:
    """Check that a step reason is one of the evidence-backed types."""
    if reason in _ALLOWED_REASON_PREFIXES:
        return True
    return any(reason == p or reason.startswith(p) for p in _ALLOWED_REASON_PREFIXES)
