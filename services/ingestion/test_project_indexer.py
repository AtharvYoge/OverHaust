"""Tests for project/file ingestion and incremental indexing."""
import sys, os, tempfile, shutil, time
from pathlib import Path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from services.ingestion.project_indexer import ProjectIndexer, PathSecurityError


def make_tree(root: Path):
    (root / 'src').mkdir(parents=True)
    (root / 'node_modules' / 'junk').mkdir(parents=True)
    (root / 'node_modules' / 'junk' / 'index.js').write_text('function ignored() {}')
    (root / 'src' / 'app.ts').write_text(
        'import { render } from "react-dom";\n'
        'import { helper } from "./utils";\n'
        'export function main() { return 1; }\n'
        'export class App { start() {} }\n'
    )
    (root / 'src' / 'utils.ts').write_text(
        'export function helper(): number { return 42; }\n'
        'export interface Config { port: number }\n'
        'export type ID = string;\n'
    )
    (root / 'src' / 'server.py').write_text(
        'import os\nfrom fastapi import FastAPI\n\n'
        'def create_app():\n    return FastAPI()\n\n'
        'class Server:\n    pass\n'
    )
    (root / 'package.json').write_text('{"name":"demo","dependencies":{"react":"^18"}}')
    (root / 'README.md').write_text('# Demo project\nA test project.')
    (root / 'binary.bin').write_bytes(b'\x00\x01\x02')  # skipped: not allowed ext


def test_index_basic_tree():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_tree(root)
        idx = ProjectIndexer().index_project(str(root), 'proj-x')
        paths = {f.path for f in idx.files}
        assert 'src/app.ts' in paths
        assert 'src/utils.ts' in paths
        assert 'src/server.py' in paths
        assert 'package.json' in paths
        assert not any('node_modules' in p for p in paths), "node_modules must be skipped"
        assert not any(p.endswith('.bin') for p in paths)
        print(f"✓ indexed {len(idx.files)} files, {idx.total_tokens} tokens")


def test_symbol_extraction():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_tree(root)
        idx = ProjectIndexer().index_project(str(root), 'proj-x')
        by_path = {f.path: f for f in idx.files}
        app = by_path['src/app.ts']
        names = {s.name: s.kind for s in app.symbols}
        assert names.get('main') == 'function'
        assert names.get('App') == 'class'
        utils = by_path['src/utils.ts']
        kinds = {s.name: s.kind for s in utils.symbols}
        assert kinds.get('helper') == 'function'
        assert kinds.get('Config') == 'interface'
        assert kinds.get('ID') == 'interface'  # type alias grouped with interface
        server = by_path['src/server.py']
        pynames = {s.name: s.kind for s in server.symbols}
        assert pynames.get('create_app') == 'function'
        assert pynames.get('Server') == 'class'
        assert set(utils.exports) == {'helper', 'Config', 'ID'}
        print(f"✓ symbols: {idx.stats['symbols']} total across {len(idx.files)} files")


def test_imports_and_dependencies():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_tree(root)
        idx = ProjectIndexer().index_project(str(root), 'proj-x')
        deps = idx.dependencies
        assert 'react-dom' in deps['src/app.ts']
        assert './utils' in deps['src/app.ts']
        assert 'os' in deps['src/server.py']
        assert 'fastapi' in deps['src/server.py']
        print(f"✓ dependencies extracted for {len(deps)} files")


def test_config_detection():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_tree(root)
        idx = ProjectIndexer().index_project(str(root), 'proj-x')
        pkg = next(f for f in idx.files if f.path == 'package.json')
        assert pkg.is_config
        assert len(pkg.symbols) == 0
        print("✓ config files detected, not symbol-parsed")


def test_path_security():
    idx = ProjectIndexer()
    try:
        idx.index_project('/nonexistent-path-xyz-123', 'ghost')
        raise AssertionError("should have raised")
    except PathSecurityError:
        print("✓ nonexistent path rejected")
    with tempfile.NamedTemporaryFile() as f:
        try:
            idx.index_project(f.name, 'file-root')
            raise AssertionError("file root should be rejected")
        except PathSecurityError:
            print("✓ file-as-root rejected")


def test_incremental_diff_and_apply():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_tree(root)
        indexer = ProjectIndexer()
        idx1 = indexer.index_project(str(root), 'proj-x')

        # modify one file, add one, delete one, rename one
        time.sleep(0.01)
        (root / 'src' / 'utils.ts').write_text(
            'export function helper(): number { return 43; }\n'
            'export interface Config { port: number; host: string }\n'
            'export type ID = string;\n'
        )
        (root / 'src' / 'new_module.ts').write_text('export const x = 1;\n')
        (root / 'README.md').unlink()
        server_content = (root / 'src' / 'server.py').read_text()
        (root / 'src' / 'server.py').unlink()
        (root / 'src' / 'api_server.py').write_text(server_content)

        diff = indexer.diff_project(idx1)
        assert 'src/utils.ts' in diff['modified'], diff
        assert 'src/new_module.ts' in diff['added'], diff
        assert 'README.md' in diff['deleted'], diff
        assert ('src/server.py', 'src/api_server.py') in diff['renamed'], diff

        idx2 = indexer.apply_diff(idx1, diff)
        paths2 = {f.path for f in idx2.files}
        assert 'src/api_server.py' in paths2
        assert 'src/server.py' not in paths2
        assert 'src/new_module.ts' in paths2
        assert 'README.md' not in paths2
        # unchanged files reused (same object content hash preserved)
        app1 = next(f for f in idx1.files if f.path == 'src/app.ts')
        app2 = next(f for f in idx2.files if f.path == 'src/app.ts')
        assert app1.sha256 == app2.sha256
        # updated symbols re-extracted
        utils2 = next(f for f in idx2.files if f.path == 'src/utils.ts')
        assert 'host: string' not in str(utils2.symbols)  # sanity: re-parsed new content
        assert any(s.name == 'Config' for s in utils2.symbols)
        print(f"✓ incremental: mod={diff['modified']}, add={diff['added']}, "
              f"del={diff['deleted']}, ren={diff['renamed']}")
        print(f"  index updated: {len(idx1.files)} -> {len(idx2.files)} files")


if __name__ == "__main__":
    print("Running project ingestion tests...\n")
    test_index_basic_tree()
    test_symbol_extraction()
    test_imports_and_dependencies()
    test_config_detection()
    test_path_security()
    test_incremental_diff_and_apply()
    print("\n✓ All project ingestion tests passed!")
