# Brief Panel Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the pre-call briefing panel from a text-heavy accordion layout to a scannable dashboard with 6 structured blocks (ContactCard, FocusPoints, PainPoints, ROI, Comparison, Objections). Migrate brief UI to Preact. Enforce LLM data contract via SGR.

**Architecture:** Strangler fig pattern — new brief panel in Preact, rest of UI stays vanilla TS. Backend uses SGR (Schema-Guided Reasoning): Pydantic schema with `Field(description=...)` constrains LLM output. Scenario fast-path transforms to same schema. Triple validation: LLM → Pydantic → Frontend.

**Tech Stack:** Preact (3KB), TypeScript strict, Python/FastAPI, Pydantic v2 with SGR, Vite + @preactjs/preset-vite, Chrome Extension MV3

**Spec:** `specs/FEAT-012-brief-panel-redesign.md`
**SGR Contract:** `specs/FEAT-012-sgr-contract.md`
**Design Spec:** `docs/AI_Sales_Copilot_Brief_Panel_Spec.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `backend/briefing/models.py` | SGR Pydantic models for `BriefData` with camelCase aliases + `Field(description=...)` |
| `extension/src/sidepanel/brief/BriefPanel.tsx` | Root Preact component — orchestrates all blocks |
| `extension/src/sidepanel/brief/ContactCard.tsx` | Avatar + role + company + tags |
| `extension/src/sidepanel/brief/FocusPoints.tsx` | 3 numbered action items |
| `extension/src/sidepanel/brief/PainPoints.tsx` | Compact pain list with red markers |
| `extension/src/sidepanel/brief/RoiHighlight.tsx` | Green ROI banner |
| `extension/src/sidepanel/brief/ComparisonCards.tsx` | Side-by-side old vs new |
| `extension/src/sidepanel/brief/ObjectionCards.tsx` | Q&A format |
| `extension/src/sidepanel/brief/ExpandButton.tsx` | Toggle for full brief text |
| `extension/src/sidepanel/brief/Divider.tsx` | Visual separator |
| `extension/src/sidepanel/brief/types.ts` | `BriefData` TypeScript interfaces |
| `extension/src/sidepanel/brief/brief.css` | Scoped brief panel styles |
| `extension/src/sidepanel/brief/mount.ts` | Preact mount/unmount bridge for vanilla TS |

### Modified Files
| File | Changes |
|------|---------|
| `backend/briefing/portrait.py` | Delete `BriefingResponse`, SGR prompt + Scenario→BriefData transform, Reparser |
| `backend/api/briefing.py` | Serialize via `model_dump(by_alias=True)` |
| `backend/tests/test_briefing.py` | Update fixtures for SGR schema, new tests |
| `backend/tests/test_redis_none.py` | Update assertions for new field names |
| `extension/package.json` | Add preact, @preactjs/preset-vite |
| `extension/vite.config.ts` | Add preact preset |
| `extension/tsconfig.json` | Add JSX config for Preact |
| `extension/src/sidepanel/sidepanel.ts` | Import mount bridge, delete old render code, update PanelState |
| `extension/src/sidepanel/sidepanel.html` | Simplify brief containers to mount points |
| `extension/src/sidepanel/sidepanel.css` | CSS variables, remove old brief styles |

---

## Progress Tracking

- [x] Task 1: Create SGR Pydantic models (`backend/briefing/models.py`)
- [x] Task 2: Transform Scenario → BriefData
- [x] Task 3: Update `generate_briefing()` with SGR prompt + Reparser
- [x] Task 4: Update API endpoint and backend tests
- [x] Task 5: Add Preact to extension build
- [x] Task 6: Create BriefData TypeScript types + brief.css
- [x] Task 7: Build Preact components (ContactCard → ExpandButton)
- [x] Task 8: Create mount bridge + update sidepanel.html
- [x] Task 9: Wire into sidepanel.ts (replace old code, storage migration)
- [x] Task 10: Visual QA and integration test

**Total Tasks:** 10 | **Completed:** 10 | **Remaining:** 0

**Status:** COMPLETE

---

### Task 1: Create SGR Pydantic models

**Files:**
- Create: `backend/briefing/models.py`
- Test: `backend/tests/test_briefing.py`

**Context:** SGR contract — `Field(description=...)` doubles as LLM instructions AND documentation. The schema IS the prompt. See `specs/FEAT-012-sgr-contract.md` for the full contract.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_briefing.py`:

