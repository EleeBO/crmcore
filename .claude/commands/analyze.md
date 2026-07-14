---
name: analyze
description: Analyze an existing web platform before redesign. Takes screenshots, documents features, and creates user stories.
arguments:
  - name: url
    description: URL of the platform to analyze
    required: true
---

# Platform Analysis Workflow

Analyzing: **$ARGUMENTS.url**

## Phase 1: Initial Reconnaissance

1. **Open the platform** in browser
2. **Take overview screenshot** of the main page
3. **Identify tech stack** (inspect network, sources)
4. **Note first impressions**:
   - Responsive design?
   - Loading performance?
   - Accessibility features?

## Phase 2: Navigation Mapping

1. **Map all navigation items** (main menu, sidebar, footer)
2. **Document URL structure**
3. **Identify user flows**:
   - Authentication flow
   - Main CRUD flows
   - Settings/profile

## Phase 3: Page-by-Page Inventory

For each significant page:

1. **Screenshot** (desktop and mobile if responsive)
2. **List components** (tables, forms, modals, cards)
3. **Document features** (sorting, filtering, search, bulk actions)
4. **Note data fields** displayed

## Phase 4: CRUD Inventory

For each data entity discovered:

1. **Identify operations** (Create, Read, Update, Delete)
2. **Document API endpoints** (from network tab)
3. **Note relationships** between entities
4. **Identify validation rules**

## Phase 5: Screenshots Capture

Take screenshots of:
- [ ] All main pages (default state)
- [ ] Forms (empty and filled)
- [ ] Error states
- [ ] Loading states
- [ ] Mobile views (if responsive)

Save to: `analysis/screenshots/`

## Phase 6: User Stories Generation

For each discovered feature, generate user stories using the `user-stories` skill format:

```markdown
## US-XXX: [Feature Name]

**As a** [discovered role]
**I want to** [observed action]
**So that** [inferred benefit]

### Acceptance Criteria
- Given [observed precondition]
- When [observed action]
- Then [observed result]
```

## Phase 7: Summary Report

Create `analysis/README.md` with:
- Platform overview
- Tech stack assessment
- Entity inventory
- Feature list with priorities
- Redesign recommendations

## Output Structure

```
analysis/
├── README.md              # Summary report
├── screenshots/
│   ├── pages/            # Page screenshots
│   └── flows/            # User flow screenshots
├── entities/
│   ├── user.md           # Entity documentation
│   └── ...
├── user-stories/
│   ├── US-001.md
│   └── ...
└── api-map.md            # Discovered endpoints
```

## Skills to Load

- `platform-analysis` - Analysis methodology
- `user-stories` - Story format
- `e2e-agent-browser` - Browser automation

## Next Steps After Analysis

1. Review analysis with stakeholders
2. Prioritize features for redesign
3. Use `/plan` to create implementation plan
4. Use `refine-fastapi` skill for CRUD implementation
