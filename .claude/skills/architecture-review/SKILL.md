---
name: Architecture Review
description: >
  Architecture review for context boundaries, layer isolation, coupling/cohesion analysis,
  and bottleneck detection. Use when asked to "review architecture", "check coupling",
  "check layers", "boundary check", "bottleneck analysis", "architecture audit",
  "dependency analysis", or "check isolation".
---

# Architecture Review

Structured 5-phase architecture review that analyzes any codebase for structural integrity,
layer violations, coupling problems, and architectural bottlenecks.

**This skill is rigid.** Follow the phases sequentially. Do not skip phases.

## Process Flow

```
Phase 1: Discovery
    |
Phase 2: Dependency Analysis
    |
Phase 3: Layer & Boundary Isolation
    |
Phase 4: Coupling & Cohesion
    |
Phase 5: Report
```

## Before You Start

1. Create a TaskCreate todo for each phase
2. Determine review scope: full codebase or specific modules (ask user if unclear)
3. If user specifies a subsystem, limit analysis to that subtree

---

## Phase 1: Discovery

**Goal:** Map the codebase structure, identify stack, architectural pattern, and layer boundaries.

### Step 1.1: Identify Stack

Use Glob to find project manifests:

| File | Stack |
|------|-------|
| `pyproject.toml`, `setup.py`, `requirements.txt` | Python |
| `package.json` | JavaScript/TypeScript |
| `go.mod` | Go |
| `Cargo.toml` | Rust |
| `*.csproj`, `*.sln` | .NET |
| `pom.xml`, `build.gradle` | Java/Kotlin |

Read the manifest to identify frameworks (FastAPI, Django, Express, Next.js, Gin, etc.).

### Step 1.2: Map Directory Structure

```bash
# Use Glob to get the full tree of source files
**/*.py  OR  **/*.ts  OR  **/*.go  (based on detected stack)
```

Classify each top-level source directory into an architectural layer:

| Directory Pattern | Layer |
|-------------------|-------|
| `domain/`, `entities/`, `core/models/` | Domain |
| `services/`, `use_cases/`, `application/`, `interactors/` | Application |
| `api/`, `routes/`, `handlers/`, `controllers/`, `views/` | Presentation |
| `infrastructure/`, `adapters/`, `repositories/`, `persistence/`, `external/` | Infrastructure |
| `utils/`, `lib/`, `helpers/`, `common/`, `shared/` | Shared/Cross-cutting |
| `tests/`, `__tests__/`, `spec/` | Test (exclude from analysis) |

If directories don't match standard patterns, infer from file contents (imports, base classes).

### Step 1.3: Detect Architectural Pattern

| Pattern | Indicators |
|---------|-----------|
| **Clean/Hexagonal** | Separate `domain/`, `application/`, `infrastructure/` directories; interfaces in domain |
| **Layered (N-tier)** | `controllers/`, `services/`, `repositories/` with clear hierarchy |
| **MVC** | `models/`, `views/`, `controllers/` (or templates) |
| **Modular monolith** | Feature-based directories (`users/`, `orders/`, `payments/`), each with own layers |
| **Microservices** | Multiple `service-*/` directories with independent manifests |
| **No clear pattern** | Mixed responsibilities, no consistent directory structure |

### Step 1.4: Identify Bounded Contexts

Look for natural boundaries:
- Separate top-level feature directories
- Independent database models/schemas
- Separate API routers/controllers by domain
- Different aggregate roots

### Phase 1 Output

Create a summary table:

```markdown
| Module/Directory | Layer | File Count | Detected Bounded Context |
|------------------|-------|------------|--------------------------|
| src/domain/user  | Domain | 5 | User Management |
| src/api/orders   | Presentation | 3 | Order Processing |
| ...              | ...   | ... | ... |
```

State the detected architectural pattern and any ambiguities.

---

## Phase 2: Dependency Analysis

**Goal:** Build the import graph, check Dependency Rule, find cycles.

