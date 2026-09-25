"""
Shared Layer-3 system prompt and hashing utilities.

The ONLY intentional difference between baseline and OverHaust is whether
OverHaust context is appended after the shared system + user prompts.
No benchmark-specific answer hints belong in the system prompt.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

# Frozen shared system prompt — change carefully; hash is part of the contract.
LAYER3_SYSTEM_PROMPT = """You are a coding agent answering questions about a local software repository.

Rules:
- Use only the repository tools provided to inspect the codebase.
- Do not invent files, symbols, or behaviour that you have not observed.
- If evidence is insufficient, say so explicitly.
- Prefer precise file paths and symbol names in your final answer.
- When you have enough evidence, stop exploring and give a concise final answer.
"""


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def system_prompt_hash(prompt: Optional[str] = None) -> str:
    return sha256_text(prompt if prompt is not None else LAYER3_SYSTEM_PROMPT)


def user_prompt_hash(prompt: str) -> str:
    return sha256_text(prompt)


def stable_json_hash(obj: Any) -> str:
    return sha256_text(json.dumps(obj, sort_keys=True, separators=(",", ":")))


def detect_extra_user_instructions(trace_prompt: str, task_prompt: str) -> bool:
    """
    True when the trace prompt is not exactly the task prompt.

    We require exact equality (after stripping trailing newlines only on both
    sides) so OverHaust cannot receive extra user-visible hints.
    """
    return (trace_prompt or "").rstrip("\n") != (task_prompt or "").rstrip("\n")
