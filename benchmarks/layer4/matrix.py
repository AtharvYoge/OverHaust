"""
Session matrix for Layer 4.

Presets:

- ``pilot`` (default): two Layer 3 tasks × both conditions × two repetitions
  = 8 sessions.
- ``full``: all five Layer 3 initial tasks × both conditions × two repetitions
  = 20 sessions.

Ordering is pair counterbalancing, not a global shuffle of sessions. Each
``(task, rep)`` is one pair. Both sessions of a pair run adjacently. Within a
task, the within-pair condition order is balanced across reps. Pair units are
shuffled with ``random.Random(seed)``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from benchmarks.schemas import BenchmarkTask


PILOT_NAME = "pilot"
FULL_NAME = "full"
PRESET_NAMES: Tuple[str, ...] = (PILOT_NAME, FULL_NAME)

PILOT_TASK_IDS: Tuple[str, ...] = ("sym_generate_kot", "arch_kitchen_hardware")
# Filename order of benchmarks/tasks/initial, the frozen Layer 3 task set.
FULL_TASK_IDS: Tuple[str, ...] = (
    "arch_kitchen_hardware",
    "cross_order_to_printer",
    "flow_order_to_kitchen",
    "impact_change_generate_kot",
    "sym_generate_kot",
)
PILOT_CONDITIONS: Tuple[str, ...] = ("baseline", "overhaust")
PILOT_REPS = 2
FULL_REPS = 2
PILOT_SEED = 1
PILOT_TASK_SET = "initial"

BASELINE_FIRST = "baseline->overhaust"
OVERHAUST_FIRST = "overhaust->baseline"
CONDITION_ORDERS: Tuple[str, ...] = (BASELINE_FIRST, OVERHAUST_FIRST)


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
    pair_id: str
    order_in_pair: int
    condition_order: str

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
            "pair_id": self.pair_id,
            "order_in_pair": self.order_in_pair,
            "condition_order": self.condition_order,
        }


def _balanced_condition_orders(reps: int, rng: random.Random) -> List[str]:
    """
    One condition_order per rep, as even a split as possible.

    When ``reps`` is odd, ``rng.randrange(2) == 0`` gives the extra slot to
    baseline-first; otherwise OverHaust-first. The assignment is then shuffled
    across reps with the same generator.
    """
    half = reps // 2
    counts = {BASELINE_FIRST: half, OVERHAUST_FIRST: half}
    if reps % 2 == 1:
        extra = BASELINE_FIRST if rng.randrange(2) == 0 else OVERHAUST_FIRST
        counts[extra] += 1
    orders = (
        [BASELINE_FIRST] * counts[BASELINE_FIRST]
        + [OVERHAUST_FIRST] * counts[OVERHAUST_FIRST]
    )
    rng.shuffle(orders)
    return orders


def plan_matrix(
    tasks: Sequence[BenchmarkTask],
    *,
    conditions: Sequence[str] = PILOT_CONDITIONS,
    reps: int = PILOT_REPS,
    seed: int = PILOT_SEED,
) -> List[SessionPlan]:
    """
    One fresh session per task × condition × rep, counterbalanced by pair.

    A pair unit is ``(task, rep)`` and contains both conditions. For each task,
    across its reps, within-pair order is balanced (reps=2 → one
    OverHaust-first pair and one baseline-first pair; odd reps differ by at
    most one). Pair units are then shuffled. ``random.Random(seed)`` drives
    both steps, in task-list order, then the pair shuffle. The two sessions of
    a pair are emitted back-to-back. ``execution_order`` is that sequence.
    ``order_in_pair`` is 1 then 2. ``condition_order`` is
    ``baseline->overhaust`` or ``overhaust->baseline``.
    """
    if reps < 1:
        raise ValueError("reps must be >= 1")
    if set(conditions) != set(PILOT_CONDITIONS) or len(tuple(conditions)) != 2:
        raise ValueError("pair counterbalancing requires baseline and overhaust")

    rng = random.Random(seed)
    pair_units: List[Tuple[BenchmarkTask, int, str]] = []
    for task in tasks:
        for rep, condition_order in enumerate(_balanced_condition_orders(reps, rng)):
            pair_units.append((task, rep, condition_order))
    rng.shuffle(pair_units)

    plans: List[SessionPlan] = []
    execution_order = 0
    for task, rep, condition_order in pair_units:
        pair_id = f"{task.task_id}-r{rep}"
        for order_in_pair, condition in enumerate(condition_order.split("->"), start=1):
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
                    pair_id=pair_id,
                    order_in_pair=order_in_pair,
                    condition_order=condition_order,
                )
            )
            execution_order += 1
    return plans


def _load_ids(task_ids: Sequence[str]) -> List[BenchmarkTask]:
    from benchmarks.tasks_loader import filter_tasks, load_task_set

    tasks = load_task_set(PILOT_TASK_SET)
    selected = filter_tasks(tasks, task_ids)
    by_id = {task.task_id: task for task in selected}
    return [by_id[task_id] for task_id in task_ids]


def load_pilot_tasks() -> List[BenchmarkTask]:
    return _load_ids(PILOT_TASK_IDS)


def load_full_tasks() -> List[BenchmarkTask]:
    return _load_ids(FULL_TASK_IDS)


def load_preset_tasks(preset: str) -> List[BenchmarkTask]:
    if preset == PILOT_NAME:
        return load_pilot_tasks()
    if preset == FULL_NAME:
        return load_full_tasks()
    raise ValueError(f"unknown preset: {preset}")


def preset_reps(preset: str) -> int:
    if preset == PILOT_NAME:
        return PILOT_REPS
    if preset == FULL_NAME:
        return FULL_REPS
    raise ValueError(f"unknown preset: {preset}")