### Step 2.1: Collect Import Statements

For each source file, use Grep to extract imports:

**Python:**
```
pattern: ^(from\s+\S+\s+import|import\s+\S+)
```

**TypeScript/JavaScript:**
```
pattern: ^import\s+.*from\s+['"]
```

**Go:**
```
pattern: ^\s*"[^"]*"
```

### Step 2.2: Build Dependency Matrix

For each module pair (A, B), record:
- Does A import B? (A depends on B)
- Does B import A? (B depends on A)
- Both? (Circular dependency)

Present as a matrix or list of edges.

### Step 2.3: Check Dependency Rule

The Dependency Rule: **source code dependencies must point inward only.**

```
Presentation → Application → Domain ← Infrastructure
```

Valid dependency directions:
- Presentation → Application (OK)
- Presentation → Domain (OK, but prefer going through Application)
- Application → Domain (OK)
- Infrastructure → Domain (OK, implements interfaces)
- Infrastructure → Application (OK for DI wiring only)

**VIOLATIONS (flag these):**
- Domain → Infrastructure (CRITICAL)
- Domain → Presentation (CRITICAL)
- Domain → Application (HIGH — domain should not know about use cases)
- Application → Presentation (HIGH)
- Application → Infrastructure (MEDIUM — should use interfaces)

### Step 2.4: Detect Circular Dependencies

Search for import cycles:
1. A imports B, B imports A (direct cycle)
2. A imports B, B imports C, C imports A (transitive cycle)

For each cycle found, report the full chain.

### Step 2.5: Cross-Context Imports

If bounded contexts were identified in Phase 1:
- Check that modules in Context A do not import types/models from Context B directly
- Integration should happen via events, shared interfaces, or anti-corruption layers

### Phase 2 Output

```markdown
### Dependency Rule Violations
| Source Module | Target Module | Direction | Severity |
|---------------|---------------|-----------|----------|
| domain/user.py | infrastructure/db.py | Domain → Infra | CRITICAL |

### Circular Dependencies
| Cycle | Modules Involved |
|-------|-----------------|
| 1 | A → B → C → A |

### Cross-Context Imports
| From Context | To Context | Import |
|-------------|------------|--------|
| Orders | Users | `from users.models import User` |
```

---

## Phase 3: Layer & Boundary Isolation

**Goal:** Check that layers and bounded contexts maintain proper isolation.

### Step 3.1: Model Leakage

Check if internal models escape their intended layer:

**What to search for:**
- ORM models (SQLAlchemy, Prisma, TypeORM) used in API response types
- Database-specific types in domain layer
- Request/Response DTOs used in domain logic
- Internal entities returned directly from API endpoints

**Python example violations:**
```python
# BAD: ORM model in API response
@router.get("/users")
async def get_users() -> list[UserORM]:  # ORM model leaked to presentation
    ...

# BAD: SQLAlchemy Session in domain
class UserService:
    def __init__(self, session: Session):  # Infrastructure in application
        ...
```

### Step 3.2: Framework Leakage

Check that the domain layer is framework-agnostic:

| Framework | Leakage Indicators in Domain |
|-----------|------------------------------|
| FastAPI | `from fastapi import ...` in domain files |
| Django | `from django.db import models` in domain files |
| Express | `import { Request, Response }` in domain files |
| Next.js | `from next/...` in domain files |
| SQLAlchemy | `from sqlalchemy import ...` in domain files |
| Prisma | `@prisma/client` in domain files |

Use Grep with pattern targeting framework imports within domain directories.

### Step 3.3: Interface Boundaries

Check if proper interfaces/protocols exist at layer boundaries:

- Domain defines repository interfaces (Python `Protocol`/`ABC`, TypeScript `interface`)
- Infrastructure implements those interfaces
- Application depends on abstractions, not implementations

