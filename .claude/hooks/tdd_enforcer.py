#!/usr/bin/env python3
"""TDD enforcer - warns when implementation code is modified without failing tests."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

YELLOW = "\033[0;33m"
CYAN = "\033[0;36m"
NC = "\033[0m"

_PROJECT_HASH = hashlib.md5(
    os.path.dirname(os.path.abspath(__file__)).encode(),
    usedforsecurity=False,
).hexdigest()[:8]

OVERRIDE_TIMEOUT = 60
WARNED_CACHE_FILE = Path(tempfile.gettempdir()) / f".tdd_enforcer_warned_{_PROJECT_HASH}.json"

EXCLUDED_EXTENSIONS = [
    ".md",
    ".rst",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".lock",
    ".sum",
    ".env",
    ".env.example",
    ".sql",
]

EXCLUDED_DIRS = [
    "/cdk/",
    "/infra/",
    "/infrastructure/",
    "/terraform/",
    "/pulumi/",
    "/stacks/",
    "/cloudformation/",
    "/aws/",
    "/deploy/",
    "/migrations/",
    "/alembic/",
    "/generated/",
    "/proto/",
    "/__generated__/",
    "/dist/",
    "/build/",
    "/node_modules/",
    "/.venv/",
    "/venv/",
    "/__pycache__/",
]


def load_warned_cache() -> dict[str, float]:
    """Load the cache of recently warned files."""
    if not WARNED_CACHE_FILE.exists():
        return {}
    try:
        with WARNED_CACHE_FILE.open() as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_warned_cache(cache: dict[str, float]) -> None:
    """Save the cache of recently warned files."""
    try:
        with WARNED_CACHE_FILE.open("w") as f:
            json.dump(cache, f)
    except OSError:
        pass


def check_override(file_path: str) -> bool:
    """Check if this file was recently warned and should be allowed (override)."""
    cache = load_warned_cache()
    now = time.time()

    cache = {k: v for k, v in cache.items() if now - v < OVERRIDE_TIMEOUT}

    if file_path in cache:
        del cache[file_path]
        save_warned_cache(cache)
        return True

    return False


def record_warning(file_path: str) -> None:
    """Record that we warned about this file."""
    cache = load_warned_cache()
    now = time.time()

    cache = {k: v for k, v in cache.items() if now - v < OVERRIDE_TIMEOUT}
    cache[file_path] = now
    save_warned_cache(cache)


def should_skip(file_path: str) -> bool:
    """Check if file should be skipped based on extension or directory."""
    path = Path(file_path)

    if path.suffix in EXCLUDED_EXTENSIONS:
        return True

    if path.name in EXCLUDED_EXTENSIONS:
        return True

    return any(excluded_dir in file_path for excluded_dir in EXCLUDED_DIRS)


def is_test_file(file_path: str) -> bool:
    """Check if file is a test file."""
    path = Path(file_path)
    name = path.name

    if name.endswith(".py"):
        stem = path.stem
        if stem.startswith("test_") or stem.endswith("_test"):
            return True

    return name.endswith((".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx"))


def has_failing_python_tests(project_dir: str) -> bool:
    """Check if there are failing tests in pytest cache."""
    cache_file = Path(project_dir) / ".pytest_cache" / "v" / "cache" / "lastfailed"

    if not cache_file.exists():
        return False

    try:
        with cache_file.open() as f:
            lastfailed = json.load(f)
            return bool(lastfailed)
    except (json.JSONDecodeError, OSError):
        return False


def find_typescript_test_file(impl_path: str) -> Path | None:
    """Find the corresponding TypeScript test file if it exists.

    Returns:
        The Path to the test file if found, or None.
    """
    path = Path(impl_path)
    directory = path.parent

    if path.name.endswith(".tsx"):
        base_name = path.name[:-4]
        extensions = [".test.tsx", ".spec.tsx", ".test.ts", ".spec.ts"]
    elif path.name.endswith(".ts"):
        base_name = path.name[:-3]
        extensions = [".test.ts", ".spec.ts"]
    else:
        return None

    for ext in extensions:
        test_file = directory / f"{base_name}{ext}"
        if test_file.exists():
            return test_file

    return None


def has_typescript_test_file(impl_path: str) -> bool:
    """Check if corresponding TypeScript test file exists."""
    return find_typescript_test_file(impl_path) is not None


# Patterns that indicate real test cases in TypeScript/JavaScript test files
_TS_TEST_PATTERNS = re.compile(
    r"""
    (?:^|\s)                     # start of line or whitespace
    (?:
        it\s*\(                  # it('...
        | it\.(?:only|skip)\s*\( # it.only('... or it.skip('...
        | test\s*\(              # test('...
        | test\.(?:only|skip)\s*\( # test.only('... or test.skip('...
        | describe\s*\(          # describe('...
        | describe\.(?:only|skip)\s*\( # describe.only('... or describe.skip('...
    )
    """,
    re.VERBOSE,
)


def typescript_test_file_has_tests(test_file_path: Path) -> bool:
    """Check if a TypeScript test file is non-empty and contains test cases.

    Args:
        test_file_path: Path to the test file.

    Returns:
        True if the file has meaningful test content, False otherwise.
    """
    try:
        content = test_file_path.read_text(encoding="utf-8")
    except OSError:
        return False

    # Check if file is empty or effectively empty (only whitespace)
    stripped = content.strip()
    if not stripped:
        return False

    # Check for at least one test case pattern
    return bool(_TS_TEST_PATTERNS.search(content))


def has_failing_jest_tests(project_dir: str) -> bool:
    """Check if there are failing tests in Jest cache.

    Looks for Jest cache in common locations and checks for test failure
    indicators.

    Args:
        project_dir: Directory to start searching from.

    Returns:
        True if failing Jest tests are detected, False otherwise.
    """
    project = Path(project_dir)

    # Common Jest cache locations
    cache_dirs = [
        project / "node_modules" / ".cache" / "jest",
        project / ".jest-cache",
        project / "jest-cache",
    ]

    for cache_dir in cache_dirs:
        if not cache_dir.is_dir():
            continue

        # Jest stores test results in JSON files within the cache.
        # Look for files that contain test failure information.
        try:
            for cache_file in cache_dir.rglob("*.json"):
                try:
                    with cache_file.open() as f:
                        data = json.load(f)
                except (json.JSONDecodeError, OSError):
                    continue

                # Jest cache format: look for test result objects
                # that indicate failures
                if isinstance(data, dict):
                    # Some Jest cache files store results with
                    # numFailingTests or testResults
                    if data.get("numFailingTests", 0) > 0:
                        return True
                    if data.get("success") is False:
                        return True

                    # Check testResults array entries
                    test_results = data.get("testResults", [])
                    for result in test_results:
                        if isinstance(result, dict):
                            if result.get("numFailingTests", 0) > 0:
                                return True
                            status = result.get("status", "")
                            if status == "failed":
                                return True
        except OSError:
            continue

    return False


def warn_and_block(file_path: str, message: str, suggestion: str) -> int:
    """Show warning, record it, and return block code. Allow on retry."""
    if check_override(file_path):
        print("", file=sys.stderr)
        print(f"{CYAN}TDD: Proceeding (override acknowledged){NC}", file=sys.stderr)
        return 0

    record_warning(file_path)
    print("", file=sys.stderr)
    print(f"{YELLOW}TDD: {message}{NC}", file=sys.stderr)
    print(f"{YELLOW}    {suggestion}{NC}", file=sys.stderr)
    print(f"{YELLOW}    (Retry to proceed anyway){NC}", file=sys.stderr)
    return 2


def run_tdd_enforcer() -> int:
    """Run TDD enforcement and return exit code."""
    try:
        hook_data = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0

    tool_name = hook_data.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        return 0

    tool_input = hook_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return 0

    if should_skip(file_path):
        return 0

    if is_test_file(file_path):
        return 0

    if file_path.endswith(".py"):
        path = Path(file_path).parent
        found_failing = False

        for _ in range(10):
            if has_failing_python_tests(str(path)):
                found_failing = True
                break
            if path.parent == path:
                break
            path = path.parent

        if found_failing:
            return 0

        return warn_and_block(
            file_path,
            "No failing tests detected",
            "Consider writing a failing test first before implementing.",
        )

    if file_path.endswith((".ts", ".tsx")):
        base_name = Path(file_path).stem
        test_file = find_typescript_test_file(file_path)

        if test_file is None:
            return warn_and_block(
                file_path,
                "No test file found for this module",
                f"Consider creating {base_name}.test.ts first.",
            )

        if not typescript_test_file_has_tests(test_file):
            return warn_and_block(
                file_path,
                f"Test file {test_file.name} exists but contains no test cases",
                "Add at least one test using it(), test(), or describe().",
            )

        # Check for failing Jest tests by walking up directories
        path = Path(file_path).parent
        for _ in range(10):
            if has_failing_jest_tests(str(path)):
                return 0
            if path.parent == path:
                break
            path = path.parent

        return 0

    return 0


if __name__ == "__main__":
    sys.exit(run_tdd_enforcer())
