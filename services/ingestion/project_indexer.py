"""
Project / file ingestion for Overhaust.

ProjectIndexer scans an explicitly authorized directory, reads safe
text-based files, and extracts structured knowledge: modules, files,
symbols (functions/classes/interfaces), imports/exports, dependencies,
and configuration. Never executes files. Enforces path containment.
"""

import os
import re
import json
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

logger = logging.getLogger(__name__)

# Safe, text-based extensions only
ALLOWED_EXTENSIONS = {
    '.ts', '.tsx', '.js', '.jsx', '.py', '.dart', '.java',
    '.json', '.yaml', '.yml', '.md', '.txt', '.xml', '.html',
    '.css', '.sql', '.toml', '.ini', '.cfg', '.env.example',
    '.go', '.rs', '.rb', '.php', '.c', '.h', '.cpp', '.cs',
    '.vue', '.svelte', '.graphql', '.prisma', '.sh',
}

# Directories never descended into
SKIP_DIRS = {
    'node_modules', '.git', '__pycache__', '.venv', 'venv', 'env',
    'dist', 'build', '.next', '.expo', 'coverage', '.cache',
    'Pods', '.gradle', '.idea', '.vscode', 'target', 'vendor',
    'DerivedData', '.dart_tool', 'android/.gradle',
}

MAX_FILE_SIZE = 1_000_000       # 1MB per file
MAX_FILES = 5000                # cap total indexed files


@dataclass
class Symbol:
    """A function/class/interface/struct extracted from a file."""
    name: str
    kind: str                   # function | class | interface | struct | enum | const
    file_path: str
    line: int
    exported: bool = False


@dataclass
class FileIndex:
    """Structured knowledge for one file."""
    path: str                   # relative to project root
    extension: str
    size: int
    sha256: str
    token_count: int
    symbols: List[Symbol] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    is_config: bool = False
    line_count: int = 0


@dataclass
class ProjectIndex:
    """Structured representation of an indexed project."""
    project_id: str
    root_path: str
    files: List[FileIndex]
    indexed_at: str
    total_tokens: int
    dependencies: Dict[str, List[str]] = field(default_factory=dict)  # file -> imported modules
    stats: Dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Symbol extraction (regex-based; deliberately conservative)
# ---------------------------------------------------------------------------

_PATTERNS = {
    'function': [
        re.compile(r'^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)', re.M),
        re.compile(r'^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(', re.M),
        re.compile(r'^\s*(?:export\s+)?(?:async\s+)?def\s+([A-Za-z_][\w]*)', re.M),
        re.compile(r'^\s*(?:public|private|protected|static|\s)*[\w<>\[\]]+\s+([a-z][\w]*)\s*\([^)]*\)\s*(?:\{|throws)', re.M),  # java-ish
        re.compile(r'^\s*func\s+(?:\(\w+\s+[\w\[\]*]+\)\s+)?([A-Za-z_][\w]*)\s*\(', re.M),  # go
    ],
    'class': [
        re.compile(r'^\s*(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)', re.M),
    ],
    'interface': [
        re.compile(r'^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)', re.M),
        re.compile(r'^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*=', re.M),
    ],
    'struct': [
        re.compile(r'^\s*(?:pub\s+)?struct\s+([A-Za-z_][\w]*)', re.M),
    ],
    'enum': [
        re.compile(r'^\s*(?:export\s+)?enum\s+([A-Za-z_$][\w$]*)', re.M),
    ],
}

_IMPORT_PATTERNS = [
    re.compile(r'^\s*import\s+(?:[\w*{}\s,]+\s+from\s+)?[\'"]([^\'"]+)[\'"]', re.M),       # js/ts
    re.compile(r'^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))', re.M),             # python
    re.compile(r'^\s*import\s+[\'"]([^\'"]+)[\'"]', re.M),                               # dart side-effect
    re.compile(r'^\s*#include\s+[<"]([^>"]+)[>"]', re.M),                                # c/cpp
    re.compile(r'^\s*use\s+([\w:]+)', re.M),                                             # rust
    re.compile(r'^\s*require\s*\(\s*[\'"]([^\'"]+)[\'"]', re.M),                         # commonjs
]

