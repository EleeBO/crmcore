---
description: Create a detailed implementation plan with exploration for Claude CodePro
model: opus
---
# PLAN MODE: Five-Phase Planning Process

> **WARNING: DO NOT use the built-in `ExitPlanMode` or `EnterPlanMode` tools.**
> This project has its own planning workflow using `/plan`, `/implement`, and `/verify` slash commands.
> The built-in Claude Code plan mode tools write to different paths and are incompatible.
> When planning is complete, simply inform the user and wait for confirmation - no special tool needed.

## MCP Servers - Use Throughout Planning

| Server | Purpose | When to Use |
|--------|---------|-------------|
| **Context7** | Up-to-date docs | Get current library documentation, API references |
| **Greptile** | AI code search | Semantic code search, find patterns, understand codebase |
| **Exa** | Web search & code examples | Research libraries, find documentation |
| **Brave Search** | General web search | Documentation, tutorials, best practices |

**Start planning with:** `use context7` for library docs, Greptile for codebase understanding.


## Using AskUserQuestion - Core Planning Tool

**The AskUserQuestion tool is essential for effective planning.** Questions are grouped into batches so users answer related questions together without interruption.

### Question Batching Strategy

Questions are consolidated into two batches for a smooth user experience:

| Batch | When | Purpose |
|-------|------|---------|
| **Batch 1** | Phase 0 (before exploration) | Clarify task, scope, priorities |
| **Batch 2** | Phase 2 (after exploration) | Architecture choices, design decisions |

**Don't scatter questions across phases** - gather them and present together.

### When to Use AskUserQuestion

| Situation | Example Question |
|-----------|------------------|
| **Unclear requirements** | "Should this feature support batch processing or single items only?" |
| **Multiple valid approaches** | Present 2-3 options with trade-offs for user to choose |
| **Ambiguous scope** | "Should we include error recovery, or fail fast?" |
| **Technology choices** | "Prefer async/await or callbacks for this integration?" |
| **Priority decisions** | "Performance or simplicity - which matters more here?" |
| **Missing domain knowledge** | "How does the existing auth flow work in production?" |

### How to Structure Questions

**Use the AskUserQuestion tool with clear options:**
```
Question: "Which authentication approach should we use?"
Options:
- Option A: JWT tokens (stateless, scalable, requires token refresh logic)
- Option B: Session-based (simpler, requires session storage)
- Option C: OAuth integration (most secure, more complex setup)
```

**Key principles:**
- Present options, not open-ended questions when possible
- Include trade-offs for each option
- **Batch related questions together** - don't interrupt user flow
- Don't proceed with assumptions - ASK


## Extending Existing Plans

**When adding tasks to existing plan:**

1. Load existing plan: `Read(file_path="docs/plans/...")`
2. Parse structure (architecture, completed tasks, pending tasks)
3. Check git status for partially completed work
4. Verify new tasks are compatible with existing architecture
5. Check total: If original + new > 12 tasks, suggest splitting
6. Mark new tasks with `[NEW]` prefix
7. Update total count: `Total Tasks: X (Originally: Y)`
8. Add extension history: `> Extended [Date]: Tasks X-Y for [feature]`


## ⚠️ CRITICAL: Migration/Refactoring Tasks

**When the task involves migrating, refactoring, or replacing existing code, you MUST complete these additional steps to prevent missing features.**

### Mandatory Feature Inventory (Phase 1.5)

**After exploration but BEFORE creating tasks:**

1. **List ALL files being replaced:**
   ```markdown
   ## Feature Inventory - Files Being Replaced

   | Old File | Functions/Classes | Status |
   |----------|-------------------|--------|
   | `old/module1.py` | `func_a()`, `func_b()`, `ClassX` | ⬜ Not mapped |
   | `old/module2.py` | `func_c()`, `func_d()` | ⬜ Not mapped |
   ```

2. **Map EVERY function/feature to a new task:**
   ```markdown
   ## Feature Mapping - Old → New

   | Old Feature | New Location | Task # |
   |-------------|--------------|--------|
   | `module1.func_a()` | `new/step1.py` | Task 3 |
   | `module1.func_b()` | `new/step1.py` | Task 3 |
   | `module2.func_c()` | `new/step2.py` | Task 5 |
   | `module2.func_d()` | ❌ MISSING | ⚠️ NEEDS TASK |
   ```

