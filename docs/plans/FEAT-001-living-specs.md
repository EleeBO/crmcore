# Living Specs + Unified Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate living specifications, FEAT-NNN numbering, multi-agent plan review, test scenario generation, and port best components from "claude code" project into CodeRush2.

**Architecture:** Approach A — separate spec and plan files. Specs in `specs/`, plans in `docs/plans/`, linked via FEAT-ID. New commands `/specify`, `/review-plan`, `/generate-tests`. Port Rules Supervisor, Context Monitor, `/remember`, expanded `/verify`, and additional rules from "claude code" project.

**Tech Stack:** Claude Code agents (Task tool, fan-out/fan-in), Gemini API (Rules Supervisor), Playwright MCP / Chrome MCP (E2E tests), Cipher (persistent memory).

---

> **IMPORTANT:** Start with fresh context. Run `/clear` before `/implement`.

Created: 2026-02-27
Status: PENDING

> **Status Lifecycle:** PENDING → COMPLETE → VERIFIED
> - PENDING: Initial state, awaiting implementation
> - COMPLETE: All tasks implemented (set by /implement)
> - VERIFIED: Rules supervisor passed (set automatically)

## Scope

### In Scope
- Living specs infrastructure (registry, templates, directories)
- FEAT-NNN numbering replacing date-based naming
- 4 new commands: /specify, /review-plan, /generate-tests, /remember
- 3 modified commands: /plan, /implement, /verify
- 5 new agents: plan-reviewer-arch/backend/frontend, test-pm, test-writer
- 2 ported hooks: rules_supervisor.py, context_monitor.py
- 5 ported rules from "claude code" project
- Config updates: settings.local.json, CLAUDE.md, .ai-rules.md

### Out of Scope
- MCP Cipher integration (requires separate MCP setup)
- Playwright MCP installation (separate setup task)
- Application code changes (this is infrastructure only)
- Agent definition files for existing agents (keep as-is)

## Context for Implementer

- **Source project for ports:** `/Users/teterinsa/Projects/claude code/`
- **Target project:** `/Users/teterinsa/Projects/CodeRush2/`
- **Existing commands at:** `.claude/commands/` (plan.md, implement.md, verify.md, setup.md, analyze.md)
- **Existing agents at:** `.claude/agents/` (orchestrator.md, architect.md, backend.md, frontend.md, tester.md, security.md, designer.md)
- **Existing hooks at:** `.claude/hooks/` (tdd_enforcer.py, file_checker_python.py, security_guard.py, environment_checker.py, skill-enforcer.sh)
- **Settings at:** `.claude/settings.local.json`
- **All files are config/documentation (markdown, Python, JSON) — TDD is skipped per tdd-enforcement.md rules**
- **The TDD enforcer hook has a broken $PROJECT_DIR reference — Write tool may fail; use Bash heredoc as workaround**
- **Design document:** `docs/plans/2026-02-27-living-specs-design.md`

## Progress Tracking

**MANDATORY: Update this checklist as tasks complete. Change `[ ]` to `[x]`.**

### 1. Setup & Infrastructure
- [ ] 1.1 Create directory structure and registry

### 2. New Commands
- [ ] 2.1 Create /specify command
- [ ] 2.2 Create /review-plan command
- [ ] 2.3 Create /generate-tests command
- [ ] 2.4 Port /remember command

### 3. Modified Commands
- [ ] 3.1 Update /plan command
- [ ] 3.2 Update /implement command
- [ ] 3.3 Replace /verify command

### 4. New Agents
- [ ] 4.1 Create plan reviewer agents (arch, backend, frontend)
- [ ] 4.2 Create test agents (test-pm, test-writer)

### 5. Hooks & Rules
- [ ] 5.1 Port rules_supervisor.py and context_monitor.py
- [ ] 5.2 Port rule files

### 6. Configuration
- [ ] 6.1 Update settings, CLAUDE.md, .ai-rules.md

**Total Tasks:** 12 | **Completed:** 0 | **Remaining:** 12

---

## Implementation Tasks

### 1. Setup & Infrastructure

#### 1.1 Create directory structure and registry

