"""Load and validate benchmark task definitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Sequence

from benchmarks.schemas import BenchmarkTask, validate_task_dict

TASKS_DIR = Path(__file__).resolve().parent / "tasks"


def load_task_file(path: Path) -> BenchmarkTask:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_task_dict(data)
    return BenchmarkTask.from_dict(data)


def load_task_set(name: str = "initial", *, tasks_dir: Optional[Path] = None) -> List[BenchmarkTask]:
    """
    Load a task set.

    Convention: benchmarks/tasks/<name>/*.json
    or benchmarks/tasks/<name>.json (list).
    """
    root = tasks_dir or TASKS_DIR
    directory = root / name
    single = root / f"{name}.json"
    tasks: List[BenchmarkTask] = []

    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            tasks.append(load_task_file(path))
    elif single.is_file():
        payload = json.loads(single.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            for item in payload:
                validate_task_dict(item)
                tasks.append(BenchmarkTask.from_dict(item))
        else:
            validate_task_dict(payload)
            tasks.append(BenchmarkTask.from_dict(payload))
    else:
        raise FileNotFoundError(f"Task set not found: {directory} or {single}")

    if not tasks:
        raise ValueError(f"Task set {name!r} is empty")
    return tasks


def filter_tasks(
    tasks: Sequence[BenchmarkTask],
    task_ids: Optional[Sequence[str]] = None,
) -> List[BenchmarkTask]:
    if not task_ids:
        return list(tasks)
    wanted = set(task_ids)
    selected = [t for t in tasks if t.task_id in wanted]
    missing = wanted - {t.task_id for t in selected}
    if missing:
        raise ValueError(f"Unknown task_id(s): {sorted(missing)}")
    return selected