3. **Verify 100% coverage before proceeding:**
   - Every row must have a Task # or explicit "Out of Scope" justification
   - "Out of Scope" means the feature is INTENTIONALLY REMOVED (with user confirmation)
   - "Out of Scope" does NOT mean "migrate as-is" - that still needs a task!

### "Out of Scope" Clarification

**CRITICAL: "Out of Scope" has a precise meaning:**

| Phrase | Meaning | Requires Task? |
|--------|---------|----------------|
| "Out of Scope: Changes to X" | X will be migrated AS-IS, no modifications | ✅ YES - migration task |
| "Out of Scope: Feature X" | X is intentionally REMOVED/not included | ❌ NO - but needs user confirmation |
| "Out of Scope: New features for X" | X migrates as-is, no NEW features added | ✅ YES - migration task |

**When in doubt, ASK THE USER:**
```
"The old code has [feature]. Should we:
A) Migrate it as-is (needs implementation task)
B) Intentionally remove it (truly out of scope)
C) Improve it (new feature, needs implementation task)"
```

### Pre-Task Verification Gate

**Before finalizing Phase 3 (Implementation Planning), verify:**

- [ ] All old files listed in Feature Inventory
- [ ] All functions/classes from old files identified
- [ ] Every feature mapped to a task OR explicitly marked "REMOVED" with user confirmation
- [ ] No row in Feature Mapping has "⬜ Not mapped" status
- [ ] User has confirmed any features marked for removal

**If any checkbox is unchecked, DO NOT proceed to Phase 4.**

---

## Creating New Plans

### Phase 0: Task Understanding & Clarification

**If argument includes FEAT-ID (e.g., `/plan FEAT-001`):**
1. Read the living spec: `Glob(pattern="specs/FEAT-*-*.md")` then `Read(file_path="specs/FEAT-NNN-*.md")`
2. Use the spec's Overview, Acceptance Criteria, and Edge Cases as the primary requirements source
3. If spec has Change History with Status: MODIFIED, extract the latest delta (ADDED/MODIFIED/REMOVED) — this is what needs to be implemented
4. Skip Question Batch 1 (requirements are already in the spec) unless clarification is needed

**If no FEAT-ID provided:**
- Plan works as before (user describes the task)
- Suggest: "Consider running `/specify` first to create a living spec for better traceability"

**First, clearly state your understanding of the task.**

Before any exploration:
1. Restate what the user is asking for in your own words
2. Identify the core problem being solved
3. List any assumptions you're making

**Then gather all clarifications needed (Question Batch 1):**

Use AskUserQuestion to ask everything upfront in a single interaction:

```
I want to confirm my understanding and clarify a few things:

Questions:
1. "Is my understanding correct?"
   - Yes, that's correct
   - Partially correct (please clarify)
   - No, let me explain

2. "What's the priority for this feature?"
   - Performance (fast, optimized)
   - Simplicity (easy to maintain)
   - Flexibility (extensible)

3. "Should error handling be comprehensive or minimal?"
   - Comprehensive (recovery, retries, detailed logging)
   - Basic (fail fast, simple error messages)
```

**Don't proceed to exploration until clarifications are complete.**

### Phase 1: Exploration

**Explore the codebase systematically.** Run explorations **one at a time** (sequentially, not in parallel).

**Exploration areas (in order):**

1. **Architecture** - Project structure, entry points, how components connect
2. **Similar Features** - Existing patterns that relate to the task, what can be reused
3. **Dependencies** - Imports, modules, what will be impacted
4. **Tests** - Test infrastructure, existing patterns, available fixtures

**For each area:**
- Use Task tool with `subagent_type='Explore'` OR search directly with Grep/Glob
- Document hypotheses (not conclusions)
- Note full file paths for relevant code
- Track questions that remain unanswered

**Also query memory and external sources:**
- Context7: `use context7` for library documentation
- Greptile: `mcp__plugin_greptile_greptile__query_repository` for semantic code search