**Objective:** Create the new directory structure for living specs, reviews, and test scenarios. Initialize the feature registry.

**Files:**
- Create: `specs/registry.md`
- Create: `specs/archive/.gitkeep`
- Create: `.claude/reviews/.gitkeep`
- Create: `tests/scenarios/.gitkeep`

**Step 1: Create directories**

```bash
mkdir -p specs/archive
mkdir -p .claude/reviews
mkdir -p tests/scenarios
```

**Step 2: Create registry.md**

Write `specs/registry.md` with this content:

```markdown
# Feature Registry

| ID | Name | Status | Spec | Plans | Created |
|----|------|--------|------|-------|---------|

## Statuses
- DRAFT — specification in progress
- ACTIVE — implemented and maintained
- MODIFIED — has pending changes
- DEPRECATED — scheduled for removal
- ARCHIVED — moved to archive/

## Next ID: FEAT-001
```

**Step 3: Create .gitkeep files**

Write empty `.gitkeep` to `specs/archive/`, `.claude/reviews/`, `tests/scenarios/`.

**Step 4: Commit**

```bash
git add specs/ .claude/reviews/.gitkeep tests/scenarios/.gitkeep
git commit -m "feat: add living specs directory structure and registry"
```

**Definition of Done:**
- [ ] `specs/registry.md` exists with correct template
- [ ] `specs/archive/`, `.claude/reviews/`, `tests/scenarios/` directories exist
- [ ] All .gitkeep files in place

---

### 2. New Commands

#### 2.1 Create /specify command

**Objective:** Create the `/specify` slash command that creates or updates living specifications with FEAT-NNN numbering.

**Files:**
- Create: `.claude/commands/specify.md`

**Step 1: Write specify.md**

Write `.claude/commands/specify.md` with frontmatter:
```yaml
---
description: Create or update a living specification for a feature
model: opus
---
```

The command must implement:

1. **Parse arguments** — extract feature name or FEAT-ID from `$ARGUMENTS`
2. **Check if FEAT exists:**
   - Read `specs/registry.md`
   - Search for matching FEAT-ID or feature name
3. **If NEW feature:**
   - Extract `Next ID` from registry (e.g., FEAT-001)
   - Collect requirements via AskUserQuestion (overview, acceptance criteria, edge cases)
   - Write `specs/FEAT-NNN-<name>.md` using living spec template
   - Update `specs/registry.md`: add row + increment Next ID
   - Set spec Status: DRAFT
4. **If EXISTING feature:**
   - Read current spec
   - Ask what changes via AskUserQuestion
   - Create delta entries (ADDED/MODIFIED/REMOVED) in Change History
   - Update Status: MODIFIED

**Key template sections:** Overview, Current State (Components, Behavior, Acceptance Criteria, Edge Cases), Change History.

**Reference:** Design doc sections 1 and 2 at `docs/plans/2026-02-27-living-specs-design.md`

**Step 2: Commit**

```bash
git add .claude/commands/specify.md
git commit -m "feat: add /specify command for living specs"
```

**Definition of Done:**
- [ ] `.claude/commands/specify.md` exists with correct frontmatter
- [ ] Handles both new and existing specs
- [ ] Uses AskUserQuestion for requirement gathering
- [ ] Updates registry.md automatically
- [ ] Living spec template matches design document

---

#### 2.2 Create /review-plan command

**Objective:** Create the `/review-plan` slash command that launches 3 parallel review agents (architect, backend, frontend) and consolidates their findings.

**Files:**
- Create: `.claude/commands/review-plan.md`

**Step 1: Write review-plan.md**

Write `.claude/commands/review-plan.md` with frontmatter:
```yaml
---
description: Multi-agent plan review with edge case discovery
model: opus
---
```

The command must implement:

1. **Read the plan file** from `$ARGUMENTS` (e.g., `docs/plans/FEAT-001-auth-system.md`)
2. **Fan-out:** Launch 3 parallel Task agents (model: sonnet):
   - Task 1: Architect review → writes `.claude/reviews/REVIEW_ARCHITECT.md`
   - Task 2: Backend review → writes `.claude/reviews/REVIEW_BACKEND.md`
   - Task 3: Frontend review → writes `.claude/reviews/REVIEW_FRONTEND.md`
   - Each agent gets: plan content + 8-item checklist + instruction to output severity/fix + 3-5 edge cases
