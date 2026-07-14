---
name: platform-analysis
description: Structured analysis of existing web platforms - feature inventory, screenshots, documentation, and redesign preparation. Use when analyzing websites before redesign or migration.
---

# Platform Analysis Skill

**Core Rule:** Systematic analysis before any redesign. Document everything with evidence.

## When to Use

- Analyzing existing web platform before redesign
- Creating feature inventory
- Documenting current functionality
- Preparing for migration to new stack

## Analysis Workflow

```
1. OVERVIEW    → High-level platform understanding
2. NAVIGATION  → Site structure and user flows
3. PAGES       → Page-by-page feature inventory
4. CRUD        → Data entities and operations
5. INTEGRATIONS → External services
6. SCREENSHOTS → Visual documentation
7. SUMMARY     → Findings and recommendations
```

## Phase 1: Overview

```markdown
## Platform Overview

**URL:** https://example.com
**Type:** [SaaS / E-commerce / Admin Panel / CRM / Other]
**Primary Users:** [Internal / External / Both]
**Tech Stack (visible):**
- Frontend: [React/Vue/Angular/Other]
- Styling: [Tailwind/Bootstrap/Custom]
- Auth: [JWT/Session/OAuth]

**First Impressions:**
- [ ] Responsive design?
- [ ] Dark mode support?
- [ ] Loading states?
- [ ] Error handling visible?
```

## Phase 2: Navigation Mapping

```markdown
## Site Structure

### Main Navigation
- Home → /
- Dashboard → /dashboard
- Users → /users
  - List → /users
  - Create → /users/new
  - Edit → /users/:id/edit
- Settings → /settings

### User Flows
1. **Login Flow:** Landing → Login → Dashboard
2. **CRUD Flow:** List → View → Edit → Save → List
3. **Onboarding:** Register → Verify → Profile Setup → Dashboard
```

## Phase 3: Page Inventory

For each significant page:

```markdown
## Page: User List (/users)

**Screenshot:** [screenshot_users_list.png]

### Components
| Component | Type | Notes |
|-----------|------|-------|
| Header | Navigation | Logo, menu, user dropdown |
| Sidebar | Navigation | Collapsible, icons |
| Data Table | Display | Sortable, filterable, pagination |
| Search Bar | Input | Debounced, filters by name/email |
| Action Buttons | Actions | Create, Export, Bulk Delete |

### Features
- [ ] Pagination (server/client)
- [ ] Sorting (columns: name, email, created_at)
- [ ] Filtering (status, role, date range)
- [ ] Search (full-text / field-specific)
- [ ] Bulk actions (delete, export)
- [ ] Row actions (view, edit, delete)

### Data Fields Displayed
| Field | Type | Sortable | Filterable |
|-------|------|----------|------------|
| ID | number | ✓ | ✗ |
| Name | string | ✓ | ✓ |
| Email | string | ✓ | ✓ |
| Role | enum | ✓ | ✓ |
| Status | enum | ✓ | ✓ |
| Created | datetime | ✓ | ✓ |
```

## Phase 4: CRUD Inventory

```markdown
## Entities & Operations

### Entity: User
| Operation | Endpoint | Method | Auth Required |
|-----------|----------|--------|---------------|
| List | /api/users | GET | ✓ |
| Create | /api/users | POST | ✓ (admin) |
| Read | /api/users/:id | GET | ✓ |
| Update | /api/users/:id | PUT/PATCH | ✓ |
| Delete | /api/users/:id | DELETE | ✓ (admin) |

### Entity: Order
| Operation | Endpoint | Method | Auth Required |
|-----------|----------|--------|---------------|
| List | /api/orders | GET | ✓ |
| ... | ... | ... | ... |

### Relationships
- User → Orders (1:N)
- Order → Items (1:N)
- Item → Product (N:1)
```

## Phase 5: Screenshots Workflow

Using agent-browser:

```bash
# Open target URL
agent-browser open https://example.com/dashboard

# Take full page screenshot
agent-browser screenshot ./analysis/screenshots/dashboard_full.png

# Interactive elements snapshot
agent-browser snapshot -i -c > ./analysis/snapshots/dashboard.json
```

### Screenshot Naming Convention

```
{page}_{state}_{viewport}.png

Examples:
- users_list_desktop.png
- users_list_mobile.png
- users_create_form_empty.png
- users_create_form_filled.png
- users_create_form_error.png
```

### States to Capture

For each page:
- [ ] Default/empty state
- [ ] Loaded with data
- [ ] Loading state
- [ ] Error state
- [ ] Mobile viewport (375px)
- [ ] Tablet viewport (768px)
- [ ] Desktop viewport (1440px)

## Phase 6: Integration Inventory

```markdown
## External Integrations

| Service | Type | Purpose |
|---------|------|---------|
| Stripe | Payment | Subscriptions |
| SendGrid | Email | Transactional |
| S3 | Storage | File uploads |
| Google OAuth | Auth | Social login |
| Sentry | Monitoring | Error tracking |
```

## Phase 7: Summary Report

```markdown
# Platform Analysis Summary

## Key Metrics
- Total Pages: 25
- CRUD Entities: 8
- External Integrations: 5
- Unique Components: ~40

## Strengths
1. Clean data table implementation
2. Good error handling
3. Responsive design

## Weaknesses
1. No dark mode
2. Slow loading on large datasets
3. Inconsistent form validation

## Redesign Priorities
1. **High:** Data tables → use TanStack Table + shadcn
2. **High:** Forms → react-hook-form + zod + shadcn
3. **Medium:** Navigation → shadcn sidebar
4. **Low:** Charts → recharts

## Estimated Effort
| Area | Pages | Complexity | Estimate |
|------|-------|------------|----------|
| Auth | 4 | Medium | M |
| Dashboard | 2 | High | L |
| Users CRUD | 4 | Medium | M |
| Orders CRUD | 5 | High | L |
| Settings | 3 | Low | S |

## Recommended Stack
- **Frontend:** Next.js 15 + shadcn/ui + Tailwind
- **Backend:** FastAPI + SQLAlchemy + PostgreSQL
- **Admin Kit:** shadcn-admin-kit or custom
```

## Output Files Structure

```
analysis/
├── README.md              # Summary report
├── screenshots/
│   ├── desktop/
│   ├── mobile/
│   └── states/
├── pages/
│   ├── dashboard.md
│   ├── users.md
│   └── ...
├── entities/
│   ├── user.md
│   ├── order.md
│   └── ...
└── integrations.md
```

## Commands Reference

```bash
# Quick analysis with just
just analyze-site https://example.com

# Manual with agent-browser
agent-browser open URL
agent-browser screenshot ./path/to/file.png
agent-browser snapshot -i -c
```

## Checklist Before Redesign

- [ ] All pages documented with screenshots
- [ ] All CRUD entities identified
- [ ] All API endpoints mapped
- [ ] User flows documented
- [ ] Integrations listed
- [ ] Pain points identified
- [ ] New stack requirements clear
- [ ] Effort estimates provided
