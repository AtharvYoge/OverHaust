"""
Retrieval over persisted project index metadata (files + symbols).

Does not store or search full file contents in SQLite — only indexed metadata.
Source snippets are read from disk at context-build time via read_indexed_snippet().
"""

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from packages.context.relevance import ScoredMemory, _keywords
from packages.retrieval.semantic import cosine_similarity
from packages.shared.config import (
    embeddings_enabled,
    get_hybrid_weights,
    get_index_search_limit,
    get_index_semantic_batch_size,
    get_index_snippet_max_chars,
    get_index_snippet_max_lines,
)

logger = logging.getLogger(__name__)


def build_index_search_text(file_record, symbol=None) -> str:
    """Build searchable text from index metadata only (no fabricated summaries)."""
    path = getattr(file_record, "path", "") or ""
    parts = [path.replace("/", " ").replace("_", " ")]
    symbols = getattr(file_record, "symbols", []) or []
    if symbol is not None:
        parts.append(getattr(symbol, "name", ""))
        parts.append(getattr(symbol, "kind", ""))
    else:
        parts.extend(getattr(s, "name", "") for s in symbols[:20])
    parts.extend(getattr(file_record, "imports", []) or [])
    parts.extend(getattr(file_record, "exports", []) or [])
    return " ".join(p for p in parts if p)


def build_index_content(file_record, symbol=None) -> str:
    """Human-readable content line for API/context (metadata-derived)."""
    path = getattr(file_record, "path", "")
    if symbol is not None:
        name = getattr(symbol, "name", "")
        kind = getattr(symbol, "kind", "symbol")
        line = getattr(symbol, "line", 0)
        return f"Symbol {name} ({kind}) in {path} at line {line}"
    syms = [getattr(s, "name", "") for s in (getattr(file_record, "symbols", []) or [])[:12]]
    content = f"File {path}"
    if syms:
        content += f" defines {', '.join(syms)}"
    imps = getattr(file_record, "imports", []) or []
    if imps:
        content += f"; imports {', '.join(imps[:6])}"
    return content


def _stable_index_id(
    project_id: str,
    record_type: str,
    file_path: str,
    symbol_name: str = "",
) -> str:
    """Deterministic id scoped to a project so identical symbols do not collide."""
    key = f"{project_id}:{record_type}:{file_path}:{symbol_name}"
    return f"index:{record_type}:{hashlib.sha256(key.encode()).hexdigest()[:12]}"


def index_hit_to_memory(
    project_id: str,
    file_record,
    *,
    symbol=None,
    indexed_at: str = "",
) -> Dict[str, Any]:
    """Convert an index hit to a synthetic memory dict for ScoredMemory."""
    path = getattr(file_record, "path", "")
    is_symbol = symbol is not None
    record_type = "indexed_symbol" if is_symbol else "indexed_file"
    meta: Dict[str, Any] = {
        "source_type": "symbol" if is_symbol else "file",
        "source_ref": path,
        "file_path": path,
        "authority": "indexer",
        "status": "active",
        "record_type": record_type,
        "knowledge_type": "code_reference",
        "provenance": path if not is_symbol else f"{path} ({getattr(symbol, 'name', '')})",
    }
    if is_symbol:
        meta["symbol_name"] = getattr(symbol, "name", "")
        meta["symbol_kind"] = getattr(symbol, "kind", "")
        meta["symbol_line"] = getattr(symbol, "line", 0)

    mem_id = _stable_index_id(
        project_id,
        "symbol" if is_symbol else "file",
        path,
        meta.get("symbol_name", ""),
    )
    return {
        "id": mem_id,
        "project_id": project_id,
        "content": build_index_content(file_record, symbol),
        "memory_type": "permanent",
        "importance_score": 0.65 if is_symbol else 0.6,
        "created_at": indexed_at or datetime.now(timezone.utc).isoformat(),
        "updated_at": indexed_at or datetime.now(timezone.utc).isoformat(),
        "metadata": meta,
    }


