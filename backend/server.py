"""Context Runtime API — FastAPI server."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.cors import CORSMiddleware

from context_engine import (
    analyze_project_context,
    compute_source_tokens,
    count_knowledge_items,
    count_source_files,
    count_source_messages,
    estimate_tokens,
    hash_content,
    select_relevant_context,
)
from labkot_demo import LABKOT_PROJECT, labkot_sources
from services import AGENT_CATALOG, compute_plan_advice, is_connectable
from models import (
    AnalyticsSummary,
    CacheDocument,
    CacheMetrics,
    Connection,
    ConnectionCreate,
    ContextCache,
    ContextSource,
    ContextSourceCreate,
    CONTEXT_TYPES,
    LoginRequest,
    LoginResponse,
    PlanAdvice,
    Project,
    ProjectCreate,
    TaskCreate,
    TaskMetrics,
    TaskRun,
    TaskSelection,
    User,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("context-runtime")

# ---------- Mongo ----------

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# ---------- Auth ----------

JWT_SECRET = os.environ.get("JWT_SECRET", "overhaust-demo-secret-change-me")
JWT_ALG = "HS256"
JWT_TTL_HOURS = 24 * 30  # 30 days

bearer = HTTPBearer(auto_error=False)


def _make_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_TTL_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> User:
    if not creds or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")

    user_id = payload.get("sub")
    email = payload.get("email")
    if not user_id or not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    # Ensure user still exists (lazy create if not)
    doc = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not doc:
        doc = User(id=user_id, email=email).model_dump()
        doc["created_at"] = doc["created_at"].isoformat()
        await db.users.insert_one(doc)
    return User(**doc)


# ---------- Helpers ----------

def _dt_to_iso(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, list):
        return [_dt_to_iso(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _dt_to_iso(v) for k, v in obj.items()}
    return obj


def _to_mongo(doc: Dict[str, Any]) -> Dict[str, Any]:
    return _dt_to_iso(doc)


def _from_mongo(doc: Dict[str, Any]) -> Dict[str, Any]:
    for k in ("created_at", "updated_at"):
        if isinstance(doc.get(k), str):
            try:
                doc[k] = datetime.fromisoformat(doc[k])
            except Exception:  # noqa: BLE001
                pass
    return doc


# ---------- App ----------

app = FastAPI(title="OverHaust Context Runtime")
api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"service": "context-runtime", "status": "ok"}


@api.get("/health")
async def health():
    return {"status": "ok"}


# ----- Auth -----

@api.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    email = req.email.lower()
    doc = await db.users.find_one({"email": email}, {"_id": 0})
    if not doc:
        user = User(email=email)
        doc = user.model_dump()
        await db.users.insert_one(_to_mongo(doc))
    else:
        doc = _from_mongo(doc)
        user = User(**doc)
    token = _make_token(user.id, user.email)
    return LoginResponse(token=token, user=user)


@api.get("/auth/me", response_model=User)
async def me(user: User = Depends(get_current_user)):
    return user


# ----- Projects -----

@api.get("/projects", response_model=List[Project])
async def list_projects(user: User = Depends(get_current_user)):
    cursor = db.projects.find({"user_id": user.id}, {"_id": 0}).sort("updated_at", -1)
    out: List[Project] = []
    async for doc in cursor:
        out.append(Project(**_from_mongo(doc)))
    return out


@api.post("/projects", response_model=Project)
async def create_project(req: ProjectCreate, user: User = Depends(get_current_user)):
    proj = Project(user_id=user.id, **req.model_dump())
    await db.projects.insert_one(_to_mongo(proj.model_dump()))
    return proj


@api.get("/projects/{project_id}", response_model=Project)
async def get_project(project_id: str, user: User = Depends(get_current_user)):
    doc = await db.projects.find_one({"id": project_id, "user_id": user.id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Project not found")
    return Project(**_from_mongo(doc))


@api.delete("/projects/{project_id}")
async def delete_project(project_id: str, user: User = Depends(get_current_user)):
    res = await db.projects.delete_one({"id": project_id, "user_id": user.id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Project not found")
    await db.context_sources.delete_many({"project_id": project_id, "user_id": user.id})
    await db.caches.delete_many({"project_id": project_id, "user_id": user.id})
    await db.tasks.delete_many({"project_id": project_id, "user_id": user.id})
    return {"deleted": True}


# ----- Context sources -----

@api.get("/projects/{project_id}/contexts", response_model=List[ContextSource])
async def list_contexts(project_id: str, user: User = Depends(get_current_user)):
    await _assert_project(project_id, user)
    cursor = db.context_sources.find(
        {"project_id": project_id, "user_id": user.id}, {"_id": 0}
    ).sort("created_at", -1)
    out: List[ContextSource] = []
    async for doc in cursor:
        out.append(ContextSource(**_from_mongo(doc)))
    return out


@api.post("/projects/{project_id}/contexts", response_model=ContextSource)
async def add_context(
    project_id: str, req: ContextSourceCreate, user: User = Depends(get_current_user)
):
    if req.type not in CONTEXT_TYPES:
        raise HTTPException(400, f"Invalid type. Allowed: {sorted(CONTEXT_TYPES)}")
    await _assert_project(project_id, user)
    src = ContextSource(
        project_id=project_id,
        user_id=user.id,
        type=req.type,
        name=req.name or "Untitled",
        content=req.content,
        tokens=estimate_tokens(req.content),
    )
    await db.context_sources.insert_one(_to_mongo(src.model_dump()))
    await db.projects.update_one(
        {"id": project_id, "user_id": user.id},
        {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return src


@api.delete("/projects/{project_id}/contexts/{source_id}")
async def delete_context(
    project_id: str, source_id: str, user: User = Depends(get_current_user)
):
    await _assert_project(project_id, user)
    res = await db.context_sources.delete_one(
        {"id": source_id, "project_id": project_id, "user_id": user.id}
    )
    if res.deleted_count == 0:
        raise HTTPException(404, "Source not found")
    return {"deleted": True}


# ----- Cache builds -----

@api.post("/projects/{project_id}/cache/build", response_model=CacheDocument)
async def build_cache(project_id: str, user: User = Depends(get_current_user)):
    proj = await _get_project(project_id, user)
    sources_raw = await _load_sources(project_id, user.id)
    if not sources_raw:
        raise HTTPException(400, "Add at least one context source before building the cache.")

    logger.info("Building cache for project %s (%d sources)", project_id, len(sources_raw))
    try:
        cache_json = await analyze_project_context(
            project=proj.model_dump(),
            sources=sources_raw,
            session_id=f"cache-build-{project_id}-{uuid.uuid4().hex[:8]}",
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Cache build failed")
        raise HTTPException(502, f"LLM analysis failed: {e}") from e

    # Coerce to schema (accepts any keys the LLM produced beyond required)
    try:
        cache = ContextCache(**cache_json)
    except Exception as e:  # noqa: BLE001
        # Attempt minimal fixup so we still return something useful
        logger.warning("Cache schema mismatch: %s. Coercing.", e)
        cache = ContextCache()
        cache_json = cache.model_dump()

    tokens = compute_source_tokens(sources_raw)
    cache_str = json.dumps(cache.model_dump(), separators=(",", ":"))
    cache_tokens = estimate_tokens(cache_str)
    reduction = 0.0 if tokens["total"] == 0 else max(0.0, 1.0 - cache_tokens / tokens["total"]) * 100.0
    metrics = CacheMetrics(
        raw_tokens=tokens,
        cache_tokens=cache_tokens,
        reduction_pct=round(reduction, 2),
        knowledge_items=count_knowledge_items(cache.model_dump()),
    )

    # Previous version
    prev = await db.caches.find_one(
        {"project_id": project_id, "user_id": user.id}, {"_id": 0}, sort=[("version", -1)]
    )
    version = ((prev or {}).get("version") or 0) + 1

    source_hashes = [hash_content(s.get("content") or "") for s in sources_raw]

    doc = CacheDocument(
        project_id=project_id,
        user_id=user.id,
        version=version,
        cache=cache,
        metrics=metrics,
        source_hashes=source_hashes,
    )
    await db.caches.insert_one(_to_mongo(doc.model_dump()))
    await db.projects.update_one(
        {"id": project_id, "user_id": user.id},
        {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return doc


@api.get("/projects/{project_id}/cache", response_model=Optional[CacheDocument])
async def get_latest_cache(project_id: str, user: User = Depends(get_current_user)):
    await _assert_project(project_id, user)
    doc = await db.caches.find_one(
        {"project_id": project_id, "user_id": user.id}, {"_id": 0}, sort=[("version", -1)]
    )
    if not doc:
        return None
    return CacheDocument(**_from_mongo(doc))


@api.get("/projects/{project_id}/cache/history", response_model=List[CacheDocument])
async def get_cache_history(project_id: str, user: User = Depends(get_current_user)):
    await _assert_project(project_id, user)
    cursor = db.caches.find(
        {"project_id": project_id, "user_id": user.id}, {"_id": 0}
    ).sort("version", -1)
    out: List[CacheDocument] = []
    async for doc in cursor:
        out.append(CacheDocument(**_from_mongo(doc)))
    return out


@api.get("/projects/{project_id}/cache/incremental")
async def incremental_status(project_id: str, user: User = Depends(get_current_user)):
    """Return which sources have changed vs the last build (hash-based)."""
    await _assert_project(project_id, user)
    latest = await db.caches.find_one(
        {"project_id": project_id, "user_id": user.id}, {"_id": 0}, sort=[("version", -1)]
    )
    if not latest:
        return {"has_cache": False, "changed_sources": [], "total_sources": 0}
    sources = await _load_sources(project_id, user.id)
    prev_hashes = set(latest.get("source_hashes") or [])
    cur_hashes = [hash_content(s.get("content") or "") for s in sources]
    changed = [
        {"name": s.get("name"), "type": s.get("type")}
        for s, h in zip(sources, cur_hashes)
        if h not in prev_hashes
    ]
    return {
        "has_cache": True,
        "cache_version": latest.get("version", 1),
        "changed_sources": changed,
        "total_sources": len(sources),
        "needs_rebuild": len(changed) > 0,
    }


# ----- Task context generation -----

@api.post("/projects/{project_id}/tasks", response_model=TaskRun)
async def create_task(
    project_id: str, req: TaskCreate, user: User = Depends(get_current_user)
):
    await _assert_project(project_id, user)
    cache_doc = await db.caches.find_one(
        {"project_id": project_id, "user_id": user.id}, {"_id": 0}, sort=[("version", -1)]
    )
    if not cache_doc:
        raise HTTPException(400, "Build the context cache first.")
    cache_json = cache_doc.get("cache") or {}
    try:
        sel_json = await select_relevant_context(
            cache_json, req.description, session_id=f"task-{project_id}-{uuid.uuid4().hex[:8]}"
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Task selection failed")
        raise HTTPException(502, f"LLM selection failed: {e}") from e

    selection = TaskSelection(
        relevant=sel_json.get("relevant") or {},
        ignored=sel_json.get("ignored") or {},
        assembled_context=sel_json.get("assembled_context") or "",
    )

    # Metrics vs raw context
    sources = await _load_sources(project_id, user.id)
    raw_tokens = compute_source_tokens(sources)["total"]
    optimized_tokens = estimate_tokens(selection.assembled_context)
    orig_items = count_knowledge_items(cache_json) + len(sources)
    opt_items = (
        len(selection.relevant.get("components") or [])
        + len(selection.relevant.get("decisions") or [])
        + len(selection.relevant.get("architecture_keys") or [])
        + len(selection.relevant.get("conversation_memory") or [])
    )
    orig_messages = count_source_messages(sources)
    orig_files = count_source_files(sources)
    metrics = TaskMetrics(
        original_tokens=raw_tokens,
        optimized_tokens=optimized_tokens,
        reduction_pct=(
            0.0 if raw_tokens == 0 else round(max(0.0, 1 - optimized_tokens / raw_tokens) * 100, 2)
        ),
        original_items=orig_items,
        optimized_items=opt_items,
        original_messages=orig_messages,
        optimized_messages=len(selection.relevant.get("conversation_memory") or []),
        original_files=orig_files,
        optimized_files=len(selection.relevant.get("components") or []),
    )

    run = TaskRun(
        project_id=project_id,
        user_id=user.id,
        description=req.description,
        selection=selection,
        metrics=metrics,
    )
    await db.tasks.insert_one(_to_mongo(run.model_dump()))
    return run


@api.get("/projects/{project_id}/tasks", response_model=List[TaskRun])
async def list_tasks(project_id: str, user: User = Depends(get_current_user)):
    await _assert_project(project_id, user)
    cursor = db.tasks.find(
        {"project_id": project_id, "user_id": user.id}, {"_id": 0}
    ).sort("created_at", -1)
    out: List[TaskRun] = []
    async for doc in cursor:
        out.append(TaskRun(**_from_mongo(doc)))
    return out


# ----- Demo seed -----

@api.post("/projects/seed/labkot", response_model=Project)
async def seed_labkot(user: User = Depends(get_current_user)):
    # Reuse existing LabKOT project for this user if present
    existing = await db.projects.find_one(
        {"user_id": user.id, "name": LABKOT_PROJECT["name"]}, {"_id": 0}
    )
    if existing:
        return Project(**_from_mongo(existing))

    proj = Project(user_id=user.id, **LABKOT_PROJECT)
    await db.projects.insert_one(_to_mongo(proj.model_dump()))

    for src in labkot_sources():
        s = ContextSource(
            project_id=proj.id,
            user_id=user.id,
            type=src["type"],
            name=src["name"],
            content=src["content"],
            tokens=estimate_tokens(src["content"]),
        )
        await db.context_sources.insert_one(_to_mongo(s.model_dump()))
    return proj


# ----- Analytics -----

@api.get("/analytics", response_model=AnalyticsSummary)
async def analytics(user: User = Depends(get_current_user)):
    projects_count = await db.projects.count_documents({"user_id": user.id})
    tasks_count = await db.tasks.count_documents({"user_id": user.id})
    cache_builds = await db.caches.count_documents({"user_id": user.id})

    # Aggregate latest caches per project
    total_raw = 0
    total_cache = 0
    knowledge = 0
    reductions: List[float] = []

    project_ids: List[str] = []
    async for p in db.projects.find({"user_id": user.id}, {"_id": 0, "id": 1}):
        project_ids.append(p["id"])

    for pid in project_ids:
        latest = await db.caches.find_one(
            {"project_id": pid, "user_id": user.id}, {"_id": 0}, sort=[("version", -1)]
        )
        if not latest:
            continue
        m = latest.get("metrics") or {}
        total_raw += (m.get("raw_tokens") or {}).get("total", 0) or 0
        total_cache += m.get("cache_tokens", 0) or 0
        knowledge += m.get("knowledge_items", 0) or 0
        r = m.get("reduction_pct") or 0.0
        if r > 0:
            reductions.append(float(r))

    avg_reduction = round(sum(reductions) / len(reductions), 2) if reductions else 0.0
    saved = max(0, total_raw - total_cache)
    connected = await db.connections.count_documents({"user_id": user.id})
    return AnalyticsSummary(
        projects=projects_count,
        total_raw_tokens=total_raw,
        total_cache_tokens=total_cache,
        avg_reduction_pct=avg_reduction,
        total_tasks=tasks_count,
        total_cache_builds=cache_builds,
        estimated_context_saved=saved,
        knowledge_items=knowledge,
        connected_agents=connected,
    )


@api.get("/analytics/history")
async def analytics_history(user: User = Depends(get_current_user)):
    """Time series of cache builds — for the reduction-over-time chart."""
    cursor = db.caches.find({"user_id": user.id}, {"_id": 0}).sort("created_at", 1)
    out: List[Dict[str, Any]] = []
    async for doc in cursor:
        m = doc.get("metrics") or {}
        out.append({
            "created_at": doc.get("created_at"),
            "raw_tokens": (m.get("raw_tokens") or {}).get("total", 0) or 0,
            "cache_tokens": m.get("cache_tokens", 0) or 0,
            "reduction_pct": m.get("reduction_pct", 0.0) or 0.0,
            "project_id": doc.get("project_id"),
            "version": doc.get("version", 1),
        })
    return out


# ----- Connections (agent-agnostic open layer) -----

@api.get("/connections/catalog")
async def connections_catalog():
    """Static catalog of supported agents with honest statuses."""
    return AGENT_CATALOG


@api.get("/connections", response_model=List[Connection])
async def list_connections(user: User = Depends(get_current_user)):
    cursor = db.connections.find({"user_id": user.id}, {"_id": 0}).sort("created_at", -1)
    out: List[Connection] = []
    async for doc in cursor:
        out.append(Connection(**_from_mongo(doc)))
    return out


@api.post("/connections", response_model=Connection)
async def create_connection(req: ConnectionCreate, user: User = Depends(get_current_user)):
    if not is_connectable(req.agent_key):
        raise HTTPException(400, "This agent isn't available to connect yet.")
    existing = await db.connections.find_one(
        {"user_id": user.id, "agent_key": req.agent_key}, {"_id": 0}
    )
    if existing:
        return Connection(**_from_mongo(existing))
    conn = Connection(user_id=user.id, agent_key=req.agent_key, agent_name=req.agent_name)
    await db.connections.insert_one(_to_mongo(conn.model_dump()))
    return conn


@api.delete("/connections/{connection_id}")
async def delete_connection(connection_id: str, user: User = Depends(get_current_user)):
    res = await db.connections.delete_one({"id": connection_id, "user_id": user.id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Connection not found")
    return {"deleted": True}


# ----- Usage / Plan advisor (all ESTIMATES) -----

@api.get("/usage/plan-advisor", response_model=PlanAdvice)
async def usage_plan_advisor(user: User = Depends(get_current_user)):
    """Simple, non-technical estimate of AI usage savings + upgrade advice.

    Reuses the analytics aggregation and the UsageService boundary. Nothing here
    reflects real third-party provider billing — everything is an estimate.
    """
    tasks_count = await db.tasks.count_documents({"user_id": user.id})
    projects_count = await db.projects.count_documents({"user_id": user.id})

    total_raw = 0
    total_cache = 0
    reductions: List[float] = []
    project_ids: List[str] = []
    async for p in db.projects.find({"user_id": user.id}, {"_id": 0, "id": 1}):
        project_ids.append(p["id"])
    for pid in project_ids:
        latest = await db.caches.find_one(
            {"project_id": pid, "user_id": user.id}, {"_id": 0}, sort=[("version", -1)]
        )
        if not latest:
            continue
        m = latest.get("metrics") or {}
        total_raw += (m.get("raw_tokens") or {}).get("total", 0) or 0
        total_cache += m.get("cache_tokens", 0) or 0
        r = m.get("reduction_pct") or 0.0
        if r > 0:
            reductions.append(float(r))
    avg_reduction = round(sum(reductions) / len(reductions), 2) if reductions else 0.0

    advice = compute_plan_advice(
        total_raw_tokens=total_raw,
        total_cache_tokens=total_cache,
        avg_reduction_pct=avg_reduction,
        projects=projects_count,
        tasks=tasks_count,
    )
    return PlanAdvice(**advice)


# ----- Helpers -----

async def _assert_project(project_id: str, user: User) -> None:
    doc = await db.projects.find_one({"id": project_id, "user_id": user.id}, {"_id": 0, "id": 1})
    if not doc:
        raise HTTPException(404, "Project not found")


async def _get_project(project_id: str, user: User) -> Project:
    doc = await db.projects.find_one({"id": project_id, "user_id": user.id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Project not found")
    return Project(**_from_mongo(doc))


async def _load_sources(project_id: str, user_id: str) -> List[Dict[str, Any]]:
    cursor = db.context_sources.find(
        {"project_id": project_id, "user_id": user_id}, {"_id": 0}
    ).sort("created_at", 1)
    out: List[Dict[str, Any]] = []
    async for doc in cursor:
        out.append(_from_mongo(doc))
    return out


# ---------- Wire ----------

app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
