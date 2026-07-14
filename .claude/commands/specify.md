---
description: Create or update a living specification for a feature
model: opus
---
# SPECIFY MODE: Living Specification Management

Create or update living specifications with FEAT-NNN numbering. Specifications evolve alongside implementation and serve as the single source of truth for each feature.

**Input:** `$ARGUMENTS` — either a feature name (for new specs) or a FEAT-ID (e.g., FEAT-001) to update an existing spec.

## Step 1: Parse Arguments and Determine Mode

1. **Read the registry:** `Read(file_path="specs/registry.md")`
2. **Parse `$ARGUMENTS`:**
   - If it matches `FEAT-\d{3}` pattern → **UPDATE mode** (existing feature)
   - Otherwise → treat as a feature name → **check if it already exists in registry**
     - If found by name → **UPDATE mode**
     - If not found → **CREATE mode** (new feature)
3. **Announce mode:** Tell the user whether you are creating a new spec or updating an existing one.

---

## Step 2a: CREATE Mode — New Feature Specification

### 2a.1 Extract Next ID

Parse `specs/registry.md` to find the `## Next ID: FEAT-NNN` line. This is the ID for the new feature.

### 2a.2 Gather Requirements

Use AskUserQuestion to collect all requirements in **one batch**:

```
I'm creating a new specification: FEAT-NNN

Questions:
1. "Describe the feature in 2-3 sentences (overview):"
   - [free text]

2. "What are the acceptance criteria? (Given/When/Then format preferred)"
   - [free text — user can list multiple]

3. "Are there any edge cases or constraints to consider?"
   - [free text — user can list multiple]

4. "Any additional context? (related features, tech preferences, etc.)"
   - [free text, or "none"]
```

**Do not proceed until the user has answered.**

### 2a.3 Generate Spec File

Create a slug from the feature name: lowercase, hyphens, no special characters.
Example: "User Authentication" → `user-authentication`

Write the spec file to: `specs/FEAT-NNN-<slug>.md`

Use the living spec template:

```markdown
# FEAT-NNN: Feature Name

Status: DRAFT
Created: YYYY-MM-DD
Last Modified: YYYY-MM-DD

## Overview
[User's overview from 2a.2, cleaned up into 2-3 clear sentences]

## Current State
No implementation yet.

### Components
- (none yet)

### Behavior
- (none yet)

### Acceptance Criteria
[Each criterion from user input, formatted as:]
- Given [precondition] When [action] Then [expected]

### Edge Cases
[Each edge case from user input, formatted as:]
- [Category]: [description]

## Change History

### v1 (YYYY-MM-DD) — Initial specification
- ADDED: Initial feature specification created
- Plan: (pending — use /plan to create)
```

Use today's date (from system context) for all date fields.

### 2a.4 Update Registry

Edit `specs/registry.md`:

1. **Add a new row** to the table:
   ```
   | FEAT-NNN | Feature Name | DRAFT | [spec](FEAT-NNN-slug.md) | — | YYYY-MM-DD |
   ```
2. **Increment Next ID:**
   - Parse current `## Next ID: FEAT-NNN`
   - Increment NNN by 1 (e.g., FEAT-001 → FEAT-002)
   - Update the line

### 2a.5 Confirm Creation

Report to the user:
```
Specification created:
- ID: FEAT-NNN
- File: specs/FEAT-NNN-slug.md
- Status: DRAFT
- Registry updated (Next ID: FEAT-MMM)

Next steps:
- Review and edit the spec directly if needed
- Run /plan FEAT-NNN to create an implementation plan
```

---

## Step 2b: UPDATE Mode — Modify Existing Specification

### 2b.1 Load Current Spec

1. **Find the spec file:** Look up the FEAT-ID in `specs/registry.md` to get the spec link, or use `Glob(pattern="specs/FEAT-NNN-*.md")` to find the file.
2. **Read the full spec:** `Read(file_path="specs/FEAT-NNN-slug.md")`
3. **Display current state** to user: Show the Overview and Acceptance Criteria so the user has context.

### 2b.2 Gather Changes

Use AskUserQuestion:

```
Current spec: FEAT-NNN — Feature Name
Status: [current status]

What would you like to change?

Questions:
1. "What changes are you making? (describe additions, modifications, removals)"
   - [free text]

2. "Give this change a short title (for the Change History entry):"
   - [free text]
```

**Do not proceed until the user has answered.**

### 2b.3 Apply Changes

1. **Parse the user's changes** into delta categories:
   - **ADDED:** New criteria, components, behaviors
   - **MODIFIED:** Changed existing items
   - **REMOVED:** Deleted items

2. **Update the spec file** using Edit tool:
   - Modify the relevant sections (Overview, Acceptance Criteria, Edge Cases, etc.)
   - Update `Last Modified: YYYY-MM-DD` to today
   - Update `Status: MODIFIED`

3. **Add Change History entry:**
   Determine the next version number by counting existing `### vN` entries.

   Append a new entry:
   ```markdown
   ### vN (YYYY-MM-DD) — User's title
   - ADDED: [items added, if any]
   - MODIFIED: [items changed, if any]
   - REMOVED: [items removed, if any]
   - Plan: (pending — use /plan FEAT-NNN to create)
   ```

### 2b.4 Update Registry Status

Edit `specs/registry.md` to change the status for this FEAT-ID to `MODIFIED`.

### 2b.5 Confirm Update

Report to the user:
```
Specification updated:
- ID: FEAT-NNN
- File: specs/FEAT-NNN-slug.md
- Status: MODIFIED
- Changes: [brief summary of ADDED/MODIFIED/REMOVED]

Next steps:
- Review the updated spec
- Run /plan FEAT-NNN to create an implementation plan for the changes
```

---

## Critical Rules

1. **USE AskUserQuestion** — Never invent requirements. Always ask the user.
2. **Batch questions together** — Ask everything in one interaction per mode.
3. **Preserve existing content** — In UPDATE mode, only change what the user requested. Do not rewrite unchanged sections.
4. **Always update the registry** — Every create or update must be reflected in `specs/registry.md`.
5. **Use today's date** — All date fields use the current date.
6. **Slugify feature names** — Lowercase, hyphens, no special characters (e.g., "OAuth Flow" → `oauth-flow`).
7. **Do not create implementation plans** — This command only manages specifications. Direct the user to `/plan` for implementation.
8. **Read before writing** — Always read `specs/registry.md` and existing spec files before making changes.