3. **Fan-in:** After all 3 complete:
   - Read all 3 review files
   - Deduplicate findings
   - Group edge cases by category (Data, State, Concurrency, Integration, UX)
   - Produce verdict: APPROVED / NEEDS REVISION / BLOCKED
   - Write `.claude/reviews/REVIEW_CONSOLIDATED.md`
4. **If NEEDS REVISION:**
   - Present findings to user
   - Ask whether to auto-apply fixes to plan and spec
   - If yes: update plan + add edge cases to spec's Acceptance Criteria

**Agent checklists (8 items each):**

Architect: system boundaries, data flow, tech choices, scalability, security, API contracts, error handling, circular dependencies

Backend: DB schema, API endpoints, auth flow, validation rules, async operations, migration strategy, error responses, performance queries

Frontend: UI states (loading/error/empty/success), component hierarchy, Server/Client Component boundaries, form validation, optimistic updates, accessibility, responsive breakpoints, error boundaries

**Step 2: Commit**

```bash
git add .claude/commands/review-plan.md
git commit -m "feat: add /review-plan command with multi-agent review"
```

**Definition of Done:**
- [ ] `.claude/commands/review-plan.md` exists
- [ ] Launches 3 parallel Task agents with model: sonnet
- [ ] Each agent has 8-item checklist specific to their domain
- [ ] Consolidation logic deduplicates and categorizes edge cases
- [ ] Produces verdict (APPROVED/NEEDS REVISION/BLOCKED)
- [ ] Writes to `.claude/reviews/` directory

---

#### 2.3 Create /generate-tests command

**Objective:** Create the `/generate-tests` slash command that generates test scenarios from living specs using a PM → Tester → Writer → Validation pipeline.

**Files:**
- Create: `.claude/commands/generate-tests.md`

**Step 1: Write generate-tests.md**

Write `.claude/commands/generate-tests.md` with frontmatter:
```yaml
---
description: Generate test scenarios from feature specifications
model: opus
---
```

The command must implement:

1. **Parse arguments:** FEAT-ID + optional `--e2e --url=<url>`
2. **Read the spec:** `specs/FEAT-NNN-name.md`
3. **Pipeline step 1 — PM Agent (Task, model: sonnet):**
   - Extract user-facing behaviors from spec
   - Generate Given/When/Then for each scenario
   - Add edge cases and boundary conditions
   - Write: `tests/scenarios/FEAT-NNN-scenarios.md`
4. **Pipeline step 2 — Tester Agent (existing tester agent role):**
   - Read scenarios.md
   - Classify: smoke / regression / edge_case / negative / boundary
   - Prioritize: P0 / P1 / P2
   - Verify coverage vs acceptance criteria
   - Write: `tests/scenarios/FEAT-NNN-matrix.md`
5. **Pipeline step 3 — Test Writer Agent (Task, model: opus):**
   - For unit/integration: generate pytest or Jest tests
   - For E2E (if --e2e): use Playwright MCP or Chrome MCP to verify selectors live, generate Playwright tests
   - Write: `tests/unit/test_feat_NNN_*.py` and/or `tests/e2e/feat_NNN_*.spec.ts`
6. **Pipeline step 4 — Validation:**
   - Run generated tests
   - Fix failures
   - Generate coverage report: `tests/scenarios/FEAT-NNN-coverage.md`

**Step 2: Commit**

```bash
git add .claude/commands/generate-tests.md
git commit -m "feat: add /generate-tests command with PM-Tester-Writer pipeline"
```

**Definition of Done:**
- [ ] `.claude/commands/generate-tests.md` exists
- [ ] 4-step pipeline (PM → Tester → Writer → Validation)
- [ ] Supports --e2e flag for browser tests
- [ ] Writes to `tests/scenarios/` directory
- [ ] Generates executable test files in `tests/unit/` or `tests/e2e/`

---

