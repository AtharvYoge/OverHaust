"""
Reproducibility metadata for every benchmark run.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from benchmarks import BENCHMARK_VERSION


def _git(cmd: list[str], cwd: Optional[str] = None) -> Optional[str]:
    try:
        out = subprocess.check_output(
            cmd, cwd=cwd, stderr=subprocess.DEVNULL, text=True, timeout=5
        )
        return out.strip() or None
    except Exception:
        return None


def restore_repository_state(repository_path: str) -> Dict[str, Any]:
    """
    Restore working tree to HEAD before a paired condition runs.

    For non-git fixture trees, records that restore is UNAVAILABLE (caller
    must ensure fixtures are not mutated, or recreate the fixture).
    """
    root = Path(repository_path)
    if not root.is_dir():
        return {"status": "UNAVAILABLE", "detail": "path missing"}
    head = _git(["git", "rev-parse", "--is-inside-work-tree"], cwd=str(root))
    if head != "true":
        return {
            "status": "UNAVAILABLE",
            "detail": "not a git work tree; fixture must be recreated between runs",
        }
    dirty_before = _git(["git", "status", "--porcelain"], cwd=str(root))
    # Discard tracked modifications; do not delete untracked (safer for fixtures).
    _git(["git", "checkout", "--", "."], cwd=str(root))
    _git(["git", "reset", "--hard", "HEAD"], cwd=str(root))
    dirty_after = _git(["git", "status", "--porcelain"], cwd=str(root))
    return {
        "status": "KNOWN",
        "verified": not bool(dirty_after),
        "mechanism": "git",
        "dirty_before": bool(dirty_before),
        "dirty_after": bool(dirty_after),
        "commit": _git(["git", "rev-parse", "HEAD"], cwd=str(root)),
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def capture_repository_snapshot(repository_path: str) -> Dict[str, Any]:
    """In-memory content snapshot of a generated fixture. Skips .git."""
    root = Path(repository_path)
    if not root.is_dir():
        return {"ok": False, "detail": "path missing", "files": {}, "tree_hash": None}
    files: Dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        files[rel] = path.read_bytes()
    lines = [f"{rel}\0{_file_sha256_bytes(data)}" for rel, data in sorted(files.items())]
    tree_hash = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    return {"ok": True, "files": files, "tree_hash": tree_hash, "file_count": len(files)}


def _file_sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tree_hash(root: Path) -> str:
    lines = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        lines.append(f"{rel}\0{_file_sha256(path)}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def restore_repository_snapshot(repository_path: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reset a non-git fixture to a captured snapshot and verify the tree hash.

    status is KNOWN only when the tree matches the snapshot after the write.
    """
    root = Path(repository_path)
    if not root.is_dir() or not snapshot.get("ok"):
        return {
            "status": "UNAVAILABLE",
            "verified": False,
            "mechanism": "content_snapshot",
            "detail": "path missing or snapshot unavailable",
        }
    files: Dict[str, bytes] = snapshot.get("files") or {}
    expected = set(files)
    for path in list(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        if rel not in expected:
            path.unlink()
    for rel, data in files.items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    actual = _tree_hash(root)
    verified = actual == snapshot.get("tree_hash")
    return {
        "status": "KNOWN" if verified else "FAILED",
        "verified": verified,
        "mechanism": "content_snapshot",
        "tree_hash": snapshot.get("tree_hash"),
        "file_count": snapshot.get("file_count"),
        "detail": None if verified else "tree hash mismatch after restore",
    }


def isolate_repository(repository_path: str, snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Restore then verify. Git work trees use git; fixtures use the snapshot."""
    root = Path(repository_path)
    if not root.is_dir():
        return {
            "status": "UNAVAILABLE",
            "verified": False,
            "mechanism": None,
            "detail": "path missing",
        }
    if _git(["git", "rev-parse", "--is-inside-work-tree"], cwd=str(root)) == "true":
        return restore_repository_state(str(root))
    if snapshot is None:
        return {
            "status": "UNAVAILABLE",
            "verified": False,
            "mechanism": "content_snapshot",
            "detail": "not a git work tree and no snapshot was captured",
        }
    return restore_repository_snapshot(str(root), snapshot)


def collect_reproducibility(
    *,
    repo_root: Optional[str] = None,
    repository_path: Optional[str] = None,
    model: Optional[str] = None,
    model_version: Optional[str] = None,
    provider: Optional[str] = None,
    seed: Optional[int] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    root = repo_root or os.getcwd()
    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "benchmark_version": BENCHMARK_VERSION,
        "overhaust_git_commit": _git(["git", "rev-parse", "HEAD"], cwd=root),
        "overhaust_git_dirty": bool(
            _git(["git", "status", "--porcelain"], cwd=root)
        ),
        "repository_path": repository_path,
        "repository_commit": (
            _git(["git", "rev-parse", "HEAD"], cwd=repository_path)
            if repository_path else None
        ),
        "provider": provider,
        "model": model,
        "model_version": model_version or model,
        "seed": seed,
        "config": config or {},
        "python": os.sys.version.split()[0],
    }