_EXPORT_PATTERNS = [
    re.compile(r'^\s*export\s+(?:default\s+)?(?:class|function|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)', re.M),
    re.compile(r'^\s*export\s*\{([^}]+)\}', re.M),
]

_CONFIG_NAMES = {
    'package.json', 'tsconfig.json', 'pyproject.toml', 'setup.py', 'setup.cfg',
    'requirements.txt', 'Cargo.toml', 'go.mod', 'pubspec.yaml', 'pom.xml',
    'build.gradle', 'composer.json', 'Gemfile', '.env.example', 'docker-compose.yml',
    'Dockerfile', 'Makefile', 'webpack.config.js', 'vite.config.ts', 'next.config.js',
    'schema.prisma', 'app.json', 'eas.json',
}


def _line_of(text: str, pos: int) -> int:
    return text.count('\n', 0, pos) + 1


def _extract_symbols(text: str, file_path: str) -> List[Symbol]:
    symbols: List[Symbol] = []
    exported_names: Set[str] = set()
    for pat in _EXPORT_PATTERNS:
        for m in pat.finditer(text):
            for name in m.group(1).split(','):
                name = name.strip().split(' as ')[-1].strip()
                if name:
                    exported_names.add(name)
    for kind, pats in _PATTERNS.items():
        for pat in pats:
            for m in pat.finditer(text):
                name = m.group(1)
                symbols.append(Symbol(
                    name=name, kind=kind, file_path=file_path,
                    line=_line_of(text, m.start()),
                    exported=name in exported_names,
                ))
    # dedupe by (name, kind)
    seen = set()
    out = []
    for s in symbols:
        key = (s.name, s.kind)
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


def _extract_imports(text: str) -> List[str]:
    found: Set[str] = set()
    for pat in _IMPORT_PATTERNS:
        for m in pat.finditer(text):
            for g in m.groups():
                if g:
                    found.add(g.strip())
    return sorted(found)


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------

class PathSecurityError(Exception):
    pass