**Search for:**
```
# Python: Protocol or ABC in domain
pattern: class\s+\w+(Repository|Service|Gateway|Port)\s*\(.*Protocol.*\)

# TypeScript: interface in domain
pattern: (export\s+)?interface\s+\w+(Repository|Service|Gateway|Port)
```

If no interfaces found at boundaries, flag as HIGH severity.

### Step 3.4: Anti-Corruption Layers

At bounded context boundaries, check for:
- Translation/mapping classes between contexts
- Dedicated adapter modules
- Event-based communication instead of direct imports

### Phase 3 Output

```markdown
### Model Leakage
| File | Leaked Type | From Layer | To Layer | Severity |
|------|-------------|-----------|----------|----------|

### Framework Leakage
| Domain File | Framework Import | Severity |
|-------------|-----------------|----------|

### Missing Interfaces
| Boundary | Expected Interface | Status |
|----------|-------------------|--------|

### Anti-Corruption Layer Status
| Context Boundary | ACL Present? | Integration Pattern |
|-----------------|--------------|-------------------|
```

---

## Phase 4: Coupling & Cohesion

**Goal:** Identify tightly coupled modules, God classes, and cohesion problems.

### Step 4.1: Fan-in / Fan-out Analysis

For each module, count:
- **Fan-in:** How many other modules import this one (indicator of responsibility)
- **Fan-out:** How many modules this one imports (indicator of dependency)

**Thresholds:**
| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| Fan-in | < 10 | 10-20 | > 20 |
| Fan-out | < 10 | 10-15 | > 15 |

High fan-in + high fan-out = **Hub module** (potential bottleneck).
High fan-in + low fan-out = **Stable foundation** (good).
Low fan-in + high fan-out = **Unstable leaf** (acceptable if concrete).

### Step 4.2: God Module Detection

Read each source file and check:

| Metric | Threshold | How to Measure |
|--------|-----------|----------------|
| Lines of code | > 500 | Count lines (exclude blanks/comments) |
| Functions/methods | > 20 | Count `def`/`function`/`method` definitions |
| Classes in one file | > 3 | Count `class` definitions |
| Name contains | "Manager", "Handler", "Processor", "Helper", "Utils" | Grep for class names |

Any file hitting 2+ thresholds is a God Module candidate.

### Step 4.3: Cohesion Proxy (LCOM-lite)

For classes with 5+ methods, check:
- Do methods share instance variables (`self.x` in Python, `this.x` in TS)?
- Are there method clusters that don't interact?
- Could the class be split into 2+ focused classes?

**Heuristic:** If a class has methods that can be grouped into 2+ non-overlapping clusters
(each cluster uses different instance variables), it likely has low cohesion.

### Step 4.4: Code Smell Detection

| Smell | Detection | Severity |
|-------|-----------|----------|
| **Feature Envy** | Method accesses another object's attributes more than its own | MEDIUM |
| **Shotgun Surgery** | `git log` shows same files always changed together across contexts | MEDIUM |
| **Inappropriate Intimacy** | Two modules with mutual dependencies and shared internal state | HIGH |
| **Primitive Obsession** | Domain concepts represented as raw strings/ints instead of value objects | LOW |
| **Long Parameter List** | Functions with > 5 parameters | LOW |
| **Data Clumps** | Same group of parameters appears in 3+ function signatures | MEDIUM |

### Step 4.5: Bottleneck Identification

Synthesize findings to identify architectural bottlenecks:

| Bottleneck Type | Indicators |
|-----------------|-----------|
| **Single Point of Failure** | Module with fan-in > 20, no interface/abstraction |
| **God Module** | > 500 LOC, > 20 functions, mixed responsibilities |
| **Shared Mutable State** | Global variables, singletons with state, shared DB tables across contexts |
| **Deep Call Chain** | Synchronous chain through 5+ modules for a single operation |
| **Tight Integration** | Two contexts coupled through direct imports (no ACL/events) |

### Phase 4 Output

