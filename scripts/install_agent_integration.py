#!/usr/bin/env python3
"""
Install OverHaust agent hook integrations.

Examples:
  python3 scripts/install_agent_integration.py --agent codex
  python3 scripts/install_agent_integration.py --agent claude --project-local
  python3 scripts/install_agent_integration.py --agent cursor
  python3 scripts/install_agent_integration.py --agent all --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.integrations.install import hook_script_path, install_agent  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Install OverHaust agent integrations")
    parser.add_argument(
        "--agent",
        required=True,
        choices=["codex", "claude", "cursor", "continue", "cline", "all"],
        help="Target agent integration",
    )
    parser.add_argument("--python", default="python3", help="Python executable for hook command")
    parser.add_argument("--dry-run", action="store_true", help="Print paths only, do not write")
    args = parser.parse_args()

    script = hook_script_path(ROOT)
    if not script.exists():
        print(f"ERROR: hook script missing: {script}", file=sys.stderr)
        return 1

    paths = install_agent(
        args.agent,
        root=ROOT,
        python=args.python,
        dry_run=args.dry_run,
    )

    action = "Would write" if args.dry_run else "Wrote"
    for path in paths:
        print(f"{action}: {path}")

    print(f"\nHook script: {script}")
    if args.agent in ("codex", "all"):
        print("\nCodex: UserPromptSubmit hook requires hook-definition trust.")
        print("  CLI:     trust via `/hooks`")
        print("  Desktop: Settings → Hooks → Trust OverHaust UserPromptSubmit")
        print("Next steps:")
        print("  1. Index the target repo (e.g. python3 scripts/ensure_overhaust_indexed.py)")
        print("  2. Trust the hook for your runtime (CLI /hooks or Desktop Settings)")
        print("  3. python3 scripts/verify_codex_integration.py --smoke")
        print("  4. python3 scripts/overhaust_doctor.py --adapter codex")
        print(
            "If OverHaust fails, the hook returns empty additionalContext "
            "and Codex continues normally."
        )
    if args.agent in ("claude", "all"):
        print(
            "\nClaude Code: UserPromptSubmit hook merges into ~/.claude/settings.json "
            "without overwriting unrelated hooks (e.g. PreToolUse)."
        )
        print("Next steps:")
        print("  1. Index the target repo (e.g. python3 scripts/ensure_overhaust_indexed.py)")
        print("  2. python3 scripts/verify_claude_integration.py --smoke")
        print("  3. Start Claude Code in the indexed repository")
        print(
            "If OverHaust fails, the hook returns empty additionalContext "
            "and Claude Code continues normally."
        )
    if args.agent in ("cursor", "all"):
        print(
            "\nCursor: uses alwaysApply rule + MCP get_relevant_context. "
            "beforeSubmitPrompt is not a model-injection path. "
            "See docs/MCP_AGENT_INTEGRATION.md."
        )
        print("Next steps:")
        print("  1. python3 scripts/ensure_overhaust_indexed.py")
        print("  2. Reload MCP servers in Cursor (or restart Cursor)")
        print("  3. python3 scripts/verify_cursor_integration.py")
        print(
            "If OverHaust MCP is unavailable, the alwaysApply rule tells the "
            "Agent to continue with normal repo tools."
        )
    if args.agent in ("continue", "all"):
        print(
            "\nContinue: project `.continue/mcpServers/overhaust.yaml` + "
            "`.continue/rules/overhaust-context.md` (alwaysApply). "
            "Uses the same MCP get_relevant_context seam as Cursor."
        )
        print("Next steps:")
        print("  1. python3 scripts/ensure_overhaust_indexed.py")
        print("  2. Reload Continue / reopen the workspace")
        print("  3. python3 scripts/overhaust_doctor.py --adapter continue")
        print(
            "If OverHaust MCP is unavailable, the alwaysApply rule tells "
            "Continue to keep using normal tools."
        )
    if args.agent in ("cline", "all"):
        print(
            "\nCline: `.clinerules/hooks/UserPromptSubmit` → "
            "contextModification (NOT Codex additionalContext)."
        )
        print("Next steps:")
        print("  1. python3 scripts/ensure_overhaust_indexed.py")
        print("  2. Enable Hooks in Cline Feature Settings")
        print("  3. python3 scripts/overhaust_doctor.py --adapter cline")
        print(
            "Delivery of contextModification to the model depends on Cline "
            "version (see Cline #13554). Doctor does not prove live consumption."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
