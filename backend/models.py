"""Pydantic models for the Context Runtime API."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Auth ----------

class LoginRequest(BaseModel):
    email: EmailStr


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_uid)
    email: EmailStr
    created_at: datetime = Field(default_factory=_now)


class LoginResponse(BaseModel):
    token: str
    user: User


# ---------- Projects ----------

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    stack: List[str] = Field(default_factory=list)


class Project(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_uid)
    user_id: str
    name: str
    description: str = ""
    stack: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


# ---------- Context sources ----------

CONTEXT_TYPES = {"conversation", "documentation", "file", "note"}


class ContextSourceCreate(BaseModel):
    type: str  # conversation | documentation | file | note
    name: str = Field(default="Untitled", max_length=200)
    content: str


class ContextSource(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_uid)
    project_id: str
    user_id: str
    type: str
    name: str
    content: str
    tokens: int = 0
    created_at: datetime = Field(default_factory=_now)


# ---------- Context Cache ----------

class ProjectIdentity(BaseModel):
    type: str = ""
    stack: List[str] = Field(default_factory=list)
    purpose: str = ""
    architecture_summary: str = ""


class ArchitectureBreakdown(BaseModel):
    frontend: str = ""
    backend: str = ""
    database: str = ""
    authentication: str = ""
    networking: str = ""
    infrastructure: str = ""


class ComponentEntry(BaseModel):
    name: str
    kind: str = ""
    purpose: str = ""


class DecisionEntry(BaseModel):
    title: str
    rationale: str = ""


class CurrentState(BaseModel):
    implemented: List[str] = Field(default_factory=list)
    in_progress: List[str] = Field(default_factory=list)
    known_issues: List[str] = Field(default_factory=list)


class ConversationMemory(BaseModel):
    permanent_knowledge: List[str] = Field(default_factory=list)
    temporary_task_context: List[str] = Field(default_factory=list)
    resolved_issues: List[str] = Field(default_factory=list)
    rejected_approaches: List[str] = Field(default_factory=list)
    open_issues: List[str] = Field(default_factory=list)


class ContextCache(BaseModel):
    project_identity: ProjectIdentity = Field(default_factory=ProjectIdentity)
    architecture: ArchitectureBreakdown = Field(default_factory=ArchitectureBreakdown)
    components: List[ComponentEntry] = Field(default_factory=list)
    decisions: List[DecisionEntry] = Field(default_factory=list)
    current_state: CurrentState = Field(default_factory=CurrentState)
    conversation_memory: ConversationMemory = Field(default_factory=ConversationMemory)


class CacheMetrics(BaseModel):
    raw_tokens: Dict[str, int] = Field(default_factory=dict)
    cache_tokens: int = 0
    reduction_pct: float = 0.0
    knowledge_items: int = 0


class CacheDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_uid)
    project_id: str
    user_id: str
    version: int = 1
    cache: ContextCache
    metrics: CacheMetrics
    source_hashes: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)


# ---------- Task Context ----------

class TaskCreate(BaseModel):
    description: str = Field(min_length=3, max_length=3000)


class TaskSelection(BaseModel):
    relevant: Dict[str, List[str]] = Field(default_factory=dict)
    ignored: Dict[str, List[str]] = Field(default_factory=dict)
    assembled_context: str = ""


class TaskMetrics(BaseModel):
    original_tokens: int = 0
    optimized_tokens: int = 0
    reduction_pct: float = 0.0
    original_items: int = 0
    optimized_items: int = 0
    original_messages: int = 0
    optimized_messages: int = 0
    original_files: int = 0
    optimized_files: int = 0


class TaskRun(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_uid)
    project_id: str
    user_id: str
    description: str
    selection: TaskSelection
    metrics: TaskMetrics
    created_at: datetime = Field(default_factory=_now)


# ---------- Analytics ----------

class AnalyticsSummary(BaseModel):
    projects: int = 0
    total_raw_tokens: int = 0
    total_cache_tokens: int = 0
    avg_reduction_pct: float = 0.0
    total_tasks: int = 0
    total_cache_builds: int = 0
    estimated_context_saved: int = 0
    knowledge_items: int = 0
    connected_agents: int = 0


# ---------- Connections (agent-agnostic) ----------
# The product is designed around an open connection layer so any AI agent can be
# supported over time (MCP, APIs, extensions, local/desktop/browser agents).

CONNECTION_STATUSES = {"available", "coming_soon", "agent_connection"}


class ConnectionCreate(BaseModel):
    agent_key: str = Field(min_length=1, max_length=60)
    agent_name: str = Field(min_length=1, max_length=80)


class Connection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_uid)
    user_id: str
    agent_key: str
    agent_name: str
    status: str = "connected"  # connected (prototype link) — not a live data pipe
    created_at: datetime = Field(default_factory=_now)


# ---------- Usage / Plan advisor (all values are ESTIMATES) ----------

class PlanAdvice(BaseModel):
    # Simple, non-technical framing of estimated AI usage savings.
    plan_name: str = "Current plan"
    current_usage_pct: int = 0            # estimated % of monthly AI allowance used
    unnecessary_pct: int = 0              # estimated % of usage that was repeated/unneeded
    optimized_usage_pct: int = 0          # estimated % after optimization
    estimated_reduction_pct: int = 0      # headline savings number
    recommendation: str = ""
    can_stay_on_plan: bool = True
    # Advanced (token) view — estimated via chars/4 heuristic
    original_tokens: int = 0
    optimized_tokens: int = 0
    information_saved_tokens: int = 0
    disclaimer: str = (
        "All figures are estimates based on your project data (chars/4 heuristic). "
        "OverHaust does not control or refund credits consumed by third-party AI providers."
    )
