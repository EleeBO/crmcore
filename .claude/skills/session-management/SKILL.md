---
name: session-management
description: Track session state, completed tasks, and context across conversations. Use at session start and when resuming work.
---

# Session Management Skill

**Core Rule:** Track what's done, what's pending, and current context to avoid repeating work.

## When to Use

- At session start (check existing state)
- After completing major tasks
- Before ending session
- When resuming after break

## Session File

Store state in `.claude/session.local.md` (gitignored):

```markdown
# Session State

## Last Updated
2024-01-15 14:30

## Current Task
Implementing user authentication

## Completed This Session
- [x] Created User model
- [x] Added password hashing
- [x] Created login endpoint

## Pending
- [ ] Add JWT tokens
- [ ] Create refresh token logic
- [ ] Add logout endpoint

## Context
- Branch: feature/auth
- Related files: src/auth/, tests/test_auth.py
- Notes: Using bcrypt for hashing

## Blockers
- Need decision on token expiry time
```

## Session Start Protocol

```
1. Check if .claude/session.local.md exists
2. IF exists:
   - Read current state
   - Report: "Resuming session. Last task: X"
   - Ask: "Continue with pending tasks?"
3. IF not exists:
   - Create new session file
   - Ask about current goal
```

## Session Update Protocol

After completing a task:
```
1. Mark task as completed in session file
2. Add any new pending items discovered
3. Update context if changed
4. Update timestamp
```

## Session End Protocol

Before ending:
```
1. Summarize what was completed
2. List what remains
3. Note any blockers
4. Update session file with clear state
```

## Gitignore

Always add to `.gitignore`:
```
.claude/session.local.md
```

## Commands

```bash
# Check session state
cat .claude/session.local.md 2>/dev/null || echo "No session file"

# Quick status
just status
```

## Integration with Tasks

When using TodoWrite/TaskCreate:
- Session file tracks high-level progress
- Task tools track granular steps
- Both complement each other

## Recovery

If session file corrupted or lost:
1. Check git status for recent changes
2. Check task list if available
3. Ask user for context
4. Rebuild session state

## Anti-Patterns

**NEVER:**
- Store secrets in session file
- Commit session file to git
- Ignore existing session state
- Lose track of pending work

**ALWAYS:**
- Check session at start
- Update after milestones
- Summarize at end
- Keep context current
