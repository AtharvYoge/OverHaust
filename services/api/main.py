"""
Main FastAPI application for Overhaust backend.
Provides REST API endpoints for interacting with the Overhaust system.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uvicorn
import logging

from packages.agent.autonomous_agent import get_overhaust_agent, OverhaustAgent
from packages.memory.memory_store import get_memory_store, MemoryStore
from packages.context.context_engine import get_context_assembler, ContextAssembler
from packages.tokenization.token_estimator import TokenEstimator, estimate_tokens, estimate_reduction

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Overhaust API",
    description="API for Overhaust AI Memory and Efficiency System",
    version="0.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for request/response
class TaskRequest(BaseModel):
    project_id: str
    task: str
    max_knowledge_items: Optional[int] = 10

class MemoryUpdateRequest(BaseModel):
    project_id: str
    content: str
    memory_type: Optional[str] = "temporary"
    importance_score: Optional[float] = 0.5
    metadata: Optional[Dict[str, Any]] = None

class SearchRequest(BaseModel):
    project_id: str
    query: str
    limit: Optional[int] = 10

class TokenEstimationRequest(BaseModel):
    text: str
    model: Optional[str] = "gpt-4"

class TokenReductionRequest(BaseModel):
    original_text: str
    optimized_text: str
    model: Optional[str] = "gpt-4"

class AgentActionResponse(BaseModel):
    action_type: str
    description: str
    parameters: Dict[str, Any]
    result: Any
    timestamp: str
    success: bool

# Dependency injection
def get_agent() -> OverhaustAgent:
    return get_overhaust_agent()

def get_memory_store_dep() -> MemoryStore:
    return get_memory_store()

def get_context_assembler_dep() -> ContextAssembler:
    return get_context_assembler()

def get_token_estimator_dep() -> TokenEstimator:
    return TokenEstimator()

# API Endpoints
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Overhaust API - AI Memory and Efficiency System",
        "version": "0.1.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": "2026-08-17T13:00:00Z"}

@app.post("/api/v1/understand-task")
async def understand_task(
    request: TaskRequest,
    agent: OverhaustAgent = Depends(get_agent)
):
    """Analyze and understand a user task."""
    try:
        analysis = agent.understand_task(request.task)
        return {
            "task_analysis": analysis,
            "agent_id": agent.agent_id
        }
    except Exception as e:
        logger.error(f"Error understanding task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/get-context")
async def get_context(
    request: TaskRequest,
    agent: OverhaustAgent = Depends(get_agent)
):
    """Get relevant context for a project and task."""
    try:
        max_items = request.max_knowledge_items if request.max_knowledge_items is not None else 10
        context = agent.get_project_context(
            request.project_id,
            request.task,
            max_knowledge_items=max_items
        )
        
        # Convert ContextPackage to dict for JSON response
        return {
            "context_id": context.id,
            "project_id": context.project_id,
            "task": context.task,
            "relevant_knowledge": [
                {
                    "id": k.id,
                    "project_id": k.project_id,
                    "source_type": k.source_type,
                    "source_title": k.source_title,
                    "title": k.title,
                    "content": k.content,
                    "knowledge_type": k.knowledge_type,
                    "importance_score": k.importance_score,
                    "extracted_at": k.extracted_at,
                    "metadata": k.metadata,
                    "source_hash": k.source_hash
                }
                for k in context.relevant_knowledge
            ],
            "relevant_files": context.relevant_files,
            "relevant_decisions": [
                {
                    "id": d.id,
                    "project_id": d.project_id,
                    "source_type": d.source_type,
                    "source_title": d.source_title,
                    "title": d.title,
                    "content": d.content,
                    "knowledge_type": d.knowledge_type,
                    "importance_score": d.importance_score,
                    "extracted_at": d.extracted_at,
                    "metadata": d.metadata,
                    "source_hash": d.source_hash
                }
                for d in context.relevant_decisions
            ],
            "current_state": context.current_state,
            "relevant_memory": context.relevant_memory,
            "constraints": context.constraints,
            "created_at": context.created_at,
            "estimated_tokens": context.estimated_tokens
        }
    except ValueError as e:
        logger.error(f"Project not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting context: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/update-memory")
async def update_memory(
    request: MemoryUpdateRequest,
    agent: OverhaustAgent = Depends(get_agent)
):
    """Update project memory with new information."""
    try:
        memory_type = request.memory_type if request.memory_type is not None else "temporary"
        importance_score = request.importance_score if request.importance_score is not None else 0.5
        memory_id = agent.update_memory(
            request.project_id,
            request.content,
            memory_type,
            importance_score,
            request.metadata
        )
        return {
            "memory_id": memory_id,
            "message": "Memory updated successfully"
        }
    except Exception as e:
        logger.error(f"Error updating memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/search-knowledge")
async def search_knowledge(
    request: SearchRequest,
    agent: OverhaustAgent = Depends(get_agent)
):
    """Search for knowledge in a project."""
    try:
        limit = request.limit if request.limit is not None else 10
        results = agent.search_project_knowledge(
            request.project_id,
            request.query,
            limit
        )
        return {
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        logger.error(f"Error searching knowledge: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/mark-resolved")
async def mark_resolved(
    project_id: str,
    issue_description: str,
    agent: OverhaustAgent = Depends(get_agent)
):
    """Mark an issue as resolved."""
    try:
        memory_id = agent.mark_resolved(project_id, issue_description)
        return {
            "memory_id": memory_id,
            "message": "Issue marked as resolved"
        }
    except Exception as e:
        logger.error(f"Error marking resolved: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/mark-stale")
async def mark_stale(
    memory_id: str,
    reason: str = "",
    agent: OverhaustAgent = Depends(get_agent)
):
    """Mark a memory as stale."""
    try:
        success = agent.mark_stale(memory_id, reason)
        if success:
            return {"message": "Memory marked as stale"}
        else:
            raise HTTPException(status_code=404, detail="Memory not found")
    except Exception as e:
        logger.error(f"Error marking stale: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/estimate-tokens")
async def estimate_tokens_endpoint(
    request: TokenEstimationRequest,
    estimator: TokenEstimator = Depends(get_token_estimator_dep)
):
    """Estimate token count for text."""
    try:
        model = request.model if request.model is not None else "gpt-4"
        tokens = estimator.estimate_tokens(request.text, model)
        return {
            "text": request.text,
            "model": model,
            "estimated_tokens": tokens
        }
    except Exception as e:
        logger.error(f"Error estimating tokens: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/estimate-reduction")
async def estimate_reduction_endpoint(
    request: TokenReductionRequest,
    estimator: TokenEstimator = Depends(get_token_estimator_dep)
):
    """Estimate token reduction between original and optimized text."""
    try:
        model = request.model if request.model is not None else "gpt-4"
        reduction = estimator.estimate_reduction(
            request.original_text,
            request.optimized_text,
            model
        )
        return {
            "original_text": request.original_text,
            "optimized_text": request.optimized_text,
            "model": model,
            "reduction_analysis": reduction
        }
    except Exception as e:
        logger.error(f"Error estimating reduction: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/agent-history/{agent_id}")
async def get_agent_history(
    agent_id: str,
    limit: int = 10,
    agent: OverhaustAgent = Depends(get_agent)
):
    """Get agent action history."""
    try:
        # Note: This would need to be implemented to get history for specific agent ID
        # For now, we'll return the current agent's history
        history = agent.get_action_history(limit)
        return {
            "agent_id": agent.agent_id,
            "history": [
                {
                    "action_type": action.action_type,
                    "description": action.description,
                    "parameters": action.parameters,
                    "result": action.result,
                    "timestamp": action.timestamp,
                    "success": action.success
                }
                for action in history
            ]
        }
    except Exception as e:
        logger.error(f"Error getting agent history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/projects/{project_id}")
async def get_project(
    project_id: str,
    memory_store: MemoryStore = Depends(get_memory_store_dep)
):
    """Get project information."""
    try:
        project = memory_store.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return project
    except Exception as e:
        logger.error(f"Error getting project: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)