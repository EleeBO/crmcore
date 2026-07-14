---
name: auto-loop
description: Automatic TDD iteration with trigger detection, loop state tracking, and max iterations. Use when implementing features with TDD cycle.
---

# Auto-Loop TDD Skill

**Core Rule:** Detect test failures, implement fixes, verify - automatically iterate until green or max attempts.

## When to Use

- After writing a failing test
- When implementing feature with TDD
- When fixing a bug with test-first approach

## Loop State

Track in memory (or session file):
- `iteration`: Current attempt (1-5)
- `max_iterations`: 5 (default)
- `last_test_output`: Error message
- `changes_made`: List of modifications

## Trigger Detection

```
RED triggers detected:
- Test failure output
- AssertionError
- Expected vs Actual mismatch
- Import errors
- TypeErrors
```

## Loop Algorithm

```
1. RUN tests → capture output
2. IF all pass → DONE (GREEN)
3. IF iteration >= max → STOP, report to user
4. ANALYZE failure message
5. IMPLEMENT minimal fix
6. INCREMENT iteration
7. GOTO 1
```

## Implementation Rules

**Minimal Changes:**
- Fix ONLY what the error message indicates
- No refactoring during RED→GREEN
- No additional features
- One change per iteration

**Failure Analysis:**
```python
# Parse error types
if "ImportError" in output:
    action = "add missing import"
elif "AttributeError" in output:
    action = "check attribute name or add method"
elif "AssertionError" in output:
    action = "fix return value or logic"
elif "TypeError" in output:
    action = "fix argument types"
```

## Max Iterations

After 5 failed attempts:
1. STOP the loop
2. Report what was tried
3. Ask user for guidance
4. Never continue blindly

## Commands

```bash
# Run tests
just test-backend
just test-frontend

# Single file
uv run pytest tests/test_specific.py -v
npm test -- --testPathPattern=specific
```

## Anti-Patterns

**NEVER:**
- Skip iterations without running tests
- Make multiple unrelated changes
- Continue past max iterations
- Ignore test output

**ALWAYS:**
- Run tests after EVERY change
- Read the FULL error message
- Make ONE targeted fix
- Track iteration count

## Integration with TDD Enforcer

This skill works WITH the TDD enforcer hook:
1. TDD enforcer ensures tests exist before code
2. Auto-loop iterates until tests pass
3. Both together = disciplined TDD

## Example Flow

```
Iteration 1:
  - Run: pytest test_user.py
  - Fail: NameError: name 'User' is not defined
  - Fix: Create User class stub

Iteration 2:
  - Run: pytest test_user.py
  - Fail: AttributeError: 'User' has no attribute 'name'
  - Fix: Add name attribute

Iteration 3:
  - Run: pytest test_user.py
  - Pass: All tests green
  - Done!
```
