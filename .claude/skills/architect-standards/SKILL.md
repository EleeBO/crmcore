---
name: architect-standards
description: Architecture documentation with C4 diagrams, ADR templates, and task decomposition rules. Use when planning features or documenting architecture.
---

# Architect Standards Skill

**Core Rule:** Document decisions with ADR, visualize with C4, limit tasks to 10-12 per plan.

## When to Use

- Planning new features
- Making architectural decisions
- Documenting system design
- Decomposing large tasks

## Task Decomposition

### The Rule of 12

**Maximum 10-12 tasks per plan.** If more needed:
- Group related tasks
- Create sub-plans
- Prioritize ruthlessly

Why 10-12? Cognitive load limits. More tasks = less focus. Plans beyond 12 tasks should be split into multiple features.

> **Note:** See `/plan` command for the authoritative task count limit.

### Task Quality

Each task must be:
- **Atomic**: One deliverable
- **Testable**: Clear success criteria
- **Estimated**: Rough complexity (S/M/L)
- **Independent**: Minimal dependencies

```markdown
## Task Example

### Task 3: Implement User Authentication
- **Deliverable**: Working login/logout endpoints
- **Success Criteria**: Tests pass, manual verification works
- **Complexity**: M
- **Dependencies**: Task 2 (database setup)
- **Files**: src/auth/, tests/test_auth.py
```

## ADR (Architecture Decision Record)

Template for documenting decisions:

```markdown
# ADR-001: Use PostgreSQL for Primary Database

## Status
Accepted

## Context
We need a database for storing user data and application state.
Requirements: ACID compliance, JSON support, good Python ecosystem.

## Decision
Use PostgreSQL 16 with asyncpg driver.

## Consequences

### Positive
- Strong ACID guarantees
- Excellent JSON support (JSONB)
- Rich ecosystem (PostGIS, full-text search)
- Team familiarity

### Negative
- Operational complexity vs SQLite
- Requires separate hosting

### Neutral
- Need to manage migrations carefully

## Alternatives Considered

### SQLite
- Pros: Simple, no server
- Cons: Limited concurrent writes, no JSON indexing

### MongoDB
- Pros: Flexible schema
- Cons: No ACID across documents, less familiar
```

## C4 Diagrams

### Level 1: System Context

```
[User] --> [Our System] --> [External API]
                       --> [Database]
```

### Level 2: Container

```
┌─────────────────────────────────────────┐
│              Our System                  │
│  ┌──────────┐  ┌──────────┐            │
│  │ Frontend │  │ Backend  │            │
│  │ (Next.js)│->│ (FastAPI)│            │
│  └──────────┘  └────┬─────┘            │
│                     │                   │
│                ┌────▼─────┐            │
│                │PostgreSQL│            │
│                └──────────┘            │
└─────────────────────────────────────────┘
```

### Level 3: Component (when needed)

```
Backend Container:
┌───────────────────────────────────┐
│  ┌─────────┐    ┌─────────────┐   │
│  │ Routes  │--->│ Services    │   │
│  └─────────┘    └──────┬──────┘   │
│                        │          │
│                 ┌──────▼──────┐   │
│                 │ Repositories│   │
│                 └─────────────┘   │
└───────────────────────────────────┘
```

## Documentation Location

```
docs/
├── architecture/
│   ├── C4/
│   │   ├── context.md
│   │   └── containers.md
│   └── decisions/
│       ├── ADR-001-database.md
│       ├── ADR-002-auth.md
│       └── README.md
```

## Planning Checklist

Before implementation:

- [ ] Problem clearly defined
- [ ] Tasks decomposed (≤12)
- [ ] Dependencies identified
- [ ] ADR written for major decisions
- [ ] C4 context diagram exists
- [ ] Success criteria defined
- [ ] Risks identified

## Anti-Patterns

**NEVER:**
- Plan without task limit
- Skip ADR for major decisions
- Start coding without clear tasks
- Have tasks with unclear deliverables

**ALWAYS:**
- Document WHY, not just WHAT
- Keep diagrams updated
- Review decisions periodically
- Link ADRs to related code
