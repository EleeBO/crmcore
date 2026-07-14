#!/usr/bin/env python3
"""Rules Supervisor - Stop hook that analyzes coding sessions against project rules using Gemini."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[0;33m"
CYAN = "\033[0;36m"
NC = "\033[0m"

RULES_SUPERVISOR_RUNNING = "CCP_RULES_SUPERVISOR_RUNNING"
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
)
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
PRIVACY_MODE = os.environ.get("RULES_SUPERVISOR_PRIVACY_MODE", "standard")


@dataclass
class ToolAction:
    """A single tool action from the session."""

    index: int
    tool_name: str
    tool_id: str
    details: str
    result_summary: str = ""
    is_test_file: bool = False
    is_test_run: bool = False
    is_success: bool | None = None


@dataclass
class SessionSummary:
    """Summary of session actions extracted from transcript."""

    files_modified: list[str] = field(default_factory=list)
    tests_run: bool = False
    tests_passed: bool | None = None
    tools_used: list[str] = field(default_factory=list)
    user_prompts: list[str] = field(default_factory=list)
    assistant_text: list[str] = field(default_factory=list)
    assistant_thinking: list[str] = field(default_factory=list)
    tool_sequence: list[ToolAction] = field(default_factory=list)
    plan_file: str = ""


@dataclass
class Violation:
    """A rule violation detected during analysis."""

    rule: str
    severity: str
    description: str


@dataclass
class RuleAssessment:
    """Assessment for a single rule."""

    rule: str
    status: str
    note: str = ""


@dataclass
class RulesReport:
    """Report from Claude analysis."""

    violations: list[Violation] = field(default_factory=list)
    rule_assessments: list[RuleAssessment] = field(default_factory=list)
    summary: str = ""
    passed: bool | None = True


@dataclass
class Rules:
    """Loaded rules from project."""

    tdd_rules: str = ""
    verification_rules: str = ""
    coding_standards: str = ""
    all_rules: str = ""


@dataclass
class RuleFile:
    """A single rule file with its content."""

    filename: str
    content: str


def _is_plan_complete(plan_path: str, project_dir: str) -> bool:
    """Check if plan file has Status: COMPLETE marker."""
    full_path = Path(project_dir) / plan_path
    if not full_path.exists():
        return False

    try:
        content = full_path.read_text()
        return "Status: COMPLETE" in content
    except OSError:
        return False


def _detect_implement_mode_and_plan(transcript_path: str) -> tuple[bool, str | None]:
    """Scan transcript to detect /implement mode and plan file."""
    path = Path(transcript_path)
    if not path.exists():
        return False, None

    is_implement_mode = False
    plan_path = None

    try:
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entry_type = entry.get("type", "")
                    message = entry.get("message", {})
                    content = message.get("content", [])

                    if entry_type == "user":
                        prompt_text = ""
                        if isinstance(content, str):
                            prompt_text = content
                        elif isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    prompt_text += block.get("text", "")

                        if "/implement" in prompt_text:
                            is_implement_mode = True

                        if not plan_path:
                            plan_match = re.search(r"@?(docs/plans/[^\s\]\)]+\.md)", prompt_text)
                            if plan_match:
                                plan_path = plan_match.group(1)

                except json.JSONDecodeError:
                    continue
    except OSError:
        pass

    return is_implement_mode, plan_path


def _find_project_root(cwd: str) -> str:
    """Find project root by walking up until we find .claude directory."""
    path = Path(cwd)
    for _ in range(10):
        if (path / ".claude").exists():
            return str(path)
        if path.parent == path:
            break
        path = path.parent
    return cwd


def _get_transcript_path(session_id: str, cwd: str) -> str | None:
    """Construct transcript path from session ID and working directory."""
    if not session_id:
        return None

    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return None

    project_slug = cwd.replace("/", "-")
    if project_slug.startswith("-"):
        project_slug = project_slug[1:]

    project_dir = claude_dir / project_slug
    if not project_dir.exists():
        for candidate in claude_dir.iterdir():
            if candidate.is_dir() and cwd.split("/")[-1] in candidate.name:
                project_dir = candidate
                break

    transcript_file = project_dir / f"{session_id}.jsonl"
    if transcript_file.exists():
        return str(transcript_file)

    return None


def _is_test_file(file_path: str) -> bool:
    """Check if a file path is a test file."""
    name = file_path.lower()
    return (
        "test_" in name
        or "_test." in name
        or "/tests/" in name
        or "\\tests\\" in name
        or name.endswith(".test.js")
        or name.endswith(".test.ts")
        or name.endswith(".spec.js")
        or name.endswith(".spec.ts")
    )


def _is_test_command(command: str) -> bool:
    """Check if a bash command is running tests."""
    return any(
        test_cmd in command
        for test_cmd in ["pytest", "npm test", "yarn test", "jest", "vitest", "uv run pytest"]
    )


def _summarize_tool_result(result_content: str, tool_name: str) -> tuple[str, bool | None]:
    """Summarize tool result and determine success/failure."""
    if not result_content:
        return "", None

    if "passed" in result_content.lower() and (
        "pytest" in result_content.lower() or "test" in result_content.lower()
    ):
        match = re.search(r"(\d+)\s+passed", result_content)
        if match:
            passed = match.group(1)
            failed_match = re.search(r"(\d+)\s+failed", result_content)
            failed = failed_match.group(1) if failed_match else "0"
            return f"Tests: {passed} passed, {failed} failed", failed == "0"

    if "error" in result_content.lower() or "Error" in result_content:
        for line in result_content.split("\n"):
            if "error" in line.lower() or "Error" in line:
                return f"ERROR: {line[:100]}", False

    if "Exit code" in result_content:
        if "Exit code 0" in result_content:
            return "Success (exit 0)", True
        else:
            match = re.search(r"Exit code (\d+)", result_content)
            if match:
                return f"Failed (exit {match.group(1)})", False

    if tool_name == "Read":
        return "File read OK", True

    if tool_name in ("Edit", "Write") and (
        "has been updated" in result_content or "has been created" in result_content
    ):
        return "OK", True

    first_line = result_content.split("\n")[0][:80]
    return first_line, None


def parse_transcript(transcript_path: str) -> SessionSummary:
    """Parse session transcript JSONL file with full tool results."""
    summary = SessionSummary()
    path = Path(transcript_path)
    action_index = 0
    tool_actions_by_id: dict[str, ToolAction] = {}

    if not path.exists():
        return summary

    def _add_tool_action(tool_name: str, tool_id: str, tool_input: dict) -> None:
        """Add a tool action to the sequence."""
        nonlocal action_index

        details = ""
        is_test_file = False
        is_test_run = False

        if tool_name in ("Write", "Edit", "MultiEdit"):
            file_path = tool_input.get("file_path", "")
            details = file_path
            is_test_file = _is_test_file(file_path)
        elif tool_name == "Bash":
            command = tool_input.get("command", "")
            details = command[:200] if len(command) > 200 else command
            is_test_run = _is_test_command(command)
        elif tool_name == "Read":
            details = tool_input.get("file_path", "")
        elif tool_name in ("Glob", "Grep"):
            details = tool_input.get("pattern", "")
        elif tool_name == "TodoWrite":
            todos = tool_input.get("todos", [])
            details = f"{len(todos)} todos"
        else:
            if "file_path" in tool_input:
                details = tool_input["file_path"]
            elif "command" in tool_input:
                details = tool_input["command"][:100]
            elif "prompt" in tool_input:
                details = tool_input["prompt"][:100]
            elif "query" in tool_input:
                details = tool_input["query"][:100]

        action_index += 1
        action = ToolAction(
            index=action_index,
            tool_name=tool_name,
            tool_id=tool_id,
            details=details,
            is_test_file=is_test_file,
            is_test_run=is_test_run,
        )
        summary.tool_sequence.append(action)
        tool_actions_by_id[tool_id] = action

    try:
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entry_type = entry.get("type", "")
                    message = entry.get("message", {})
                    content = message.get("content", [])

                    if isinstance(content, list):
                        for block in content:
                            if not isinstance(block, dict):
                                continue

                            block_type = block.get("type", "")

                            if block_type == "tool_use":
                                tool_name = block.get("name", "")
                                tool_id = block.get("id", "")
                                if tool_name:
                                    summary.tools_used.append(tool_name)
                                    tool_input = block.get("input", {})
                                    _add_tool_action(tool_name, tool_id, tool_input)

                                    file_path = tool_input.get("file_path", "")
                                    if file_path and tool_name in ("Write", "Edit", "MultiEdit"):
                                        summary.files_modified.append(file_path)
                                    if tool_name == "Bash" and _is_test_command(
                                        tool_input.get("command", "")
                                    ):
                                        summary.tests_run = True

                            elif block_type == "tool_result":
                                tool_id = block.get("tool_use_id", "")
                                result_content = block.get("content", "")
                                if (
                                    isinstance(result_content, str)
                                    and tool_id in tool_actions_by_id
                                ):
                                    action = tool_actions_by_id[tool_id]
                                    action.result_summary, action.is_success = (
                                        _summarize_tool_result(result_content, action.tool_name)
                                    )

                            elif block_type == "text":
                                text = block.get("text", "")
                                if text:
                                    summary.assistant_text.append(text[:300])

                            elif block_type == "thinking":
                                thinking = block.get("thinking", "")
                                if thinking:
                                    summary.assistant_thinking.append(thinking[:500])

                    if entry_type == "tool_use":
                        tool_name = entry.get("tool_name", "") or entry.get("name", "")
                        tool_id = entry.get("id", f"legacy_{action_index}")
                        if tool_name:
                            summary.tools_used.append(tool_name)
                            tool_input = entry.get("tool_input", {}) or entry.get("input", {})
                            _add_tool_action(tool_name, tool_id, tool_input)

                            file_path = tool_input.get("file_path", "")
                            if file_path and tool_name in ("Write", "Edit", "MultiEdit"):
                                summary.files_modified.append(file_path)
                            if tool_name == "Bash" and _is_test_command(
                                tool_input.get("command", "")
                            ):
                                summary.tests_run = True

                    elif entry_type == "user":
                        prompt_text = ""
                        if isinstance(content, str) and content:
                            prompt_text = content
                            summary.user_prompts.append(content)
                        elif isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    text = block.get("text", "")
                                    prompt_text += text
                                    summary.user_prompts.append(text)

                        plan_match = re.search(r"@?(docs/plans/[^\s\]]+\.md)", prompt_text)
                        if plan_match and not summary.plan_file:
                            summary.plan_file = plan_match.group(1)

                except json.JSONDecodeError:
                    continue
    except OSError:
        pass

    return summary


def load_rules(project_dir: str) -> Rules:
    """Load rules from .claude/rules/ directories."""
    rules = Rules()
    project_path = Path(project_dir)
    rules_base = project_path / ".claude" / "rules"

    all_rules_parts = []

    for subdir in ["standard", "custom"]:
        rules_dir = rules_base / subdir
        if not rules_dir.exists():
            continue

        for rule_file in sorted(rules_dir.glob("*.md")):
            try:
                content = rule_file.read_text()
                all_rules_parts.append(f"# {rule_file.stem}\n{content}")

                name_lower = rule_file.stem.lower()
                if "tdd" in name_lower:
                    rules.tdd_rules += content + "\n"
                elif "verif" in name_lower or "execution" in name_lower:
                    rules.verification_rules += content + "\n"
                elif "coding" in name_lower or "standard" in name_lower:
                    rules.coding_standards += content + "\n"
            except OSError:
                continue

    # Living spec rules — additional checks for spec lifecycle
    living_spec_rules = [
        "Living spec status must be updated after /implement (DRAFT→ACTIVE or MODIFIED→ACTIVE)",
        "specs/registry.md must be updated with current status",
        "Change History entry must exist in spec for current plan",
    ]
    all_rules_parts.append(
        "# living-spec-lifecycle\n" + "\n".join(f"- {r}" for r in living_spec_rules)
    )

    rules.all_rules = "\n\n".join(all_rules_parts)
    return rules


def load_rule_files(project_dir: str) -> list[RuleFile]:
    """Load individual rule files from .claude/rules/ directories."""
    rule_files: list[RuleFile] = []
    project_path = Path(project_dir)
    rules_base = project_path / ".claude" / "rules"

    for subdir in ["standard", "custom"]:
        rules_dir = rules_base / subdir
        if not rules_dir.exists():
            continue

        for rule_file in sorted(rules_dir.glob("*.md")):
            try:
                content = rule_file.read_text()
                rule_files.append(RuleFile(filename=rule_file.stem, content=content))
            except OSError:
                continue

    # Append living spec lifecycle as a synthetic rule file
    living_spec_content = (
        "# Living Spec Lifecycle Rules\n\n"
        "These rules ensure living specifications stay in sync with implementation.\n\n"
        "- Living spec status must be updated after /implement (DRAFT→ACTIVE or MODIFIED→ACTIVE)\n"
        "- specs/registry.md must be updated with current status\n"
        "- Change History entry must exist in spec for current plan\n"
    )
    rule_files.append(RuleFile(filename="living-spec-lifecycle", content=living_spec_content))

    return rule_files


def get_git_diff(project_dir: str) -> tuple[str, list[str]]:
    """Get git diff for the project."""
    changed_files: list[str] = []
    diff_text = ""

    try:
        result = subprocess.run(
            ["git", "diff", "HEAD"],  # noqa: S607
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        diff_text = result.stdout

        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],  # noqa: S607
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.stdout:
            changed_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return diff_text, changed_files


SUPERVISOR_SYSTEM_PROMPT = """You are a code review supervisor for Claude CodePro.

