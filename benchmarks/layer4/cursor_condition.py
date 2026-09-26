"""
Cursor condition toggle, isolation, and cli-config guard.

Baseline and OverHaust use the same cursor-agent argv. The only intended
difference is a project-level `.cursor/hooks.json` `sessionStart` hook on the
OverHaust workspace copy. Baseline has no hooks file. Neither workspace gets
OverHaust `.cursor/rules` or MCP config. The harness checks that on disk.

`--model` rewrites `~/.cursor/cli-config.json` model keys. The guard snapshots
those keys and the other files the CLI rewrites, and restores them after the
run, including when a session fails.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from benchmarks.layer4.cursor_parse import OVERHAUST_MCP_TOOL_NAMES, TELEMETRY_CATALOG
from benchmarks.repro import capture_repository_snapshot, restore_repository_snapshot


INTEGRATION_NONE = "none"
INTEGRATION_HOOK = "cursor_session_start_hook"
ISOLATION_HOME = "isolated-home"
ISOLATION_MCP = "mcp-toggle"
ISOLATIONS = (ISOLATION_HOME, ISOLATION_MCP)
CURSOR_DEFAULT_MODEL = "gpt-5.5-medium"
TARGET_CURSOR_AGENT_VERSION = "2026.09.26-dd393fe"
PROMPT_CACHE_POLICY = (
    "Provider-side prompt caching was not independently controlled; "
    "cached-input usage was recorded and retained as part of the measured "
    "session usage."
)
HOOK_SCRIPT_NAME = "overhaust_cursor_session_start_hook.py"

CLI_CONFIG_MODEL_KEYS = (
    "model",
    "selectedModel",
    "modelParameters",
    "hasChangedDefaultModel",
    "modelSelectionHistory",
)
REWRITTEN_CURSOR_FILES = (
    "cli-config.json",
    "agent-cli-state.json",
    "statsig-cache.json",
)
MCP_SNAPSHOT_FILES = (
    "mcp.json",
    "cli-config.json",
)

CURSOR_PERMISSIONS = {
    "print": True,
    "output_format": "stream-json",
    "trust": True,
    "force": False,
    "sandbox": None,
    "approve_mcps": False,
    "stdin": "/dev/null",
}


@dataclass
class HookLayout:
    ok: bool
    hooks_present: bool
    events: List[str]
    command: Optional[str]
    problems: List[str] = field(default_factory=list)
    extra_paths: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "hooks_present": self.hooks_present,
            "events": list(self.events),
            "command": self.command,
            "problems": list(self.problems),
            "extra_paths": list(self.extra_paths),
        }


@dataclass
class PreparedWorkspace:
    root: Path
    restore_verified: bool
    fixture_hash: str
    pre_agent_hash: Optional[str]
    layout: HookLayout
    hook_command: Optional[str]
    integration_path: str
    detail: Optional[str] = None


def cursor_hook_command(repo_root: Path, python: str) -> str:
    script = repo_root / "scripts" / "integrations" / HOOK_SCRIPT_NAME
    return f'{python} "{script}"'


def build_cursor_command(*, binary: str, prompt: str, model: str) -> List[str]:
    """Argv checked against cursor-agent 2026.09.26. The prompt is one argument."""
    if not model:
        raise ValueError("cursor-agent requires an explicit --model")
    if prompt == "-" or prompt.startswith("-"):
        raise ValueError("Refusing a prompt cursor-agent would treat as a flag.")
    return [
        binary,
        "-p",
        "--output-format", "stream-json",
        "--trust",
        "--model", model,
        prompt,
    ]


def write_prompt_file(
    path: Path,
    *,
    harness_session_id: str,
    workspace_root: Path,
    prompt: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "harness_session_id": harness_session_id,
        "workspace_root": str(workspace_root),
        "prompt": prompt,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def build_cursor_env(
    base: Dict[str, str],
    *,
    db_path: str,
    project_id: str,
    hook_debug_path: Path,
    prompt_file: Optional[Path],
    harness_session_id: str,
    home: Optional[Path],
) -> Dict[str, str]:
    """
    Child environment. The task prompt is not copied into an env var.

    `OVERHAUST_CURSOR_PROMPT_FILE` is set only for the OverHaust condition.
    `isolated-home` sets HOME to an empty per-session directory. Credentials
    are not copied into that directory. `CURSOR_API_KEY` is left in the
    environment when the caller already set it.
    """
    env = dict(base)
    env["OVERHAUST_DB_PATH"] = db_path
    env["OVERHAUST_PROJECT_ID"] = project_id
    env["OVERHAUST_INTEGRATION_DEBUG"] = "1"
    env["OVERHAUST_INTEGRATION_DEBUG_FILE"] = str(hook_debug_path)
    env.pop("OVERHAUST_CURSOR_PROMPT_FILE", None)
    env.pop("OVERHAUST_CURSOR_SESSION_ID", None)
    if prompt_file is not None:
        env["OVERHAUST_CURSOR_PROMPT_FILE"] = str(prompt_file)
        env["OVERHAUST_CURSOR_SESSION_ID"] = harness_session_id
    if home is not None:
        env["HOME"] = str(home)
    return env


def _cursor_tree(root: Path) -> List[str]:
    cursor = root / ".cursor"
    if not cursor.exists():
        return []
    return sorted(
        path.relative_to(root).as_posix()
        for path in cursor.rglob("*")
        if path.is_file()
    )


def _hook_commands(data: Dict[str, Any]) -> List[str]:
    commands: List[str] = []
    groups = (data.get("hooks") or {}).get("sessionStart") or []
    if not isinstance(groups, list):
        return commands
    for group in groups:
        if isinstance(group, dict) and group.get("command"):
            commands.append(str(group["command"]))
        elif isinstance(group, dict):
            nested = group.get("hooks")
            if isinstance(nested, list):
                for entry in nested:
                    if isinstance(entry, dict) and entry.get("command"):
                        commands.append(str(entry["command"]))
    return commands


def verify_hook_layout(root: Path, *, condition: str, hook_command: str) -> HookLayout:
    """Read the workspace. Do not assume the condition was applied."""
    problems: List[str] = []
    files = _cursor_tree(root)
    hooks_path = root / ".cursor" / "hooks.json"
    rules = root / ".cursor" / "rules"
    mcp = root / ".cursor" / "mcp.json"
    if rules.exists():
        problems.append("workspace contains .cursor/rules")
    if mcp.exists():
        problems.append("workspace contains .cursor/mcp.json")
    events: List[str] = []
    command: Optional[str] = None
    if condition == "baseline":
        if hooks_path.exists():
            problems.append("baseline workspace contains .cursor/hooks.json")
        if files:
            problems.append("baseline workspace contains .cursor files: " + ", ".join(files))
    elif condition == "overhaust":
        if not hooks_path.is_file():
            problems.append("overhaust workspace is missing .cursor/hooks.json")
        else:
            try:
                data = json.loads(hooks_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = None
                problems.append("overhaust hooks.json is not JSON")
            if isinstance(data, dict):
                hook_map = data.get("hooks") or {}
                if isinstance(hook_map, dict):
                    events = sorted(str(name) for name in hook_map.keys())
                if events != ["sessionStart"]:
                    problems.append(
                        "overhaust hooks.json events must be only sessionStart, "
                        f"got {events}"
                    )
                commands = _hook_commands(data)
                command = commands[0] if commands else None
                if command != hook_command:
                    problems.append("sessionStart command does not match the harness hook")
                if command and "overhaust_user_prompt_hook.py" in command:
                    problems.append("sessionStart points at the Codex UserPromptSubmit hook")
                if command and HOOK_SCRIPT_NAME not in command:
                    problems.append("sessionStart command is not the Cursor sessionStart hook")
        unexpected = [path for path in files if path != ".cursor/hooks.json"]
        if unexpected:
            problems.append("overhaust workspace has extra .cursor files: " + ", ".join(unexpected))
    else:
        problems.append(f"unknown condition {condition}")
    return HookLayout(
        ok=not problems,
        hooks_present=hooks_path.is_file(),
        events=events,
        command=command,
        problems=problems,
        extra_paths=files,
    )


def prepare_session_workspace(
    canonical: Path,
    canonical_snapshot: Dict[str, Any],
    dest: Path,
    *,
    condition: str,
    hook_command: str,
) -> PreparedWorkspace:
    """
    Restore the shared fixture, copy it, then install hooks only for OverHaust.

    A fixture that already contains `.cursor` is rejected. The copy is verified
    before the agent starts.
    """
    fixture_hash = str(canonical_snapshot.get("tree_hash") or "")
    restore = restore_repository_snapshot(str(canonical), canonical_snapshot)
    current = capture_repository_snapshot(str(canonical))
    current_hash = str(current.get("tree_hash") or "")
    if not restore.get("verified") or current_hash != fixture_hash:
        layout = HookLayout(False, False, [], None, ["snapshot restore was not verified"])
        return PreparedWorkspace(
            root=dest,
            restore_verified=False,
            fixture_hash=fixture_hash,
            pre_agent_hash=None,
            layout=layout,
            hook_command=None,
            integration_path=INTEGRATION_NONE if condition == "baseline" else INTEGRATION_HOOK,
            detail=restore.get("detail") or "snapshot restore was not verified",
        )
    if _cursor_tree(canonical):
        layout = HookLayout(
            False,
            False,
            [],
            None,
            ["fixture contains .cursor config and cannot be used as a Cursor workspace"],
        )
        return PreparedWorkspace(
            root=dest,
            restore_verified=True,
            fixture_hash=fixture_hash,
            pre_agent_hash=None,
            layout=layout,
            hook_command=None,
            integration_path=INTEGRATION_NONE if condition == "baseline" else INTEGRATION_HOOK,
            detail="fixture contains .cursor config",
        )
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(canonical, dest)
    if condition == "overhaust":
        cursor_dir = dest / ".cursor"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        hooks = {
            "version": 1,
            "description": (
                "Layer 4 OverHaust condition. sessionStart calls "
                "invoke_context_request. No MCP server is configured here."
            ),
            "hooks": {
                "sessionStart": [
                    {"command": hook_command},
                ],
            },
        }
        (cursor_dir / "hooks.json").write_text(
            json.dumps(hooks, indent=2) + "\n",
            encoding="utf-8",
        )
        integration = INTEGRATION_HOOK
        installed = hook_command
    elif condition == "baseline":
        integration = INTEGRATION_NONE
        installed = None
    else:
        raise ValueError(f"invalid condition: {condition}")
    layout = verify_hook_layout(dest, condition=condition, hook_command=hook_command)
    pre_agent = capture_repository_snapshot(str(dest))
    return PreparedWorkspace(
        root=dest,
        restore_verified=True,
        fixture_hash=fixture_hash,
        pre_agent_hash=str(pre_agent.get("tree_hash") or "") or None,
        layout=layout,
        hook_command=installed,
        integration_path=integration,
        detail=None if layout.ok else "; ".join(layout.problems),
    )


def _file_sha256(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


class CursorStateGuard:
    """Snapshot and restore the Cursor CLI files a headless run rewrites."""

    def __init__(self, state_home: Path) -> None:
        self.state_home = state_home
        self.cursor_dir = state_home / ".cursor"
        self._blobs: Dict[str, Optional[bytes]] = {}
        self._model_keys: Dict[str, Any] = {}
        self._missing_keys: List[str] = []

    def snapshot(self) -> Dict[str, Any]:
        self.cursor_dir.mkdir(parents=True, exist_ok=True)
        for name in REWRITTEN_CURSOR_FILES:
            path = self.cursor_dir / name
            self._blobs[name] = path.read_bytes() if path.is_file() else None
        self._model_keys, self._missing_keys = _read_model_keys(self.cursor_dir / "cli-config.json")
        return {
            "model_keys": self._model_keys,
            "absent_model_keys": list(self._missing_keys),
            "files": {name: _file_sha256(self.cursor_dir / name) for name in REWRITTEN_CURSOR_FILES},
        }

    def restore(self) -> Dict[str, Any]:
        """Put the snapshotted files back, then check the model keys."""
        self.cursor_dir.mkdir(parents=True, exist_ok=True)
        for name, blob in self._blobs.items():
            path = self.cursor_dir / name
            if blob is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_bytes(blob)
        after_keys, after_missing = _read_model_keys(self.cursor_dir / "cli-config.json")
        keys_ok = after_keys == self._model_keys and set(after_missing) == set(self._missing_keys)
        files_ok = all(
            _file_sha256(self.cursor_dir / name) == (
                hashlib.sha256(blob).hexdigest() if blob is not None else None
            )
            for name, blob in self._blobs.items()
        )
        return {
            "model_keys_restored": keys_ok,
            "files_restored": files_ok,
            "model_keys": after_keys,
            "absent_model_keys": after_missing,
        }


def _read_model_keys(path: Path) -> tuple[Dict[str, Any], List[str]]:
    if not path.is_file():
        return {}, list(CLI_CONFIG_MODEL_KEYS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, list(CLI_CONFIG_MODEL_KEYS)
    if not isinstance(data, dict):
        return {}, list(CLI_CONFIG_MODEL_KEYS)
    present = {key: data[key] for key in CLI_CONFIG_MODEL_KEYS if key in data}
    missing = [key for key in CLI_CONFIG_MODEL_KEYS if key not in data]
    return present, missing


class McpToggleGuard:
    """
    Disable the `overhaust` MCP server for both conditions, then restore.

    The snapshot is the bytes of the user Cursor config files plus the
    `mcp list` text from before the disable. Restore writes those bytes
    back and checks the hash. A second `mcp list` is compared when the
    runner can execute it.
    """

    def __init__(
        self,
        state_home: Path,
        binary: str,
        runner: Callable[..., Any],
        env: Dict[str, str],
    ) -> None:
        self.state_home = state_home
        self.binary = binary
        self.runner = runner
        self.env = env
        self.cursor_dir = state_home / ".cursor"
        self._blobs: Dict[str, Optional[bytes]] = {}
        self._list_before: Optional[str] = None

    def snapshot(self) -> Dict[str, Any]:
        self.cursor_dir.mkdir(parents=True, exist_ok=True)
        for name in MCP_SNAPSHOT_FILES:
            path = self.cursor_dir / name
            self._blobs[name] = path.read_bytes() if path.is_file() else None
        listed = self.runner([self.binary, "mcp", "list"], dict(self.env), str(self.state_home), 20)
        self._list_before = (listed.stdout or "") + (listed.stderr or "")
        return {
            "files": {name: blob is not None for name, blob in self._blobs.items()},
            "list_exit_code": listed.returncode,
            "overhaust_listed": _mentions_overhaust(self._list_before),
        }

    def disable(self) -> Dict[str, Any]:
        result = self.runner(
            [self.binary, "mcp", "disable", "overhaust"],
            dict(self.env),
            str(self.state_home),
            20,
        )
        return {
            "exit_code": result.returncode,
            "timed_out": result.timed_out,
            "stderr": (result.stderr or "")[:500],
        }

    def overhaust_still_listed(self) -> bool:
        listed = self.runner(
            [self.binary, "mcp", "list"],
            dict(self.env),
            str(self.state_home),
            20,
        )
        text = (listed.stdout or "") + (listed.stderr or "")
        if listed.returncode not in (0,):
            return True
        return _mentions_overhaust(text)

    def restore(self) -> Dict[str, Any]:
        for name, blob in self._blobs.items():
            path = self.cursor_dir / name
            if blob is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_bytes(blob)
        hashes_ok = True
        for name, blob in self._blobs.items():
            path = self.cursor_dir / name
            if blob is None:
                hashes_ok = hashes_ok and not path.exists()
            else:
                hashes_ok = hashes_ok and path.is_file() and path.read_bytes() == blob
        listed = self.runner([self.binary, "mcp", "list"], dict(self.env), str(self.state_home), 20)
        after = (listed.stdout or "") + (listed.stderr or "")
        list_ok = listed.returncode == 0 and (
            _mentions_overhaust(after) == _mentions_overhaust(self._list_before or "")
        )
        return {
            "files_restored": hashes_ok,
            "list_matches_snapshot": list_ok,
            "restored": hashes_ok and list_ok,
        }


def _mentions_overhaust(text: str) -> bool:
    lowered = (text or "").lower()
    if "overhaust" in lowered:
        return True
    return any(name in lowered for name in OVERHAUST_MCP_TOOL_NAMES)


def redact_cursor(text: str, env: Dict[str, str]) -> str:
    redacted = text or ""
    for key in ("CURSOR_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY"):
        secret = (env.get(key) or "").strip()
        if len(secret) >= 8:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted


def telemetry_catalog_lines() -> List[str]:
    lines = []
    for item in TELEMETRY_CATALOG:
        lines.append(f"{item['field']}: {item['label']} — {item['detail']}")
    return lines
