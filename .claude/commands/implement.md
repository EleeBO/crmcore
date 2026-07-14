---
description: Execute implementation plans in batches with Claude CodePro
model: opus
---
# IMPLEMENT MODE: Task Execution with Mandatory Context Gathering

**Execute ALL tasks continuously. NO stopping unless context manager says context is full.**

## ⛔ CRITICAL: Task Completion Tracking is MANDATORY

**After completing EACH task, you MUST:**

1. **IMMEDIATELY edit the plan file** to change `[ ]` to `[x]` for that task
2. **Update the Progress Tracking counts** (Completed/Remaining)
3. **DO NOT proceed to next task** until the checkbox is updated

**This is NON-NEGOTIABLE. If you skip this step:**
- The rules supervisor will detect incomplete task tracking
- Verification will fail
- You will need to re-implement

**Example - After completing Task 5:**
```
Edit the plan file:
- [ ] Task 5: Implement X  →  - [x] Task 5: Implement X
Update counts:
**Completed:** 4 | **Remaining:** 8  →  **Completed:** 5 | **Remaining:** 7
```

## CRITICAL: No Sub-Agents During Implementation

**NEVER use the Task tool or spawn sub-agents during implementation.** Sub-agents slow down execution and waste context. Instead:
- Use direct tools: Read, Grep, Glob, Bash, Write, Edit
- Use MCP tools directly: Exa, Greptile, Context7
- If you need external docs, use `mcp__exa__get_code_context_exa()` directly

## Tools - Use Throughout Implementation

| Tool | Purpose | When to Use |
|------|---------|-------------|
| **Project Memory** | Persistent learnings | Read `.claude/memory/` at start, write learnings after each task |
| **Greptile** | Semantic code search | Find related code, verify patterns |
| **Exa** | Web search & code examples | Look up library APIs, find solutions |
| **Context7** | Library documentation | Look up current API docs for any library |

**Read `.claude/memory/` at start and write learnings at end of each task.**


## Mandatory Context Gathering Phase (REQUIRED)

**Before ANY implementation, you MUST:**

1. **Read the COMPLETE plan** - Understanding overall architecture and design
2. **Verify comprehension** - Summarize what you learned to demonstrate understanding
3. **Identify dependencies** - List files, functions, classes that need modification
4. **Check current state:**
   - Git status: `git status --short` and `git diff --name-only`
   - Diagnostics: `uv run ruff check src/` and `uv run mypy src/` (or `npx tsc --noEmit`)
   - Plan progress: Check for `[x]` completed tasks
5. **Query knowledge base:**
   - Project Memory: Read `.claude/memory/` for past implementations and gotchas
   - Greptile: Related patterns and components (`mcp__plugin_greptile_greptile__*`)
   - Exa: External documentation if needed
6. **Read living spec (if plan references one):**
   - Look for `Spec: specs/FEAT-NNN-*.md` line in the plan header
   - If found, read the spec to understand the feature's full context
   - Note the spec's Status and latest Change History entry

## ⚠️ CRITICAL: Migration/Refactoring Tasks

**When the plan involves replacing existing code, perform these ADDITIONAL checks:**

### Before Starting Implementation

1. **Locate the Feature Inventory section** in the plan
2. **If Feature Inventory is MISSING** - STOP and inform user:
   ```
   "This migration plan is missing a Feature Inventory section.
   Without it, features may be accidentally omitted.
   Please run `/plan` again to add the inventory, or manually add it to the plan."
   ```
3. **Verify ALL features are mapped** - Every row must have a Task #
4. **Read the OLD code completely** - Don't rely on the plan alone

### During Implementation

For EACH task that migrates old functionality:

1. **Read the corresponding old file(s)** listed in Feature Inventory
2. **Create a checklist** of functions/behaviors from old code
3. **Verify each function/behavior exists** in new code after implementation
4. **Test with same inputs** - Old and new code should produce same outputs

### Before Marking Task Complete

**For migration tasks, add this to Definition of Done:**

- [ ] All functions from old code have equivalents in new code
- [ ] Behavior matches old code (same inputs → same outputs)
- [ ] No features accidentally omitted

### Red Flags - STOP Implementation

If you notice ANY of these, STOP and report to user:

- Feature Inventory section missing from plan
- Old file has functions not mentioned in any task
- "Out of Scope" items that should actually be migrated
- Tests pass but functionality is missing compared to old code

## TDD is MANDATORY

**No production code without a failing test first.** Follow the TDD rules in your context.

| Requires TDD | Skip TDD |
|--------------|----------|
| New functions/methods | Documentation changes |
| API endpoints | Config file updates |
| Business logic | IaC code (CDK, Terraform, Pulumi) |
| Bug fixes | Formatting/style changes |

**The TDD enforcer hook will warn you if you skip this.**

## Per-Task Execution Flow

**For EVERY task, follow this exact sequence:**

