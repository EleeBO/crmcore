#!/usr/bin/env python3
"""Check docs update - PreToolUse hook that reminds to update docs/specs when committing.

Runs before git commit commands. Checks staged files against documentation
mapping rules and prints reminders if specs or docs may need updating.
Non-blocking (always exits 0).
"""

from __future__ import annotations

import json
import subprocess
import sys

YELLOW = "\033[0;33m"
CYAN = "\033[0;36m"
NC = "\033[0m"

# Mapping: if files under a source path are staged, the corresponding doc/section may need updating.
DOC_UPDATE_RULES: dict[str, dict[str, str]] = {
    # Implementation code -> might need spec update
    "src/": {
        "doc": "specs/",
        "section": "Living Specs",
        "reason": "Implementation code changed — check if spec needs updating",
    },
    # API changes -> spec behavior section
    "src/api/": {
        "doc": "specs/",
        "section": "Behavior",
        "reason": "API endpoint changed — update spec Behavior section",
    },
    # Database changes -> spec components
    "src/models/": {
        "doc": "specs/",
        "section": "Components",
        "reason": "Database model changed — update spec Components",
    },
    # New commands -> CLAUDE.md
    ".claude/commands/": {
        "doc": "CLAUDE.md",
        "section": "Workflow",
        "reason": "Command added/changed — update CLAUDE.md workflow",
    },
    # New agents -> CLAUDE.md
    ".claude/agents/": {
        "doc": "CLAUDE.md",
        "section": "Agents",
        "reason": "Agent added/changed — update CLAUDE.md agents table",
    },
    # New hooks -> CLAUDE.md
    ".claude/hooks/": {
        "doc": "CLAUDE.md",
        "section": "Hooks",
        "reason": "Hook added/changed — update CLAUDE.md hooks",
    },
    # Test changes -> might need spec acceptance criteria update
    "tests/": {
        "doc": "specs/",
        "section": "Acceptance Criteria",
        "reason": "Tests changed — verify spec acceptance criteria still match",
    },
}


def get_staged_files() -> list[str]:
    """Get list of staged files from git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


def check_docs_need_update(staged_files: list[str]) -> list[dict[str, str]]:
    """Check if any staged files map to documentation that should be updated.

    Returns a list of reminders (doc, section, reason) for files that
    match DOC_UPDATE_RULES but whose corresponding docs are NOT in the
    staged set.
    """
    reminders: list[dict[str, str]] = []
    seen_docs: set[str] = set()

    for staged_file in staged_files:
        for path_prefix, rule in DOC_UPDATE_RULES.items():
            if staged_file.startswith(path_prefix):
                doc_target = rule["doc"]

                # Check if the doc is already being committed
                doc_already_staged = any(sf.startswith(doc_target) or sf == doc_target for sf in staged_files)

                if not doc_already_staged:
                    # Deduplicate by (doc, section)
                    key = f"{doc_target}:{rule['section']}"
                    if key not in seen_docs:
                        seen_docs.add(key)
                        reminders.append(rule)

    return reminders


def is_git_commit_command(command: str) -> bool:
    """Check if the command is a git commit."""
    # Match various forms: git commit, git commit -m, etc.
    cmd = command.strip()
    return cmd.startswith("git commit") or cmd.startswith("git -c") and "commit" in cmd


def main() -> int:
    """Main entry point for the PreToolUse hook."""
    # Read hook input from stdin
    try:
        hook_data = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0

    # Extract the command from tool_input
    tool_input = hook_data.get("tool_input", {})
    command = tool_input.get("command", "")

    if not command:
        return 0

    # Only trigger on git commit commands
    if not is_git_commit_command(command):
        return 0

    # Get staged files
    staged_files = get_staged_files()
    if not staged_files:
        return 0

    # Check if docs need updating
    reminders = check_docs_need_update(staged_files)

    if reminders:
        print(f"\n{CYAN}Docs Update Reminder{NC}", file=sys.stderr)
        print(f"{CYAN}{'─' * 40}{NC}", file=sys.stderr)
        for reminder in reminders:
            print(f"  {YELLOW}{reminder['reason']}{NC}", file=sys.stderr)
            print(f"    Update: {reminder['doc']} → {reminder['section']}", file=sys.stderr)
        print(f"{CYAN}{'─' * 40}{NC}\n", file=sys.stderr)

    # Always non-blocking
    return 0


if __name__ == "__main__":
    sys.exit(main())