def _expand_identifier_keywords(words: List[str]) -> List[str]:
    """
    Split dotted identifiers such as Class.method into searchable parts.

    Query tokenizers keep ``OverhaustAgent.get_relevant_context`` as one word,
    which never matches the indexed symbol ``get_relevant_context``.
    """
    expanded: List[str] = []
    seen = set()
    for word in words or []:
        parts = [word]
        if "." in word:
            parts.extend(p for p in word.split(".") if p)
        for part in parts:
            key = part.lower()
            if key and key not in seen:
                seen.add(key)
                expanded.append(part)
    return expanded


def _matches_index_term(text: str, term: str) -> bool:
    """Use token-aware matching for short terms such as KOT."""
    if len(term) > 3:
        return term.lower() in text.lower()
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    tokens = re.findall(r"[A-Za-z0-9]+", separated.lower())
    return term.lower() in tokens


def score_index_record(
    query: str,
    search_text: str,
    path: str,
    *,
    symbol_name: Optional[str] = None,
    is_config: bool = False,
) -> Tuple[float, List[str]]:
    """Keyword score for one index record with intent-aware adjustments."""
    from packages.retrieval.index_ranking import adjust_index_score, detect_query_intent

    q_lower = query.strip().lower()
    text_lower = search_text.lower()
    reasons: List[str] = []
    score = 0.0
    content_matched = False
    path_matched = False

    if q_lower and q_lower in text_lower:
        score += 3.0
        reasons.append("exact phrase in index metadata")
        content_matched = True

    q_words = _expand_identifier_keywords(_keywords(query))
    if not q_words:
        return 0.0, []

    matched = 0
    for qw in q_words:
        variants = {qw}
        if qw.endswith("s") and len(qw) > 3:
            variants.add(qw[:-1])
        else:
            variants.add(qw + "s")
        hit = False
        for v in variants:
            if _matches_index_term(search_text, v):
                matched += 1
                hit = True
                content_matched = True
                break
            if (
                len(v) >= 3
                and v not in {"app", "lib", "src"}
                and _matches_index_term(path, v)
            ):
                matched += 1.5
                hit = True
                path_matched = True
                break
        if hit:
            reasons.append(f"keyword '{qw}'")

    if symbol_name:
        sym_l = symbol_name.lower()
        for qw in q_words:
            if len(qw) >= 3 and _matches_index_term(symbol_name, qw):
                content_matched = True
                if f"symbol name '{qw}'" not in reasons:
                    reasons.append(f"symbol name '{qw}'")
            # Qualified names (Class.method) should rank the method above the class.
            if "." in qw and sym_l == qw.split(".")[-1].lower():
                score += 4.0
                content_matched = True
                reasons.append(f"qualified symbol '{symbol_name}'")

    if matched == 0:
        return 0.0, []

    score += matched * 1.5
    if any(
        _matches_index_term(path, w)
        for w in q_words
        if len(w) >= 3 and w not in {"app", "lib", "src"}
    ):
        score += 1.0
        path_matched = True
        reasons.append("path match")

    path_only = path_matched and not content_matched
    intent = detect_query_intent(query)
    return adjust_index_score(
        query,
        intent,
        path,
        symbol_name,
        score,
        reasons,
        path_only_match=path_only,
        is_config=is_config,
    )


