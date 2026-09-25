"""
Controlled repositories at SMALL / MEDIUM / LARGE sizes for fair comparison.

All fixtures are generated under a temp directory and indexed into an isolated
MemoryStore. Production DBs are never used.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Literal, Optional

from packages.memory.memory_store import MemoryStore
from packages.retrieval.test_fixtures import (
    make_flow_beam_tree,
    make_labkot_retrieval_tree,
)
from services.ingestion.index_store import ProjectIndexStore

from benchmarks.fixture import FixtureProject

RepoSize = Literal["small", "medium", "large"]


def _write_tiny(root: Path) -> None:
    """SMALL: one obvious file — full-file read is often cheaper than packaged context."""
    (root / "src").mkdir(parents=True)
    (root / "src" / "kot.ts").write_text(
        "/** Kitchen Order Ticket generator */\n"
        "export function generateKOT(orderId: string) {\n"
        "  return { orderId, items: [], printedAt: Date.now() };\n"
        "}\n",
        encoding="utf-8",
    )


def _write_large(root: Path) -> None:
    """LARGE: LabKOT + beam tree + synthetic noise modules."""
    make_labkot_retrieval_tree(root)
    make_flow_beam_tree(root)
    noise = root / "lib" / "noise"
    noise.mkdir(parents=True, exist_ok=True)
    for i in range(40):
        (noise / f"module_{i:02d}.dart").write_text(
            f"// noise module {i}\n"
            f"class NoiseService{i} {{\n"
            f"  void run{i}() {{}}\n"
            f"}}\n",
            encoding="utf-8",
        )
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "architecture.md").write_text(
        "# Architecture\n\nKitchen orders flow to Quikot printers via hardware adapters.\n",
        encoding="utf-8",
    )


def prepare_sized_fixture(
    size: RepoSize = "medium",
    *,
    project_id: Optional[str] = None,
    root: Optional[Path] = None,
) -> FixtureProject:
    """
    Build and index a fixture of the requested size.

    small  → single-file tree
    medium → make_labkot_retrieval_tree (existing)
    large  → labkot + beam + noise
    """
    pid = project_id or f"bench-{size}"
    tmp: Optional[tempfile.TemporaryDirectory] = None
    if root is None:
        tmp = tempfile.TemporaryDirectory(prefix=f"overhaust-bench-{size}-")
        base = Path(tmp.name)
        tree = base / "repo"
        tree.mkdir()
        db_path = str(base / "bench.db")
    else:
        tree = Path(root)
        tree.mkdir(parents=True, exist_ok=True)
        db_path = str(tree.parent / "bench.db")

    if size == "small":
        _write_tiny(tree)
        repo_label = "fixture:tiny_kot"
    elif size == "medium":
        make_labkot_retrieval_tree(tree)
        repo_label = "fixture:labkot_retrieval"
    elif size == "large":
        _write_large(tree)
        repo_label = "fixture:labkot_large"
    else:
        raise ValueError(f"unknown size: {size}")

    store = MemoryStore(db_path)
    store.add_project(pid, f"Benchmark {size}", repo_label, str(tree))
    ProjectIndexStore(store).sync_project(pid, str(tree))
    fx = FixtureProject(
        project_id=pid,
        root=tree,
        db_path=db_path,
        memory_store=store,
        _tmpdir=tmp,
    )
    # Attach size/label for runners without changing FixtureProject dataclass.
    fx.repository_size = size  # type: ignore[attr-defined]
    fx.repository_label = repo_label  # type: ignore[attr-defined]
    return fx


def count_source_files(root: Path) -> int:
    return sum(1 for p in root.rglob("*") if p.is_file() and p.suffix in {
        ".ts", ".tsx", ".dart", ".py", ".md", ".js"
    })