1. **READ PLAN'S IMPLEMENTATION STEPS** - List all files to create/modify/delete
2. **Perform Call Chain Analysis:**
   - **Trace Upwards (Callers):** Identify what calls the code you're modifying
   - **Trace Downwards (Callees):** Identify what the modified code calls
   - **Side Effects:** Check for database, cache, external system impacts
3. **Mark task as in_progress** in TodoWrite
4. **Check diagnostics** - `ruff check + mypy (Python) or tsc --noEmit (TypeScript)`
5. **Execute TDD Flow (RED → GREEN → REFACTOR):**
   - Write failing test first, **verify it fails**
   - Implement minimal code to pass
   - Refactor if needed (keep tests green)
6. **Verify tests pass** - `uv run pytest tests/path/to/test.py -v`
7. **Run actual program** - Show real output with sample data
8. **Check diagnostics again** - Must be zero errors
9. **Validate Definition of Done** - Check all criteria from plan
10. **Mark task completed** in TodoWrite

### ⛔ STEP 11 IS MANDATORY - DO NOT SKIP

11. **UPDATE PLAN FILE IMMEDIATELY:**
    ```
    Use Edit tool to change in the plan file:
    - [ ] Task N: ...  →  - [x] Task N: ...

    Also update Progress Tracking section:
    **Completed:** X | **Remaining:** Y
    ```
    **You MUST do this BEFORE proceeding to the next task.**
    **Failure to update = incomplete implementation.**

12. **Check context usage**

## Critical Task Rules

**⚠️ NEVER SKIP TASKS:**
- EVERY task MUST be fully implemented
- NO exceptions for "MVP scope" or complexity
- If blocked: STOP and report specific blockers
- NEVER mark complete without doing the work

## Verification Checklist

Before marking complete:
- [ ] Test written and FAILED (RED phase)
- [ ] Implementation written
- [ ] Test PASSES (GREEN phase)
- [ ] Program executed with verified output
- [ ] No diagnostics errors

## When All Tasks Complete

**⚠️ CRITICAL: Follow these steps exactly:**

1. Quick verification: `ruff check + mypy (Python) or tsc --noEmit (TypeScript)` and `uv run pytest`
2. **FOR MIGRATIONS ONLY - Feature Parity Check:**
   - Run the NEW code and verify it produces expected output
   - Compare behavior with OLD code (if still available)
   - Check Feature Inventory - every feature should now be implemented
   - If ANY feature is missing: **DO NOT mark complete** - add tasks for missing features
3. Store learnings in `.claude/memory/` (Write a summary file)

### ARCHIVE: Update Living Spec (if plan has Spec: reference)

**This step is MANDATORY when the plan references a living spec.**

4. **Read the spec file:**
   ```
   Read(file_path="specs/FEAT-NNN-name.md")
   ```

5. **Merge delta into Current State:**
   - Read the plan's `## Delta` section (ADDED/MODIFIED/REMOVED)
   - Update the spec's `## Current State` section:
     - Add new items from ADDED
     - Update existing items from MODIFIED
     - Remove items from REMOVED

6. **Update Components list:**
   - Add paths to all new files created during implementation
   - Update descriptions for modified files
   - Remove entries for deleted files

7. **Update Behavior section:**
   - Add new endpoints/functions implemented
   - Update changed behaviors
   - Remove deprecated behaviors

8. **Add Change History entry:**
   ```markdown
   ### vN (YYYY-MM-DD) — [title from plan summary]
   - ADDED: [list from delta]
   - MODIFIED: [list from delta]
   - REMOVED: [list from delta]
   - Plan: [link to plan](../docs/plans/FEAT-NNN-name.md)
   ```
   Determine version number by counting existing `### vN` entries + 1.

9. **Update spec Status:**
   - If was DRAFT → set to ACTIVE
   - If was MODIFIED → set to ACTIVE
   - Update `Last Modified: YYYY-MM-DD` to today's date

10. **Update registry:**
    - Edit `specs/registry.md`
    - Change Status column for this FEAT-ID to ACTIVE

### Finalize

11. **MANDATORY: Update plan status to COMPLETE**
    ```
    Edit the plan file and change the Status line:
    Status: PENDING  →  Status: COMPLETE
    ```
    This triggers the Rules Supervisor on your next response.
12. Inform user: "✅ All tasks complete. Spec updated (ACTIVE). Run `/verify`"
13. DO NOT run /verify yourself

### Migration Completion Checklist

**For migration/refactoring tasks, verify before marking COMPLETE:**

- [ ] All tests pass
- [ ] New code runs without errors
- [ ] Feature Inventory shows all features mapped to completed tasks
- [ ] Old code functionality is replicated in new code
- [ ] "Out of Scope" items were intentional removals (user confirmed), not forgotten migrations

**If you cannot check ALL boxes, the migration is INCOMPLETE. Add new tasks.**
