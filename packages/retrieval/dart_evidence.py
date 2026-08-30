"""
Static evidence extraction for Dart/TS-style source files.

Detects typed code-flow edges from source text without AST or LLM inference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

# Evidence edge types (aligned with code_flow.FlowStep.edge_type)
EDGE_IMPORT = "import"
EDGE_EXPORT = "export"
EDGE_DIRECT_CALL = "direct_call"
EDGE_CONSTRUCTOR = "constructor"
EDGE_INHERITANCE = "inheritance"
EDGE_PLATFORM_CHANNEL = "platform_channel"
EDGE_TEXTUAL = "textual_symbol_match"
EDGE_QUERY_MATCH = "query_match"
EDGE_CALLER = "caller"
EDGE_SAME_FILE_CALLER = "same_file_caller"
EDGE_ADAPTER_BOUNDARY = "adapter_boundary"

STRONG_EDGE_TYPES = frozenset({
    EDGE_DIRECT_CALL,
    EDGE_CONSTRUCTOR,
    EDGE_PLATFORM_CHANNEL,
    EDGE_INHERITANCE,
    EDGE_ADAPTER_BOUNDARY,
})

MEDIUM_EDGE_TYPES = frozenset({
    EDGE_CALLER,
    EDGE_SAME_FILE_CALLER,
    EDGE_EXPORT,
})

WEAK_EDGE_TYPES = frozenset({
    EDGE_IMPORT,
})

EDGE_PRIORITY = {
    EDGE_DIRECT_CALL: 100,
    EDGE_ADAPTER_BOUNDARY: 95,
    EDGE_CONSTRUCTOR: 90,
    EDGE_PLATFORM_CHANNEL: 85,
    EDGE_INHERITANCE: 80,
    EDGE_CALLER: 65,
    EDGE_SAME_FILE_CALLER: 60,
    EDGE_EXPORT: 35,
    EDGE_IMPORT: 40,
    EDGE_TEXTUAL: 0,
    EDGE_QUERY_MATCH: 50,
}

_DEFINITION_LINE = re.compile(
    r"^\s*(?:@\w+(?:\.\w+)?\s+)*"
    r"(?:async\s+)?(?:[\w<>,\[\]?]+\s+)+([A-Za-z_]\w*)\s*\(",
)

_RECEIVER_CALL = re.compile(r"\.([A-Za-z_]\w*)\s*\(")
_BARE_CALL = re.compile(r"(?<![.\w])([A-Za-z_]\w*)\s*\(")
_STATIC_CALL = re.compile(r"([A-Z][A-Za-z0-9_]*)\.([A-Za-z_]\w*)\s*\(")
_CONSTRUCTOR = re.compile(r"(?<![.\w])([A-Z][A-Za-z0-9_]*)\s*\(")
_INHERITANCE = re.compile(
    r"^\s*(?:abstract\s+)?class\s+\w+\s+"
    r"(?:extends|implements|with)\s+([A-Z][A-Za-z0-9_]*)",
    re.M,
)

_PLATFORM_CHANNEL = re.compile(
    r"(?:MethodChannel|EventChannel|BasicMessageChannel)\(\s*['\"]([^'\"]+)['\"]"
)
_INVOKE_METHOD = re.compile(
    r"_channel\.invokeMethod(?:<[^>]+>)?\(\s*['\"]([^'\"]+)['\"]"
)


@dataclass
class EdgeEvidence:
    edge_type: str
    target_file: str
    target_symbol: str
    target_kind: str
    line: int
    evidence: str
    import_str: str = ""
    direction: str = "forward"
    source_symbol: str = ""
    source_file: str = ""


def strip_comments(source: str) -> str:
    """Remove // and /* */ comments for safer pattern matching."""
    out: List[str] = []
    i = 0
    n = len(source)
    in_block = False
    while i < n:
        if in_block:
            end = source.find("*/", i)
            if end == -1:
                break
            i = end + 2
            in_block = False
            continue
        if source.startswith("//", i):
            end = source.find("\n", i)
            if end == -1:
                break
            i = end
            continue
        if source.startswith("/*", i):
            in_block = True
            i += 2
            continue
        out.append(source[i])
        i += 1
    return "".join(out)


