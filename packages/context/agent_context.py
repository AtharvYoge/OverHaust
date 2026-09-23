"""
Compact agent-oriented context assembly for external AI integrations.

Single canonical entry point: assemble_agent_context(project_id, prompt).
Reuses unified search, selective code-flow tracing, snippet reads, and abstention.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional, Union

from packages.knowledge.abstention import RELEVANCE_SUFFICIENT, assess_evidence
from packages.retrieval.flow_graph import classify_flow_traversal_intent
from packages.shared.config import (
    get_context_max_evidence,
    get_context_max_files,
    get_context_max_symbols,
    get_context_search_limit,
)

logger = logging.getLogger("overhaust.context")

REST_MAX_PROMPT_LENGTH = 500
MAX_PROMPT_LENGTH = REST_MAX_PROMPT_LENGTH  # REST / default invoke_context_request
MCP_MAX_PROMPT_LENGTH = 8000  # Cursor Agent prompts; REST stays at 500

IncludeCodeFlowOption = Union[Literal["auto"], bool]

_FLOW_INTENTS_FOR_AUTO_TRACE = frozenset({
    "forward_process",
    "delivery_destination",
    "hardware_transport",
    "origin_generation",
})

_STATIC_DISCLAIMER = (
    "Static index evidence only; path order reflects source relationships, "
    "not proven runtime behavior."
)

_COMMON_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "can", "this", "that", "these", "those",
})

# Bounded one-hop callee packaging for call/delegation questions (not full call-graph).
_MAX_ONE_HOP_CALLEES = 2

_FROM_IMPORT_RE = re.compile(
    r"from\s+([\w.]+)\s+import\s+([A-Za-z_][\w]*(?:\s*,\s*[A-Za-z_][\w]*)*)"
)
_CALL_NAME_RE = re.compile(r"(?<!\.)\b([A-Za-z_][\w]*)\s*\(")
_SELF_CALL_RE = re.compile(r"\bself\.([A-Za-z_][\w]*)\s*\(")
_DEF_OR_CLASS_RE = re.compile(r"\b(?:def|class)\s+([A-Za-z_][\w]*)")

_SKIP_CALLEE_NAMES = frozenset({
    "print", "len", "str", "int", "float", "list", "dict", "set", "tuple",
    "range", "open", "super", "isinstance", "getattr", "setattr", "hasattr",
    "type", "bool", "bytes", "object", "property", "staticmethod",
    "classmethod", "enumerate", "zip", "map", "filter", "sorted", "min",
    "max", "sum", "any", "all", "iter", "next", "format", "repr", "id",
    "Optional", "Dict", "List", "Any", "Union", "Tuple", "Set", "Callable",
    "True", "False", "None", "return", "yield", "await", "async",
})

_FORWARD_CALL_PATTERNS = (
    re.compile(r"\bwhat\s+does\b.+\b(call|invoke|delegate)", re.I),
    re.compile(r"\b(calls?|invokes?|delegates?\s+to)\b", re.I),
    re.compile(r"\bwhere\s+does\b.+\bgo\b", re.I),
    re.compile(r"\bwhat\s+happens\s+after\b", re.I),
    re.compile(r"\bhow\s+does\b.+\breach\b", re.I),
    re.compile(r"\bdefined\b.+\b(call|invoke|delegate)", re.I),
    re.compile(r"\b(execution\s+goes|goes\s+next|next\s+hop)\b", re.I),
)

_REVERSE_CALL_PATTERNS = (
    re.compile(r"\bwhat\s+calls\b", re.I),
    re.compile(r"\bwho\s+calls\b", re.I),
    re.compile(r"\bwhere\s+is\b.+\bhandled\b", re.I),
)


@dataclass
class AgentContextMetrics:
    files_count: int = 0
    symbols_count: int = 0
    approx_source_lines: int = 0
    response_bytes: int = 0
    latency_ms: int = 0
    code_flow_included: bool = False


@dataclass
class AgentContextResponse:
    project_id: str
    prompt: str
    task_analysis: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    relevant_files: List[Dict[str, Any]] = field(default_factory=list)
    relevant_symbols: List[Dict[str, Any]] = field(default_factory=list)
    code_flow: Optional[Dict[str, Any]] = None
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    relevant_decisions: List[Dict[str, Any]] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    context: str = ""
    confidence: str = "high"
    insufficient_evidence: bool = False
    evidence_note: str = ""
    disclaimer: str = _STATIC_DISCLAIMER
    metrics: AgentContextMetrics = field(default_factory=AgentContextMetrics)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["metrics"] = asdict(self.metrics)
        return payload

    def to_mcp_payload(self) -> Dict[str, Any]:
        """Stable MCP-facing payload (same as to_dict; documented contract)."""
        return self.to_dict()


def _clamp_budget(value: Optional[int], ceiling: int) -> int:
    if value is None:
        return ceiling
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return ceiling
    if parsed < 1:
        return 1
    return min(parsed, ceiling)


def _validate_prompt(prompt: str, max_length: int = REST_MAX_PROMPT_LENGTH) -> str:
    cleaned = (prompt or "").strip()
    if not cleaned:
        raise ValueError("prompt is required")
    if len(cleaned) > max_length:
        raise ValueError(f"prompt exceeds maximum length of {max_length}")
    return cleaned


def _resolve_project_id(
    project_id: str,
    root_path: Optional[str],
    memory_store,
) -> str:
    pid = (project_id or "").strip()
    path = (root_path or "").strip()

    if not pid and not path:
        raise ValueError("project_id or root_path is required")

    if path and not pid:
        resolved = resolve_project_id(path, memory_store=memory_store)
        if not resolved:
            raise ValueError(f"No registered project found for path: {path}")
        return resolved

    if path and pid:
        resolved = resolve_project_id(path, memory_store=memory_store)
        if resolved and resolved != pid:
            raise ValueError(
                f"project_id {pid} does not match root_path (expected {resolved})"
            )

    return pid


def _log_context_request(response: AgentContextResponse) -> None:
    metrics = response.metrics
    logger.info(
        "context_request project_id=%s latency_ms=%d files=%d symbols=%d "
        "code_flow=%s insufficient=%s",
        response.project_id,
        metrics.latency_ms,
        metrics.files_count,
        metrics.symbols_count,
        metrics.code_flow_included,
        response.insufficient_evidence,
    )


def invoke_context_request(
    project_id: str,
    prompt: str,
    *,
    root_path: Optional[str] = None,
    include_code_flow: IncludeCodeFlowOption = "auto",
    max_files: Optional[int] = None,
    max_symbols: Optional[int] = None,
    max_evidence: Optional[int] = None,
    max_prompt_length: Optional[int] = None,
    memory_store=None,
) -> AgentContextResponse:
    """
    Validated entry point for external context requests (API, MCP, agent).

    Resolves project_id, clamps budgets, assembles context, and logs safely.
    REST callers should omit max_prompt_length (defaults to 500).
    MCP callers may pass MCP_MAX_PROMPT_LENGTH.
    """
    if memory_store is None:
        from packages.memory.memory_store import get_memory_store
        memory_store = get_memory_store()

    limit = REST_MAX_PROMPT_LENGTH if max_prompt_length is None else int(max_prompt_length)
    cleaned_prompt = _validate_prompt(prompt, max_length=limit)
    resolved_id = _resolve_project_id(project_id, root_path, memory_store)

    clamped_files = _clamp_budget(max_files, get_context_max_files())
    clamped_symbols = _clamp_budget(max_symbols, get_context_max_symbols())
    clamped_evidence = _clamp_budget(max_evidence, get_context_max_evidence())

    response = assemble_agent_context(
        resolved_id,
        cleaned_prompt,
        memory_store=memory_store,
        include_code_flow=include_code_flow,
        max_files=clamped_files,
        max_symbols=clamped_symbols,
        max_evidence=clamped_evidence,
    )
    _log_context_request(response)
    return response


def resolve_project_id(root_path: str, memory_store=None) -> Optional[str]:
    """Resolve a registered project_id from an absolute repository path."""
    from services.ingestion.index_store import ProjectIndexStore

    if memory_store is None:
        from packages.memory.memory_store import get_memory_store
        memory_store = get_memory_store()

    return ProjectIndexStore(memory_store).resolve_project_id(root_path)


def list_projects_for_agent(memory_store=None) -> List[Dict[str, Any]]:
    """List registered projects with index status for external agents."""
    from services.ingestion.index_store import ProjectIndexStore

    if memory_store is None:
        from packages.memory.memory_store import get_memory_store
        memory_store = get_memory_store()

    store = ProjectIndexStore(memory_store)
    projects: List[Dict[str, Any]] = []
    for project in memory_store.list_projects():
        pid = project.get("id") or project.get("project_id", "")
        root = store.get_project_root(pid)
        indexed = store.load_index_or_none(pid) is not None
        projects.append({
            "project_id": pid,
            "name": project.get("name", ""),
            "description": project.get("description", ""),
            "root_path": root or "",
            "indexed": indexed,
        })
    return projects


def _is_flow_question(prompt: str) -> bool:
    """True when the prompt asks about process/path, not implementation."""
    q = (prompt or "").lower()
    return (
        ("how" in q and any(w in q for w in (
            "reach", "flow", "work", "get", "send", "pass", "move",
        )))
        or ("where" in q and any(w in q for w in (
            "sent", "routed", "handled", "processed", "go", "reach",
        )))
    )


def should_include_code_flow(
    prompt: str,
    include_code_flow: IncludeCodeFlowOption,
    top_relevance: float,
) -> bool:
    """Decide whether to invoke code-flow tracing for this request."""
    if include_code_flow is False:
        return False
    if top_relevance < RELEVANCE_SUFFICIENT:
        return False
    if include_code_flow is True:
        return True
    if not _is_flow_question(prompt):
        return False
    intent = classify_flow_traversal_intent(prompt)
    return intent.kind in _FLOW_INTENTS_FOR_AUTO_TRACE


def _analyze_task(prompt: str) -> Dict[str, Any]:
    words = re.findall(r"\b[a-zA-Z]+\b", prompt.lower())
    keywords = list(dict.fromkeys(
        w for w in words if w not in _COMMON_WORDS and len(w) > 3
    ))[:10]

    task_lower = prompt.lower()
    if any(w in task_lower for w in ("fix", "bug", "error", "issue", "problem")):
        task_type = "troubleshooting"
    elif any(w in task_lower for w in (
        "build", "create", "implement", "add", "change", "modify", "update",
    )):
        task_type = "development"
    elif any(w in task_lower for w in ("explain", "understand", "learn", "what")):
        task_type = "learning"
    elif any(w in task_lower for w in ("review", "check", "audit", "inspect")):
        task_type = "review"
    else:
        task_type = "general"

    return {"task_type": task_type, "keywords": keywords}


def _confidence_label(insufficient: bool, evidence_note: str) -> str:
    if insufficient:
        return "insufficient"
    if evidence_note and "low confidence" in evidence_note.lower():
        return "low"
    return "high"


def _extract_decisions(scored_knowledge: List[Any]) -> List[Dict[str, Any]]:
    decisions: List[Dict[str, Any]] = []
    for item in scored_knowledge:
        if getattr(item, "knowledge_type", "") != "decision":
            continue
        decisions.append({
            "id": item.id,
            "content": item.content,
            "importance": item.importance_score,
        })
    return decisions


def _identify_constraints(knowledge_items: List[Any], task: str) -> List[str]:
    patterns = [
        r"(?i)must\s+([^\n]+)",
        r"(?i)should\s+([^\n]+)",
        r"(?i)cannot\s+([^\n]+)",
        r"(?i)limited\s+to\s+([^\n]+)",
        r"(?i)requirement\s*[:=]\s*([^\n]+)",
        r"(?i)constraint\s*[:=]\s*([^\n]+)",
    ]
    all_text = task + " " + " ".join(
        getattr(k, "content", "") for k in knowledge_items
    )
    constraints: List[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, all_text):
            constraint = match.group(0).strip()
            if len(constraint) > 10:
                constraints.append(constraint)
    return list(dict.fromkeys(constraints))[:5]


def _relationships_from_flow(code_flow: Dict[str, Any]) -> List[Dict[str, Any]]:
    steps = code_flow.get("process_steps") or code_flow.get("steps") or []
    relationships: List[Dict[str, Any]] = []
    for index in range(len(steps) - 1):
        current = steps[index]
        nxt = steps[index + 1]
        relationships.append({
            "from": {
                "file": current.get("file", ""),
                "symbol": current.get("symbol", ""),
            },
            "to": {
                "file": nxt.get("file", ""),
                "symbol": nxt.get("symbol", ""),
            },
            "edge_type": nxt.get("edge_type", ""),
            "evidence": nxt.get("evidence") or nxt.get("reason", ""),
        })
    return relationships


def _build_summary(
    relevant_symbols: List[Dict[str, Any]],
    relevant_files: List[Dict[str, Any]],
    insufficient: bool,
) -> str:
    if insufficient:
        return "No sufficiently relevant project evidence matched this prompt."
    names: List[str] = []
    for sym in relevant_symbols[:3]:
        name = sym.get("name")
        if name and name not in names:
            names.append(name)
    for file_item in relevant_files[:3]:
        path = file_item.get("path", "")
        base = path.split("/")[-1] if path else ""
        if base and base not in names:
            names.append(base)
    if not names:
        return "Limited project evidence matched this prompt."
    if len(names) == 1:
        return f"Top match involves {names[0]}."
    joined = ", ".join(names[:-1]) + f", and {names[-1]}"
    return f"Top matches involve {joined}."


def _build_context_text(
    prompt: str,
    relevant_files: List[Dict[str, Any]],
    relevant_symbols: List[Dict[str, Any]],
    evidence: List[Dict[str, Any]],
    code_flow: Optional[Dict[str, Any]],
    relevant_decisions: List[Dict[str, Any]],
    constraints: List[str],
    insufficient: bool,
    evidence_note: str,
) -> str:
    lines: List[str] = [f"## Task\n{prompt.strip()}"]

    if insufficient:
        lines.append(f"\n## Evidence\n{evidence_note or 'Insufficient project evidence.'}")
        return "\n".join(lines)

    if relevant_symbols:
        lines.append("\n## Relevant symbols")
        for sym in relevant_symbols:
            loc = f"{sym['file']}:{sym.get('line', 0)}"
            lines.append(f"- {loc} {sym['name']} ({sym.get('kind', 'symbol')})")

    if relevant_files:
        lines.append("\n## Relevant files")
        for file_item in relevant_files:
            path = file_item.get("path", "")
            symbol = file_item.get("symbol")
            line = file_item.get("symbol_line")
            header = path
            if symbol and line:
                header = f"{path}:{line} {symbol}"
            lines.append(f"- {header}")
            snippet = file_item.get("snippet")
            if snippet:
                lines.append(f"  ```\n  {snippet.strip()}\n  ```")

    if code_flow and not code_flow.get("insufficient_evidence"):
        lines.append("\n## Code flow")
        summary = code_flow.get("summary", "").strip()
        if summary:
            lines.append(summary)
        for step in code_flow.get("process_steps") or code_flow.get("steps") or []:
            loc = f"{step.get('file', '')}:{step.get('line', 0)}"
            lines.append(
                f"- {loc} {step.get('symbol', '')} ({step.get('reason', '')})"
            )

    if evidence and not relevant_files:
        lines.append("\n## Evidence")
        for item in evidence[:5]:
            loc = f"{item.get('path', '')}:{item.get('line', 0)}"
            sym = item.get("symbol", "")
            lines.append(f"- {loc} {sym} — {item.get('reason', '')}")

    if relevant_decisions:
        lines.append("\n## Decisions")
        for decision in relevant_decisions[:3]:
            lines.append(f"- {decision.get('content', '').strip()}")

    if constraints:
        lines.append("\n## Constraints")
        for constraint in constraints[:3]:
            lines.append(f"- {constraint}")

    return "\n".join(lines)


def _approx_source_lines(
    relevant_files: List[Dict[str, Any]],
    evidence: List[Dict[str, Any]],
) -> int:
    total = 0
    for file_item in relevant_files:
        snippet = file_item.get("snippet") or ""
        total += max(1, len(snippet.splitlines())) if snippet else 0
    for item in evidence:
        snippet = item.get("snippet") or ""
        if snippet:
            total += len(snippet.splitlines())
        elif item.get("path"):
            total += 1
    return total


def _is_test_path(path: str) -> bool:
    """True for unit/integration test paths (aligned with _impl_path_rank)."""
    normalized = (path or "").replace("\\", "/")
    lower = normalized.lower()
    base = lower.rsplit("/", 1)[-1]
    return (
        lower.startswith("test/")
        or lower.startswith("tests/")
        or "/test/" in lower
        or "/tests/" in lower
        or base.startswith("test_")
        or "_test." in base
        or ".test." in base
    )


def _is_benchmark_or_fixture_path(path: str) -> bool:
    """True for disposable benchmark clones / fixtures, not product code."""
    lower = (path or "").replace("\\", "/").lower()
    return (
        "benchmark-runs/" in lower
        or "/fixture/" in lower
        or "/fixtures/" in lower
        or "/fixture" in lower
    )


def _is_secondary_context_path(path: str) -> bool:
    """Paths that should not lead packaged agent context when impl hits exist."""
    return _is_test_path(path) or _is_benchmark_or_fixture_path(path)


def _prioritize_implementation_hits(
    files: List[Dict[str, Any]],
    symbols: List[Dict[str, Any]],
    task_type: str,
    max_files: int,
    max_symbols: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Prefer implementation paths over tests/benchmark fixtures in packaged context."""
    del task_type  # retained for call-site compatibility; demotion is always applied

    primary_files = [f for f in files if not _is_secondary_context_path(f.get("path", ""))]
    secondary_files = [f for f in files if _is_secondary_context_path(f.get("path", ""))]
    ordered_files = (primary_files + secondary_files)[:max_files]

    primary_symbols = [s for s in symbols if not _is_secondary_context_path(s.get("file", ""))]
    secondary_symbols = [s for s in symbols if _is_secondary_context_path(s.get("file", ""))]
    ordered_symbols = (primary_symbols + secondary_symbols)[:max_symbols]

    return ordered_files, ordered_symbols


