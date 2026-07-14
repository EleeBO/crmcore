"""Python file checker hook - runs ruff on edited Python files."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

SKIP_DIRS = {
    "node_modules", ".venv", "venv", "__pycache__", ".git",
    "dist", "build", ".ruff_cache", "migrations", "generated",
}


def should_check(file_path: str) -> bool:
    """Check if file is a non-test Python file worth checking."""
    path = Path(file_path)

    if path.suffix != ".py":
        return False

    if any(part in SKIP_DIRS for part in path.parts):
        return False

    if "test" in path.name or "spec" in path.name:
        return False

    return True


def auto_format(file_path: Path) -> None:
    """Auto-format file with ruff before checks."""
    ruff_bin = shutil.which("ruff")
    if not ruff_bin:
        return

    try:
        subprocess.run(
            [ruff_bin, "check", "--select", "I,RUF022", "--fix", str(file_path)],
            capture_output=True,
            check=False,
        )
        subprocess.run(
            [ruff_bin, "format", str(file_path)],
            capture_output=True,
            check=False,
        )
    except Exception:
        pass


def run_ruff_check(file_path: Path) -> tuple[bool, str]:
    """Run ruff check."""
    ruff_bin = shutil.which("ruff")
    if not ruff_bin:
        return False, ""

    try:
        result = subprocess.run(
            [ruff_bin, "check", str(file_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout + result.stderr
        has_issues = bool(output.strip()) and "All checks passed" not in output
        return has_issues, output
    except Exception:
        return False, ""


def main() -> int:
    """Main entry point."""
    try:
        hook_data = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0

    tool_input = hook_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path or not should_check(file_path):
        return 0

    if not shutil.which("ruff"):
        return 0

    path = Path(file_path)
    auto_format(path)

    has_issues, output = run_ruff_check(path)

    if has_issues:
        lines = output.splitlines()
        error_lines = [l for l in lines if l.strip() and not l.startswith("Found")]
        error_count = len(error_lines)
        plural = "issue" if error_count == 1 else "issues"

        print("", file=sys.stderr)
        print(f"{RED}Ruff: {error_count} {plural} in {path.name}{NC}", file=sys.stderr)
        for line in error_lines[:10]:
            print(f"  {line}", file=sys.stderr)
        print("", file=sys.stderr)
        return 2

    print(f"{GREEN}✅ Ruff: OK{NC}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
