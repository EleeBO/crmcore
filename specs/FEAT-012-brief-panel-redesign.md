# FEAT-012: Brief Panel Redesign — Adaptation Spec

**Status:** DRAFT
**Date:** 2026-03-19
**Source:** `docs/AI_Sales_Copilot_Brief_Panel_Spec.md`

---

## 1. Gap Analysis: Spec vs Current Codebase

### 1.1 Architecture Gap

| Aspect | Spec | Current | Decision |
|--------|------|---------|----------|
| Framework | React + TSX, CSS Modules | Vanilla TS, plain CSS, DOM manipulation | **Keep vanilla TS** — React migration is out of scope |
| Components | `BriefPanel.tsx`, `ContactCard.tsx`, etc. | Monolithic `sidepanel.ts` (2159 lines) | Extract render functions into separate modules |
| Styling | CSS Modules (`BriefPanel.module.css`) | Single `sidepanel.css` (1481 lines) | Introduce CSS custom properties (variables), keep single CSS file |
| Build | (implied React bundling) | Vite + `vite-plugin-web-extension` | Keep Vite — no changes needed |

**Key decision:** The spec assumes React. Our extension is vanilla TS with innerHTML rendering. We keep the current architecture but restructure the rendering code into modular functions and introduce CSS variables for the design system.

### 1.2 Data Contract Gap

**Current backend response** (`POST /api/v1/briefing`):

```json
{
  "portrait": {
    "role": "Руководитель отдела продаж",
    "pain_points": ["..."],
    "motivators": ["..."],
    "budget": "500 000 руб.",
    "decision_timeline": "конец квартала",
    "communication_style": "деловой"
  },
  "strategy": {
    "approach": "Акцент на быстром ROI",
    "key_messages": ["Интеграция за 2 недели"],
    "avoid": ["Сравнение с amoCRM"]
  },
  "objections": [
    { "objection": "Слишком дорого", "response": "Экономия 30% в год." }
  ]
}
```

**Spec requires** (`BriefData`):

```json
{
  "contact": { "role", "company", "companyDetail", "avatarInitials", "budgetNote" },
  "profileTags": [{ "label", "color" }],
  "focusPoints": [{ "headline", "detail" }],
  "painPoints": ["..."],
  "roi": { "value", "description" },
  "comparison": { "current": {...}, "proposed": {...} },
  "objections": [{ "question", "answer" }],
  "fullBrief": "markdown"
}
```