Your task is to analyze a coding session and determine if:
1. The developer followed EACH rule file provided
2. If an implementation plan was provided, all tasks were completed correctly

IMPORTANT: You MUST check EACH rule file separately and provide an assessment for each one.

Respond ONLY with a valid JSON object (no markdown, no code blocks):
{
  "rule_assessments": [
    {"rule": "rule-filename", "status": "pass", "note": "Brief note on compliance"},
    {"rule": "rule-filename", "status": "fail", "note": "What was not followed"}
  ],
  "violations": [
    {"rule": "rule-or-plan", "severity": "critical", "description": "Detailed violation"}
  ],
  "summary": "Brief overall assessment",
  "passed": true/false
}

Rules for assessments:
- Include EVERY rule file in "rule_assessments" with status "pass" or "fail"
- Only include "violations" for rules that failed
- "note" should be a brief explanation (1 sentence)

Severity levels for violations:
- "critical": Must be fixed before committing (e.g., no tests, code not executed)
- "warning": Should be addressed (e.g., minor deviation from standards)
"""


def _build_analysis_prompt(
    session_summary: SessionSummary,
    rules: Rules,
    git_diff: str,
    changed_files: list[str],
    rule_files: list[RuleFile] | None = None,
    plan_content: str = "",
) -> tuple[str, int]:
    """Build the analysis prompt with data masking. Returns (prompt, token_estimate).

    Data masking controlled by RULES_SUPERVISOR_PRIVACY_MODE env var:
    - "standard" (default): Excludes assistant_thinking blocks, truncates
      Write/Edit inputs to file path + char count, truncates Bash outputs
      to first 200 characters.
    - "strict": Excludes ALL code content and git diff; only transmits
      tool names, sequence, and markers.
    """
    is_strict = PRIVACY_MODE == "strict"
    prompt_parts: list[str] = []

    if plan_content:
        prompt_parts.append("## IMPLEMENTATION PLAN (check if tasks were completed)")
        prompt_parts.append(plan_content)
        prompt_parts.append("\n")

    prompt_parts.append("## Session Summary (FINAL STATE)\n")
    prompt_parts.append(
        "IMPORTANT: Analyze the FINAL state of the session, not intermediate states."
    )
    prompt_parts.append("If an issue was present early but fixed later, it is NOT a violation.\n")

    prompt_parts.append(f"- Total files modified: {len(session_summary.files_modified)}")
    if session_summary.files_modified:
        recent_files = session_summary.files_modified[-20:]
        prompt_parts.append(f"  - Recent: {', '.join(recent_files)}")

    prompt_parts.append(
        f"- Tests run during session: {'Yes' if session_summary.tests_run else 'No'}"
    )
    prompt_parts.append(f"- Unique tools used: {', '.join(set(session_summary.tools_used))}")

    if session_summary.user_prompts:
        prompt_parts.append(f"\n## ALL USER REQUESTS ({len(session_summary.user_prompts)} total)")
        for i, prompt in enumerate(session_summary.user_prompts, 1):
            prompt_parts.append(f"[{i}] {prompt[:500]}")

    if session_summary.tool_sequence:
        if is_strict:
            # Strict privacy: only tool names and sequence, no content
            prompt_parts.append("\n## TOOL SEQUENCE (strict privacy mode - names only)")
            for action in session_summary.tool_sequence:
                markers: list[str] = []
                if action.is_test_file:
                    markers.append("TEST_FILE")
                if action.is_test_run:
                    markers.append("TEST_RUN")
                if action.is_success is True:
                    markers.append("OK")
                elif action.is_success is False:
                    markers.append("FAIL")
                marker_str = f" | {', '.join(markers)}" if markers else ""
                prompt_parts.append(f"[{action.index}] {action.tool_name}{marker_str}")
        else:
            # Standard mode: include details with masking
            prompt_parts.append(
                "\n## TOOL SEQUENCE WITH RESULTS (chronological - CRITICAL for rule checking)"
            )
            prompt_parts.append("Format: [index] TOOL: details -> RESULT | markers")
            prompt_parts.append(
                "Check: tests written BEFORE implementation, tests run AFTER changes,"
                " program executed\n"
            )
            for action in session_summary.tool_sequence:
                markers = []
                if action.is_test_file:
                    markers.append("TEST_FILE")
                if action.is_test_run:
                    markers.append("TEST_RUN")
                if action.is_success is True:
                    markers.append("OK")
                elif action.is_success is False:
                    markers.append("FAIL")
                marker_str = f" | {', '.join(markers)}" if markers else ""

                # Truncate Write/Edit tool inputs to file path + char count
                details = action.details
                if action.tool_name in ("Write", "Edit", "MultiEdit") and details:
                    file_path = details.split("\n")[0] if "\n" in details else details
                    details = f"{file_path} ({len(action.details)} chars)"

                # Truncate Bash result output to 200 chars
                result_summary = action.result_summary
                if action.tool_name == "Bash" and result_summary:
                    result_summary = result_summary[:200]

                result_str = f" -> {result_summary}" if result_summary else ""
                prompt_parts.append(
                    f"[{action.index}] {action.tool_name}: {details}{result_str}{marker_str}"
                )

    # Include assistant text in standard mode only (never in strict)
    if not is_strict and session_summary.assistant_text:
        prompt_parts.append(
            f"\n## ASSISTANT STATEMENTS ({len(session_summary.assistant_text)} messages)"
        )
        for i, text in enumerate(session_summary.assistant_text, 1):
            prompt_parts.append(f"[{i}] {text}")

    # assistant_thinking blocks are always excluded — they contain internal
    # reasoning that should not be transmitted to external APIs

    if rule_files:
        prompt_parts.append("\n## RULES TO CHECK (check EACH rule file separately)")
        for rf in rule_files:
            prompt_parts.append(f"\n### Rule File: {rf.filename}")
            prompt_parts.append(rf.content[:1500])
    elif rules.all_rules:
        prompt_parts.append("\n## Project Rules to Check Against")
        prompt_parts.append(rules.all_rules[:10000])

    if changed_files:
        prompt_parts.append(f"\n## Files Changed ({len(changed_files)})")
        file_list = changed_files[:50]
        prompt_parts.append(", ".join(file_list))

    # Git diff excluded in strict mode (contains code content)
    if not is_strict and git_diff:
        prompt_parts.append("\n## Git Diff (summary of changes)")
        prompt_parts.append(git_diff[:8000])

    prompt_parts.append(
        "\n\nAnalyze the FINAL state against EACH rule file. Report violations by rule filename."
    )
    prompt_parts.append("Respond with JSON only, no markdown code blocks.")

    prompt = "\n".join(prompt_parts)
    token_estimate = len(prompt) // 4
    return prompt, token_estimate


def _call_gemini_api(prompt: str, system_prompt: str) -> str:
    """Call Gemini API via HTTP and return response text."""
    import httpx

    api_key = os.environ.get(GEMINI_API_KEY_ENV, "")
    if not api_key:
        raise ValueError(f"Missing {GEMINI_API_KEY_ENV} environment variable")

    url = f"{GEMINI_API_URL}?key={api_key}"

    payload = {
        "contents": [{"role": "user", "parts": [{"text": f"{system_prompt}\n\n{prompt}"}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4096,
            "thinkingConfig": {
                "thinkingBudget": 8192,
            },
        },
    }

    try:
        response = httpx.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()

        candidates = result.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if parts:
                return parts[0].get("text", "")

        return ""
    except httpx.HTTPStatusError as e:
        error_body = e.response.text
        raise RuntimeError(f"Gemini API error {e.response.status_code}: {error_body}") from e
    except httpx.RequestError as e:
        raise RuntimeError(f"Gemini API connection error: {e}") from e


def _parse_gemini_response(response_text: str) -> RulesReport:
    """Parse Gemini's JSON response into a RulesReport."""
    try:
        text = response_text.strip()

        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            text = text[start:end].strip()

        data = json.loads(text)

        violations = []
        for v in data.get("violations", []):
            violations.append(
                Violation(
                    rule=v.get("rule", "Unknown"),
                    severity=v.get("severity", "warning"),
                    description=v.get("description", ""),
                )
            )

        rule_assessments = []
        for a in data.get("rule_assessments", []):
            rule_assessments.append(
                RuleAssessment(
                    rule=a.get("rule", "Unknown"),
                    status=a.get("status", "pass"),
                    note=a.get("note", ""),
                )
            )

        return RulesReport(
            violations=violations,
            rule_assessments=rule_assessments,
            summary=data.get("summary", ""),
            passed=data.get("passed", len(violations) == 0),
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return RulesReport(
            violations=[],
            rule_assessments=[],
            summary="Unable to parse analysis response",
            passed=True,
        )


def analyze_with_gemini(
    session_summary: SessionSummary,
    rules: Rules,
    git_diff: str,
    changed_files: list[str],
    rule_files: list[RuleFile] | None = None,
    plan_content: str = "",
) -> RulesReport:
    """Analyze session against rules using Gemini API."""
    prompt, token_estimate = _build_analysis_prompt(
        session_summary, rules, git_diff, changed_files, rule_files, plan_content
    )
    print(f"   Sending ~{token_estimate:,} tokens...")

    try:
        response_text = _call_gemini_api(prompt, SUPERVISOR_SYSTEM_PROMPT)
        print(f"   {GREEN}Analysis complete{NC}")
    except Exception as e:
        print(f"   {YELLOW}API error: {e}{NC}")
        return RulesReport(
            violations=[],
            summary="API unavailable — compliance could not be verified",
            passed=None,
        )

    return _parse_gemini_response(response_text)


def _update_plan_status(project_dir: str, plan_path: str, new_status: str) -> None:
    """Update the Status: line in the plan file."""
    full_path = Path(project_dir) / plan_path
    if not full_path.exists():
        return

    try:
        content = full_path.read_text()
        updated = re.sub(
            r"^Status:\s*\w+", f"Status: {new_status}", content, count=1, flags=re.MULTILINE
        )
        full_path.write_text(updated)
    except OSError:
        pass


def _save_results(transcript_path: str, report: RulesReport) -> None:
    """Save results for one-time execution check."""
    session_id = Path(transcript_path).stem

    results_dir = Path.home() / ".claude" / "supervisor-results"
    results_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "passed": report.passed,
        "summary": report.summary,
        "violations": [
            {"rule": v.rule, "severity": v.severity, "description": v.description}
            for v in report.violations
        ],
    }

    (results_dir / f"{session_id}.json").write_text(json.dumps(results))


