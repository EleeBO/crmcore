#!/usr/bin/env python3
"""Version bump reminder — PreToolUse hook for git commit.

Fires before git commit commands. Checks if extension files are staged
but extension/manifest.json version has NOT been bumped. Reminds to
bump the version before committing.

Non-blocking (exit 1 = warning) so it doesn't prevent commits, but
clearly reminds the developer.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

YELLOW = "\033[0;33m"
NC = "\033[0m"

# Paths under which changes require a version bump
EXTENSION_PATHS = (
    "extension/src/",
    "extension/public/",
)

MANIFEST_PATH = "extension/manifest.json"


def _git() -> str | None:
    """Resolve full path to git binary."""
    return shutil.which("git")


def get_staged_files() -> list[str]:
    """Get list of staged files from git."""
    git = _git()
    if not git:
        return []
    try:
        result = subprocess.run(
            [git, "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


def manifest_version_changed() -> bool:
    """Check if manifest.json version field is in the staged diff."""
    git = _git()
    if not git:
        return False
    try:
        result = subprocess.run(
            [git, "diff", "--cached", "-U0", "--", MANIFEST_PATH],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False
        for line in result.stdout.splitlines():
            if line.startswith("+") and '"version"' in line:
                return True
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def is_git_commit_command(command: str) -> bool:
    """Check if the command is a git commit."""
    cmd = command.strip()
    return "git commit" in cmd


def main() -> int:
    """Main entry point for the PreToolUse hook."""
    try:
        hook_data = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0

    tool_name = hook_data.get("tool_name", "")
    if tool_name != "Bash":
        return 0

    tool_input = hook_data.get("tool_input", {})
    command = tool_input.get("command", "")

    if not command or not is_git_commit_command(command):
        return 0

    staged_files = get_staged_files()
    if not staged_files:
        return 0

    extension_files = [f for f in staged_files if any(f.startswith(p) for p in EXTENSION_PATHS)]

    if not extension_files:
        return 0

    if manifest_version_changed():
        return 0

    # Version NOT bumped — warn
    print("", file=sys.stderr)
    print(
        f"{YELLOW}Version Bump: extension files changed but "
        f"version in {MANIFEST_PATH} was not bumped{NC}",
        file=sys.stderr,
    )
    print(
        f'{YELLOW}    Bump "version" in {MANIFEST_PATH} before committing{NC}',
        file=sys.stderr,
    )
    changed = ", ".join(extension_files[:5])
    if len(extension_files) > 5:
        changed += f" (+{len(extension_files) - 5} more)"
    print(
        f"{YELLOW}    Changed: {changed}{NC}",
        file=sys.stderr,
    )
    print("", file=sys.stderr)

    # Inject context so the model knows to bump version
    print(
        "REMINDER: Extension source files were changed. "
        "Bump the version in extension/manifest.json "
        "before committing. "
        "Use semver: PATCH for fixes, MINOR for features, "
        "MAJOR for breaking changes."
    )

    return 1


if __name__ == "__main__":
    sys.exit(main())