```python
from typing import get_type_hints


class TestBriefDataModels:
    """Tests for SGR BriefData Pydantic models."""

    def test_brief_data_serializes_to_camelcase(self):
        from backend.briefing.models import BriefContact, BriefData, BriefFocusPoint

        brief = BriefData(
            contact=BriefContact(role="CTO", company="Acme"),
            focus_points=[BriefFocusPoint(headline="Test", detail="Detail")],
            pain_points=["pain1"],
        )
        data = brief.model_dump(by_alias=True)
        assert "focusPoints" in data
        assert "painPoints" in data
        assert "profileTags" in data
        assert "fullBrief" in data
        assert "focus_points" not in data

    def test_brief_profile_tag_rejects_invalid_color(self):
        from backend.briefing.models import BriefProfileTag

        with pytest.raises(Exception):
            BriefProfileTag(label="test", color="yellow")

    def test_brief_profile_tag_accepts_valid_colors(self):
        from backend.briefing.models import BriefProfileTag

        for color in ("blue", "green", "amber"):
            tag = BriefProfileTag(label="test", color=color)
            assert tag.color == color

    def test_brief_data_empty_defaults(self):
        from backend.briefing.models import BriefData

        brief = BriefData()
        data = brief.model_dump(by_alias=True)
        assert data["contact"]["role"] == ""
        assert data["profileTags"] == []
        assert data["focusPoints"] == []
        assert data["painPoints"] == []
        assert data["roi"] is None
        assert data["comparison"] is None
        assert data["objections"] == []
        assert data["fullBrief"] == ""

    def test_brief_data_schema_has_descriptions(self):
        """SGR: every field in the schema must have a description for the LLM."""
        from backend.briefing.models import BriefContact, BriefFocusPoint, BriefObjection

        for model in (BriefContact, BriefFocusPoint, BriefObjection):
            schema = model.model_json_schema()
            for name, prop in schema.get("properties", {}).items():
                assert "description" in prop, f"{model.__name__}.{name} missing description"

    def test_brief_data_json_schema_for_llm(self):
        """BriefData.model_json_schema() is valid for response_format."""
        from backend.briefing.models import BriefData

        schema = BriefData.model_json_schema()
        assert "properties" in schema
        assert "contact" in schema["properties"]

    def test_brief_data_validates_llm_response(self):
        """BriefData can parse a typical LLM JSON response."""
        from backend.briefing.models import BriefData

        llm_response = {
            "contact": {"role": "CTO", "company": "Test Corp"},
            "profileTags": [{"label": "ROI-focused", "color": "blue"}],
            "focusPoints": [{"headline": "Save time", "detail": "Auto-fill CRM"}],
            "painPoints": ["Manual data entry"],
            "roi": {"value": "42M", "description": "annual revenue uplift"},
            "comparison": None,
            "objections": [{"question": "Too expensive", "answer": "30% savings"}],
            "fullBrief": "Full text here.",
        }
        brief = BriefData.model_validate(llm_response)
        assert brief.contact.role == "CTO"
        assert brief.roi is not None
        assert brief.roi.value == "42M"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_briefing.py::TestBriefDataModels -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `backend/briefing/models.py`**

```python
"""SGR BriefData models — schema IS the LLM prompt (FEAT-012).

Every Field(description=...) serves dual purpose:
1. Pydantic documentation
2. LLM instruction when schema is passed via response_format

See specs/FEAT-012-sgr-contract.md for the full contract.
"""

from __future__ import annotations

from typing import Annotated, Literal