def print_progress(message: str, prefix: str = "") -> None:
    """Print progress message to stdout."""
    print(f"{prefix} {message}", flush=True)


def run_rules_supervisor(
    transcript_path: str, project_dir: str, plan_path: str | None = None
) -> int:
    """Run the rules supervisor analysis and return exit code."""
    print(f"\n{CYAN}Rules Supervisor - Analyzing session...{NC}\n", flush=True)

    if not Path(transcript_path).exists():
        print(f"{RED}Error: Transcript file not found: {transcript_path}{NC}", file=sys.stderr)
        return 1

    plan_content = ""
    if plan_path:
        plan_file = Path(project_dir) / plan_path
        if plan_file.exists():
            plan_content = plan_file.read_text()
            print(f"Loaded plan: {plan_path}")
        else:
            print(f"{YELLOW}Plan file not found: {plan_path}{NC}")

    print_progress("Loading rules from .claude/rules/...")
    rules = load_rules(project_dir)
    rule_files = load_rule_files(project_dir)

    if rule_files:
        print(f"   {GREEN}Loaded {len(rule_files)} rule files:{NC}")
        for rf in rule_files:
            print(f"      - {rf.filename}")
    else:
        print(f"   {YELLOW}No rules found in .claude/rules/{NC}")

    print_progress("Parsing session transcript...")
    session_summary = parse_transcript(transcript_path)
    print(f"   {GREEN}Found {len(session_summary.tools_used)} tool uses{NC}")
    print(f"   {GREEN}Files modified: {len(session_summary.files_modified)}{NC}")
    print(f"   {GREEN}Tests detected: {'Yes' if session_summary.tests_run else 'No'}{NC}")

    print_progress("Getting git diff...")
    git_diff, changed_files = get_git_diff(project_dir)
    print(f"   {GREEN}Changed files: {len(changed_files)}{NC}")

    print_progress("Analyzing with Gemini...")
    report = analyze_with_gemini(
        session_summary, rules, git_diff, changed_files, rule_files, plan_content
    )

    _save_results(transcript_path, report)

    print(f"\n{CYAN}{'=' * 50}{NC}")
    print(f"{CYAN}  RULES COMPLIANCE REPORT{NC}")
    print(f"{CYAN}{'=' * 50}{NC}\n")

    if report.rule_assessments:
        for assessment in report.rule_assessments:
            if assessment.status == "pass":
                icon = f"{GREEN}OK{NC}"
                status = f"{GREEN}PASS{NC}"
            else:
                icon = f"{RED}X{NC}"
                status = f"{RED}FAIL{NC}"
            print(f"  {icon} {assessment.rule}: {status}")
            if assessment.note:
                print(f"      {assessment.note}")
        print()

    if report.violations:
        print(f"{RED}{'-' * 50}{NC}")
        print(f"{RED}  VIOLATIONS{NC}")
        print(f"{RED}{'-' * 50}{NC}\n")
        for violation in report.violations:
            severity_label = "CRITICAL" if violation.severity == "critical" else "WARNING"
            print(f"  [{severity_label}] {violation.rule}")
            print(f"      {violation.description}\n")

    print(f"{CYAN}{'=' * 50}{NC}")
    if report.passed is None:
        print(f"{YELLOW}  Compliance could not be verified (API unavailable){NC}")
    elif report.passed:
        print(f"{GREEN}  Session compliant with project rules{NC}")
    else:
        violation_count = len(report.violations)
        print(f"{RED}  {violation_count} violation(s) found{NC}")
    print(f"{CYAN}{'=' * 50}{NC}\n")

    if plan_path and report.passed is False:
        _update_plan_status(project_dir, plan_path, "PENDING")

    if report.passed is None:
        return 1
    return 0 if report.passed else 1


