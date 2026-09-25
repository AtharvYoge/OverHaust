"""
Cross-agent multi-repository validation (emission paths only).

Proves MCP + UserPromptSubmit hook emit correct, isolated context for two
repos. Does NOT prove Cursor/Codex/Claude UI/model consumption.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "scripts" / "integrations" / "overhaust_user_prompt_hook.py"

ALPHA = "ALPHA_CONTEXT_2026"
BETA = "BETA_CONTEXT_2026"
ALPHA_NEW = "ALPHA_FRESH_TOKEN_9981"


def _write_repos(base: Path) -> tuple[Path, Path]:
    repo_a = base / "repo-A"
    repo_b = base / "repo-B"
    (repo_a / "src" / "nested").mkdir(parents=True)
    (repo_b / "src").mkdir(parents=True)
    (repo_a / "src" / "alpha_marker.py").write_text(
        f'UNIQUE = "{ALPHA}"\n\n'
        f"class AlphaContextMarker:\n"
        f"    token = UNIQUE\n"
    )
    (repo_b / "src" / "beta_marker.py").write_text(
        f'UNIQUE = "{BETA}"\n\n'
        f"class BetaContextMarker:\n"
        f"    token = UNIQUE\n"
    )
    return repo_a, repo_b


def _blob(resp) -> str:
    return json.dumps(resp.to_dict())


def _run_hook(cwd: Path, prompt: str, env: dict) -> str:
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({
            "prompt": prompt,
            "cwd": str(cwd),
            "hook_event_name": "UserPromptSubmit",
        }),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    return (payload.get("hookSpecificOutput") or {}).get("additionalContext") or ""


@pytest.fixture()
def dual_repos(tmp_path):
    from packages.memory.memory_store import MemoryStore
    from services.ingestion.project_lifecycle import ensure_project_indexed

    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()
    store = MemoryStore(db.name)
    repo_a, repo_b = _write_repos(tmp_path)
    ensure_project_indexed("xagent-a", str(repo_a), name="A", memory_store=store)
    ensure_project_indexed("xagent-b", str(repo_b), name="B", memory_store=store)
    env = os.environ.copy()
    env["OVERHAUST_DB_PATH"] = db.name
    yield store, repo_a, repo_b, env, db.name
    try:
        os.unlink(db.name)
    except OSError:
        pass


def test_multi_repo_resolution_and_isolation(dual_repos):
    from packages.context.agent_context import invoke_context_request, resolve_project_id

    store, repo_a, repo_b, _env, _db = dual_repos
    assert resolve_project_id(str(repo_a), memory_store=store) == "xagent-a"
    assert resolve_project_id(str(repo_b), memory_store=store) == "xagent-b"
    assert resolve_project_id(str(repo_a / "src" / "nested"), memory_store=store) == "xagent-a"

    ca = invoke_context_request(
        "xagent-a",
        "Where is AlphaContextMarker?",
        memory_store=store,
    )
    cb = invoke_context_request(
        "xagent-b",
        "Where is BetaContextMarker?",
        memory_store=store,
    )
    ba, bb = _blob(ca), _blob(cb)
    assert "AlphaContextMarker" in ba and ALPHA in ba
    assert "BetaContextMarker" in bb and BETA in bb
    assert BETA not in ba and "BetaContextMarker" not in ba
    assert ALPHA not in bb and "AlphaContextMarker" not in bb


def test_mcp_and_hook_emit_isolated_markers(dual_repos):
    from services.mcp_server.server import OverhaustMCPServer

    store, repo_a, repo_b, env, _db = dual_repos
    mcp = OverhaustMCPServer(memory_store=store)
    ta = json.loads(mcp._tool_get_relevant_context({
        "root_path": str(repo_a),
        "prompt": "Find AlphaContextMarker",
    }).content[0].text)
    tb = json.loads(mcp._tool_get_relevant_context({
        "root_path": str(repo_b),
        "prompt": "Find BetaContextMarker",
    }).content[0].text)
    assert ta["project_id"] == "xagent-a"
    assert tb["project_id"] == "xagent-b"
    assert "AlphaContextMarker" in json.dumps(ta)
    assert "BetaContextMarker" in json.dumps(tb)
    assert "BetaContextMarker" not in json.dumps(ta)
    assert "AlphaContextMarker" not in json.dumps(tb)

    ha = _run_hook(repo_a, "Explain AlphaContextMarker", env)
    hb = _run_hook(repo_b, "Explain BetaContextMarker", env)
    hn = _run_hook(repo_a / "src" / "nested", "Explain AlphaContextMarker", env)
    assert "<!-- overhaust-context -->" in ha
    assert "AlphaContextMarker" in ha and "BetaContextMarker" not in ha
    assert "BetaContextMarker" in hb and "AlphaContextMarker" not in hb
    assert "AlphaContextMarker" in hn and "BetaContextMarker" not in hn


def test_explicit_reindex_freshness_for_marker_token(dual_repos):
    from packages.context.agent_context import invoke_context_request
    from services.ingestion.project_lifecycle import ensure_project_indexed

    store, repo_a, _repo_b, env, _db = dual_repos
    marker = repo_a / "src" / "alpha_marker.py"
    marker.write_text(
        f'UNIQUE = "{ALPHA_NEW}"\n\n'
        f"class AlphaContextMarker:\n"
        f"    token = UNIQUE\n"
    )
    ensure_project_indexed("xagent-a", str(repo_a), memory_store=store)
    resp = invoke_context_request(
        "xagent-a",
        "AlphaContextMarker UNIQUE token",
        memory_store=store,
    )
    blob = _blob(resp)
    assert ALPHA_NEW in blob
    assert ALPHA not in blob

    additional = _run_hook(repo_a, "AlphaContextMarker UNIQUE token", env)
    assert ALPHA_NEW in additional
    assert ALPHA not in additional
