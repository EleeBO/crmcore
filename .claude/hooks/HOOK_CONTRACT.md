# Hook Contract

## Exit Codes

| Code | Meaning | Behavior |
|------|---------|----------|
| 0 | Pass | Silent — hook approved the action |
| 1 | Warning | Non-blocking — message shown to user, execution continues |
| 2 | Block | Blocking — execution paused, user must acknowledge or retry |

## Communication Channels

| Channel | Purpose |
|---------|---------|
| stdout | Context injection — output is added to the model's context |
| stderr | Display messages — shown to user in terminal |

## Hook Types

### PreToolUse
- Fires BEFORE a tool executes
- Exit 2 prevents the tool from running
- Receives tool name and parameters as JSON on stdin

### PostToolUse
- Fires AFTER a tool completes
- Exit 2 shows a warning about the completed action
- Receives tool name, parameters, and result as JSON on stdin

### Stop
- Fires when the session ends
- Exit codes are advisory (session is already ending)
- Receives session transcript context on stdin

## Registered Hooks

| Hook | Type | Exit Codes Used | Blocking? |
|------|------|-----------------|-----------|
| tdd_enforcer.py | PreToolUse | 0=pass, 2=soft-block (60s retry) | Yes (with retry) |
| file_checker_python.py | PostToolUse | 0=pass, 2=block (lint errors) | Yes |
| security_guard.py | PostToolUse | 0=pass, 1=warning | No (advisory) |
| environment_checker.py | PreToolUse | 0=pass, 1=missing optional, 2=missing required | Yes (required only) |
| skill-enforcer.sh | PreToolUse | 0=pass (context injection only) | No |
| version_bump_reminder.py | PreToolUse | 0=pass, 1=warning (version not bumped) | No (advisory) |

## Rules for New Hooks

1. Always return 0 for success (silent pass)
2. Use 1 for non-blocking warnings that should be shown
3. Use 2 for blocking issues that must be acknowledged
4. Write user-facing messages to stderr
5. Write context-injection data to stdout
6. Include a docstring/comment at the top explaining the hook's purpose
7. Handle stdin JSON parsing gracefully (don't crash on malformed input)
8. Use /tmp files with project-hash isolation for caching: `/tmp/.hook_name_{project_hash}.json`

## Caching Convention

For hooks that cache results:
- Include project root hash in filename for multi-project isolation
- Use JSON format with TTL field
- Example: `/tmp/.tdd_enforcer_{hash8}.json`
