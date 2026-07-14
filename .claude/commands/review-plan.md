---
description: Multi-agent plan review with edge case discovery
model: opus
---
# REVIEW-PLAN MODE: Multi-Agent Plan Review

Launch 3 parallel review agents (Architect, Backend, Frontend) to review an implementation plan, then consolidate findings into a single verdict.

**Input:** `$ARGUMENTS` — path to the plan file (e.g., `docs/plans/FEAT-001-auth-system.md`)

---

## Step 1: Load Plan and Spec

1. **Read the plan file:**
   ```
   Read(file_path="$ARGUMENTS")
   ```
   Store the full plan content as `PLAN_CONTENT`.

2. **Extract spec link (if present):**
   - Look for a line like `Spec: specs/FEAT-NNN-*.md` or a markdown link to a spec file in the plan header/summary.
   - If found, read the spec file:
     ```
     Read(file_path="<spec-path>")
     ```
     Store as `SPEC_CONTENT`.
   - If no spec link found, set `SPEC_CONTENT` to `"(No linked specification found)"`.

3. **Ensure the reviews directory exists:**
   ```
   Bash(command="mkdir -p .claude/reviews")
   ```

---

## Step 2: Fan-Out — Launch 3 Parallel Review Agents

Launch all 3 Task agents **in parallel** (in the same response). Each agent uses `model: sonnet` for cost efficiency.

**CRITICAL:** All 3 Task calls MUST be made in the same response so they run concurrently. Each Task receives the full plan and spec content inline (not file paths).

### Task 1: Architect Review

```
Task(
  subagent_type="general-purpose",
  model="sonnet",
  prompt="""
You are an Architect reviewing an implementation plan. Write your review to `.claude/reviews/REVIEW_ARCHITECT.md`.

## Plan Content

<plan>
{PLAN_CONTENT}
</plan>

## Spec Content

<spec>
{SPEC_CONTENT}
</spec>

## Your Review Checklist (8 items)

Evaluate each item as PASS or FAIL with severity (BLOCKER/MAJOR/MINOR):

1. **System Boundaries** — Are service/module boundaries clearly defined? Are responsibilities well-separated?
2. **Data Flow** — Is the data flow between components explicit and complete? Are transformations documented?
3. **Technology Choices** — Are tech choices justified and appropriate? Any unnecessary complexity?
4. **Scalability** — Will the design handle growth? Are bottlenecks identified?
5. **Security** — Are auth, authz, input validation, and secrets management addressed?
6. **API Contracts** — Are interfaces between components well-defined? Request/response schemas clear?
7. **Error Handling** — Is the error handling strategy comprehensive? Failure modes documented?
8. **Circular Dependencies** — Are there circular dependency risks between modules/services?

## Instructions

1. Evaluate each checklist item against the plan and spec.
2. For any FAIL item, assign a severity (BLOCKER, MAJOR, or MINOR) and describe the issue and recommended fix.
3. Identify 3-5 edge cases the plan does not address. Categorize each as: Data, State, Concurrency, Integration, or UX.
4. Determine your overall verdict: PASS (all items pass or only MINOR issues) or FAIL (any BLOCKER or MAJOR issues).
5. Write your review to `.claude/reviews/REVIEW_ARCHITECT.md` using the exact format below.

## Output Format

Write the file `.claude/reviews/REVIEW_ARCHITECT.md` with this exact structure:

```markdown
# Architect Review

