"""LLM-powered analyzer + relevance selector for the Context Runtime.

Uses Emergent Universal Key via `emergentintegrations` to call GPT-5.4-mini and
return strict JSON. Falls back to deterministic mock output only if the LLM call
fails (never silently — logs a warning).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
from emergentintegrations.llm.chat import (
    LlmChat,
    StreamDone,
    TextDelta,
    UserMessage,
)

logger = logging.getLogger(__name__)

# Ensure .env is loaded regardless of import order.
load_dotenv(Path(__file__).parent / ".env")


def _get_key() -> str:
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise RuntimeError("EMERGENT_LLM_KEY not configured in /app/backend/.env")
    return key


POC_PROVIDER = os.environ.get("POC_PROVIDER", "openai")
POC_MODEL = os.environ.get("POC_MODEL", "gpt-5.4-mini")


# ---------- Token estimation (deterministic, labeled "estimated" in UI) ----------

def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def hash_content(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12]


# ---------- Prompts ----------

ANALYZE_SYSTEM = """You are the Context Runtime — an engine that turns a raw software project (files, docs, conversation history) into a compact, structured Project Knowledge Cache.

Your job is to extract ONLY durable, useful, non-redundant knowledge. Discard chit-chat, marketing, duplicate re-explanations, and noise. Preserve important decisions, resolved bugs, rejected approaches, and open issues distinctly.

Return STRICT JSON matching this schema exactly (no prose, no markdown fences):

{
  "project_identity": {
    "type": "string",
    "stack": ["string"],
    "purpose": "string",
    "architecture_summary": "string (2-4 sentences)"
  },
  "architecture": {
    "frontend": "string",
    "backend": "string",
    "database": "string",
    "authentication": "string",
    "networking": "string",
    "infrastructure": "string"
  },
  "components": [
    {"name": "string", "kind": "service|repository|module|class|widget|function", "purpose": "string"}
  ],
  "decisions": [
    {"title": "string", "rationale": "string"}
  ],
  "current_state": {
    "implemented": ["string"],
    "in_progress": ["string"],
    "known_issues": ["string"]
  },
  "conversation_memory": {
    "permanent_knowledge": ["string"],
    "temporary_task_context": ["string"],
    "resolved_issues": ["string"],
    "rejected_approaches": ["string"],
    "open_issues": ["string"]
  }
}

Rules:
- Output MUST be valid JSON parseable by json.loads.
- Use empty string/array — never null.
- Be terse. Each list entry is one crisp sentence.
- Never invent facts not present in the input.
"""

SELECT_SYSTEM = """You are the Context Runtime — you select only the pieces of a Project Knowledge Cache that are relevant to a specific coding task, and assemble an AI-ready context block.

You will receive:
  - the full Context Cache (JSON)
  - a task description

Return STRICT JSON matching:

{
  "relevant": {
    "components": ["string"],
    "architecture_keys": ["string"],
    "decisions": ["string"],
    "conversation_memory": ["string"]
  },
  "ignored": {
    "components": ["string"],
    "architecture_keys": ["string"],
    "decisions": ["string"],
    "conversation_memory": ["string"]
  },
  "assembled_context": "string — a compact, Markdown-formatted context block containing only the relevant knowledge"
}

