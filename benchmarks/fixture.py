"""
Controlled fixture project for the initial benchmark task set.

Uses packages.retrieval.test_fixtures.make_labkot_retrieval_tree — a real,
indexed kitchen/order fixture already used by OverHaust tests. The harness
indexes it into a temporary MemoryStore so production DBs are untouched.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from packages.memory.memory_store import MemoryStore
from packages.retrieval.test_fixtures import make_labkot_retrieval_tree
from services.ingestion.index_store import ProjectIndexStore

DEFAULT_PROJECT_ID = "bench-labkot"


@dataclass
class FixtureProject:
    project_id: str
    root: Path
    db_path: str
    memory_store: MemoryStore
    _tmpdir: Optional[tempfile.TemporaryDirectory] = None

    def close(self) -> None:
        if self._tmpdir is not None:
            self._tmpdir.cleanup()
            self._tmpdir = None

    def __enter__(self) -> "FixtureProject":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def prepare_labkot_fixture(
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    root: Optional[Path] = None,
) -> FixtureProject:
    """
    Create (or reuse) a LabKOT retrieval tree and index it.

    When root is None, a TemporaryDirectory owns the tree and DB.
    """
    tmp: Optional[tempfile.TemporaryDirectory] = None
    if root is None:
        tmp = tempfile.TemporaryDirectory(prefix="overhaust-bench-")
        base = Path(tmp.name)
        tree = base / "repo"
        tree.mkdir()
        db_path = str(base / "bench.db")
    else:
        tree = Path(root)
        tree.mkdir(parents=True, exist_ok=True)
        db_path = str(tree.parent / "bench.db")

    make_labkot_retrieval_tree(tree)
    store = MemoryStore(db_path)
    store.add_project(project_id, "Benchmark LabKOT", "controlled fixture", str(tree))
    ProjectIndexStore(store).sync_project(project_id, str(tree))
    return FixtureProject(
        project_id=project_id,
        root=tree,
        db_path=db_path,
        memory_store=store,
        _tmpdir=tmp,
    )