def _line_of(source: str, pos: int) -> int:
    return source.count("\n", 0, pos) + 1


def _snippet(source: str, line_no: int, width: int = 100) -> str:
    lines = source.splitlines()
    if line_no < 1 or line_no > len(lines):
        return ""
    text = lines[line_no - 1].strip()
    if len(text) > width:
        return text[: width - 3] + "..."
    return text


def is_definition_line(line: str, name: str) -> bool:
    """True when line declares a method/function rather than calling it."""
    stripped = line.strip()
    if stripped.startswith(("return ", "await ", "throw ", "yield ")):
        return False
    if re.search(rf"=\s*{re.escape(name)}\s*\(", stripped):
        return False
    m = _DEFINITION_LINE.match(stripped)
    if m and m.group(1) == name:
        return True
    if re.match(
        rf"^\s*(?:@\w+(?:\.\w+)?\s+)*(?:async\s+)?"
        rf"(?:void|Future|String|int|bool|Widget|dynamic|[\w<>,\[\]?]+)\s+"
        rf"{re.escape(name)}\s*\(",
        stripped,
    ):
        return True
    return False


def _symbol_lookup(
    reachable: List[Tuple[str, Any, str]],
) -> Dict[str, List[Tuple[str, Any, str]]]:
    by_name: Dict[str, List[Tuple[str, Any, str]]] = {}
    for item in reachable:
        sym = item[1]
        name = getattr(sym, "name", "")
        if name:
            by_name.setdefault(name, []).append(item)
    return by_name


def _class_names(reachable: List[Tuple[str, Any, str]]) -> Set[str]:
    names: Set[str] = set()
    for _f, sym, _via in reachable:
        if getattr(sym, "kind", "") in ("class", "enum", "interface", "struct"):
            names.add(getattr(sym, "name", ""))
    return {n for n in names if n}


def find_source_edges(
    source: str,
    file_path: str,
    reachable: List[Tuple[str, Any, str]],
    *,
    current_symbol: str = "",
    include_same_file_callers: bool = True,
    lookups: Optional[Dict[str, Any]] = None,
) -> List[EdgeEvidence]:
    """
    Find evidence-backed edges from source in the current file.

    When current_symbol is set, only scan that symbol's body for outbound edges.
    """
    if not source:
        return []

    start_line, end_line = _symbol_body_span(source, file_path, current_symbol, lookups)
    scoped_source = _slice_source_lines(source, start_line, end_line) if current_symbol else source
    line_offset = start_line - 1 if current_symbol else 0

    cleaned = strip_comments(scoped_source)
    lines = scoped_source.splitlines()
    by_name = _symbol_lookup(reachable)
    class_names = _class_names(reachable)
    edges: List[EdgeEvidence] = []
    seen: Set[Tuple[str, str, str, int]] = set()

    def add(
        edge_type: str,
        sym_file: str,
        sym,
        line_no: int,
        evidence: str,
    ) -> None:
        name = getattr(sym, "name", "") if sym else ""
        kind = getattr(sym, "kind", "file") if sym else "file"
        abs_line = line_no + line_offset
        key = (edge_type, sym_file, name, abs_line)
        if key in seen:
            return
        seen.add(key)
        edges.append(
            EdgeEvidence(
                edge_type=edge_type,
                target_file=sym_file,
                target_symbol=name,
                target_kind=kind,
                line=abs_line,
                evidence=evidence,
            )
        )

    for line_no, raw_line in enumerate(lines, start=1):
        line = strip_comments(raw_line)

        for m in _RECEIVER_CALL.finditer(line):
            name = m.group(1)
            if name not in by_name or is_definition_line(raw_line, name):
                continue
            if current_symbol and name == current_symbol and f".{name}(" in raw_line:
                continue
            for sym_file, sym, _via in by_name[name]:
                add(
                    EDGE_DIRECT_CALL,
                    sym_file,
                    sym,
                    line_no,
                    f"{file_path} calls {name} via receiver at line {line_no + line_offset}",
                )

        for m in _STATIC_CALL.finditer(line):
            cls_name, method = m.group(1), m.group(2)
            if method not in by_name or is_definition_line(raw_line, method):
                continue
            for sym_file, sym, _via in by_name[method]:
                add(
                    EDGE_DIRECT_CALL,
                    sym_file,
                    sym,
                    line_no,
                    f"{file_path} calls {cls_name}.{method} at line {line_no + line_offset}",
                )

        for m in _CONSTRUCTOR.finditer(line):
            name = m.group(1)
            if name not in class_names or name not in by_name:
                continue
            if is_definition_line(raw_line, name):
                continue
            if re.search(rf"=\s*{re.escape(name)}\s*\(", raw_line):
                continue
            for sym_file, sym, _via in by_name[name]:
                if getattr(sym, "kind", "") not in ("class", "enum"):
                    continue
                add(
                    EDGE_CONSTRUCTOR,
                    sym_file,
                    sym,
                    line_no,
                    f"{file_path} constructs {name} at line {line_no + line_offset}",
                )

        for m in _BARE_CALL.finditer(line):
            name = m.group(1)
            if name in class_names:
                continue
            if name not in by_name or is_definition_line(raw_line, name):
                continue
            if any(
                prev in raw_line
                for prev in (f".{name}(", f"{name}.", "class ", "extends ", "implements ")
            ):
                continue
            for sym_file, sym, _via in by_name[name]:
                add(
                    EDGE_DIRECT_CALL,
                    sym_file,
                    sym,
                    line_no,
                    f"{file_path} calls {name} at line {line_no + line_offset}",
                )

    for m in _INHERITANCE.finditer(cleaned):
        name = m.group(1)
        if name not in by_name:
            continue
        line_no = _line_of(source, m.start())
        for sym_file, sym, _via in by_name[name]:
            add(
                EDGE_INHERITANCE,
                sym_file,
                sym,
                line_no,
                f"{file_path} extends/implements {name}",
            )

    return edges


