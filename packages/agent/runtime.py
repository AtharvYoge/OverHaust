"""
Agent runtime upgrade for Overhaust.

Wraps OverhaustAgent with a goal-directed loop:

  understand task -> inspect project -> search knowledge -> build context
  -> detect gaps -> retrieve more -> finalize -> (optionally) update memory

Produces a concise ACTION LOG (not chain-of-thought) suitable for users
and logs.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

from packages.agent.autonomous_agent import OverhaustAgent
from packages.context.relevance import LayeredRelevanceEngine

logger = logging.getLogger(__name__)


@dataclass
class ActionLogEntry:
    """One human-readable action in the agent's run log."""
    step: int
    action: str
    detail: str
    at: str = field(default_factory=lambda: datetime.now().isoformat())

    def render(self) -> str:
        return f"[{self.step}] {self.action}: {self.detail}"


@dataclass
class AgentRunResult:
    """Outcome of a full agent run."""
    task: str
    project_id: str
    context_id: Optional[str]
    estimated_tokens: int
    knowledge_items: int
    gaps: List[str]
    action_log: List[ActionLogEntry]
    memory_updates: List[str] = field(default_factory=list)

    def render_log(self) -> str:
        return "\n".join(e.render() for e in self.action_log)


# Signals that the built context may be missing something
_GAP_CHECKS = [
    ('open_issue', 'no open-issue knowledge found — if this is a bug task, ingest the conversation where it was reported'),
    ('decision', 'no prior decisions found — context may miss rationale'),
    ('permanent_knowledge', 'no architecture/permanent knowledge found — consider indexing the project'),
]


class AgentRuntime:
    """Goal-directed agent loop with action logging and gap detection."""

    def __init__(self, agent: OverhaustAgent):
        self.agent = agent
        self.relevance = LayeredRelevanceEngine(agent.memory_store)

    def run(self, project_id: str, task: str,
            max_knowledge_items: int = 10,
            learn_from_result: bool = True) -> AgentRunResult:
        log: List[ActionLogEntry] = []
        step = 0

        def note(action: str, detail: str):
            nonlocal step
            step += 1
            log.append(ActionLogEntry(step=step, action=action, detail=detail))
            logger.info(f"agent run: {action} - {detail}")

        # 1. Understand task
        analysis = self.agent.understand_task(task)
        note("Analyzing task",
             f"type={analysis['task_type']}, keywords={analysis['keywords'][:4]}")

        # 2. Inspect project summary
        project = self.agent.memory_store.get_project(project_id)
        if project is None:
            note("Project lookup", f"project {project_id} not found — aborting")
            return AgentRunResult(task=task, project_id=project_id, context_id=None,
                                  estimated_tokens=0, knowledge_items=0,
                                  gaps=['project not found'], action_log=log)
        note("Inspecting project", f"{project.get('name', project_id)}")

        # 3. Search knowledge (relevance engine)
        scored = self.relevance.search(project_id, task, limit=max_knowledge_items)
        note("Searching project knowledge", f"{len(scored)} candidates scored")

        # 4. Build context
        ctx = self.agent.get_project_context(project_id, task,
                                             max_knowledge_items=max_knowledge_items)
        note("Built optimized context",
             f"{len(ctx.relevant_knowledge)} knowledge items, ~{ctx.estimated_tokens} tokens (estimated)")

        # 5. Detect missing information
        gaps = self._detect_gaps(ctx, analysis)
        for g in gaps:
            note("Gap detected", g)

        # 6. Retrieve additional info for top gap (one extra pass, bounded)
        if gaps and len(scored) < max_knowledge_items * 2:
            extra = self._second_pass(project_id, task, analysis,
                                      exclude_ids={k.id for k in ctx.relevant_knowledge},
                                      limit=3)
            if extra:
                note("Retrieved additional information", f"{len(extra)} extra memories")
            else:
                note("Additional retrieval", "nothing more found locally")

        # 7. Optionally update memory with the task focus (learning)
        memory_updates: List[str] = []
        if learn_from_result and analysis['task_type'] in ('troubleshooting', 'development'):
            mem_id = self.agent.update_memory(
                project_id,
                f"Current focus: {task}",
                memory_type='task',
                importance_score=0.7,
                metadata={'knowledge_type': 'current_task', 'status': 'active',
                          'learned_by': self.agent.agent_id}
            )
            memory_updates.append(mem_id)
            note("Updated memory", "recorded current task focus")

        note("Context ready", f"context_id={ctx.id}")
        return AgentRunResult(
            task=task, project_id=project_id, context_id=ctx.id,
            estimated_tokens=ctx.estimated_tokens,
            knowledge_items=len(ctx.relevant_knowledge),
            gaps=gaps, action_log=log, memory_updates=memory_updates,
        )

    # ------------------------------------------------------------------

    def _detect_gaps(self, ctx, analysis) -> List[str]:
        present = {k.knowledge_type for k in ctx.relevant_knowledge}
        gaps: List[str] = []
        for ktype, message in _GAP_CHECKS:
            if ktype not in present:
                # only flag decisions/architecture as gaps when pool is small overall
                if ktype in ('decision', 'permanent_knowledge') and len(ctx.relevant_knowledge) >= 4:
                    continue
                gaps.append(message)
        return gaps[:3]

    def _second_pass(self, project_id: str, task: str, analysis,
                     exclude_ids: set, limit: int) -> List[Dict[str, Any]]:
        """Bounded follow-up retrieval using alternate keywords."""
        alt_terms = [k for k in analysis.get('keywords', []) if len(k) > 4]
        found: List[Dict[str, Any]] = []
        seen = set(exclude_ids)
        for term in alt_terms[:3]:
            for sm in self.relevance.search(project_id, term, limit=limit):
                if sm.memory['id'] not in seen:
                    seen.add(sm.memory['id'])
                    found.append(sm.memory)
        return found[:limit]