**After explorations complete:**
1. Read each identified file to verify hypotheses
2. Build a complete mental model of current architecture
3. Identify integration points and potential risks
4. Note reusable patterns

### Phase 2: Design Decisions

**Present findings and gather all design decisions (Question Batch 2).**

Summarize what you found, then use AskUserQuestion with all decisions at once:

```
Based on my exploration, I found [summary of key findings].

I have some design questions:

Questions:
1. "Which architecture approach should we use?"
   - Option A: [description + trade-offs]
   - Option B: [description + trade-offs]
   - Option C: [description + trade-offs]

2. "How should we handle [specific concern found during exploration]?"
   - Option A: [approach]
   - Option B: [approach]

3. "The existing [component] uses [pattern]. Should we follow it or try something different?"
   - Follow existing pattern (consistency)
   - Use new approach (explain why)
```

**After user answers:**
- Summarize the chosen design approach
- Confirm: "Does this design work for your needs?"
- Don't proceed until design is validated

### Phase 3: Implementation Planning

**CRITICAL: Task Count Limit**
- **Maximum: 10-12 tasks per plan**
- If breakdown exceeds 12 tasks, use AskUserQuestion to ask user to split into multiple features

**OpenSpec-Style Task Numbering:**
```
Section.Task format:
1. Setup & Configuration
   - [ ] 1.1 First setup task
   - [ ] 1.2 Second setup task
2. Core Implementation
   - [ ] 2.1 First core task
   - [ ] 2.2 Second core task
3. Integration
   - [ ] 3.1 Integration task
```

**Task Structure:**
```markdown
### 1. [Capability Name]

#### 1.1 [Task Name]

**Objective:** [1-2 sentences describing what to build]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py`
- Test: `tests/exact/path/to/test.py`

**Implementation Steps:**
1. Write failing test - Define expected behavior
2. Implement minimal code - Make test pass
3. Verify execution - Run actual program
4. Integration test - Test with other components

**Definition of Done:**
- [ ] All tests pass (unit, integration if applicable)
- [ ] No diagnostics errors (linting, type checking)
- [ ] Code functions correctly with real data
- [ ] Edge cases handled appropriately
- [ ] Error messages are clear and actionable
```

**Zero-context assumption:**
- Assume implementer knows nothing about codebase
- Provide exact file paths
- Explain domain concepts
- List integration points
- Reference similar patterns in codebase

### Phase 4: Documentation

**Save plan to:**
- If FEAT-ID provided: `docs/plans/FEAT-NNN-<feature-name>.md`
  - If plan already exists, append version: `FEAT-NNN-<feature-name>-v2.md`, `-v3.md`, etc.
- If no FEAT-ID: `docs/plans/YYYY-MM-DD-<feature-name>.md` (legacy format)

**Required plan template:**

```markdown
# [Feature Name] Implementation Plan

> **IMPORTANT:** Start with fresh context. Run `/clear` before `/implement`.

Created: [Date]
Status: PENDING
Spec: specs/FEAT-NNN-name.md (if applicable)

> **Status Lifecycle:** PENDING → COMPLETE → VERIFIED
> - PENDING: Initial state, awaiting implementation
> - COMPLETE: All tasks implemented (set by /implement)
> - VERIFIED: Rules supervisor passed (set automatically)

## Summary
**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about chosen approach]

**Tech Stack:** [Key technologies/libraries]

## Scope

### In Scope
- [What WILL be changed/built]
- [Specific components affected]

### Out of Scope
- [What will NOT be changed]
- [Explicit boundaries]

## Prerequisites
- [Any requirements before starting]
- [Dependencies that must exist]
- [Environment setup needed]

## Context for Implementer
- [Key codebase convention or pattern]
- [Domain knowledge needed]
- [Integration points or dependencies]

## Delta (from spec)

> **Changes from latest spec modification. Only present for MODIFIED specs.**