Plan: {plan file path}
Date: {today's date YYYY-MM-DD}
Verdict: PASS / FAIL

## Checklist

| # | Item | Status | Severity | Details |
|---|------|--------|----------|---------|
| 1 | System Boundaries | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 2 | Data Flow | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 3 | Technology Choices | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 4 | Scalability | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 5 | Security | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 6 | API Contracts | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 7 | Error Handling | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 8 | Circular Dependencies | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |

## Issues

### [Issue N]: [Title]
- **Severity:** BLOCKER / MAJOR / MINOR
- **Section:** [plan section where the issue is]
- **Issue:** [description of the problem]
- **Fix:** [recommended fix]

(Repeat for each FAIL item. Omit this section if all items PASS.)

## Edge Cases

1. [Category]: [description]
2. [Category]: [description]
3. [Category]: [description]
(3-5 edge cases)
```

IMPORTANT: Use the Write tool to create the file at `.claude/reviews/REVIEW_ARCHITECT.md`. Do NOT just output the review — you must write it to that file.
"""
)
```

### Task 2: Backend Review

```
Task(
  subagent_type="general-purpose",
  model="sonnet",
  prompt="""
You are a Backend Engineer reviewing an implementation plan. Write your review to `.claude/reviews/REVIEW_BACKEND.md`.

## Plan Content

<plan>
{PLAN_CONTENT}
</plan>

## Spec Content

<spec>
{SPEC_CONTENT}
</spec>

## Your Review Checklist (8 items)

Evaluate each item as PASS or FAIL with severity (BLOCKER/MAJOR/MINOR):

1. **DB Schema** — Is the database schema well-designed? Are relationships, indexes, and constraints defined?
2. **API Endpoints** — Are all endpoints listed with methods, paths, request/response schemas, and status codes?
3. **Auth Flow** — Is the authentication/authorization flow complete and secure?
4. **Validation Rules** — Are input validation rules defined for all user-facing inputs?
5. **Async Operations** — Are background tasks, queues, and async flows identified and handled?
6. **Migration Strategy** — Is there a clear database migration plan? Are rollback scenarios covered?
7. **Error Responses** — Are error response formats consistent? Are HTTP status codes appropriate?
8. **Performance Queries** — Are potentially expensive queries identified? Are indexes and pagination planned?

## Instructions

1. Evaluate each checklist item against the plan and spec.
2. For any FAIL item, assign a severity (BLOCKER, MAJOR, or MINOR) and describe the issue and recommended fix.
3. Identify 3-5 edge cases the plan does not address. Categorize each as: Data, State, Concurrency, Integration, or UX.
4. Determine your overall verdict: PASS (all items pass or only MINOR issues) or FAIL (any BLOCKER or MAJOR issues).
5. Write your review to `.claude/reviews/REVIEW_BACKEND.md` using the exact format below.

## Output Format

Write the file `.claude/reviews/REVIEW_BACKEND.md` with this exact structure:

```markdown
# Backend Review

Plan: {plan file path}
Date: {today's date YYYY-MM-DD}
Verdict: PASS / FAIL

## Checklist

| # | Item | Status | Severity | Details |
|---|------|--------|----------|---------|
| 1 | DB Schema | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 2 | API Endpoints | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 3 | Auth Flow | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 4 | Validation Rules | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 5 | Async Operations | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 6 | Migration Strategy | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 7 | Error Responses | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 8 | Performance Queries | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |

## Issues

### [Issue N]: [Title]
- **Severity:** BLOCKER / MAJOR / MINOR
- **Section:** [plan section where the issue is]
- **Issue:** [description of the problem]
- **Fix:** [recommended fix]

(Repeat for each FAIL item. Omit this section if all items PASS.)

## Edge Cases

1. [Category]: [description]
2. [Category]: [description]
3. [Category]: [description]
(3-5 edge cases)
```

IMPORTANT: Use the Write tool to create the file at `.claude/reviews/REVIEW_BACKEND.md`. Do NOT just output the review — you must write it to that file.
"""
)
```

### Task 3: Frontend Review

```
Task(
  subagent_type="general-purpose",
  model="sonnet",
  prompt="""
You are a Frontend Engineer reviewing an implementation plan. Write your review to `.claude/reviews/REVIEW_FRONTEND.md`.

## Plan Content

<plan>
{PLAN_CONTENT}
</plan>

## Spec Content

<spec>
{SPEC_CONTENT}
</spec>

## Your Review Checklist (8 items)

Evaluate each item as PASS or FAIL with severity (BLOCKER/MAJOR/MINOR):

1. **UI States** — Are all UI states defined? (loading, error, empty, success, partial)
2. **Component Hierarchy** — Is the component tree clear? Are responsibilities well-distributed?
3. **Server/Client Component Boundaries** — Are Server Components and Client Components correctly separated? Is "use client" usage minimized?
4. **Form Validation** — Are client-side and server-side validation rules defined? Are error messages specified?
5. **Optimistic Updates** — Are optimistic UI patterns defined where appropriate? Are rollback strategies included?
6. **Accessibility** — Are ARIA labels, keyboard navigation, screen reader support, and focus management addressed?
7. **Responsive Breakpoints** — Are breakpoints defined? Is the mobile-first approach followed?
8. **Error Boundaries** — Are React Error Boundaries placed at appropriate levels? Are fallback UIs defined?

## Instructions

1. Evaluate each checklist item against the plan and spec.
2. For any FAIL item, assign a severity (BLOCKER, MAJOR, or MINOR) and describe the issue and recommended fix.
3. Identify 3-5 edge cases the plan does not address. Categorize each as: Data, State, Concurrency, Integration, or UX.
4. Determine your overall verdict: PASS (all items pass or only MINOR issues) or FAIL (any BLOCKER or MAJOR issues).
5. Write your review to `.claude/reviews/REVIEW_FRONTEND.md` using the exact format below.

## Output Format

Write the file `.claude/reviews/REVIEW_FRONTEND.md` with this exact structure:

```markdown
# Frontend Review

Plan: {plan file path}
Date: {today's date YYYY-MM-DD}
Verdict: PASS / FAIL

## Checklist

| # | Item | Status | Severity | Details |
|---|------|--------|----------|---------|
| 1 | UI States | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 2 | Component Hierarchy | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 3 | Server/Client Component Boundaries | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 4 | Form Validation | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 5 | Optimistic Updates | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 6 | Accessibility | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 7 | Responsive Breakpoints | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |
| 8 | Error Boundaries | PASS/FAIL | -/BLOCKER/MAJOR/MINOR | [notes] |

## Issues

### [Issue N]: [Title]
- **Severity:** BLOCKER / MAJOR / MINOR
- **Section:** [plan section where the issue is]
- **Issue:** [description of the problem]
- **Fix:** [recommended fix]

(Repeat for each FAIL item. Omit this section if all items PASS.)

## Edge Cases

1. [Category]: [description]
2. [Category]: [description]
3. [Category]: [description]
(3-5 edge cases)
```

IMPORTANT: Use the Write tool to create the file at `.claude/reviews/REVIEW_FRONTEND.md`. Do NOT just output the review — you must write it to that file.
"""
)
```

---

## Step 3: Fan-In — Consolidate Reviews

**Wait for all 3 Task agents to complete**, then proceed.

1. **Read all 3 review files:**
   ```
   Read(file_path=".claude/reviews/REVIEW_ARCHITECT.md")
   Read(file_path=".claude/reviews/REVIEW_BACKEND.md")
   Read(file_path=".claude/reviews/REVIEW_FRONTEND.md")
   ```

2. **Parse each review:**
   - Extract the verdict (PASS/FAIL)
   - Count issues by severity (BLOCKER, MAJOR, MINOR)
   - Collect all issues with their details
   - Collect all edge cases

3. **Deduplicate issues:**
   - Compare issues across all 3 reviews
   - If two or more agents flag the same issue (similar section + similar description), merge them into one entry and note which agents flagged it
   - Keep the highest severity if agents disagree

4. **Group edge cases by category:**
   - **Data** — Data integrity, validation, corruption, encoding
   - **State** — Race conditions in UI state, stale data, caching
   - **Concurrency** — Parallel requests, deadlocks, resource contention
   - **Integration** — Cross-service failures, API versioning, contract breakage
   - **UX** — Confusing flows, accessibility gaps, error messaging

5. **Determine consolidated verdict:**
   - **BLOCKED** — Any review has a BLOCKER issue
   - **NEEDS REVISION** — Any review has a MAJOR issue (but no BLOCKERS)
   - **APPROVED** — All reviews PASS with only MINOR issues or no issues

6. **Write the consolidated review** to `.claude/reviews/REVIEW_CONSOLIDATED.md` using this exact format:

```markdown
# Consolidated Review

Plan: {plan file path from $ARGUMENTS}
Date: {today's date YYYY-MM-DD}
Verdict: APPROVED / NEEDS REVISION / BLOCKED

## Summary
- Architect: PASS/FAIL (N issues)
- Backend: PASS/FAIL (N issues)
- Frontend: PASS/FAIL (N issues)
- Total issues: N (B blockers, M major, m minor)

## All Issues (deduplicated)

### BLOCKERS
(List all BLOCKER-severity issues, or "None" if there are no blockers.)

### MAJOR
(List all MAJOR-severity issues, or "None" if there are no major issues.)

### MINOR
(List all MINOR-severity issues, or "None" if there are no minor issues.)

## Edge Cases by Category

### Data
- [edge case description]

### State
- [edge case description]

### Concurrency
- [edge case description]

### Integration
- [edge case description]

### UX
- [edge case description]

## Recommended Actions
1. [Prioritized action to address BLOCKER or MAJOR issues]
2. [Next action]
...
```

---

## Step 4: Present Results and Handle Revisions

### If verdict is APPROVED:

Report to the user:
```
Plan review complete: APPROVED

All 3 reviewers passed. The plan is ready for implementation.
Review details: .claude/reviews/REVIEW_CONSOLIDATED.md

Next step: Run /implement $ARGUMENTS
```

### If verdict is NEEDS REVISION or BLOCKED:

1. **Present the consolidated findings** to the user. Show:
   - The verdict
   - All BLOCKER and MAJOR issues with their recommended fixes
   - The edge cases grouped by category

2. **Ask the user** using AskUserQuestion:
   ```
   The plan has issues that need attention.

   Questions:
   1. "Should I auto-apply the recommended fixes to the plan and spec?"
      - Yes, apply all recommended fixes automatically
      - No, I will fix them manually
      - Let me review the individual agent reviews first
   ```

3. **If user chooses auto-apply:**
   - Read the plan file again (it may have changed)
   - For each BLOCKER and MAJOR issue, apply the recommended fix to the relevant section of the plan
   - If a spec file exists, add the discovered edge cases to the spec's "Acceptance Criteria" and "Edge Cases" sections
   - Update the spec's Change History with a new version entry:
     ```markdown
     ### vN (YYYY-MM-DD) — Post-review edge cases
     - ADDED: Edge cases from multi-agent review
     ```
   - Report what was changed

4. **If user chooses manual review:**
   - Point the user to the individual review files:
     - `.claude/reviews/REVIEW_ARCHITECT.md`
     - `.claude/reviews/REVIEW_BACKEND.md`
     - `.claude/reviews/REVIEW_FRONTEND.md`
     - `.claude/reviews/REVIEW_CONSOLIDATED.md`
   - Suggest re-running `/review-plan` after fixes are applied

---

## Critical Rules

1. **All 3 Task agents MUST be launched in the same response** — This ensures they run in parallel, not sequentially.
2. **Each Task agent uses `model: sonnet`** — Cost efficiency for the review sub-tasks.
3. **Pass full content, not file paths** — Each agent receives the plan and spec content inline in its prompt so it does not need to read files.
4. **Each agent writes its own file** — Architect writes `REVIEW_ARCHITECT.md`, Backend writes `REVIEW_BACKEND.md`, Frontend writes `REVIEW_FRONTEND.md`.
5. **Deduplication is mandatory** — The consolidated review must not repeat the same issue found by multiple agents.
6. **Edge cases must be categorized** — Every edge case goes into one of: Data, State, Concurrency, Integration, UX.
7. **Verdict logic is strict:**
   - Any BLOCKER => BLOCKED
   - Any MAJOR (no BLOCKERS) => NEEDS REVISION
   - Only MINOR or no issues => APPROVED
8. **Do NOT modify the plan or spec unless the user explicitly approves auto-apply.**
9. **Always use today's date** in all review files.
10. **Read before writing** — Always re-read files before applying fixes in the auto-apply step.