def is_call_delegation_question(prompt: str) -> bool:
    """
    True when the prompt asks what something calls/invokes/delegates to,
    or where execution goes next. Does not enable code-flow tracing.
    """
    text = (prompt or "").strip()
    if not text:
        return False
    if any(p.search(text) for p in _FORWARD_CALL_PATTERNS):
        return True
    # Reverse caller questions are recognized but currently do not expand
    # (no cheap reverse index); keep detection for tests/API clarity.
    return any(p.search(text) for p in _REVERSE_CALL_PATTERNS)


def _is_forward_call_question(prompt: str) -> bool:
    text = (prompt or "").strip()
    return bool(text) and any(p.search(text) for p in _FORWARD_CALL_PATTERNS)


def _module_hint_to_path_suffix(module: str) -> str:
    """packages.context.agent_context -> packages/context/agent_context"""
    return (module or "").replace(".", "/").strip("/")


def _slice_primary_callable_body(snippet: str, primary_symbol: str) -> str:
    """Restrict a window to ``def primary_symbol`` … next peer def/class."""
    if not snippet or not primary_symbol:
        return snippet or ""
    lines = snippet.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^\s*def\s+{re.escape(primary_symbol)}\b", line):
            start = i
            break
    if start is None:
        return snippet
    def_indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for j in range(start + 1, len(lines)):
        raw = lines[j]
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent <= def_indent and re.match(r"^(def|class)\s+", raw.lstrip()):
            end = j
            break
    return "\n".join(lines[start:end])


