#!/usr/bin/env python3
"""Environment checker - verifies all required tools are installed."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
RED = "\033[0;31m"
CYAN = "\033[0;36m"
NC = "\033[0m"

_PROJECT_HASH = hashlib.md5(
    os.path.dirname(os.path.abspath(__file__)).encode(),
    usedforsecurity=False,
).hexdigest()[:8]

# Cache file to avoid checking every time
CACHE_FILE = Path(tempfile.gettempdir()) / f".claude_env_checked_{_PROJECT_HASH}"
CACHE_DURATION = 3600  # 1 hour


@dataclass
class Tool:
    name: str
    command: str
    install_hint: str
    required: bool = True
    version_flag: str = "--version"


# Required tools for CodeRush2
TOOLS = [
    # Python ecosystem
    Tool("python3", "python3", "Install Python 3.11+: https://python.org"),
    Tool("uv", "uv", "curl -LsSf https://astral.sh/uv/install.sh | sh"),
    Tool("ruff", "ruff", "uv tool install ruff", required=False),
    Tool("mypy", "mypy", "uv tool install mypy", required=False),
    # Node.js ecosystem
    Tool("node", "node", "Install Node.js: https://nodejs.org"),
    Tool("npm", "npm", "Comes with Node.js"),
    # Agent Browser
    Tool(
        "agent-browser",
        "agent-browser",
        "npm install -g agent-browser && agent-browser install",
        required=False,
    ),
    # Git
    Tool("git", "git", "Install Git: https://git-scm.com"),
]


def check_tool(tool: Tool) -> tuple[bool, str]:
    """Check if a tool is installed and get its version."""
    binary = shutil.which(tool.command)
    if not binary:
        return False, ""

    try:
        result = subprocess.run(
            [binary, tool.version_flag],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version = result.stdout.strip().split("\n")[0][:50]
        return True, version
    except Exception:
        return True, "installed"


def check_python_packages() -> list[tuple[str, bool]]:
    """Check if Python dev packages are available."""
    packages = ["pytest", "structlog"]
    results = []

    for pkg in packages:
        try:
            result = subprocess.run(
                ["python3", "-c", f"import {pkg}"],
                capture_output=True,
                timeout=5,
            )
            results.append((pkg, result.returncode == 0))
        except Exception:
            results.append((pkg, False))

    return results


def should_check() -> bool:
    """Check if we should run the environment check."""
    if not CACHE_FILE.exists():
        return True

    import time

    mtime = CACHE_FILE.stat().st_mtime
    return (time.time() - mtime) > CACHE_DURATION


def mark_checked() -> None:
    """Mark that we've completed the check."""
    CACHE_FILE.touch()


def run_environment_check(force: bool = False) -> int:
    """Run environment check and return exit code.

    Returns:
        0: All required tools present
        1: Only optional tools missing (warning, non-blocking)
        2: Required tools missing (blocking)
    """
    if not force and not should_check():
        return 0

    print("", file=sys.stderr)
    print(f"{CYAN}Checking development environment...{NC}", file=sys.stderr)
    print("", file=sys.stderr)

    missing_required = []
    missing_optional = []
    installed = []

    for tool in TOOLS:
        found, version = check_tool(tool)
        if found:
            installed.append((tool.name, version))
        elif tool.required:
            missing_required.append(tool)
        else:
            missing_optional.append(tool)

    # Show installed tools
    if installed:
        print(f"{GREEN}Installed:{NC}", file=sys.stderr)
        for name, version in installed:
            print(f"  {GREEN}✓{NC} {name}: {version}", file=sys.stderr)
        print("", file=sys.stderr)

    # Show missing optional tools
    if missing_optional:
        print(f"{YELLOW}Optional (not installed):{NC}", file=sys.stderr)
        for tool in missing_optional:
            print(f"  {YELLOW}○{NC} {tool.name}", file=sys.stderr)
            print(f"    Install: {tool.install_hint}", file=sys.stderr)
        print("", file=sys.stderr)

    # Show missing required tools
    if missing_required:
        print(f"{RED}Required (missing):{NC}", file=sys.stderr)
        for tool in missing_required:
            print(f"  {RED}✗{NC} {tool.name}", file=sys.stderr)
            print(f"    Install: {tool.install_hint}", file=sys.stderr)
        print("", file=sys.stderr)
        print(f"{RED}Please install missing required tools before proceeding.{NC}", file=sys.stderr)
        return 2

    mark_checked()

    if not missing_optional:
        print(f"{GREEN}All tools installed and ready!{NC}", file=sys.stderr)
    else:
        print(
            f"{GREEN}Required tools ready. Optional tools can be installed later.{NC}",
            file=sys.stderr,
        )
        return 1

    return 0


def main() -> int:
    """Main entry point."""
    force = "--force" in sys.argv

    # Consume stdin if called as a hook (JSON on stdin), but still run the check.
    # The hook context is not needed; we just need to drain stdin so it doesn't block.
    try:
        json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        pass

    return run_environment_check(force=force)


if __name__ == "__main__":
    sys.exit(main())
