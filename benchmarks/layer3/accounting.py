"""
Provider-normalized token accounting for Layer 3.

Never assumes total = input + output when cached semantics exist.
Never converts unavailable cached usage into zero.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from benchmarks.schemas import TokenKind


@dataclass
class NormalizedUsage:
    """
    Normalized view + raw provider fields.

    Presence semantics:
      None  → UNAVAILABLE / not reported (not zero)
    """

    # Raw provider fields (preserved)
    raw_input_tokens: Optional[int] = None
    raw_output_tokens: Optional[int] = None
    raw_cached_input_tokens: Optional[int] = None
    raw_total_tokens: Optional[int] = None
    raw_provider_usage: Dict[str, Any] = field(default_factory=dict)

    # Normalized
    uncached_input_tokens: Optional[int] = None
    cached_input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_billable_tokens: Optional[int] = None

    uncached_input_tokens_kind: str = TokenKind.UNAVAILABLE.value
    cached_input_tokens_kind: str = TokenKind.UNAVAILABLE.value
    output_tokens_kind: str = TokenKind.UNAVAILABLE.value
    total_billable_tokens_kind: str = TokenKind.UNAVAILABLE.value

    accounting_notes: str = ""
    provider_semantics: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def has_exact_billable_total(self) -> bool:
        return (
            self.total_billable_tokens is not None
            and self.total_billable_tokens_kind == TokenKind.EXACT.value
        )


# Documented provider semantics (referenced by reports).
OPENAI_CHAT_SEMANTICS = (
    "OpenAI Chat Completions usage typically reports prompt_tokens (input, "
    "often including cached), completion_tokens (output), and optionally "
    "prompt_tokens_details.cached_tokens. total_tokens is usually "
    "prompt_tokens + completion_tokens. Cached tokens are a subset of "
    "prompt_tokens — do NOT add cached on top of prompt_tokens. "
    "Billable cost may treat cached tokens at a reduced rate; this harness "
    "reports counts separately and does not invent dollar conversions."
)


def normalize_openai_usage(usage: Optional[Dict[str, Any]]) -> NormalizedUsage:
    """
    Normalize OpenAI-style usage dict.

    Does not invent zeros for missing cached fields.
    """
    out = NormalizedUsage(
        provider_semantics=OPENAI_CHAT_SEMANTICS,
        raw_provider_usage=dict(usage or {}),
    )
    if not usage:
        out.accounting_notes = "No provider usage object; all fields UNAVAILABLE."
        return out

    prompt = usage.get("prompt_tokens")
    if prompt is None:
        prompt = usage.get("input_tokens")
    completion = usage.get("completion_tokens")
    if completion is None:
        completion = usage.get("output_tokens")
    total = usage.get("total_tokens")

    cached = None
    details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details")
    if isinstance(details, dict) and "cached_tokens" in details:
        cached = details.get("cached_tokens")
    elif "cached_tokens" in usage:
        cached = usage.get("cached_tokens")

    out.raw_input_tokens = int(prompt) if prompt is not None else None
    out.raw_output_tokens = int(completion) if completion is not None else None
    out.raw_cached_input_tokens = int(cached) if cached is not None else None
    out.raw_total_tokens = int(total) if total is not None else None

    if out.raw_output_tokens is not None:
        out.output_tokens = out.raw_output_tokens
        out.output_tokens_kind = TokenKind.EXACT.value

    if out.raw_cached_input_tokens is not None:
        out.cached_input_tokens = out.raw_cached_input_tokens
        out.cached_input_tokens_kind = TokenKind.EXACT.value
    else:
        out.cached_input_tokens = None
        out.cached_input_tokens_kind = TokenKind.UNAVAILABLE.value
        out.accounting_notes += (
            "cached_input_tokens UNAVAILABLE (provider did not report). "
            "Not treated as zero. "
        )

    if out.raw_input_tokens is not None:
        if out.cached_input_tokens is not None:
            out.uncached_input_tokens = max(0, out.raw_input_tokens - out.cached_input_tokens)
            out.uncached_input_tokens_kind = TokenKind.EXACT.value
        else:
            # Input known but cache unknown — report full input as uncached? NO.
            # Leave uncached UNKNOWN so we don't pretend cache was zero.
            out.uncached_input_tokens = None
            out.uncached_input_tokens_kind = TokenKind.UNAVAILABLE.value
            out.accounting_notes += (
                "uncached_input_tokens UNAVAILABLE because cached portion unknown. "
            )

    if out.raw_total_tokens is not None:
        out.total_billable_tokens = out.raw_total_tokens
        out.total_billable_tokens_kind = TokenKind.EXACT.value
        out.accounting_notes += (
            "total_billable_tokens taken from provider total_tokens "
            "(not recomputed as input+output). "
        )
    elif out.raw_input_tokens is not None and out.raw_output_tokens is not None:
        # Only synthesize when provider omitted total but gave input+output.
        # Do NOT add cached separately (already inside input if present).
        out.total_billable_tokens = out.raw_input_tokens + out.raw_output_tokens
        out.total_billable_tokens_kind = TokenKind.EXACT.value
        out.accounting_notes += (
            "total_billable_tokens derived as prompt_tokens+completion_tokens "
            "because provider omitted total_tokens; cached not double-counted. "
        )
    else:
        out.total_billable_tokens = None
        out.total_billable_tokens_kind = TokenKind.UNAVAILABLE.value
        out.accounting_notes += "total_billable_tokens UNAVAILABLE. "

    return out