def run_stop_hook() -> int:
    """Run stop hook trigger and return exit code.

    Returns 2 (warning) with analysis output, or 0 (silent) if:
    - Already running (prevents infinite loops from sub-sessions)
    - No Gemini API key
    - Invalid input
    - Missing session info
    - Not in /implement mode with a plan
    """
    if os.environ.get(RULES_SUPERVISOR_RUNNING):
        return 0

    if not os.environ.get(GEMINI_API_KEY_ENV):
        return 0

    try:
        hook_data = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0

    session_id = hook_data.get("session_id", "")
    transcript_path = hook_data.get("transcript_path", "")
    cwd = hook_data.get("cwd", os.getcwd())

    if not session_id:
        return 0

    if not transcript_path:
        transcript_path = _get_transcript_path(session_id, cwd)

    if not transcript_path:
        return 0

    project_dir = _find_project_root(cwd)

    is_implement_mode, plan_path = _detect_implement_mode_and_plan(transcript_path)
    if not is_implement_mode or not plan_path:
        return 0

    if not _is_plan_complete(plan_path, project_dir):
        return 0

    os.environ[RULES_SUPERVISOR_RUNNING] = "1"

    return run_rules_supervisor(transcript_path, project_dir, plan_path)


if __name__ == "__main__":
    sys.exit(run_stop_hook())
