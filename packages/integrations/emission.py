"""
Shared emission probe for hook-based host adapters.

Runs a hook script as a subprocess against a throwaway indexed fixture and
reports whether OverHaust context was emitted in the host's native format.
This proves *emission*, never model consumption.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, Optional

CONTEXT_MARKER = "<!-- overhaust-context -->"
_PROBE_PROMPT = "Where is the KOT generated?"


@dataclass
class EmissionProbeResult:
    ok: bool
    emitted: bool
    context_bytes: int = 0
    error: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def probe_hook_emission(
    hook_script: Path,
    build_stdin: Callable[[str, str], str],
    extract_context: Callable[[Dict[str, object]], Optional[str]],
    *,
    repo_root: Optional[Path] = None,
    timeout: int = 60,
) -> EmissionProbeResult:
    """
    build_stdin(prompt, cwd) -> host-native stdin JSON string
    extract_context(stdout_json) -> injected context text or None
    """
    if not hook_script.exists():
        return EmissionProbeResult(ok=False, emitted=False, error=f"missing hook script {hook_script}")

    from packages.memory.memory_store import MemoryStore
    from packages.retrieval.test_fixtures import make_kot_tree
    from services.ingestion.index_store import ProjectIndexStore

    tmpdir = tempfile.mkdtemp(prefix="overhaust-probe-")
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()
    try:
        root = Path(tmpdir)
        make_kot_tree(root)
        store = MemoryStore(db.name)
        store.add_project("overhaust-probe", "OverHaustProbe", "", str(root))
        ProjectIndexStore(store).sync_project("overhaust-probe", str(root))

        env = os.environ.copy()
        env["OVERHAUST_DB_PATH"] = db.name
        proc = subprocess.run(
            [sys.executable, str(hook_script)],
            input=build_stdin(_PROBE_PROMPT, str(root)),
            text=True,
            capture_output=True,
            cwd=str(repo_root or hook_script.resolve().parents[2]),
            env=env,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            return EmissionProbeResult(ok=False, emitted=False, error=proc.stderr[-500:])
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            return EmissionProbeResult(ok=False, emitted=False, error=f"invalid JSON: {exc}")
        context = extract_context(payload) or ""
        return EmissionProbeResult(
            ok=True,
            emitted=CONTEXT_MARKER in context,
            context_bytes=len(context.encode("utf-8")),
        )
    except Exception as exc:  # fail-open: probe failure is a finding, not a crash
        return EmissionProbeResult(ok=False, emitted=False, error=str(exc))
    finally:
        try:
            os.unlink(db.name)
        except OSError:
            pass


def user_prompt_submit_stdin(prompt: str, cwd: str) -> str:
    """Codex / Claude UserPromptSubmit stdin."""
    return json.dumps({"prompt": prompt, "cwd": cwd, "hook_event_name": "UserPromptSubmit"})


def additional_context_from(payload: Dict[str, object]) -> Optional[str]:
    """Codex / Claude hookSpecificOutput.additionalContext."""
    hso = payload.get("hookSpecificOutput")
    if isinstance(hso, dict):
        value = hso.get("additionalContext")
        return value if isinstance(value, str) else None
    return None