def _extract_direct_callee_candidates(
    snippet: str,
    primary_symbol: str,
) -> List[Dict[str, str]]:
    """
    Extract imported/called names from a bounded implementation snippet.

    Prefers names that appear in ``from … import …`` and are also called.
    Skips self.* local helpers and common builtins.
    """
    body = _slice_primary_callable_body(snippet, primary_symbol)
    if not body:
        return []

    imported: Dict[str, str] = {}
    for match in _FROM_IMPORT_RE.finditer(body):
        module = match.group(1)
        for raw in match.group(2).split(","):
            name = raw.strip().split(" as ")[-1].strip()
            if name and name not in _SKIP_CALLEE_NAMES:
                imported[name] = module

    self_calls = {m.group(1) for m in _SELF_CALL_RE.finditer(body)}
    defined_here = {m.group(1) for m in _DEF_OR_CLASS_RE.finditer(body)}
    called: List[str] = []
    for match in _CALL_NAME_RE.finditer(body):
        name = match.group(1)
        if name in _SKIP_CALLEE_NAMES:
            continue
        if name == primary_symbol or name in defined_here:
            continue
        if name in self_calls:
            continue
        if name not in called:
            called.append(name)

    ordered: List[Dict[str, str]] = []
    # Prefer imported-and-called names (cross-module delegation).
    for name in called:
        if name in imported:
            ordered.append({"name": name, "module": imported[name]})
    for name, module in imported.items():
        if name not in {c["name"] for c in ordered}:
            ordered.append({"name": name, "module": module})
    for name in called:
        if name not in {c["name"] for c in ordered}:
            ordered.append({"name": name, "module": ""})
    return ordered[:_MAX_ONE_HOP_CALLEES * 2]