def search_index_keyword(
    project_id: str,
    query: str,
    index,
    limit: int = 8,
) -> List[ScoredMemory]:
    """Rank indexed files and symbols by keyword overlap."""
    if index is None or not getattr(index, "files", None):
        return []

    indexed_at = getattr(index, "indexed_at", "") or ""
    candidates: List[ScoredMemory] = []

    for file_record in index.files:
        path = getattr(file_record, "path", "")
        if not path:
            continue

        file_text = build_index_search_text(file_record)
        fscore, freasons = score_index_record(
            query, file_text, path,
            is_config=getattr(file_record, "is_config", False),
        )
        if fscore > 0:
            mem = index_hit_to_memory(project_id, file_record, indexed_at=indexed_at)
            candidates.append(ScoredMemory(
                memory=mem,
                score=round(fscore, 4),
                reasons=freasons or ["file metadata match"],
                retrieval_methods=["index_keyword"],
            ))

        for sym in getattr(file_record, "symbols", []) or []:
            sym_text = build_index_search_text(file_record, sym)
            sscore, sreasons = score_index_record(
                query, sym_text, path,
                symbol_name=getattr(sym, "name", ""),
                is_config=getattr(file_record, "is_config", False),
            )
            if sscore > 0:
                sym_score = sscore + 0.5  # slight boost for direct symbol hit
                mem = index_hit_to_memory(
                    project_id, file_record, symbol=sym, indexed_at=indexed_at
                )
                candidates.append(ScoredMemory(
                    memory=mem,
                    score=round(sym_score, 4),
                    reasons=sreasons or [f"symbol {getattr(sym, 'name', '')}"],
                    retrieval_methods=["index_keyword"],
                ))

    candidates.sort(key=lambda s: s.score, reverse=True)
    from packages.retrieval.index_ranking import rank_index_candidates
    return rank_index_candidates(query, candidates)[:limit]


def _index_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _resolve_index_embeddings(
    work_items: List[Tuple[Dict[str, Any], str]],
    project_id: str,
    provider,
    embedding_store,
) -> List[Optional[List[float]]]:
    """Load cached vectors or batch-embed missing index records."""
    model_id = provider.model_id
    batch_size = get_index_semantic_batch_size()
    vectors: List[Optional[List[float]]] = [None] * len(work_items)
    pending: List[Tuple[str, str, str, int]] = []

    for i, (mem, text) in enumerate(work_items):
        mem_id = mem["id"]
        content_hash = _index_content_hash(text)
        stored = embedding_store.get(mem_id, model_id)
        if stored is not None and stored[0] == content_hash:
            vectors[i] = stored[1]
        else:
            pending.append((mem_id, text, content_hash, i))

    for start in range(0, len(pending), batch_size):
        chunk = pending[start : start + batch_size]
        texts = [item[1] for item in chunk]
        try:
            embedded = provider.embed_texts(texts)
        except Exception as exc:
            logger.warning("Batch index embed failed: %s", exc)
            continue
        for (mem_id, _text, content_hash, idx), vec in zip(chunk, embedded):
            embedding_store.upsert(mem_id, project_id, model_id, content_hash, vec)
            vectors[idx] = vec

    return vectors


def _semantic_candidate_limit(limit: int) -> int:
    return min(max(limit, 1) * 10, 100)