- ADDED: [items from spec's latest Change History entry]
- MODIFIED: [items changed]
- REMOVED: [items removed]

## Feature Inventory (FOR MIGRATION/REFACTORING ONLY)

> **Include this section when replacing existing code. Delete if not applicable.**

### Files Being Replaced

| Old File | Functions/Classes | Mapped to Task |
|----------|-------------------|----------------|
| `old/file1.py` | `func_a()`, `func_b()` | 2.1 |
| `old/file2.py` | `ClassX`, `func_c()` | 2.2, 2.3 |

### Feature Mapping Verification

- [ ] All old files listed above
- [ ] All functions/classes identified
- [ ] Every feature has a task number
- [ ] No features accidentally omitted

**⚠️ If any feature shows "❌ MISSING", add a task before implementation!**

## Progress Tracking

**MANDATORY: Update this checklist as tasks complete. Change `[ ]` to `[x]`.**

### 1. Setup & Configuration
- [ ] 1.1 [Task summary]
- [ ] 1.2 [Task summary]

### 2. Core Implementation
- [ ] 2.1 [Task summary]
- [ ] 2.2 [Task summary]

### 3. Integration & Testing
- [ ] 3.1 [Task summary]

**Total Tasks:** [Number] | **Completed:** 0 | **Remaining:** [Number]

## Implementation Tasks

### 1. Setup & Configuration

#### 1.1 [Task Name]
[Full task structure from Phase 3]

#### 1.2 [Task Name]
[Full task structure from Phase 3]

### 2. Core Implementation

#### 2.1 [Task Name]
[Full task structure from Phase 3]

### 3. Integration & Testing

#### 3.1 [Task Name]
[Full task structure from Phase 3]

## Testing Strategy
- Unit tests: [What to test in isolation]
- Integration tests: [What to test together]
- Manual verification: [Steps to verify manually]

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| [Risk 1] | Low/Med/High | Low/Med/High | [How to mitigate] |

## Open Questions
- [Any remaining questions for the user]
- [Decisions deferred to implementation]

---
**USER: Please review this plan. Edit any section directly, then confirm to proceed.**
```
### Phase 5: Implementation Handoff

**After saving plan:**

1. **Index in Greptile:** Ensure repository is indexed for future code searches
2. **Inform user:** "Plan saved to docs/plans/FEAT-NNN-<feature>.md" (or legacy path if no FEAT-ID)
3. **Request review:** Ask user to review and edit the plan
4. **Wait for explicit confirmation** before proceeding
5. **Update registry:** If FEAT-ID provided, update `specs/registry.md`:
   - Add or update the Plans column with link to the new plan
   - Example: `[v1](../docs/plans/FEAT-001-auth-system.md)`

**After user confirms:**

1. **Re-read the plan file completely** - User may have edited it
2. **Note any changes** the user made
3. **Acknowledge changes** before proceeding
4. Provide next steps:
   "Ready for implementation. Options:
   - Run `/review-plan docs/plans/FEAT-NNN-<feature>.md` for multi-agent review
   - Run `/clear` then `/implement docs/plans/FEAT-NNN-<feature>.md` to start implementing"

**DO NOT write or edit any implementation files until confirmed.**


## Critical Rules

These rules are non-negotiable:

1. **USE AskUserQuestion when uncertain** - Don't guess, ask the user
2. **Batch questions together** - Don't interrupt user with scattered questions
3. **Run explorations sequentially** - One at a time, never in parallel
4. **NEVER write implementation code during planning** - Planning and implementing are separate
5. **NEVER assume - verify by reading files** - Hypotheses must be confirmed
6. **ALWAYS get user confirmation before implementing** - User owns the decision
7. **ALWAYS re-read the plan after user confirms** - They may have edited it
8. **The plan must be detailed enough that another developer could follow it**
9. **NEVER use built-in ExitPlanMode or EnterPlanMode tools** - This project uses custom `/plan`, `/implement`, `/verify` slash commands. The built-in plan mode tools are incompatible with this workflow.
10. **FOR MIGRATIONS: Create Feature Inventory BEFORE tasks** - List every file, function, and class being replaced. Map each to a task. No unmapped features allowed.
11. **"Out of Scope" ≠ "Don't implement"** - "Out of Scope: Changes to X" means migrate X as-is (still needs a task). Only "Out of Scope: Remove X" means no task needed (requires user confirmation).