def _impl_path_rank(path: str, module_hint: str = "") -> tuple:
    """Lower tuple sorts first: prefer real implementation over tests/benchmarks."""
    normalized = (path or "").replace("\\", "/").lower()
    penalty = 0
    if _is_benchmark_or_fixture_path(path) or "benchmark" in normalized:
        penalty += 200
    if _is_test_path(path):
        penalty += 100
    hint = _module_hint_to_path_suffix(module_hint).lower()
    if hint and hint not in normalized and f"{hint}." not in normalized:
        penalty += 20
    elif hint and (normalized.endswith(f"{hint}.py") or f"/{hint}." in normalized
                   or normalized.endswith(hint)):
        penalty -= 50
    return (penalty, len(normalized))


def _resolve_callee_in_index(
    index,
    symbol_name: str,
    *,
    module_hint: str = "",
    primary_path: str = "",
) -> Optional[Dict[str, Any]]:
    """Resolve a callee name against persisted index symbols (no rescan)."""
    if index is None or not symbol_name:
        return None

    candidates: List[Dict[str, Any]] = []
    for file_record in getattr(index, "files", []) or []:
        path = getattr(file_record, "path", "") or ""
        if not path:
            continue
        if primary_path and path == primary_path:
            # Same-file helpers are not useful one-hop continuations.
            continue
        for sym in getattr(file_record, "symbols", []) or []:
            name = getattr(sym, "name", "") or ""
            if name != symbol_name:
                continue
            candidates.append({
                "name": name,
                "file": path,
                "line": int(getattr(sym, "line", 0) or 0),
                "kind": getattr(sym, "kind", "") or "symbol",
            })

    if not candidates:
        return None

    candidates.sort(key=lambda c: _impl_path_rank(c["file"], module_hint))
    best = candidates[0]
    # Reject benchmark/test-only resolutions when better options exist; if all
    # are noisy, still return the best available for graceful degradation.
    return best