def _build_semantic_work_items(
    project_id: str,
    index,
    keyword_hits: Optional[List[ScoredMemory]],
    indexed_at: str,
    query: str = "",
    limit: int = 8,
) -> List[Tuple[Dict[str, Any], str]]:
    """Candidates for index semantic search — keyword prefilter, else file-level cap."""
    if keyword_hits:
        items: List[Tuple[Dict[str, Any], str]] = []
        for sm in keyword_hits:
            mem = sm.memory
            meta = mem.get("metadata") or {}
            path = meta.get("file_path") or ""
            sym_name = meta.get("symbol_name")
            file_record = next(
                (f for f in (getattr(index, "files", []) or []) if f.path == path),
                None,
            )
            if file_record is None:
                items.append((mem, mem.get("content") or path))
                continue
            sym = None
            if sym_name:
                sym = next(
                    (s for s in (file_record.symbols or []) if s.name == sym_name),
                    None,
                )
            text = build_index_search_text(file_record, sym)
            items.append((mem, text))
        return items

    cap = _semantic_candidate_limit(limit)
    ranked: List[Tuple[float, Dict[str, Any], str]] = []

    for file_record in getattr(index, "files", []) or []:
        path = getattr(file_record, "path", "")
        if not path:
            continue
        file_text = build_index_search_text(file_record)
        fscore, _ = score_index_record(
            query, file_text, path,
            is_config=getattr(file_record, "is_config", False),
        )
        if fscore > 0:
            mem = index_hit_to_memory(project_id, file_record, indexed_at=indexed_at)
            ranked.append((fscore, mem, file_text))
        for sym in getattr(file_record, "symbols", []) or []:
            sym_text = build_index_search_text(file_record, sym)
            sscore, _ = score_index_record(
                query, sym_text, path,
                symbol_name=getattr(sym, "name", ""),
                is_config=getattr(file_record, "is_config", False),
            )
            if sscore > 0:
                mem = index_hit_to_memory(
                    project_id, file_record, symbol=sym, indexed_at=indexed_at
                )
                ranked.append((sscore + 0.5, mem, sym_text))

    if ranked:
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [(mem, text) for _, mem, text in ranked[:cap]]

    items = []
    for file_record in getattr(index, "files", []) or []:
        path = getattr(file_record, "path", "")
        if not path:
            continue
        mem = index_hit_to_memory(project_id, file_record, indexed_at=indexed_at)
        text = build_index_search_text(file_record)
        items.append((mem, text))
        if len(items) >= cap:
            break
    return items


def search_index_semantic(
    project_id: str,
    query: str,
    index,
    limit: int = 8,
    provider=None,
    memory_store=None,
    keyword_hits: Optional[List[ScoredMemory]] = None,
) -> List[ScoredMemory]:
    """Semantic search over index metadata with persisted embeddings."""
    if index is None or not getattr(index, "files", None):
        return []

    if provider is None:
        from packages.retrieval.embeddings import get_embedding_provider
        provider = get_embedding_provider()

    if not provider.is_available:
        return []

    if memory_store is None:
        from packages.memory.memory_store import get_memory_store
        memory_store = get_memory_store()

    from packages.retrieval.embedding_store import EmbeddingStore

    query_vec = provider.embed_query(query)
    if not query_vec:
        return []

    indexed_at = getattr(index, "indexed_at", "") or ""
    embedding_store = EmbeddingStore(memory_store)
    work_items = _build_semantic_work_items(
        project_id, index, keyword_hits, indexed_at, query=query, limit=limit
    )
    if not work_items:
        return []

    vectors = _resolve_index_embeddings(
        work_items, project_id, provider, embedding_store
    )

    hits: List[ScoredMemory] = []
    for (mem, _text), vec in zip(work_items, vectors):
        if vec is None:
            continue
        sim = cosine_similarity(query_vec, vec)
        if sim <= 0.05:
            continue
        meta = mem.get("metadata") or {}
        label = meta.get("symbol_name") or meta.get("file_path") or mem.get("id", "")
        hits.append(ScoredMemory(
            memory=mem,
            score=round(sim, 4),
            reasons=[f"index semantic similarity: {sim:.3f} ({label})"],
            retrieval_methods=["index_semantic"],
        ))

    hits.sort(key=lambda s: s.score, reverse=True)
    return hits[:limit]


