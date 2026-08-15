"""Service boundaries for OverHaust — the "AI Memory Layer".

The product surface is intentionally simple, but the system is structured as a set
of independent services so it can scale into serious infrastructure later:

    User / Agent
          -> Connection Layer      (agent-agnostic links: MCP / API / extensions)
          -> Knowledge Service     (ingestion of chats, files, docs, notes)
          -> Memory Service        (durable + temporary AI memory extraction)
          -> Relevance Service     (find only what's needed for a request)
          -> Context Preparation   (assemble the smallest useful context)
          -> Usage Analyzer        (estimate how much unnecessary info was avoided)

Knowledge/Memory/Relevance/Context-preparation already live in `context_engine.py`
(the LLM core). This module adds the two NEW boundaries the revision introduces:

    * UsageService     — turns raw cache/task metrics into simple, human-friendly
                         savings estimates (Simple view) and a "Do I need a bigger
                         plan?" advisor. Everything is clearly an ESTIMATE.
    * ConnectionService — persists agent connections (prototype links). It never
                         claims to be a live data pipe to a third-party provider.

Keeping these as thin, pure functions makes it easy to move them behind their own
processes/queues later without touching the API layer.
"""
from __future__ import annotations

from typing import Any, Dict, List


# --------------------------------------------------------------------------- #
# UsageService — estimated savings + plan advisor (no third-party billing calls)
# --------------------------------------------------------------------------- #

# A simulated monthly AI allowance used only to visualise savings in the prototype.
_SIMULATED_MONTHLY_ALLOWANCE_TOKENS = 1_000_000
_DEFAULT_REDUCTION_PCT = 65  # fallback headline when no builds exist yet


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compute_plan_advice(
    *,
    total_raw_tokens: int,
    total_cache_tokens: int,
    avg_reduction_pct: float,
    projects: int,
    tasks: int,
) -> Dict[str, Any]:
    """Return a simple, non-technical estimate of AI usage savings.

    All numbers are ESTIMATES derived from the user's own project data. This never
    reflects real third-party provider billing.
    """
    # Headline reduction: prefer the measured average reduction across memory builds.
    reduction = int(round(avg_reduction_pct)) if avg_reduction_pct and avg_reduction_pct > 0 else 0
    if reduction <= 0:
        reduction = _DEFAULT_REDUCTION_PCT
    reduction = int(_clamp(reduction, 10, 92))

    # Estimated share of usage that was repeated / unneeded (tracks the reduction).
    unnecessary = int(_clamp(reduction, 10, 75))

    # Estimated portion of the monthly allowance the user is currently consuming.
    # Grows with how much they actually work (projects + tasks), capped high so the
    # "you may not need to upgrade" story is meaningful.
    current_usage = int(_clamp(58 + projects * 6 + tasks * 3, 40, 96))

    # After optimization, the same work needs less of the allowance.
    optimized_usage = int(round(current_usage * (1 - unnecessary / 100.0)))
    optimized_usage = int(_clamp(optimized_usage, 5, current_usage))

    can_stay = optimized_usage < 85
    if current_usage >= 80 and can_stay:
        recommendation = "You may be able to stay on your current plan."
    elif can_stay:
        recommendation = "You have comfortable headroom on your current plan."
    else:
        recommendation = "You may genuinely need more capacity — but optimizing first still helps."

    # Advanced (token) view — estimated.
    original_tokens = int(total_raw_tokens or 0)
    if original_tokens <= 0:
        original_tokens = int(_SIMULATED_MONTHLY_ALLOWANCE_TOKENS * current_usage / 100.0)
    optimized_tokens = int(total_cache_tokens or round(original_tokens * (1 - reduction / 100.0)))
    optimized_tokens = int(_clamp(optimized_tokens, 0, original_tokens))
    saved = max(0, original_tokens - optimized_tokens)

    return {
        "plan_name": "Current plan",
        "current_usage_pct": current_usage,
        "unnecessary_pct": unnecessary,
        "optimized_usage_pct": optimized_usage,
        "estimated_reduction_pct": reduction,
        "recommendation": recommendation,
        "can_stay_on_plan": can_stay,
        "original_tokens": original_tokens,
        "optimized_tokens": optimized_tokens,
        "information_saved_tokens": saved,
    }


# --------------------------------------------------------------------------- #
# ConnectionService — catalog of supported agents (open connection layer)
# --------------------------------------------------------------------------- #

# Honest statuses: we do NOT claim planned integrations are live.
#   available          -> can be linked in the prototype now
#   agent_connection   -> works today through a generic agent connection
#   coming_soon        -> planned, not yet available
AGENT_CATALOG: List[Dict[str, str]] = [
    {"key": "cursor", "name": "Cursor", "category": "Coding agent", "status": "available"},
    {"key": "claude", "name": "Claude", "category": "Assistant", "status": "available"},
    {"key": "chatgpt", "name": "ChatGPT", "category": "Assistant", "status": "available"},
    {"key": "claude_code", "name": "Claude Code", "category": "Coding agent", "status": "agent_connection"},
    {"key": "replit", "name": "Replit", "category": "Cloud IDE agent", "status": "agent_connection"},
    {"key": "gemini", "name": "Gemini", "category": "Assistant", "status": "coming_soon"},
    {"key": "windsurf", "name": "Windsurf", "category": "Editor agent", "status": "coming_soon"},
    {"key": "openhands", "name": "OpenHands", "category": "Autonomous agent", "status": "coming_soon"},
    {"key": "openclaw", "name": "OpenClaw", "category": "Autonomous agent", "status": "coming_soon"},
    {"key": "hermes", "name": "Hermes", "category": "Agent framework", "status": "coming_soon"},
    {"key": "other", "name": "Other AI agent", "category": "Agent Connection", "status": "agent_connection"},
]

_CONNECTABLE = {a["key"]: a for a in AGENT_CATALOG if a["status"] in ("available", "agent_connection")}


def is_connectable(agent_key: str) -> bool:
    return agent_key in _CONNECTABLE