def _primary_implementation_symbol(
    relevant_symbols: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    for sym in relevant_symbols:
        path = sym.get("file") or ""
        name = sym.get("name") or ""
        if not name or not path:
            continue
        if _impl_path_rank(path)[0] >= 100:
            continue
        return sym
    return relevant_symbols[0] if relevant_symbols else None


def _locate_def_line(lines: List[str], symbol_name: str, hinted_line: int) -> int:
    """Prefer the indexed line when it matches; otherwise find ``def/class name``."""
    if not symbol_name:
        return hinted_line
    pattern = re.compile(rf"^\s*(?:async\s+)?(?:def|class)\s+{re.escape(symbol_name)}\b")
    if hinted_line > 0 and hinted_line <= len(lines):
        if pattern.search(lines[hinted_line - 1]):
            return hinted_line
    for idx, line in enumerate(lines, 1):
        if pattern.search(line):
            return idx
    return hinted_line


def _snippet_for_symbol(
    root_path: str,
    path: str,
    symbol_line: int,
    *,
    symbol_name: str = "",
    align: str = "center",
) -> tuple[Optional[str], int]:
    """
    Read a bounded snippet for a symbol.

    Returns (snippet, anchor_line). align='start' biases the window to the
    function body. When symbol_name is provided, the definition line is
    re-anchored if the persisted index line is stale.
    """
    from packages.retrieval.index_retrieval import read_indexed_snippet
    from packages.shared.config import (
        get_index_snippet_max_chars,
        get_index_snippet_max_lines,
    )

    hinted = int(symbol_line or 0)
    if align != "start":
        return (
            read_indexed_snippet(root_path, path, symbol_line=hinted or None),
            hinted,
        )

    from services.ingestion.project_indexer import PathSecurityError, ProjectIndexer

    max_lines = get_index_snippet_max_lines()
    max_chars = get_index_snippet_max_chars()
    try:
        indexer = ProjectIndexer()
        root = indexer._validate_root(root_path)
        rel = path.replace("\\", "/").lstrip("/")
        if ".." in rel.split("/"):
            raise PathSecurityError(f"Path traversal rejected: {path}")
        full = (root / rel).resolve()
        full.relative_to(root)
        text = full.read_bytes().decode("utf-8", errors="replace")
    except (PathSecurityError, ValueError, OSError):
        return (
            read_indexed_snippet(root_path, path, symbol_line=hinted or None),
            hinted,
        )

    lines = text.splitlines()
    anchor = _locate_def_line(lines, symbol_name, hinted)
    if not anchor:
        return read_indexed_snippet(root_path, path, symbol_line=None), hinted

    start = max(0, anchor - 3)  # include decorators / def line
    end = min(len(lines), start + max_lines)
    snippet = f"// lines {start + 1}-{end} of {path}\n" + "\n".join(lines[start:end])
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars] + "\n// ... truncated"
    return snippet, anchor