def search_index_hybrid(
    project_id: str,
    query: str,
    index,
    limit: int = 8,
    provider=None,
    memory_store=None,
) -> List[ScoredMemory]:
    """Fuse index keyword + semantic scores."""
    kw = search_index_keyword(project_id, query, index, limit=limit * 3)
    sem = search_index_semantic(
        project_id,
        query,
        index,
        limit=limit * 3,
        provider=provider,
        memory_store=memory_store,
        keyword_hits=kw if kw else None,
    )

    merged: Dict[str, Dict[str, Any]] = {}
    max_kw = max((r.score for r in kw), default=0.0) or 1.0

    for kr in kw:
        mid = kr.memory["id"]
        merged[mid] = {
            "memory": kr.memory,
            "kw_norm": kr.score / max_kw,
            "sem_score": 0.0,
            "kw_reasons": list(kr.reasons),
            "sem_reasons": [],
            "methods": ["index_keyword"],
        }

    for sr in sem:
        mid = sr.memory["id"]
        if mid not in merged:
            merged[mid] = {
                "memory": sr.memory,
                "kw_norm": 0.0,
                "sem_score": sr.score,
                "kw_reasons": [],
                "sem_reasons": list(sr.reasons),
                "methods": ["index_semantic"],
            }
        else:
            merged[mid]["sem_score"] = sr.score
            merged[mid]["sem_reasons"] = list(sr.reasons)
            if "index_semantic" not in merged[mid]["methods"]:
                merged[mid]["methods"].append("index_semantic")

    if not merged:
        return []

    from packages.retrieval.index_ranking import hybrid_weights_for_query, rank_index_candidates

    w = hybrid_weights_for_query(query, kw)
    scored: List[ScoredMemory] = []
    for entry in merged.values():
        final = w["keyword"] * entry["kw_norm"] + w["semantic"] * entry["sem_score"]
        reasons: List[str] = []
        if entry["kw_norm"] > 0:
            reasons.extend(entry["kw_reasons"])
        if entry["sem_score"] > 0:
            reasons.extend(entry["sem_reasons"])
        if final > 0.05:
            methods = list(entry["methods"])
            if "index_hybrid" not in methods:
                methods.append("index_hybrid")
            scored.append(ScoredMemory(
                memory=entry["memory"],
                score=round(final, 4),
                reasons=reasons,
                retrieval_methods=methods,
            ))

    scored = rank_index_candidates(query, scored)
    return scored[:limit]


def search_index_records(
    project_id: str,
    query: str,
    index,
    limit: Optional[int] = None,
    memory_store=None,
) -> List[ScoredMemory]:
    """Search project index using keyword or hybrid based on config."""
    if index is None:
        return []
    lim = limit if limit is not None else get_index_search_limit()
    if embeddings_enabled():
        return search_index_hybrid(
            project_id, query, index, limit=lim, memory_store=memory_store
        )
    return search_index_keyword(project_id, query, index, limit=lim)


def read_indexed_snippet(
    root_path: str,
    rel_path: str,
    *,
    symbol_line: Optional[int] = None,
    max_lines: Optional[int] = None,
    max_chars: Optional[int] = None,
) -> Optional[str]:
    """
    Read a bounded snippet from disk with path containment checks.
    Returns None if path is invalid or unreadable.
    """
    from services.ingestion.project_indexer import ProjectIndexer, PathSecurityError

    max_lines = max_lines if max_lines is not None else get_index_snippet_max_lines()
    max_chars = max_chars if max_chars is not None else get_index_snippet_max_chars()

    try:
        indexer = ProjectIndexer()
        root = indexer._validate_root(root_path)
        rel = rel_path.replace("\\", "/").lstrip("/")
        if ".." in rel.split("/"):
            raise PathSecurityError(f"Path traversal rejected: {rel_path}")
        full = (root / rel).resolve()
        full.relative_to(root)
    except (PathSecurityError, ValueError, OSError) as exc:
        logger.warning("Snippet read rejected for %s: %s", rel_path, exc)
        return None

    try:
        raw = full.read_bytes()
        text = raw.decode("utf-8", errors="replace")
    except OSError:
        return None

    lines = text.splitlines()
    if symbol_line and symbol_line > 0:
        start = max(0, symbol_line - max_lines // 2)
        end = min(len(lines), start + max_lines)
        snippet_lines = lines[start:end]
        prefix = f"// lines {start + 1}-{end} of {rel_path}\n"
    else:
        snippet_lines = lines[:max_lines]
        prefix = f"// first {len(snippet_lines)} lines of {rel_path}\n"

    snippet = prefix + "\n".join(snippet_lines)
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars] + "\n// ... truncated"
    return snippet