#### 2.4 Port /remember command

**Objective:** Port the `/remember` command from the "claude code" project. This saves session learnings in Cipher before `/clear`.

**Files:**
- Source: `/Users/teterinsa/Projects/claude code/.claude/commands/remember.md`
- Create: `.claude/commands/remember.md` (adapted copy)

**Step 1: Read source file**

Read `/Users/teterinsa/Projects/claude code/.claude/commands/remember.md`

**Step 2: Write adapted version**

Copy content to `.claude/commands/remember.md`. Adaptations:
- Keep all content as-is (it's already well-structured)
- MCP server references (Cipher) stay — if Cipher isn't configured, the command gracefully informs user

**Step 3: Commit**

```bash
git add .claude/commands/remember.md
git commit -m "feat: port /remember command from claude-code project"
```

**Definition of Done:**
- [ ] `.claude/commands/remember.md` exists
- [ ] Has correct frontmatter (description, model)
- [ ] 4-step process: update plan → identify learnings → store in Cipher → confirm

---

### 3. Modified Commands

#### 3.1 Update /plan command

**Objective:** Modify `/plan` to support FEAT-ID numbering, reading from living specs, and delta-spec sections.

**Files:**
- Modify: `.claude/commands/plan.md`

**Changes required (exact line references):**

1. **Phase 0 (line ~152):** Add step to read living spec:
   - If argument is FEAT-NNN: read `specs/FEAT-NNN-*.md` for context
   - If no FEAT-ID: check if `/specify` was run, warn if not
   - Add delta from spec's latest Change History entry to plan context

2. **Phase 4 (line ~298):** Change file naming:
   - Old: `docs/plans/YYYY-MM-DD-<feature-name>.md`
   - New: `docs/plans/FEAT-NNN-<feature-name>.md`
   - If plan already exists, append `-v2`, `-v3`, etc.
   - Add `## Delta` section with ADDED/MODIFIED/REMOVED from spec

3. **Phase 5 (line ~417):** Add registry update:
   - Update `specs/registry.md` with link to new plan

4. **Plan template (line ~302):** Update template:
   - Add `Spec: specs/FEAT-NNN-name.md` after Status line
   - Add `## Delta` section before Progress Tracking
   - Change progress tracking numbering from "Task N" to "N.N" format

5. **Add SlashCommand permission** in settings for /specify, /review-plan, /generate-tests, /remember

**Step 1: Apply all changes to plan.md**

Edit `.claude/commands/plan.md` applying all 4 changes above.

**Step 2: Commit**

```bash
git add .claude/commands/plan.md
git commit -m "feat: update /plan for FEAT-ID numbering and living spec integration"
```

**Definition of Done:**
- [ ] Phase 0 reads living spec when FEAT-ID provided
- [ ] Phase 4 uses FEAT-NNN naming (no dates)
- [ ] Phase 5 updates registry.md
- [ ] Plan template includes Spec reference and Delta section
- [ ] Progress tracking uses N.N numbering

---

#### 3.2 Update /implement command

**Objective:** Add archive step to `/implement` that merges delta into the living spec after all tasks complete.

**Files:**
- Modify: `.claude/commands/implement.md`

**Changes required:**

1. **After "When All Tasks Complete" section (line ~173):** Add ARCHIVE step (steps 5-11):
   - Read the spec file path from plan header (Spec: line)
   - Read `specs/FEAT-NNN.md`
   - Merge delta from plan into spec's "Current State" section
   - Update Components list with new/modified files
   - Update Behavior section with new endpoints/functions
   - Add Change History entry (version, date, ADDED/MODIFIED/REMOVED, plan link)
   - Update spec Status: DRAFT→ACTIVE or MODIFIED→ACTIVE
   - Update `specs/registry.md` (status column)

2. **MCP Servers table (line ~39):** Keep existing, no changes needed

3. **Context Gathering (line ~49):** Add step to read spec if plan references one

**Step 1: Apply all changes to implement.md**

Edit `.claude/commands/implement.md` applying the archive step.

**Step 2: Commit**

```bash
git add .claude/commands/implement.md
git commit -m "feat: add archive step to /implement for living spec updates"
```

**Definition of Done:**
- [ ] Archive step documented after task completion
- [ ] Spec gets updated Current State, Components, Behavior
- [ ] Change History entry added automatically
- [ ] Spec Status transitions to ACTIVE
- [ ] Registry updated

---

#### 3.3 Replace /verify command

**Objective:** Replace the current 5-step `/verify` with the 10-step version from the "claude code" project.

**Files:**
- Source: `/Users/teterinsa/Projects/claude code/.claude/commands/verify.md`
- Modify: `.claude/commands/verify.md` (full replacement)

**Step 1: Read source**

Read `/Users/teterinsa/Projects/claude code/.claude/commands/verify.md` (already read above — 206 lines, 10-step process).

**Step 2: Replace verify.md**

Replace entire content of `.claude/commands/verify.md` with the "claude code" version. Adaptations:
- Keep frontmatter compatible with CodeRush2
- Replace references to `mcp__ide__getDiagnostics()` with `just test` / `just lint` commands (CodeRush2 may not have IDE MCP)
- Keep all 10 steps: unit tests → integration tests → program execution → feature parity → call chain → coverage → quality → code review → E2E → final

**Step 3: Commit**

```bash
git add .claude/commands/verify.md
git commit -m "feat: replace /verify with expanded 10-step version"
```

**Definition of Done:**
- [ ] verify.md has 10 verification steps
- [ ] Includes mandatory program execution step
- [ ] Includes code review simulation checklist
- [ ] Includes E2E verification step
- [ ] Status lifecycle: COMPLETE → VERIFIED

---

### 4. New Agents

#### 4.1 Create plan reviewer agents

**Objective:** Create 3 read-only reviewer agent definitions for plan review.

**Files:**
- Create: `.claude/agents/plan-reviewer-arch.md`
- Create: `.claude/agents/plan-reviewer-backend.md`
- Create: `.claude/agents/plan-reviewer-frontend.md`

**Step 1: Write plan-reviewer-arch.md**

Agent definition with:
- Role: Architecture reviewer
- Tools: Read, Glob, Grep only (read-only)
- 8-item checklist: system boundaries, data flow, tech choices, scalability, security, API contracts, error handling, circular dependencies
- Output format: severity (BLOCKER/MAJOR/MINOR) + section + issue + fix
- Must generate 3-5 edge cases per review
- Writes output to `.claude/reviews/REVIEW_ARCHITECT.md`

**Step 2: Write plan-reviewer-backend.md**

Same structure, backend-specific checklist:
- DB schema, API endpoints, auth flow, validation, async ops, migrations, error responses, performance

**Step 3: Write plan-reviewer-frontend.md**

Same structure, frontend-specific checklist:
- UI states, component hierarchy, Server/Client, form validation, optimistic updates, a11y, responsive, error boundaries

**Step 4: Commit**

```bash
git add .claude/agents/plan-reviewer-*.md
git commit -m "feat: add plan reviewer agents (arch, backend, frontend)"
```

**Definition of Done:**
- [ ] All 3 agent files exist with correct structure
- [ ] Each has unique 8-item checklist
- [ ] All are read-only (no Write/Edit tools)
- [ ] Output format is consistent across all 3

---

#### 4.2 Create test agents

**Objective:** Create PM and Writer agent definitions for test scenario generation.

**Files:**
- Create: `.claude/agents/test-pm.md`
- Create: `.claude/agents/test-writer.md`

**Step 1: Write test-pm.md**

Agent definition with:
- Role: Test Product Manager — acceptance criteria specialist
- Tools: Read, Glob, Grep
- Workflow: read spec → extract behaviors → write Given/When/Then → add edge cases
- Output format: YAML-structured scenarios with type/priority/given/when/then/test_data

**Step 2: Write test-writer.md**

Agent definition with:
- Role: Test code writer
- Tools: Read, Write, Edit, Bash (for running tests), Playwright/Chrome MCP tools
- Workflow: read scenarios → generate pytest/Jest/Playwright files → run and verify
- Supports both unit tests and E2E browser tests

**Step 3: Commit**

```bash
git add .claude/agents/test-pm.md .claude/agents/test-writer.md
git commit -m "feat: add test-pm and test-writer agents"
```

**Definition of Done:**
- [ ] Both agent files exist
- [ ] test-pm outputs structured scenarios
- [ ] test-writer generates executable test files
- [ ] test-writer supports both unit and E2E modes

---

### 5. Hooks & Rules

#### 5.1 Port rules_supervisor.py and context_monitor.py

**Objective:** Port both Python hooks from the "claude code" project with adaptations for living specs.

**Files:**
- Source: `/Users/teterinsa/Projects/claude code/.claude/hooks/rules_supervisor.py`
- Source: `/Users/teterinsa/Projects/claude code/.claude/hooks/context_monitor.py`
- Create: `.claude/hooks/rules_supervisor.py`
- Create: `.claude/hooks/context_monitor.py`

**Step 1: Port context_monitor.py**

Copy `/Users/teterinsa/Projects/claude code/.claude/hooks/context_monitor.py` as-is to `.claude/hooks/context_monitor.py`. No adaptations needed — it's self-contained.

**Step 2: Port rules_supervisor.py**

Copy `/Users/teterinsa/Projects/claude code/.claude/hooks/rules_supervisor.py` to `.claude/hooks/rules_supervisor.py`. Adaptations:
- Add checks for living spec status updates (spec MODIFIED→ACTIVE)
- Add check for registry.md update
- Add check for Change History entry in spec
- Keep Gemini API integration as-is

**Step 3: Commit**

```bash
git add .claude/hooks/rules_supervisor.py .claude/hooks/context_monitor.py
git commit -m "feat: port rules_supervisor and context_monitor hooks"
```

**Definition of Done:**
- [ ] Both files exist and are executable
- [ ] context_monitor.py warns at 85%, blocks at 95%
- [ ] rules_supervisor.py calls Gemini API for compliance check
- [ ] rules_supervisor.py includes living spec status checks

---

#### 5.2 Port rule files

**Objective:** Port 5 rule files from the "claude code" project.

**Files:**
- Source: `/Users/teterinsa/Projects/claude code/.claude/rules/standard/workflow-enforcement.md`
- Source: `/Users/teterinsa/Projects/claude code/.claude/rules/standard/verification-before-completion.md`
- Source: `/Users/teterinsa/Projects/claude code/.claude/rules/standard/execution-verification.md`
- Source: `/Users/teterinsa/Projects/claude code/.claude/rules/standard/git-operations.md`
- Source: `/Users/teterinsa/Projects/claude code/.claude/rules/standard/systematic-debugging.md`
- Create: `.claude/rules/standard/` (5 files)

**Step 1: Read all 5 source files**

Read each file from the source project.

**Step 2: Copy with minimal adaptations**

Copy each file to `.claude/rules/standard/`. Adaptations:
- `workflow-enforcement.md`: already read above — add living specs lifecycle (DRAFT→ACTIVE→MODIFIED→DEPRECATED→ARCHIVED) alongside plan lifecycle
- `verification-before-completion.md`: already read above — port as-is
- `execution-verification.md`, `git-operations.md`, `systematic-debugging.md`: read and port as-is

**Step 3: Commit**

```bash
git add .claude/rules/standard/workflow-enforcement.md
git add .claude/rules/standard/verification-before-completion.md
git add .claude/rules/standard/execution-verification.md
git add .claude/rules/standard/git-operations.md
git add .claude/rules/standard/systematic-debugging.md
git commit -m "feat: port 5 rule files from claude-code project"
```

**Definition of Done:**
- [ ] All 5 rule files exist in `.claude/rules/standard/`
- [ ] workflow-enforcement.md includes living spec lifecycle
- [ ] verification-before-completion.md has evidence-before-claims rule
- [ ] No broken references to tools or paths

---

### 6. Configuration

#### 6.1 Update settings, CLAUDE.md, .ai-rules.md

**Objective:** Update configuration files to register new commands, hooks, and document the new workflow.

**Files:**
- Modify: `.claude/settings.local.json`
- Modify: `CLAUDE.md`
- Modify: `.ai-rules.md`

**Step 1: Update settings.local.json**

Add to `permissions.allow`:
```json
"SlashCommand(/specify:*)",
"SlashCommand(/review-plan:*)",
"SlashCommand(/generate-tests:*)",
"SlashCommand(/remember:*)"
```

Add to `hooks.PostToolUse[0].hooks` (after security_guard):
```json
{
  "type": "command",
  "command": "python3 $PROJECT_DIR/.claude/hooks/context_monitor.py"
}
```

Add new `hooks.Stop` section:
```json
"Stop": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "python3 $PROJECT_DIR/.claude/hooks/rules_supervisor.py"
      }
    ]
  }
]
```

**Step 2: Update CLAUDE.md**

Add to Workflow section (after line 24):
```markdown
## Workflow

1. **Setup**: `/setup` - Check environment, install dependencies
2. **Specify**: `/specify` - Create/update living specification
3. **Plan**: `/plan FEAT-NNN` - Create implementation plan from spec
4. **Review**: `/review-plan` - Multi-agent plan review
5. **Implement**: `/implement` - Execute plan with TDD
6. **Verify**: `/verify` - 10-step verification
7. **Test**: `/generate-tests FEAT-NNN` - Generate test scenarios
8. **Remember**: `/remember` - Save learnings before /clear
```

Add new Agents rows:
```markdown
| Plan Reviewer (x3) | Reviewer | Plan review (arch/backend/frontend) |
| Test PM | QA PM | Acceptance criteria from specs |
| Test Writer | QA Dev | Executable test generation |
```

Add new section after Hooks:
```markdown
## Living Specs

Feature specifications persist in `specs/` directory:
- `specs/registry.md` — central FEAT-NNN registry
- `specs/FEAT-NNN-name.md` — living specification
- Lifecycle: DRAFT → ACTIVE → MODIFIED → DEPRECATED → ARCHIVED
```

Update directory structure to include `specs/` and `tests/scenarios/`.

Add new hooks: Rules Supervisor, Context Monitor.

**Step 3: Update .ai-rules.md**

Update Agent Workflow section (line ~37):
```markdown
## Agent Workflow

1. /setup     - Check environment (first time)
2. /analyze   - Analyze existing platform (for redesign)
3. /specify   - Create/update living specification
4. /plan      - Create plan from spec (FEAT-NNN)
5. /review-plan - Multi-agent plan review
6. /implement - Execute with TDD
7. /verify    - 10-step verification
8. /generate-tests - Create test scenarios
9. /remember  - Save learnings before /clear
```

**Step 4: Commit**

```bash
git add .claude/settings.local.json CLAUDE.md .ai-rules.md
git commit -m "feat: update config for living specs workflow"
```

**Definition of Done:**
- [ ] settings.local.json has new SlashCommand permissions
- [ ] settings.local.json has context_monitor in PostToolUse
- [ ] settings.local.json has rules_supervisor in Stop hook
- [ ] CLAUDE.md documents new workflow, agents, living specs
- [ ] .ai-rules.md has updated agent workflow
- [ ] All 8 commands listed in workflow

---

## Testing Strategy

- **Manual verification:** After each task, run the relevant command and verify it produces expected output
- **Hook testing:** Run `python3 .claude/hooks/context_monitor.py` directly to verify it doesn't crash
- **Command testing:** Run `/specify test-feature` in a new Claude Code session to verify end-to-end
- **Integration test:** Run full workflow `/specify → /plan → /review-plan → /implement → /verify` on a small feature

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| TDD hook blocks .md file writes | High | Low | Use Bash heredoc workaround or fix $PROJECT_DIR |
| Gemini API key not configured | Medium | Medium | rules_supervisor.py returns 0 (silent) without key |
| Cipher MCP not available | Medium | Low | /remember gracefully informs user |
| Registry.md concurrent edits | Low | Medium | Sequential command execution prevents this |

## Open Questions

- Fix $PROJECT_DIR in TDD enforcer hook? (Currently broken — can't find tdd_enforcer.py)
- Should /generate-tests default to Playwright MCP or Chrome MCP for E2E?
