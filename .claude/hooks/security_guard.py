#!/usr/bin/env python3
"""Security guard hook - checks for common security issues in code."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

YELLOW = "\033[0;33m"
RED = "\033[0;31m"
NC = "\033[0m"

# Patterns that indicate potential security issues
SECURITY_PATTERNS = [
    # Hardcoded secrets
    (r'password\s*=\s*["\'][^"\']+["\']', "Potential hardcoded password"),
    (r'api[_-]?key\s*=\s*["\'][^"\']+["\']', "Potential hardcoded API key"),
    (r'secret\s*=\s*["\'][^"\']+["\']', "Potential hardcoded secret"),
    (r'token\s*=\s*["\'][^"\']+["\']', "Potential hardcoded token"),
    # SQL injection risks (f-string interpolation)
    (r'\.execute\s*\(\s*f["\']', "Potential SQL injection - use parameterized queries"),
]

# File extensions to check
CHECKED_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx"}

# Directories to skip
SKIP_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".git", "dist", "build"}


def should_check_file(file_path: str) -> bool:
    """Check if file should be scanned for security issues."""
    path = Path(file_path)

    if path.suffix not in CHECKED_EXTENSIONS:
        return False

    for part in path.parts:
        if part in SKIP_DIRS:
            return False

    if "test" in path.name.lower() or "spec" in path.name.lower():
        return False

    return True


def check_content(content: str) -> list[tuple[str, str, int]]:
    """Check content for security issues."""
    issues = []
    lines = content.split("\n")

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue

        for pattern, message in SECURITY_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                issues.append((message, line.strip()[:80], i))

    return issues


def run_security_guard() -> int:
    """Run security checks and return exit code."""
    try:
        hook_data = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0

    tool_name = hook_data.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        return 0

    tool_input = hook_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path or not should_check_file(file_path):
        return 0

    content = tool_input.get("content", "") or tool_input.get("new_string", "")
    if not content:
        return 0

    issues = check_content(content)

    if issues:
        print("", file=sys.stderr)
        print(f"{YELLOW}Security Warning in: {file_path}{NC}", file=sys.stderr)
        print("", file=sys.stderr)

        for message, line, line_num in issues:
            print(f"  Line {line_num}: {RED}{message}{NC}", file=sys.stderr)
            print(f"    {line}", file=sys.stderr)

        print("", file=sys.stderr)
        print(f"{YELLOW}Review these potential security issues.{NC}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(run_security_guard())