**Field mapping (what exists vs what's needed):**

| Spec Field | Current Source | Action |
|------------|---------------|--------|
| `contact.role` | `portrait.role` | Rename in mapping |
| `contact.company` | **MISSING** | LLM must extract from documents |
| `contact.companyDetail` | **MISSING** | LLM must extract from documents |
| `contact.avatarInitials` | **MISSING** | Generate from `role` on frontend |
| `contact.budgetNote` | `portrait.budget` | Reformat |
| `profileTags` | `portrait.motivators` | LLM must return structured tags with colors |
| `focusPoints` | `strategy.key_messages` | LLM must return `{headline, detail}` pairs |
| `painPoints` | `portrait.pain_points` | Direct mapping |
| `roi.value` | **MISSING** | LLM must generate |
| `roi.description` | **MISSING** | LLM must generate |
| `comparison.current` | **MISSING** | LLM must extract from documents |
| `comparison.proposed` | **MISSING** | LLM must generate |
| `objections[].question` | `objections[].objection` | Rename |
| `objections[].answer` | `objections[].response` | Rename |
| `fullBrief` | **MISSING** | LLM must generate markdown summary |

---

## 2. Changes Required

### 2.1 Backend Changes

#### 2.1.1 New Pydantic Models

**File:** `backend/briefing/models.py` (NEW)

```python
from pydantic import BaseModel

class BriefContact(BaseModel):
    role: str = ""
    company: str = ""
    company_detail: str = ""
    avatar_initials: str = ""
    budget_note: str = ""

class BriefProfileTag(BaseModel):
    label: str
    color: str  # "blue" | "green" | "amber"

class BriefFocusPoint(BaseModel):
    headline: str
    detail: str

class BriefRoi(BaseModel):
    value: str
    description: str

class BriefComparisonSide(BaseModel):
    name: str
    price: str
    pros: str = ""
    cons: str = ""

class BriefComparison(BaseModel):
    current: BriefComparisonSide
    proposed: BriefComparisonSide

class BriefObjection(BaseModel):
    question: str
    answer: str

class BriefData(BaseModel):
    contact: BriefContact = BriefContact()
    profile_tags: list[BriefProfileTag] = []
    focus_points: list[BriefFocusPoint] = []
    pain_points: list[str] = []
    roi: BriefRoi | None = None
    comparison: BriefComparison | None = None
    objections: list[BriefObjection] = []
    full_brief: str = ""
```

#### 2.1.2 Updated LLM Prompt

**File:** `backend/briefing/portrait.py` — modify `generate_briefing()`

The LLM system prompt must be updated to request the new JSON schema. The prompt should instruct the model to:

1. Extract company name and details from uploaded documents
2. Generate `profileTags` with color hints (`blue`/`green`/`amber`) based on buyer's behavioral type
3. Transform `key_messages` into structured `focusPoints` with `{headline, detail}`
4. Calculate or estimate `roi` from document data
5. Extract competitor comparison if documents mention current solutions
6. Generate `fullBrief` as a markdown summary

The response schema in the prompt changes from:

```
Current: { portrait: {...}, strategy: {...}, objections: [...] }
New:     { contact: {...}, profile_tags: [...], focus_points: [...], pain_points: [...], roi: {...}, comparison: {...}, objections: [...], full_brief: "..." }
```

#### 2.1.3 API Response Change

**File:** `backend/api/briefing.py`

The endpoint returns the new `BriefData` structure. This is a **breaking change** — the frontend must be updated simultaneously.

**Migration strategy:** Add a `v2` field or version param. Simplest: change in one commit since frontend + backend are in the same repo.

#### 2.1.4 Backward Compatibility

Old cached briefings in Redis will have the old format. Options:

- **Option A (recommended):** Add a migration function `migrate_v1_to_v2(old_data) -> BriefData` that maps old fields to new ones, filling missing fields with defaults.
- **Option B:** Invalidate cache on deploy (TTL is 30min, so natural expiry is fast).

---

### 2.2 Frontend Changes

#### 2.2.1 New TypeScript Interfaces

**File:** `extension/src/shared/types.ts` — add new types

```typescript
interface BriefContact {
  role: string;
  company: string;
  companyDetail?: string;
  avatarInitials: string;
  budgetNote?: string;
}

interface BriefProfileTag {
  label: string;
  color: 'blue' | 'green' | 'amber';
}

interface BriefFocusPoint {
  headline: string;
  detail: string;
}

interface BriefRoi {
  value: string;
  description: string;
}

interface BriefComparisonSide {
  name: string;
  price: string;
  pros?: string;
  cons?: string;
}

interface BriefComparison {
  current: BriefComparisonSide;
  proposed: BriefComparisonSide;
}

interface BriefObjection {
  question: string;
  answer: string;
}

interface BriefData {
  contact: BriefContact;
  profileTags: BriefProfileTag[];
  focusPoints: BriefFocusPoint[];
  painPoints: string[];
  roi?: BriefRoi;
  comparison?: BriefComparison;
  objections: BriefObjection[];
  fullBrief?: string;
}
```

#### 2.2.2 New Render Functions

**File:** `extension/src/sidepanel/brief-renderer.ts` (NEW)

Extract briefing rendering from `sidepanel.ts` into a dedicated module. Functions:

| Function | Renders | Replaces |
|----------|---------|----------|
| `renderContactCard(contact, profileTags)` | Avatar, role, company, tags | `renderPortrait()` (partially) |
| `renderFocusPoints(focusPoints)` | 3 numbered action items | `renderStrategy()` (partially) |
| `renderPainPoints(painPoints)` | Compact pain list with red `!` | Pain part of `renderPortrait()` |
| `renderRoiHighlight(roi)` | Green ROI banner | NEW |
| `renderComparisonCards(comparison)` | Side-by-side old vs new | NEW |
| `renderObjectionCards(objections)` | Q&A format | `renderObjections()` (restructured) |
| `renderExpandButton(fullBrief)` | Toggle for full brief markdown | NEW |
| `renderBriefPanel(data: BriefData)` | Orchestrator — calls all above | `renderBriefingToContainers()` |

Each function returns an `HTMLElement` (not HTML string) for safer DOM construction. Use `document.createElement` instead of innerHTML where possible.

#### 2.2.3 HTML Structure Changes

**File:** `extension/src/sidepanel/sidepanel.html`

Replace the current Phase 2 briefing section (lines 133-154):

```html
<!-- CURRENT (remove) -->
<details class="briefing-section" id="portrait-card" open>
  <summary>Портрет покупателя</summary>
  <div id="portrait-text" class="briefing-section-body"></div>
</details>
<details class="briefing-section" id="strategy-card" open>...</details>
<details class="briefing-section" id="objections-card" open>...</details>
```

```html
<!-- NEW -->
<div id="briefing-content" class="brief-panel" hidden>
  <div id="brief-contact-card"></div>
  <div class="brief-divider"></div>
  <div id="brief-focus-points"></div>
  <div id="brief-pain-points"></div>
  <div class="brief-divider"></div>
  <div id="brief-roi"></div>
  <div id="brief-comparison"></div>
  <div class="brief-divider"></div>
  <div id="brief-objections"></div>
  <div id="brief-expand"></div>
</div>
```

The same structure applies to Phase 3 (collapsed) and Phase 4 (done) containers, but with abbreviated versions.

#### 2.2.4 CSS Changes

**File:** `extension/src/sidepanel/sidepanel.css`

**Step 1:** Introduce CSS custom properties (add to `:root`):

```css
:root {
  /* Typography */
  --font-base: 13px;
  --font-sm: 12px;
  --font-xs: 11px;
  --font-lg: 15px;
  --font-xl: 22px;

  /* Backgrounds */
  --background-primary: #ffffff;
  --background-secondary: #f5f5f5;

  /* Text */
  --text-primary: #1a1a1a;
  --text-secondary: #4b5563;
  --text-tertiary: #9ca3af;
  --text-info: #2563eb;

  /* Borders */
  --border-tertiary: #e5e7eb;

  /* Tag colors */
  --tag-blue-bg: #E6F1FB;
  --tag-blue-text: #185FA5;
  --tag-green-bg: #EAF3DE;
  --tag-green-text: #3B6D11;
  --tag-amber-bg: #FAEEDA;
  --tag-amber-text: #854F0B;

  /* ROI */
  --roi-bg: #EAF3DE;
  --roi-text: #3B6D11;

  /* Comparison */
  --compare-current-bg: #FCEBEB;
  --compare-current-text: #791F1F;
  --compare-proposed-bg: #EAF3DE;
  --compare-proposed-text: #27500A;

  /* Layout */
  --card-radius: 12px;
  --section-padding: 16px;
  --section-gap: 12px;
}
```

**Step 2:** Add new component styles per the spec's visual rules (see section 3 below).

**Step 3:** Remove old `.briefing-section`, `.portrait-*`, `.approach-box`, `.chip`, `.objection-card` styles.

---

## 3. Visual Implementation Details

### 3.1 ContactCard

```
┌──────────────────────────────────────┐
│ [КД]  Коммерческий директор          │
│       ООО «СтройГрупп» · 5 филиалов  │
│       Согласовывает ген. директор...  │
│                                      │
│ [ROI-ориентирован] [Любит цифры] ... │
└──────────────────────────────────────┘
```

- Avatar: 40x40px, border-radius 10px, gradient blue bg, white initials 16px/500
- Role: 15px/500
- Company + detail: 12px, `--text-secondary`
- Budget note: 11px, `--text-tertiary`
- Tags: pills, border-radius 20px, 11px, colored per `color` field

### 3.2 FocusPoints

```
┌──────────────────────────────────────┐
│ ФОКУС РАЗГОВОРА                      │
│                                      │
│ ① Экономия 2ч/день — CRM сам        │
│   заполняет карточки после звонков   │
│ ② Единая воронка — Все 5 филиалов    │
│   в одном дашборде                   │
│ ③ Нативная 1С — Без костылей,        │
│   данные синхронизируются авто        │
└──────────────────────────────────────┘
```

- Background: `--background-secondary`
- Label: 11px, uppercase, letter-spacing 0.5px, `--text-tertiary`
- Number circles: 20x20px, `--text-info` bg, white text 11px
- Headline: 13px/500 (bold)
- Detail: 13px/400, `--text-secondary`, after em dash

### 3.3 PainPoints

```
│ ! 2 часа/день на ручное заполнение   │
│ ! Нет единой воронки                 │
│ ! Bitrix24 тормозит при >10K сделок  │
```

- Red `!` icon: 16px, `#E24B4A`
- Text: 12px, `--text-secondary`
- No cards, no bullets — compact list

### 3.4 RoiHighlight

```
┌──────────────────────────────────────┐
│  42 млн ₽                           │
│  потенциальная допвыручка/год        │
└──────────────────────────────────────┘
```

- Background: `--roi-bg`, border-radius 12px
- Value: 22px/500, `--roi-text`
- Description: 12px, `--roi-text`, max 2 lines

### 3.5 ComparisonCards

```
┌─────────────────┐ ┌─────────────────┐
│ Bitrix24        │ │ СберCRM Бизнес  │
│ ~35 000 ₽/мес   │ │ 23 460 ₽/мес    │
│ тормозит, нет 1С│ │ 40 лиц., –15%   │
└─────────────────┘ └─────────────────┘
  (red tones)         (green tones)
```

- Two blocks in row: flex, gap 8px
- Left: `--compare-current-bg`, `--compare-current-text`
- Right: `--compare-proposed-bg`, `--compare-proposed-text`
- Name: 11px/500, Price: 14px/500, Details: 12px/400

### 3.6 ObjectionCards

```
│ ГОТОВЫЕ ОТВЕТЫ НА ВОЗРАЖЕНИЯ         │
│                                      │
│ «У нас уже есть Bitrix24»           │
│ → СберCRM дешевле на 33%...          │
│ ─────────────────────────────        │
│ «Сложно переезжать»                 │
│ → Миграция за 2 недели...            │
```

- Section label: 11px, uppercase
- Question: 12px/500
- Answer: 12px/400, `--text-secondary`, starts with `→ `
- Separator: 0.5px `--border-tertiary`
- Max 3 objections

### 3.7 ExpandButton

```
┌──────────────────────────────────────┐
│       Открыть полный бриф →          │
└──────────────────────────────────────┘
```

- Full width, 12px, `--text-secondary`
- Border: 0.5px `--border-tertiary`
- On click: toggles markdown `fullBrief` content below
- Hidden if `fullBrief` is empty

---

## 4. What to Keep, What to Change

### 4.1 Keep As-Is

- Phase engine (0-4 phases) in `sidepanel.ts`
- WebSocket connection handling
- `chrome.storage.local` state management
- Vite build pipeline
- Header bar and recording bar
- Hint cards rendering (not part of this feature)
- Service worker communication

### 4.2 Remove

- Old `renderPortrait()` function (lines 1452-1483)
- Old `renderStrategy()` function (lines 1485-1507)
- Old `renderObjections()` function (lines 1509-1521)
- Old `renderBriefingToContainers()` function (lines 1523-1548)
- Old CSS: `.briefing-section`, `.portrait-role`, `.pain-list`, `.pain-marker`, `.chip`, `.info-row`, `.comm-style`, `.approach-box`, `.key-messages-list`, `.avoid-list`, `.objection-card`
- Old HTML: `<details>` accordion structure for briefing cards
- Old TS interfaces: `BriefingPortrait`, `BriefingStrategy`, `BriefingObjection`, `BriefingData`

### 4.3 Change

| Component | Change |
|-----------|--------|
| `sidepanel.ts` | Replace old render calls with `renderBriefPanel(data)` from new module |
| `sidepanel.html` | Replace Phase 2/3/4 briefing containers with new flat DOM structure |
| `sidepanel.css` | Add CSS variables to `:root`, add new component styles, remove old briefing styles |
| `shared/types.ts` | Add `BriefData` and related interfaces |
| `backend/briefing/portrait.py` | Update LLM prompt to return new schema |
| `backend/briefing/models.py` (NEW) | New Pydantic models |
| `backend/api/briefing.py` | Return new data shape |
| `backend/tests/test_briefing.py` | Update test fixtures for new schema |

---

## 5. Spec Corrections

Issues found in the original spec that need adjustment for our codebase:

### 5.1 No React — File Structure Change

**Spec says:**
```
src/components/brief/
├── BriefPanel.tsx
├── BriefPanel.module.css
├── ContactCard.tsx
...
```

**Adapted:**
```
extension/src/sidepanel/
├── sidepanel.ts          # (existing) — calls brief-renderer
├── sidepanel.html        # (existing) — updated DOM containers
├── sidepanel.css         # (existing) — updated styles
├── brief-renderer.ts     # (NEW) — all brief rendering functions
extension/src/shared/
├── types.ts              # (existing) — add BriefData types
```

### 5.2 No CSS Modules — Use CSS Variables + BEM

The spec uses CSS Modules (`BriefPanel.module.css`). We use plain CSS with class name prefixing:

- All new classes prefixed with `brief-` to avoid collision
- CSS variables in `:root` instead of module scoping
- Example: `.brief-contact-card`, `.brief-focus-points`, `.brief-roi`

### 5.3 Dark Mode — Deferred

The spec includes dark mode rules. Current extension has no dark mode support anywhere. **Decision: defer dark mode to a follow-up.** Add CSS variables now so dark mode can be added later by overriding variables in a `@media (prefers-color-scheme: dark)` block.

### 5.4 Accessibility — Partial

The spec requires `tabIndex`, `role="button"`, `aria-label`, focus rings. Current extension has zero accessibility support. **Decision: add basic a11y to new brief components only** (not retrofit entire extension):

- `role="region"` + `aria-label` on section containers
- `role="button"` + `tabindex="0"` + keyboard handler on ExpandButton
- Ensure color contrast meets WCAG AA

### 5.5 `avatarInitials` — Frontend Generation

The spec puts `avatarInitials` in the data contract. This is better generated on the frontend from the `role` field (take first letters of words), since the backend may not always know the right abbreviation. **Decision: generate on frontend, don't include in API.**

### 5.6 Optional Blocks — Graceful Degradation

The spec doesn't cover what happens when `roi`, `comparison`, or `fullBrief` are missing. The LLM may not always have enough data to generate these.

**Decision:**
- `roi` block: hide entirely if `roi` is `null`
- `comparison` block: hide entirely if `comparison` is `null`
- `fullBrief` / ExpandButton: hide if `fullBrief` is empty or absent
- `contact.company`: if unknown, show only role
- `profileTags`: if empty array, hide tags row
- Always show: `focusPoints`, `painPoints`, `objections` (these are core)

### 5.7 Phase 3 (Live Call) — Collapsed Brief

The spec only covers Phase 2 (pre-call briefing view). During the live call (Phase 3), the brief is shown in a collapsed sidebar. **Decision: for Phase 3, show only ContactCard + FocusPoints in a compact view.** ROI, comparison, and objections are accessible via a "Show brief" toggle.

### 5.8 Max Height / Scroll

The spec says "no scroll at ~800px." Our panel is `100vh` minus header (44px) and control bar (52px), leaving ~504px on a 600px screen. The brief WILL need to scroll on small screens. **Decision: allow scroll but optimize content density to minimize it.**

---

## 6. Implementation Order

| # | Task | Scope | Depends On |
|---|------|-------|------------|
| 1 | Add `BriefData` types to `shared/types.ts` | Frontend | — |
| 2 | Create `brief-renderer.ts` with all render functions | Frontend | 1 |
| 3 | Add CSS variables + new brief styles to `sidepanel.css` | Frontend | — |
| 4 | Update `sidepanel.html` — new DOM containers | Frontend | — |
| 5 | Wire `brief-renderer` into `sidepanel.ts`, remove old code | Frontend | 1, 2, 3, 4 |
| 6 | Create `backend/briefing/models.py` with new Pydantic models | Backend | — |
| 7 | Update LLM prompt in `portrait.py` for new schema | Backend | 6 |
| 8 | Update `backend/api/briefing.py` to return new structure | Backend | 6, 7 |
| 9 | Add `migrate_v1_to_v2()` for cached data compatibility | Backend | 6 |
| 10 | Update `test_briefing.py` with new fixtures | Backend | 6, 7, 8 |
| 11 | Update Phase 3 (collapsed brief) rendering | Frontend | 2, 5 |
| 12 | Update Phase 4 (done) rendering | Frontend | 2, 5 |
| 13 | Manual visual QA in Chrome sidebar | QA | All above |

---

## 7. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM doesn't reliably produce new fields (ROI, comparison) | Missing UI blocks | Make all new blocks optional with graceful hide |
| Prompt change degrades existing field quality | Worse briefings | A/B test prompts, keep old prompt as fallback |
| Cache contains old-format data | Frontend crashes | `migrate_v1_to_v2()` converter |
| Phase 3/4 rendering breaks | UX regression during calls | Test all 5 phases manually |
| CSS variable introduction conflicts with existing styles | Visual glitches | Prefix all new classes with `brief-` |

---

## 8. Acceptance Criteria (Adapted)

1. [ ] New `BriefData` interface in `shared/types.ts`
2. [ ] `brief-renderer.ts` renders all 6 blocks from `BriefData`
3. [ ] Optional fields (`roi`, `comparison`, `fullBrief`, `budgetNote`, `companyDetail`) gracefully hidden when absent
4. [ ] `focusPoints` capped at 3 items
5. [ ] `objections` capped at 3 items
6. [ ] CSS variables defined in `:root` for all design tokens
7. [ ] "Открыть полный бриф" button toggles `fullBrief` markdown content
8. [ ] Panel width strictly 380px, no horizontal overflow
9. [ ] All text blocks max 2 lines with `text-overflow: ellipsis` on overflow
10. [ ] Phase 2, 3, and 4 all render the new brief format
11. [ ] Backend returns new `BriefData` JSON structure
12. [ ] Old cached briefings handled via migration or cache invalidation
13. [ ] Tests updated for new data structure
14. [ ] No regressions in non-briefing functionality (hints, recording, file upload)