from annotated_types import MaxLen
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    """Base model: camelCase JSON aliases, snake_case Python attrs."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class BriefContact(_CamelModel):
    role: str = Field(
        default="",
        description="Должность ЛПР. Извлеки из документов. Пример: 'Коммерческий директор'",
    )
    company: str = Field(
        default="",
        description="Название компании клиента. Пример: 'ООО «СтройГрупп»'",
    )
    company_detail: str = Field(
        default="",
        description="Одна краткая деталь о компании (филиалы, сотрудники). Пусто если нет.",
    )
    budget_note: str = Field(
        default="",
        description="Кто согласовывает бюджет. Пусто если нет в документах.",
    )


class BriefProfileTag(_CamelModel):
    label: str = Field(
        description="Поведенческая черта покупателя, до 3 слов.",
    )
    color: Literal["blue", "green", "amber"] = Field(
        description="blue=аналитика, green=рост, amber=срочность",
    )


class BriefFocusPoint(_CamelModel):
    headline: str = Field(
        description="Краткий тезис до 5 слов — ЧТО предложить.",
    )
    detail: str = Field(
        default="",
        description="Одно предложение — ПОЧЕМУ это важно клиенту.",
    )


class BriefRoi(_CamelModel):
    value: str = Field(
        description="Главное число ROI с единицей. Verbatim из документов.",
    )
    description: str = Field(
        description="Одно предложение — что это число означает.",
    )


class BriefComparisonSide(_CamelModel):
    name: str = Field(description="Название решения")
    price: str = Field(description="Цена verbatim из документов")
    pros: str = Field(default="", description="Плюсы (для нашего предложения)")
    cons: str = Field(default="", description="Минусы (для текущего решения)")


class BriefComparison(_CamelModel):
    current: BriefComparisonSide = Field(
        description="Текущее решение клиента. Если не упомянуто — null для comparison.",
    )
    proposed: BriefComparisonSide = Field(
        description="Наше предложение.",
    )


class BriefObjection(_CamelModel):
    question: str = Field(
        description="Возражение клиента, в кавычках, от первого лица.",
    )
    answer: str = Field(
        description="Готовый ответ, с цифрами, до 2 предложений.",
    )


class BriefData(_CamelModel):
    """SGR root schema. Field order matters: context → strategy → tactics."""

    contact: BriefContact = Field(default_factory=BriefContact)
    profile_tags: Annotated[list[BriefProfileTag], MaxLen(3)] = Field(default_factory=list)
    pain_points: Annotated[list[str], MaxLen(5)] = Field(default_factory=list)
    focus_points: Annotated[list[BriefFocusPoint], MaxLen(3)] = Field(default_factory=list)
    roi: BriefRoi | None = Field(
        default=None,
        description="Null если в документах нет конкретных чисел для ROI.",
    )
    comparison: BriefComparison | None = Field(
        default=None,
        description="Null если текущее решение клиента не упомянуто.",
    )
    objections: Annotated[list[BriefObjection], MaxLen(3)] = Field(default_factory=list)
    full_brief: str = Field(
        default="",
        description="Полный текстовый бриф, plain text, 300-500 слов.",
    )
```

- [ ] **Step 4: Run tests — all pass**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_briefing.py::TestBriefDataModels -v`

- [ ] **Step 5: Commit**

```bash
git add backend/briefing/models.py backend/tests/test_briefing.py
git commit -m "feat(briefing): SGR BriefData Pydantic models with LLM-descriptive fields"
```

---

### Task 2: Transform Scenario → BriefData

**Files:**
- Modify: `backend/briefing/portrait.py`
- Test: `backend/tests/test_briefing.py`

**Context:** The Scenario fast-path bypasses LLM. We map Scenario fields to BriefData per the SGR contract mapping table. Missing fields (`company`, `roi`, `comparison`, `full_brief`) stay as defaults — this is an intentional tradeoff (speed vs completeness). See SGR contract § "Scenario → BriefData Mapping".

- [ ] **Step 1: Write tests for `scenario_to_brief()`**

Add `TestScenarioToBrief` class to `backend/tests/test_briefing.py` with tests for:
- Portrait → contact mapping (role, budget_note)
- `Objection.trigger` → `BriefObjection.question` rename
- `key_messages` → `focus_points` conversion
- Caps: max 3 focus_points, max 3 objections
- Avatar initials generation from role
- Motivators → profile_tags with rotating colors
- Empty scenario → empty BriefData (no crash)

```python
class TestScenarioToBrief:
    def test_maps_portrait_to_contact(self):
        from backend.briefing.portrait import scenario_to_brief
        from backend.pipeline.scenario import BuyerPortrait, Scenario

        scenario = Scenario(
            portrait=BuyerPortrait(role="CTO", budget="500K", pain_points=["latency"]),
        )
        brief = scenario_to_brief(scenario)
        assert brief.contact.role == "CTO"
        assert brief.contact.budget_note == "500K"
        assert brief.pain_points == ["latency"]

    def test_maps_trigger_to_question(self):
        from backend.briefing.portrait import scenario_to_brief
        from backend.pipeline.scenario import Objection, Scenario

        scenario = Scenario(objections=[
            Objection(trigger="дорого", response="ROI за 3 мес"),
        ])
        brief = scenario_to_brief(scenario)
        assert brief.objections[0].question == "дорого"
        assert brief.objections[0].answer == "ROI за 3 мес"

    def test_maps_key_messages_to_focus_points(self):
        from backend.briefing.portrait import scenario_to_brief
        from backend.pipeline.scenario import Scenario, Strategy

        scenario = Scenario(strategy=Strategy(key_messages=["Fast", "Cheap", "Good"]))
        brief = scenario_to_brief(scenario)
        assert len(brief.focus_points) == 3
        assert brief.focus_points[0].headline == "Fast"

    def test_caps_at_3(self):
        from backend.briefing.portrait import scenario_to_brief
        from backend.pipeline.scenario import Objection, Scenario, Strategy

        scenario = Scenario(
            strategy=Strategy(key_messages=["a", "b", "c", "d", "e"]),
            objections=[Objection(trigger=f"t{i}", response=f"r{i}") for i in range(5)],
        )
        brief = scenario_to_brief(scenario)
        assert len(brief.focus_points) == 3
        assert len(brief.objections) == 3

    def test_generates_initials(self):
        from backend.briefing.portrait import scenario_to_brief
        from backend.pipeline.scenario import BuyerPortrait, Scenario

        brief = scenario_to_brief(Scenario(portrait=BuyerPortrait(role="Коммерческий директор")))
        assert brief.contact.avatar_initials == "КД"

    def test_motivators_to_tags(self):
        from backend.briefing.portrait import scenario_to_brief
        from backend.pipeline.scenario import BuyerPortrait, Scenario

        scenario = Scenario(portrait=BuyerPortrait(motivators=["ROI-focused", "Likes data"]))
        brief = scenario_to_brief(scenario)
        assert len(brief.profile_tags) == 2
        assert brief.profile_tags[0].color in ("blue", "green", "amber")

    def test_empty_scenario(self):
        from backend.briefing.models import BriefData
        from backend.briefing.portrait import scenario_to_brief
        from backend.pipeline.scenario import Scenario

        brief = scenario_to_brief(Scenario())
        assert isinstance(brief, BriefData)
        assert brief.contact.role == ""
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement `scenario_to_brief()` and `_make_initials()` in `portrait.py`**

Add imports from `backend.briefing.models` and `backend.pipeline.scenario`. Implement the transformation per the SGR contract mapping table.

- [ ] **Step 4: Run tests — all pass**
- [ ] **Step 5: Commit**

---

### Task 3: Update `generate_briefing()` with SGR prompt + Reparser

**Files:**
- Modify: `backend/briefing/portrait.py` (full rewrite)
- Test: `backend/tests/test_briefing.py`

**Context:** Three generation paths, all returning `BriefData`:
1. **Cache hit (v2):** Parse and return
2. **Scenario path:** `scenario_to_brief()` + cache result
3. **LLM path:** SGR prompt with `BriefData.model_json_schema()` in system prompt, Reparser pattern on failure

Key changes from old code:
- Delete `BriefingResponse` dataclass
- New `_SYSTEM_PROMPT` with SGR schema
- `_parse_briefing()` → validate with `BriefData.model_validate()`
- v1 cache detection: if JSON has `"portrait"` key → skip, fall through to regeneration
- Cache only after successful validation
- Scenario path result is cached to Redis

- [ ] **Step 1: Write tests**

Replace `TestBriefing` class with tests for:
- LLM path returns `BriefData`
- Scenario path returns `BriefData` and caches result
- v1 cached data triggers LLM re-generation
- `redis=None` returns empty `BriefData`
- Reparser: invalid JSON → retry

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Rewrite `portrait.py`**

Full file replacement. Key implementation details:
- `_SYSTEM_PROMPT` includes `BriefData.model_json_schema()` as the JSON schema
- `_BRIEFING_TEMPLATE` sends documents + instruction to fill schema
- `_parse_briefing()` uses `BriefData.model_validate()` with v1 detection
- `generate_briefing()` returns `BriefData` on all paths
- Scenario path caches: `redis.set(cache_key, result.model_dump_json(by_alias=True))`
- LLM path caches only after successful parse
- Reparser: on `ValidationError`, send error back to LLM for one retry

- [ ] **Step 4: Run all tests**
- [ ] **Step 5: Commit**

---

### Task 4: Update API endpoint and backend tests

**Files:**
- Modify: `backend/api/briefing.py`
- Modify: `backend/tests/test_redis_none.py`
- Test: Full backend suite

- [ ] **Step 1: Write endpoint test asserting camelCase keys**
- [ ] **Step 2: Run test — fails (old format)**
- [ ] **Step 3: Update `briefing.py`** — `result.model_dump(by_alias=True)`
- [ ] **Step 4: Update `test_redis_none.py`** — new field names, remove unused `mock_redis` param
- [ ] **Step 5: Run full backend suite**
- [ ] **Step 6: Commit**

---

### Task 5: Add Preact to extension build

**Files:**
- Modify: `extension/package.json`
- Modify: `extension/vite.config.ts`
- Modify: `extension/tsconfig.json`

**Context:** Strangler fig — only the brief panel uses Preact. Rest of UI stays vanilla TS. We need:
- `preact` (3KB gzipped)
- `@preactjs/preset-vite` (JSX transform)
- TSConfig: `"jsx": "react-jsx"`, `"jsxImportSource": "preact"`
- Add `*.tsx` to tsconfig includes

- [ ] **Step 1: Install Preact deps**

```bash
cd /Users/teterinsa/Projects/crmcore/extension && pnpm add preact && pnpm add -D @preactjs/preset-vite
```

- [ ] **Step 2: Update `vite.config.ts`**

Add preact preset:
```typescript
import preact from "@preactjs/preset-vite";

export default defineConfig({
  plugins: [
    preact(),
    webExtension({ ... }),
  ],
});
```

- [ ] **Step 3: Update `tsconfig.json`**

Add JSX support:
```json
{
  "compilerOptions": {
    "jsx": "react-jsx",
    "jsxImportSource": "preact"
  },
  "include": ["src/**/*.ts", "src/**/*.tsx"]
}
```

- [ ] **Step 4: Create smoke-test component**

Create `extension/src/sidepanel/brief/Smoke.tsx`:
```tsx
export function Smoke() {
  return <div data-testid="preact-smoke">Preact works</div>;
}
```

- [ ] **Step 5: Verify build compiles**

```bash
cd /Users/teterinsa/Projects/crmcore/extension && npx vite build
```

- [ ] **Step 6: Delete smoke test, commit**

```bash
rm extension/src/sidepanel/brief/Smoke.tsx
git add extension/package.json extension/vite.config.ts extension/tsconfig.json pnpm-lock.yaml
git commit -m "feat(extension): add Preact to build pipeline (strangler fig)"
```

---

### Task 6: Create BriefData TypeScript types + CSS

**Files:**
- Create: `extension/src/sidepanel/brief/types.ts`
- Create: `extension/src/sidepanel/brief/brief.css`
- Modify: `extension/src/sidepanel/sidepanel.css` (add CSS variables to `:root`, remove old brief styles)

**Context:** Types mirror the backend SGR contract. CSS uses custom properties for the design system per the design spec.

- [ ] **Step 1: Create `types.ts`**

```typescript
/** BriefData — mirrors backend SGR contract (specs/FEAT-012-sgr-contract.md). */

export interface BriefContact {
  role: string;
  company: string;
  companyDetail?: string;
  avatarInitials?: string;  // Generated on frontend from role
  budgetNote?: string;
}

export interface BriefProfileTag {
  label: string;
  color: "blue" | "green" | "amber";
}

export interface BriefFocusPoint {
  headline: string;
  detail?: string;
}

export interface BriefRoi {
  value: string;
  description: string;
}

export interface BriefComparisonSide {
  name: string;
  price: string;
  pros?: string;
  cons?: string;
}

export interface BriefComparison {
  current: BriefComparisonSide;
  proposed: BriefComparisonSide;
}

export interface BriefObjection {
  question: string;
  answer: string;
}

export interface BriefData {
  contact: BriefContact;
  profileTags: BriefProfileTag[];
  painPoints: string[];
  focusPoints: BriefFocusPoint[];
  roi?: BriefRoi | null;
  comparison?: BriefComparison | null;
  objections: BriefObjection[];
  fullBrief?: string;
}
```

- [ ] **Step 2: Create `brief.css`** — all `.brief-*` component styles per design spec

- [ ] **Step 3: Add CSS variables to `sidepanel.css` `:root`** — design tokens

- [ ] **Step 4: Remove old brief styles from `sidepanel.css`** — `.portrait-*`, `.chip*`, `.approach-*`, `.key-messages-*`, `.avoid-*`, `.objection-card`, `.objection-q`, `.objection-a`

- [ ] **Step 5: Verify build**
- [ ] **Step 6: Commit**

---

### Task 7: Build Preact components

**Files:**
- Create: `extension/src/sidepanel/brief/ContactCard.tsx`
- Create: `extension/src/sidepanel/brief/FocusPoints.tsx`
- Create: `extension/src/sidepanel/brief/PainPoints.tsx`
- Create: `extension/src/sidepanel/brief/RoiHighlight.tsx`
- Create: `extension/src/sidepanel/brief/ComparisonCards.tsx`
- Create: `extension/src/sidepanel/brief/ObjectionCards.tsx`
- Create: `extension/src/sidepanel/brief/ExpandButton.tsx`
- Create: `extension/src/sidepanel/brief/Divider.tsx`
- Create: `extension/src/sidepanel/brief/BriefPanel.tsx`

**Context:** Each component receives typed props from `BriefData`. Components return `null` when data is missing (graceful hide). Text content rendered via JSX `{text}` — Preact auto-escapes (no XSS). `fullBrief` rendered as `textContent` equivalent via `<pre>` with `white-space: pre-wrap`. Caps enforced: `.slice(0, 3)`.

- [ ] **Step 1: Create `Divider.tsx`**

```tsx
export function Divider() {
  return <div class="brief-divider" />;
}
```

- [ ] **Step 2: Create `ContactCard.tsx`**

```tsx
import type { BriefContact, BriefProfileTag } from "./types";

function makeInitials(role: string): string {
  const words = role.trim().split(/\s+/);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  if (words.length === 1 && words[0]) return words[0].slice(0, 2).toUpperCase();
  return "";
}

interface Props {
  contact: BriefContact;
  tags: BriefProfileTag[];
}

export function ContactCard({ contact, tags }: Props) {
  if (!contact.role) return null;

  const initials = contact.avatarInitials || makeInitials(contact.role);
  const company = [contact.company, contact.companyDetail].filter(Boolean).join(" \u00B7 ");

  return (
    <div class="brief-contact-card">
      <div class="brief-contact-row">
        {initials && <div class="brief-avatar">{initials}</div>}
        <div class="brief-contact-info">
          <div class="brief-contact-role">{contact.role}</div>
          {company && <div class="brief-contact-company">{company}</div>}
          {contact.budgetNote && <div class="brief-contact-budget">{contact.budgetNote}</div>}
        </div>
      </div>
      {tags.length > 0 && (
        <div class="brief-tags">
          {tags.slice(0, 3).map((tag) => (
            <span key={tag.label} class={`brief-tag brief-tag--${tag.color}`}>{tag.label}</span>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create `FocusPoints.tsx`**

```tsx
import type { BriefFocusPoint } from "./types";

export function FocusPoints({ points }: { points: BriefFocusPoint[] }) {
  const capped = points.slice(0, 3);
  if (capped.length === 0) return null;

  return (
    <div class="brief-focus">
      <div class="brief-section-label">ФОКУС РАЗГОВОРА</div>
      <div class="brief-focus-list">
        {capped.map((fp, i) => (
          <div key={i} class="brief-focus-item">
            <span class="brief-focus-num">{i + 1}</span>
            <div class="brief-focus-text">
              <span class="brief-focus-headline">{fp.headline}</span>
              {fp.detail && <>{" \u2014 "}<span class="brief-focus-detail">{fp.detail}</span></>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create `PainPoints.tsx`, `RoiHighlight.tsx`, `ComparisonCards.tsx`, `ObjectionCards.tsx`, `ExpandButton.tsx`**

Each follows the same pattern: typed props, return `null` if data is empty/null, caps via `.slice()`. See SGR contract for display rules.

`ExpandButton` uses `useState` for toggle state:
```tsx
import { useState } from "preact/hooks";

export function ExpandButton({ text }: { text?: string }) {
  const [open, setOpen] = useState(false);
  if (!text) return null;

  return (
    <div class="brief-expand-wrapper">
      <button
        class="brief-expand-btn"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        {open ? "Скрыть полный бриф \u2191" : "Открыть полный бриф \u2192"}
      </button>
      {open && <pre class="brief-expand-content">{text}</pre>}
    </div>
  );
}
```

- [ ] **Step 5: Create `BriefPanel.tsx`** — orchestrator

```tsx
import type { BriefData } from "./types";
import { ComparisonCards } from "./ComparisonCards";
import { ContactCard } from "./ContactCard";
import { Divider } from "./Divider";
import { ExpandButton } from "./ExpandButton";
import { FocusPoints } from "./FocusPoints";
import { ObjectionCards } from "./ObjectionCards";
import { PainPoints } from "./PainPoints";
import { RoiHighlight } from "./RoiHighlight";

interface Props {
  data: BriefData;
  compact?: boolean;  // Phase 3: only ContactCard + FocusPoints
}

export function BriefPanel({ data, compact }: Props) {
  if (compact) {
    return (
      <div class="brief-panel">
        <ContactCard contact={data.contact} tags={data.profileTags} />
        <FocusPoints points={data.focusPoints} />
      </div>
    );
  }

  return (
    <div class="brief-panel">
      <ContactCard contact={data.contact} tags={data.profileTags} />
      <Divider />
      <FocusPoints points={data.focusPoints} />
      <PainPoints points={data.painPoints} />
      <Divider />
      <RoiHighlight roi={data.roi} />
      <ComparisonCards comparison={data.comparison} />
      <Divider />
      <ObjectionCards objections={data.objections} />
      <ExpandButton text={data.fullBrief} />
    </div>
  );
}
```

- [ ] **Step 6: Verify build**
- [ ] **Step 7: Commit**

---

### Task 8: Create mount bridge + update HTML

**Files:**
- Create: `extension/src/sidepanel/brief/mount.ts`
- Modify: `extension/src/sidepanel/sidepanel.html`

**Context:** The mount bridge lets vanilla TS code render/update/unmount Preact components into DOM containers. This is the strangler fig boundary.

- [ ] **Step 1: Create `mount.ts`**

```typescript
import { render, h } from "preact";
import { BriefPanel } from "./BriefPanel";
import type { BriefData } from "./types";
import "./brief.css";

/**
 * Mount/update brief panel into a DOM container.
 * Call with data=null to unmount (clear container).
 */
export function mountBriefPanel(
  container: HTMLElement,
  data: BriefData | null,
  compact = false,
): void {
  if (!data) {
    render(null, container);
    return;
  }
  render(h(BriefPanel, { data, compact }), container);
}

/**
 * Type guard: checks if cached data is v2 BriefData format.
 */
export function isBriefDataV2(data: unknown): data is BriefData {
  return (
    typeof data === "object" &&
    data !== null &&
    "contact" in data &&
    "focusPoints" in data
  );
}
```

- [ ] **Step 2: Update `sidepanel.html`**

Replace Phase 2 `<details>` blocks with a single mount point:
```html
<div id="briefing-content" hidden>
  <!-- Preact BriefPanel mounts here -->
</div>
```

Replace Phase 3 collapsed brief:
```html
<div id="briefing-collapsed" class="briefing-collapsed">
  <!-- Preact BriefPanel (compact) mounts here -->
</div>
```

Replace Phase 4 brief:
```html
<div id="briefing-collapsed-done" class="briefing-collapsed">
  <!-- Preact BriefPanel mounts here -->
</div>
```

Preserve `#briefing-content` ID (referenced by `setPhase()`).

- [ ] **Step 3: Verify build**
- [ ] **Step 4: Commit**

---

### Task 9: Wire into sidepanel.ts

**Files:**
- Modify: `extension/src/sidepanel/sidepanel.ts`

**Context:** This is the integration task. Remove old types and render functions. Import mount bridge. Update `PanelState`. Add client-side v1 migration. Fix `resetForNewCall()`.

- [ ] **Step 1: Add import**

```typescript
import { isBriefDataV2, mountBriefPanel } from "./brief/mount";
import type { BriefData } from "./brief/types";
```

- [ ] **Step 2: Delete old interfaces** — `BriefingPortrait`, `BriefingStrategy`, `BriefingObjection`, `BriefingData` (lines 244-268)

- [ ] **Step 3: Update `PanelState`** — `briefing: BriefData | null`

- [ ] **Step 4: Delete old render functions** — `renderPortrait`, `renderStrategy`, `renderObjections`, `renderBriefingToContainers` (lines 1452-1548)

- [ ] **Step 5: Add new `renderBriefToAllPhases()`**

```typescript
function renderBriefToAllPhases(data: BriefData): void {
  const phase2 = $("briefing-content");
  if (phase2) mountBriefPanel(phase2, data);

  const phase3 = $("briefing-collapsed");
  if (phase3) mountBriefPanel(phase3, data, true);  // compact

  const phase4 = $("briefing-collapsed-done");
  if (phase4) mountBriefPanel(phase4, data);
}
```

- [ ] **Step 6: Update `fetchAndRenderBriefing()`** — cast to `BriefData`, call `renderBriefToAllPhases`

- [ ] **Step 7: Update `init()` storage restore** — add `isBriefDataV2()` check, clear stale v1 data

```typescript
if (state.briefing) {
  if (isBriefDataV2(state.briefing)) {
    renderBriefToAllPhases(state.briefing);
  } else {
    await saveState({ briefing: null });
  }
  updateFileStrip(state.fileNames);
}
```

- [ ] **Step 8: Fix `resetForNewCall()`** — clear storage + unmount Preact

```typescript
void saveState({ briefing: null });
const phase2 = $("briefing-content");
if (phase2) mountBriefPanel(phase2, null);
hide($("briefing-content"));
const phase3 = $("briefing-collapsed");
if (phase3) mountBriefPanel(phase3, null);
const phase4 = $("briefing-collapsed-done");
if (phase4) mountBriefPanel(phase4, null);
```

- [ ] **Step 9: Delete `escapeHtml` function** (Preact auto-escapes JSX)

- [ ] **Step 10: Verify build**
- [ ] **Step 11: Commit**

---

### Task 10: Visual QA and integration test

- [ ] **Step 1: Build extension** — `cd extension && npx vite build`
- [ ] **Step 2: Run backend tests** — `python -m pytest backend/tests/ -v`
- [ ] **Step 3: Load extension in Chrome**
- [ ] **Step 4: Start backend** — `python -m uvicorn backend.main:app --reload`
- [ ] **Step 5: Visual QA checklist**

Phase 2:
- [ ] ContactCard: avatar, role, company, tags
- [ ] FocusPoints: 3 numbered items max, section label
- [ ] PainPoints: red `!` markers
- [ ] ROI: green highlight (or hidden if null)
- [ ] Comparison: side-by-side (or hidden if null)
- [ ] ObjectionCards: Q&A, max 3, `→` prefix
- [ ] ExpandButton: toggles fullBrief text
- [ ] No horizontal overflow at 380px
- [ ] Text clamps at 2 lines

Phase 3:
- [ ] Compact brief: ContactCard + FocusPoints only
- [ ] Splitter works with new content height

Phase 4:
- [ ] Full brief in post-call view
- [ ] "New Call" clears all brief content

Storage:
- [ ] Extension reopen restores cached brief
- [ ] Old v1 cached data silently cleared

- [ ] **Step 6: Final commit**

---

## Risk Mitigations

| Risk | Mitigation |
|---|---|
| BLOCKER: Scenario fast-path returns old format | Task 2: `scenario_to_brief()` + cache result |
| BLOCKER: chrome.storage.local v1 data | Task 9 Step 7: `isBriefDataV2()` + clear stale |
| BLOCKER: PanelState.briefing type | Task 9 Step 3: explicit type change |
| MAJOR: snake/camelCase gap | Task 1: `alias_generator=to_camel` |
| MAJOR: BriefingResponse is dataclass | Task 3: delete, return `BriefData` |
| MAJOR: Phase 3/4 undefined | Task 8: mount points + compact prop |
| MAJOR: fullBrief XSS | Task 7: Preact auto-escapes, `<pre>` for fullBrief |
| MAJOR: No error boundaries | Preact components return `null` on missing data |
| SGR: LLM hallucination | `Field(description="null если нет данных")` + triple validation |
| SGR: Invalid color | `Literal["blue","green","amber"]` in Pydantic |
| Edge: trigger→question key | Task 2: explicit mapping |
| Edge: resetForNewCall leak | Task 9 Step 8: `saveState({briefing: null})` + unmount |
| Edge: Scenario path not cached | Task 3: cache after transform |
| Edge: Bad LLM output cached | Task 3: cache only after successful parse |
| Edge: 380px overflow | Task 6: `max-width: 380px; overflow-x: hidden` |