class ProjectIndexer:
    """Indexes an explicitly authorized project directory."""

    def __init__(self, token_estimator=None):
        from packages.tokenization.token_estimator import TokenEstimator
        self.estimator = token_estimator or TokenEstimator()

    def _validate_root(self, root_path: str) -> Path:
        root = Path(root_path).expanduser().resolve()
        if not root.exists():
            raise PathSecurityError(f"Path does not exist: {root}")
        if not root.is_dir():
            raise PathSecurityError(f"Path is not a directory: {root}")
        return root

    def _iter_files(self, root: Path) -> List[Path]:
        files: List[Path] = []
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.')]
            for fname in filenames:
                if fname.startswith('.'):
                    continue
                p = Path(dirpath) / fname
                ext = p.suffix.lower()
                if ext not in ALLOWED_EXTENSIONS and fname not in _CONFIG_NAMES:
                    continue
                try:
                    if p.stat().st_size > MAX_FILE_SIZE:
                        continue
                    # Containment check (guards against symlinked dirs)
                    p.resolve().relative_to(root)
                except (OSError, ValueError):
                    continue
                files.append(p)
                if len(files) >= MAX_FILES:
                    return files
        return files

    def index_file(self, path: Path, root: Path) -> Optional[FileIndex]:
        try:
            raw = path.read_bytes()
            text = raw.decode('utf-8', errors='replace')
        except OSError:
            return None
        rel = str(path.relative_to(root))
        sha = hashlib.sha256(raw).hexdigest()
        is_config = path.name in _CONFIG_NAMES or path.suffix.lower() in {'.json', '.yaml', '.yml', '.toml', '.ini', '.xml'}
        idx = FileIndex(
            path=rel,
            extension=path.suffix.lower(),
            size=len(raw),
            sha256=sha,
            token_count=self.estimator.estimate_tokens(text),
            symbols=_extract_symbols(text, rel) if not is_config else [],
            imports=_extract_imports(text),
            exports=[],
            is_config=is_config,
            line_count=text.count('\n') + 1,
        )
        idx.exports = sorted({s.name for s in idx.symbols if s.exported})
        return idx

    def index_project(self, root_path: str, project_id: str) -> ProjectIndex:
        root = self._validate_root(root_path)
        files: List[FileIndex] = []
        for p in self._iter_files(root):
            idx = self.index_file(p, root)
            if idx:
                files.append(idx)
        deps: Dict[str, List[str]] = {f.path: f.imports for f in files if f.imports}
        stats: Dict[str, int] = {}
        for f in files:
            stats[f.extension] = stats.get(f.extension, 0) + 1
        stats['symbols'] = sum(len(f.symbols) for f in files)
        stats['config_files'] = sum(1 for f in files if f.is_config)
        return ProjectIndex(
            project_id=project_id,
            root_path=str(root),
            files=files,
            indexed_at=datetime.now().isoformat(),
            total_tokens=sum(f.token_count for f in files),
            dependencies=deps,
            stats=stats,
        )

    # ------------------------------------------------------------------
    # Incremental update
    # ------------------------------------------------------------------

    def diff_project(self, previous: ProjectIndex, root_path: Optional[str] = None) -> Dict[str, List[str]]:
        """
        Compare current on-disk state to a previous index.
        Returns {'added': [...], 'modified': [...], 'deleted': [...], 'renamed': [(old,new)]}
        Renames detected by matching content hash of deleted+added files.
        """
        root = self._validate_root(root_path or previous.root_path)
        current_paths = {str(p.relative_to(root)): p for p in self._iter_files(root)}
        old_by_path = {f.path: f for f in previous.files}

        added, modified, deleted = [], [], []
        old_hashes: Dict[str, str] = {f.sha256: f.path for f in previous.files}
        new_hashes: Dict[str, str] = {}

        for rel, p in current_paths.items():
            try:
                sha = hashlib.sha256(p.read_bytes()).hexdigest()
            except OSError:
                continue
            new_hashes[sha] = rel
            if rel not in old_by_path:
                added.append(rel)
            elif old_by_path[rel].sha256 != sha:
                modified.append(rel)

        for rel in old_by_path:
            if rel not in current_paths:
                deleted.append(rel)

        # Rename detection: deleted+added sharing the same content hash
        renamed = []
        still_added = []
        for rel in added:
            pass  # computed below after we know hashes of added files
        # Recompute hashes for added files (done above in new_hashes where possible)
        for old_rel in list(deleted):
            old_sha = old_by_path[old_rel].sha256
            if old_sha in new_hashes:
                new_rel = new_hashes[old_sha]
                if new_rel in added:
                    renamed.append((old_rel, new_rel))
                    deleted.remove(old_rel)
                    added.remove(new_rel)

        return {'added': added, 'modified': modified, 'deleted': deleted, 'renamed': renamed}

    def apply_diff(self, previous: ProjectIndex, diff: Dict[str, List[Any]],
                   root_path: Optional[str] = None) -> ProjectIndex:
        """
        Incrementally update a previous index given a diff from diff_project().
        Only re-reads files that changed; reuses FileIndex for untouched files.
        """
        root = self._validate_root(root_path or previous.root_path)
        touched = set(diff['added']) | set(diff['modified']) | {n for _, n in diff['renamed']}
        removed = set(diff['deleted']) | {o for o, _ in diff['renamed']}

        kept = [f for f in previous.files if f.path not in removed and f.path not in touched]
        new_files: List[FileIndex] = list(kept)
        for rel in sorted(touched):
            p = root / rel
            if p.exists():
                idx = self.index_file(p, root)
                if idx:
                    new_files.append(idx)

        deps = {f.path: f.imports for f in new_files if f.imports}
        stats: Dict[str, int] = {}
        for f in new_files:
            stats[f.extension] = stats.get(f.extension, 0) + 1
        stats['symbols'] = sum(len(f.symbols) for f in new_files)
        stats['config_files'] = sum(1 for f in new_files if f.is_config)
        return ProjectIndex(
            project_id=previous.project_id,
            root_path=str(root),
            files=new_files,
            indexed_at=datetime.now().isoformat(),
            total_tokens=sum(f.token_count for f in new_files),
            dependencies=deps,
            stats=stats,
        )
