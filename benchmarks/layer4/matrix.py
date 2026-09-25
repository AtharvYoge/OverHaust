"""
Session matrix for Layer 4.

The pilot is an instrumentation preset: two Layer 3 tasks, both conditions,
two repetitions. It is not a result.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from benchmarks.schemas import BenchmarkTask


PILOT_NAME = "pilot"
PILOT_TASK_IDS: Tuple[str, ...] = ("sym_generate_kot", "arch_kitchen_hardware")
PILOT_CONDITIONS: Tuple[str, ...] = ("baseline", "overhaust")
PILOT_REPS = 2
PILOT_SEED = 1
PILOT_TASK_SET = "initial"


@dataclass(frozen=True)
class SessionPlan:
    session_id: str
    task_id: str
    condition: str
    rep: int
    seed: int
    execution_order: int
    prompt: str
    project_id: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "condition": self.condition,
            "rep": self.rep,
            "seed": self.seed,
            "execution_order": self.execution_order,
            "prompt": self.prompt,
            "project_id": self.project_id,
        }


def plan_matrix(
    tasks: Sequence[BenchmarkTask],
    *,
    conditions: Sequence[str] = PILOT_CONDITIONS,
    reps: int = PILOT_REPS,
    seed: int = PILOT_SEED,
) -> List[SessionPlan]:
    """
    One fresh session per task × condition × rep.

    Canonical order (before the seed shuffle) is task list order, then
    baseline before overhaust, then rep 0..n-1. `random.Random(seed)`
    shuffles that list. `execution_order` is the shuffled index.
    """
    if reps < 1:
        raise ValueError("reps must be >= 1")
    for condition in conditions:
        if condition not in {"baseline", "overhaust"}:
            raise ValueError(f"invalid condition: {condition}")

    cells: List[Tuple[BenchmarkTask, str, int]] = []
    for task in tasks:
        for condition in conditions:
            for rep in range(reps):
                cells.append((task, condition, rep))

    order = list(range(len(cells)))
    random.Random(seed).shuffle(order)

    plans: List[SessionPlan] = []
    for execution_order, index in enumerate(order):
        task, condition, rep = cells[index]
        plans.append(
            SessionPlan(
                session_id=f"{task.task_id}-{condition}-r{rep}",
                task_id=task.task_id,
                condition=condition,
                rep=rep,
                seed=seed,
                execution_order=execution_order,
                prompt=task.prompt,
                project_id=task.project_id,
            )
        )
    plans.sort(key=lambda plan: plan.execution_order)
    return plans


def load_pilot_tasks() -> List[BenchmarkTask]:
    from benchmarks.tasks_loader import filter_tasks, load_task_set

    tasks = load_task_set(PILOT_TASK_SET)
    # Preserve the preset order, not alphabetical file order.
    selected = filter_tasks(tasks, PILOT_TASK_IDS)
    by_id = {task.task_id: task for task in selected}
    return [by_id[task_id] for task_id in PILOT_TASK_IDS]