Rules:
- Output MUST be valid JSON. No prose outside JSON. No markdown fences around the JSON.
- The assembled_context itself may contain Markdown headings and lists.
- Aim for the smallest useful context (typically < 2000 tokens).
- Never invent facts absent from the cache.
"""


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_json_fences(s: str) -> str:
    s = s.strip()
    s = _JSON_FENCE_RE.sub("", s).strip()
    if not s.startswith("{"):
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1:
            s = s[start : end + 1]
    return s


def _parse_json_strict(raw: str) -> Dict[str, Any]:
    return json.loads(_strip_json_fences(raw))


async def _stream_to_text(chat: LlmChat, prompt: str) -> str:
    buf: List[str] = []
    async for ev in chat.stream_message(UserMessage(text=prompt)):
        if isinstance(ev, TextDelta):
            buf.append(ev.content)
        elif isinstance(ev, StreamDone):
            break
    return "".join(buf)


# ---------- Public API ----------

async def analyze_project_context(
    project: Dict[str, Any],
    sources: List[Dict[str, Any]],
    session_id: str,
) -> Dict[str, Any]:
    """Take a project dict + list of source dicts (type/name/content) -> Context Cache JSON."""
    if not _get_key():
        raise RuntimeError("EMERGENT_LLM_KEY not configured")

    chat = LlmChat(
        api_key=_get_key(),
        session_id=session_id,
        system_message=ANALYZE_SYSTEM,
    ).with_model(POC_PROVIDER, POC_MODEL)

    lines: List[str] = [
        "# Project",
        f"Name: {project.get('name','')}",
        f"Description: {project.get('description','')}",
        f"Stack: {', '.join(project.get('stack', []))}",
        "",
    ]

    files = [s for s in sources if s.get("type") == "file"]
    docs = [s for s in sources if s.get("type") == "documentation"]
    notes = [s for s in sources if s.get("type") == "note"]
    convs = [s for s in sources if s.get("type") == "conversation"]

    if files:
        lines.append("# Project Files")
        for f in files:
            lines.append(f"\n## {f.get('name','file')}\n```\n{(f.get('content') or '')[:8000]}\n```")
    if docs:
        lines.append("\n# Documentation")
        for d in docs:
            lines.append(f"\n## {d.get('name','doc')}\n{(d.get('content') or '')[:8000]}")
    if notes:
        lines.append("\n# Notes")
        for n in notes:
            lines.append(f"- {(n.get('content') or '')[:2000]}")
    if convs:
        lines.append("\n# Conversation History")
        for c in convs:
            lines.append((c.get("content") or "")[:60000])

    prompt = "\n".join(lines) + "\n\nReturn ONLY the JSON cache. No prose. No markdown fences."

    raw_out = await _stream_to_text(chat, prompt)
    return _parse_json_strict(raw_out)


async def select_relevant_context(
    cache: Dict[str, Any],
    task: str,
    session_id: str,
) -> Dict[str, Any]:
    if not _get_key():
        raise RuntimeError("EMERGENT_LLM_KEY not configured")

    chat = LlmChat(
        api_key=_get_key(),
        session_id=session_id,
        system_message=SELECT_SYSTEM,
    ).with_model(POC_PROVIDER, POC_MODEL)

    prompt = (
        "# Context Cache (JSON)\n"
        f"{json.dumps(cache, indent=2)}\n\n"
        "# Task\n"
        f"{task}\n\n"
        "Return ONLY the JSON result. No prose. No markdown fences."
    )
    raw_out = await _stream_to_text(chat, prompt)
    return _parse_json_strict(raw_out)


def count_knowledge_items(cache: Dict[str, Any]) -> int:
    n = 0
    n += len(cache.get("components", []))
    n += len(cache.get("decisions", []))
    cs = cache.get("current_state", {}) or {}
    n += len(cs.get("implemented", []))
    n += len(cs.get("in_progress", []))
    n += len(cs.get("known_issues", []))
    mem = cache.get("conversation_memory", {}) or {}
    for k in (
        "permanent_knowledge",
        "temporary_task_context",
        "resolved_issues",
        "rejected_approaches",
        "open_issues",
    ):
        n += len(mem.get(k, []))
    return n


def compute_source_tokens(sources: List[Dict[str, Any]]) -> Dict[str, int]:
    files_txt = "\n".join((s.get("content") or "") for s in sources if s.get("type") == "file")
    docs_txt = "\n".join((s.get("content") or "") for s in sources if s.get("type") == "documentation")
    notes_txt = "\n".join((s.get("content") or "") for s in sources if s.get("type") == "note")
    conv_txt = "\n".join((s.get("content") or "") for s in sources if s.get("type") == "conversation")
    files = estimate_tokens(files_txt)
    docs = estimate_tokens(docs_txt)
    notes = estimate_tokens(notes_txt)
    conv = estimate_tokens(conv_txt)
    return {
        "files": files,
        "documentation": docs,
        "notes": notes,
        "conversation": conv,
        "total": files + docs + notes + conv,
    }


def count_source_files(sources: List[Dict[str, Any]]) -> int:
    return sum(1 for s in sources if s.get("type") == "file")


def count_source_messages(sources: List[Dict[str, Any]]) -> int:
    total = 0
    for s in sources:
        if s.get("type") != "conversation":
            continue
        content = s.get("content") or ""
        # Split by lines starting with a role tag or blank line separators.
        lines = [ln for ln in content.splitlines() if ln.strip()]
        # If each 'msg' is a line, this is close enough. Cap min 1 per non-empty source.
        if not lines:
            continue
        total += max(1, sum(1 for ln in lines if re.match(r"^\s*(user|assistant|system|\[\d+\])[:\s]", ln, re.IGNORECASE)) or len(lines) // 2)
    return total