def _merge_one_hop_callees(
    *,
    relevant_files: List[Dict[str, Any]],
    relevant_symbols: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
    callees: List[Dict[str, Any]],
    max_files: int,
    max_symbols: int,
    max_evidence: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Insert callees near the front; demote noise to stay within budgets."""
    if not callees:
        return relevant_files, relevant_symbols, evidence_items

    existing_sym_keys = {
        (s.get("file"), s.get("name")) for s in relevant_symbols
    }
    existing_paths = {f.get("path") for f in relevant_files}

    # Keep primary (first) slots; inject callees immediately after.
    new_symbols = list(relevant_symbols)
    new_files = list(relevant_files)
    new_evidence = list(evidence_items)

    insert_sym_at = min(1, len(new_symbols))
    insert_file_at = min(1, len(new_files))
    insert_ev_at = min(1, len(new_evidence))

    for callee in callees:
        key = (callee["file"], callee["name"])
        if key not in existing_sym_keys:
            new_symbols.insert(insert_sym_at, {
                "name": callee["name"],
                "file": callee["file"],
                "line": callee["line"],
                "kind": callee.get("kind") or "symbol",
                "relevance_score": float(callee.get("relevance_score", 0.0)),
            })
            existing_sym_keys.add(key)
            insert_sym_at += 1

        if callee["file"] not in existing_paths:
            new_files.insert(insert_file_at, {
                "path": callee["file"],
                "relevance_score": float(callee.get("relevance_score", 0.0)),
                "symbol": callee["name"],
                "symbol_line": callee["line"],
                "snippet": callee.get("snippet"),
            })
            existing_paths.add(callee["file"])
            insert_file_at += 1
        else:
            # Ensure an existing file entry carries the callee-centered snippet.
            for file_item in new_files:
                if file_item.get("path") == callee["file"] and callee.get("snippet"):
                    if file_item.get("symbol") != callee["name"]:
                        file_item["symbol"] = callee["name"]
                        file_item["symbol_line"] = callee["line"]
                        file_item["snippet"] = callee["snippet"]
                    break

        ev_key = (callee["file"], callee["name"], callee["line"])
        if not any(
            (e.get("path"), e.get("symbol"), e.get("line")) == ev_key
            for e in new_evidence
        ):
            new_evidence.insert(insert_ev_at, {
                "path": callee["file"],
                "symbol": callee["name"],
                "line": callee["line"],
                "reason": "one-hop callee",
                "snippet": callee.get("snippet"),
                "record_type": "indexed_symbol",
                "relevance_score": float(callee.get("relevance_score", 0.0)),
            })
            insert_ev_at += 1

    return (
        new_files[:max_files],
        new_symbols[:max_symbols],
        new_evidence[:max_evidence],
    )


def _expand_one_hop_callees(
    *,
    project_id: str,
    prompt: str,
    memory_store,
    relevant_files: List[Dict[str, Any]],
    relevant_symbols: List[Dict[str, Any]],
    evidence_items: List[Dict[str, Any]],
    max_files: int,
    max_symbols: int,
    max_evidence: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    For forward call/delegation questions, add up to 1–2 direct callees
    resolved from the persisted index + bounded primary snippet.
    """
    if not _is_forward_call_question(prompt):
        return relevant_files, relevant_symbols, evidence_items

    primary = _primary_implementation_symbol(relevant_symbols)
    if not primary:
        return relevant_files, relevant_symbols, evidence_items

    primary_path = primary.get("file") or ""
    primary_name = primary.get("name") or ""
    primary_line = int(primary.get("line") or 0)

    from services.ingestion.index_store import ProjectIndexStore

    index_store = ProjectIndexStore(memory_store)
    index = index_store.load_index_or_none(project_id)
    root_path = index_store.get_project_root(project_id) or ""
    if index is None or not root_path:
        return relevant_files, relevant_symbols, evidence_items

    # Always use a forward-biased primary window so neighboring methods are
    # not treated as callees (e.g. trace_code_flow above get_relevant_context).
    snippet, _primary_anchor = _snippet_for_symbol(
        root_path,
        primary_path,
        primary_line,
        symbol_name=primary_name,
        align="start",
    )

    candidates = _extract_direct_callee_candidates(snippet or "", primary_name)
    resolved: List[Dict[str, Any]] = []
    seen_names: set = set()
    for cand in candidates:
        name = cand["name"]
        if name in seen_names:
            continue
        hit = _resolve_callee_in_index(
            index,
            name,
            module_hint=cand.get("module") or "",
            primary_path=primary_path,
        )
        if hit is None:
            continue
        seen_names.add(name)
        live_snippet, live_line = _snippet_for_symbol(
            root_path,
            hit["file"],
            hit["line"],
            symbol_name=hit["name"],
            align="start",
        )
        resolved.append({
            **hit,
            "line": live_line or hit["line"],
            "snippet": live_snippet,
            "relevance_score": max(
                float(primary.get("relevance_score") or 0.0) * 0.85,
                1.0,
            ),
        })
        if len(resolved) >= _MAX_ONE_HOP_CALLEES:
            break

    return _merge_one_hop_callees(
        relevant_files=relevant_files,
        relevant_symbols=relevant_symbols,
        evidence_items=evidence_items,
        callees=resolved,
        max_files=max_files,
        max_symbols=max_symbols,
        max_evidence=max_evidence,
    )


def assemble_agent_context(
    project_id: str,
    prompt: str,
    *,
    memory_store=None,
    include_code_flow: IncludeCodeFlowOption = "auto",
    max_files: Optional[int] = None,
    max_symbols: Optional[int] = None,
    max_evidence: Optional[int] = None,
) -> AgentContextResponse:
    """
    Assemble compact repository context for an external AI agent.

    Raises ValueError if project_id is not registered.
    """
    from packages.context.context_engine import ContextAssembler
    from packages.context.retrieval import search_project_knowledge_scored, trace_code_flow

    if memory_store is None:
        from packages.memory.memory_store import get_memory_store
        memory_store = get_memory_store()

    started = time.perf_counter()
    max_files = max_files if max_files is not None else get_context_max_files()
    max_symbols = max_symbols if max_symbols is not None else get_context_max_symbols()
    max_evidence = max_evidence if max_evidence is not None else get_context_max_evidence()
    search_limit = max(get_context_search_limit(), max_files * 2, max_symbols)

    project = memory_store.get_project(project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")

    assembler = ContextAssembler(memory_store=memory_store)
    scored = search_project_knowledge_scored(
        project_id, prompt, memory_store=memory_store, limit=search_limit,
    )
    evidence_assessment = assess_evidence(scored, prompt)
    insufficient = evidence_assessment.get("insufficient_evidence", False)
    evidence_note = evidence_assessment.get("evidence_note", "")

    top_relevance = scored[0].score if scored else 0.0
    task_analysis = _analyze_task(prompt)

    relevant_knowledge = assembler._scored_to_knowledge(scored) if scored else []
    relevant_decisions = _extract_decisions(relevant_knowledge)
    constraints = _identify_constraints(relevant_knowledge, prompt)

    relevant_files: List[Dict[str, Any]] = []
    relevant_symbols: List[Dict[str, Any]] = []
    evidence_items: List[Dict[str, Any]] = []

    if not insufficient:
        relevant_files = assembler._get_relevant_files(project_id, prompt, max_files)

        seen_symbol_keys: set = set()
        for sm in scored:
            meta = sm.memory.get("metadata") or {}
            if meta.get("record_type") != "indexed_symbol":
                continue
            name = meta.get("symbol_name") or ""
            path = meta.get("file_path") or meta.get("source_ref") or ""
            line = meta.get("symbol_line") or 0
            key = (path, name, line)
            if not name or key in seen_symbol_keys:
                continue
            seen_symbol_keys.add(key)
            relevant_symbols.append({
                "name": name,
                "file": path,
                "line": line,
                "kind": meta.get("symbol_kind") or meta.get("kind") or "symbol",
                "relevance_score": round(sm.score, 4),
            })

        relevant_files, relevant_symbols = _prioritize_implementation_hits(
            relevant_files,
            relevant_symbols,
            task_analysis.get("task_type", "general"),
            max_files,
            max_symbols,
        )

        seen_evidence: set = set()
        for sm in scored:
            meta = sm.memory.get("metadata") or {}
            record_type = meta.get("record_type")
            if record_type not in ("indexed_file", "indexed_symbol", "memory"):
                continue
            path = meta.get("file_path") or meta.get("source_ref") or ""
            symbol = meta.get("symbol_name") or ""
            line = meta.get("symbol_line") or 0
            key = (path, symbol, line, sm.memory.get("id", ""))
            if key in seen_evidence:
                continue
            seen_evidence.add(key)

            snippet = None
            if record_type in ("indexed_file", "indexed_symbol") and path:
                for file_item in relevant_files:
                    if file_item.get("path") == path:
                        snippet = file_item.get("snippet")
                        break

            reasons = list(getattr(sm, "reasons", []) or [])
            evidence_items.append({
                "path": path,
                "symbol": symbol,
                "line": line,
                "reason": reasons[0] if reasons else "query match",
                "snippet": snippet,
                "record_type": record_type,
                "relevance_score": round(sm.score, 4),
            })
            if len(evidence_items) >= max_evidence:
                break

        relevant_files, relevant_symbols, evidence_items = _expand_one_hop_callees(
            project_id=project_id,
            prompt=prompt,
            memory_store=memory_store,
            relevant_files=relevant_files,
            relevant_symbols=relevant_symbols,
            evidence_items=evidence_items,
            max_files=max_files,
            max_symbols=max_symbols,
            max_evidence=max_evidence,
        )

    code_flow: Optional[Dict[str, Any]] = None
    relationships: List[Dict[str, Any]] = []
    code_flow_included = False

    if not insufficient and should_include_code_flow(prompt, include_code_flow, top_relevance):
        code_flow = trace_code_flow(project_id, prompt, memory_store=memory_store)
        code_flow_included = True
        if code_flow.get("insufficient_evidence"):
            code_flow = None
            code_flow_included = False
        else:
            relationships = _relationships_from_flow(code_flow)

    summary = _build_summary(relevant_symbols, relevant_files, insufficient)
    context_text = _build_context_text(
        prompt,
        relevant_files,
        relevant_symbols,
        evidence_items,
        code_flow,
        relevant_decisions,
        constraints,
        insufficient,
        evidence_note,
    )

    latency_ms = int((time.perf_counter() - started) * 1000)
    response = AgentContextResponse(
        project_id=project_id,
        prompt=prompt,
        task_analysis=task_analysis,
        summary=summary,
        relevant_files=[
            {
                "path": f["path"],
                "relevance_score": round(float(f.get("relevance_score", 0)), 4),
                "symbol": f.get("symbol"),
                "symbol_line": f.get("symbol_line"),
                "snippet": f.get("snippet"),
            }
            for f in relevant_files
        ],
        relevant_symbols=relevant_symbols,
        code_flow=code_flow,
        relationships=relationships,
        evidence=evidence_items,
        relevant_decisions=relevant_decisions,
        constraints=constraints,
        context=context_text,
        confidence=_confidence_label(insufficient, evidence_note),
        insufficient_evidence=insufficient,
        evidence_note=evidence_note,
        disclaimer=_STATIC_DISCLAIMER,
        metrics=AgentContextMetrics(
            files_count=len(relevant_files),
            symbols_count=len(relevant_symbols),
            approx_source_lines=_approx_source_lines(relevant_files, evidence_items),
            response_bytes=0,
            latency_ms=latency_ms,
            code_flow_included=code_flow_included,
        ),
    )

    serialized = json.dumps(response.to_dict(), default=str)
    response.metrics.response_bytes = len(serialized.encode("utf-8"))
    return response