def _same_file_symbols(
    reachable: List[Tuple[str, Any, str]],
    file_path: str,
) -> List[Any]:
    return [sym for f, sym, _via in reachable if f == file_path]


def _skip_string(text: str, i: int) -> int:
    """Return index after a quote-delimited string starting at i, or i+1."""
    n = len(text)
    quote = text[i]
    triple = text[i : i + 3] == quote * 3
    i += 3 if triple else 1
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if triple:
            if text[i : i + 3] == quote * 3:
                return i + 3
            i += 1
            continue
        if ch == quote:
            return i + 1
        i += 1
    return n


def _match_braces_end(text: str, open_pos: int, start_line: int, fallback: int) -> int:
    """1-based line of the `}` matching `{` at open_pos."""
    depth = 1
    k = open_pos + 1
    n = len(text)
    while k < n:
        c = text[k]
        if c in ("'", '"'):
            k = _skip_string(text, k)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start_line + text[:k].count("\n")
        k += 1
    return fallback


def _function_body_end_line(lines: List[str], start_line: int) -> int:
    """Find 1-based end line of a function body via brace matching.

    Parameter-list parens are closed first so Dart named-parameter `{`
    (e.g. `foo(Bar bar, {int? x}) {`) is not treated as the function body.
    Brace matching then starts at the body `{`, not at a far-away next symbol.
    """
    start_idx = max(start_line - 1, 0)
    stripped = [strip_comments(line) for line in lines[start_idx:]]
    text = "\n".join(stripped)
    n = len(text)
    i = 0
    paren = 0
    seen_paren = False
    fallback = min(start_line + 80, len(lines))

    while i < n:
        ch = text[i]
        if ch in ("'", '"'):
            i = _skip_string(text, i)
            continue
        if not seen_paren:
            if ch == "(":
                seen_paren = True
                paren = 1
            i += 1
            continue
        if paren > 0:
            if ch == "(":
                paren += 1
            elif ch == ")":
                paren -= 1
            i += 1
            continue
        if ch.isspace():
            i += 1
            continue
        async_m = re.match(r"(?:async|sync)\s*\*?\s*", text[i:])
        if async_m:
            i += async_m.end()
            continue
        if ch == "=" and i + 1 < n and text[i + 1] == ">":
            j = i + 2
            while j < n:
                if text[j] in ("'", '"'):
                    j = _skip_string(text, j)
                    continue
                if text[j] == ";":
                    return start_line + text[: j].count("\n")
                j += 1
            return min(start_line + 2, len(lines)) or 1
        if ch == "{":
            return _match_braces_end(text, i, start_line, fallback)
        i += 1
    return fallback