```markdown
### Fan-in / Fan-out Table
| Module | Fan-in | Fan-out | Classification |
|--------|--------|---------|---------------|
| lib/db.py | 25 | 3 | Hub (bottleneck) |

### God Modules
| File | LOC | Functions | Classes | Smells |
|------|-----|-----------|---------|--------|

### Cohesion Issues
| Class | Methods | Clusters | Recommendation |
|-------|---------|----------|---------------|

### Code Smells
| Smell | Location | Description | Severity |
|-------|----------|-------------|----------|

### Bottlenecks
| Type | Module(s) | Impact | Priority |
|------|-----------|--------|----------|
```

---

## Phase 5: Report

**Goal:** Synthesize all findings into a structured, actionable report.

### Report Template

Save to `docs/architecture-review-YYYY-MM-DD.md`:

```markdown
# Architecture Review Report

**Date:** YYYY-MM-DD
**Scope:** [full codebase / specific modules]
**Stack:** [detected stack]
**Architectural Pattern:** [detected pattern]

## Executive Summary

| Dimension | Status | Findings |
|-----------|--------|----------|
| Dependency Direction | [RED/YELLOW/GREEN] | N violations |
| Layer Isolation | [RED/YELLOW/GREEN] | N leakages |
| Coupling | [RED/YELLOW/GREEN] | N problematic modules |
| Cohesion | [RED/YELLOW/GREEN] | N God modules |
| Boundary Integrity | [RED/YELLOW/GREEN] | N cross-context issues |

**Overall Health:** [RED/YELLOW/GREEN]

## Critical Findings (must fix)

1. [Finding with file:line reference]
2. ...

## High Priority Findings (should fix)

1. ...

## Medium/Low Findings (consider fixing)

1. ...

## Dependency Graph

[ASCII representation of module dependencies with layer annotations]

## Metrics Summary

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Max fan-in | N | < 20 | OK/WARN |
| Max fan-out | N | < 15 | OK/WARN |
| Circular deps | N | 0 | OK/FAIL |
| Layer violations | N | 0 | OK/FAIL |
| God modules | N | 0 | OK/WARN |

## Recommendations

### Immediate Actions
1. [Action with expected impact]

### Short-term Improvements
1. [Action with expected impact]

### Long-term Architectural Goals
1. [Action with expected impact]
```

### Traffic Light Criteria

| Status | Criteria |
|--------|---------|
| GREEN | 0 critical findings, <= 2 high, metrics within thresholds |
| YELLOW | 0 critical, 3+ high findings, OR 1-2 metrics over threshold |
| RED | Any critical finding, OR 5+ high findings, OR 3+ metrics over threshold |

---

## Severity Reference

| Severity | Description | Examples |
|----------|-------------|---------|
| **CRITICAL** | Architectural integrity broken, must fix immediately | Domain imports infrastructure; circular dependencies between layers |
| **HIGH** | Significant structural problem, fix soon | Missing interface boundaries; God modules; framework leakage in domain |
| **MEDIUM** | Maintainability concern, plan to address | High coupling between modules; feature envy; data clumps |
| **LOW** | Code quality opportunity | Primitive obsession; long parameter lists; naming smells |

---

## Guidelines for the Reviewer

1. **Be concrete.** Every finding must reference a specific file and line number.
2. **No false alarms.** If a pattern exists but makes sense in context (e.g., a helper module
   intentionally has high fan-in), note it as an accepted risk, not a violation.
3. **Prioritize actionable findings.** "This is bad" is not useful. "Extract X into interface Y
   and implement in Z" is useful.
4. **Respect existing patterns.** If the codebase intentionally uses a simpler architecture
   (e.g., no domain layer in a CRUD app), don't flag the absence of DDD patterns.
5. **Scale to the project.** A 5-file script doesn't need the same rigor as a 500-file system.
   Skip irrelevant phases and say why.
6. **Use parallel agents.** For large codebases, dispatch Explore agents per phase or per module
   to analyze in parallel, then synthesize results.