def _symbol_body_span(
    source: str,
    file_path: str,
    current_symbol: str,
    lookups: Optional[Dict[str, Any]] = None,
) -> Tuple[int, int]:
    """Return 1-based inclusive line range for current_symbol in source."""
    if not current_symbol or not source:
        return 1, len(source.splitlines())

    symbols = []
    if lookups:
        symbols = sorted(
            lookups.get("symbols_by_file", {}).get(file_path, []),
            key=lambda s: getattr(s, "line", 0),
        )
    lines = source.splitlines()
    start = 1
    end = len(lines)
    sym_kind = ""
    for i, sym in enumerate(symbols):
        if getattr(sym, "name", "") != current_symbol:
            continue
        start = max(getattr(sym, "line", 1), 1)
        sym_kind = getattr(sym, "kind", "")
        if sym_kind == "function":
            end = _function_body_end_line(lines, start)
        elif i + 1 < len(symbols):
            end = max(getattr(symbols[i + 1], "line", len(lines) + 1) - 1, start)
        else:
            end = len(lines)
        break
    else:
        # Fallback when symbol is missing from index metadata.
        for i, line in enumerate(lines, start=1):
            if current_symbol in line and "(" in line:
                start = i
                end = _function_body_end_line(lines, start)
                break
    return start, end


def _slice_source_lines(source: str, start_line: int, end_line: int) -> str:
    lines = source.splitlines()
    if not lines:
        return source
    s = max(start_line - 1, 0)
    e = min(end_line, len(lines))
    return "\n".join(lines[s:e])


def find_same_file_callers(
    source: str,
    file_path: str,
    callee_name: str,
    reachable: List[Tuple[str, Any, str]],
) -> List[EdgeEvidence]:
    """Emit direct_call edges to same-file symbols whose body invokes callee_name."""
    if not source or not callee_name:
        return []

    same_file = [
        sym
        for f, sym, _via in reachable
        if f == file_path and getattr(sym, "name", "") != callee_name
    ]
    if not same_file:
        return []

    same_file.sort(key=lambda s: getattr(s, "line", 0))
    lines = source.splitlines()
    call_pat = re.compile(rf"(?<![.\w]){re.escape(callee_name)}\s*\(")
    edges: List[EdgeEvidence] = []
    seen: Set[str] = set()

    for i, sym in enumerate(same_file):
        caller = getattr(sym, "name", "")
        kind = getattr(sym, "kind", "")
        if not caller or caller in seen:
            continue
        if kind in ("class", "enum", "interface", "struct", "platform_channel"):
            continue
        start = max(getattr(sym, "line", 1) - 1, 0)
        end = _function_body_end_line(lines, getattr(sym, "line", 1))
        chunk_lines = lines[start:end]
        chunk = strip_comments("\n".join(chunk_lines))
        if not call_pat.search(chunk):
            continue
        call_line = start + 1
        for offset, raw in enumerate(chunk_lines):
            if call_pat.search(strip_comments(raw)) and not is_definition_line(raw, callee_name):
                call_line = start + offset + 1
                break
        seen.add(caller)
        edges.append(
            EdgeEvidence(
                edge_type=EDGE_SAME_FILE_CALLER,
                target_file=file_path,
                target_symbol=caller,
                target_kind=getattr(sym, "kind", "function"),
                line=call_line,
                evidence=f"{caller}() calls {callee_name}() at line {call_line} (same file, static evidence)",
                direction="backward",
                source_symbol=caller,
                source_file=file_path,
            )
        )
    return edges


def edge_priority(edge_type: str) -> int:
    return EDGE_PRIORITY.get(edge_type, 0)
