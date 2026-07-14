---
name: interface-design
description: Design system for consistent UI across sessions. Craft, memory, and enforcement for dashboards, admin panels, and applications. Use when building interfaces with shadcn/ui.
---

# Interface Design Skill

**Core Rule:** Design decisions must be explicit and persistent. No drift across sessions.

## When to Use

- Building dashboards and admin panels
- Creating consistent component libraries
- Establishing design tokens and patterns
- Reviewing UI for consistency

**NOT for:** Marketing sites, landing pages (use web-design-guidelines instead)

## Philosophy

> When you build UI with Claude, design decisions get made: spacing values, colors, depth strategy, surface elevation. Without structure, those decisions drift across sessions.

This skill provides:
1. **Craft** — Principle-based design guidance
2. **Memory** — Persists decisions in `.interface-design/system.md`
3. **Consistency** — Ensures components follow established patterns

## Design Direction Templates

### Precision & Density (Developer Tools, Admin Panels)

```markdown
## Design Direction: Precision & Density

**Character:** Technical, efficient, information-dense
**Users:** Power users, developers, administrators

### Spacing Scale
- xs: 4px (0.25rem)
- sm: 8px (0.5rem)
- md: 12px (0.75rem)
- lg: 16px (1rem)
- xl: 24px (1.5rem)

### Typography
- Font: Inter, system-ui
- Base: 13px / 1.5
- Headers: 600 weight
- Monospace: JetBrains Mono for code

### Colors
- Background: hsl(0 0% 100%) / hsl(240 10% 4%)
- Surface: hsl(0 0% 98%) / hsl(240 6% 10%)
- Border: hsl(0 0% 90%) / hsl(240 4% 16%)
- Primary: hsl(220 90% 56%)
- Destructive: hsl(0 84% 60%)
- Muted: hsl(0 0% 46%)

### Depth Strategy
- Minimal shadows
- Border-defined containers
- Subtle hover states (background shift)

### Component Patterns
- Dense tables with 32px rows
- Compact form inputs (32px height)
- Icon-only actions where possible
- Keyboard shortcuts prominent
```

### Warmth & Approachability (Consumer Apps)

```markdown
## Design Direction: Warmth & Approachability

**Character:** Friendly, accessible, inviting
**Users:** General consumers, non-technical users

### Spacing Scale
- xs: 8px (0.5rem)
- sm: 12px (0.75rem)
- md: 16px (1rem)
- lg: 24px (1.5rem)
- xl: 32px (2rem)
- 2xl: 48px (3rem)

### Typography
- Font: Plus Jakarta Sans, system-ui
- Base: 16px / 1.6
- Headers: 700 weight
- Rounded, friendly feel

### Colors
- Background: hsl(30 25% 98%) / hsl(220 20% 10%)
- Surface: hsl(30 20% 100%) / hsl(220 15% 14%)
- Primary: hsl(25 95% 53%) (warm orange)
- Accent: hsl(150 60% 45%) (friendly green)

### Depth Strategy
- Soft shadows (0 4px 12px rgba(0,0,0,0.08))
- Rounded corners (8-16px radius)
- Gradient accents

### Component Patterns
- Generous padding
- Large touch targets (44px minimum)
- Friendly illustrations
- Progress indicators
```

## System File Template

Create `.interface-design/system.md` in your project:

```markdown
# Interface Design System

**Project:** [Project Name]
**Direction:** [Precision & Density / Warmth & Approachability / Custom]
**Created:** [Date]

## Design Tokens

### Spacing
| Token | Value | Use |
|-------|-------|-----|
| --space-xs | 4px | Inline gaps |
| --space-sm | 8px | Component padding |
| --space-md | 12px | Section spacing |
| --space-lg | 16px | Card padding |
| --space-xl | 24px | Section gaps |

### Typography
| Token | Value |
|-------|-------|
| --font-sans | Inter, system-ui |
| --font-mono | JetBrains Mono |
| --text-xs | 11px / 1.4 |
| --text-sm | 13px / 1.5 |
| --text-base | 14px / 1.5 |
| --text-lg | 16px / 1.5 |
| --text-xl | 20px / 1.4 |

### Colors
[Define your palette]

### Radius
| Token | Value |
|-------|-------|
| --radius-sm | 4px |
| --radius-md | 6px |
| --radius-lg | 8px |
| --radius-full | 9999px |

## Component Standards

### Buttons
- Primary: filled, primary color
- Secondary: outlined, muted
- Ghost: no border, subtle hover
- Height: 32px (sm), 36px (md), 40px (lg)

### Forms
- Input height: 36px
- Label: text-sm, muted, above input
- Error: text-destructive, below input
- Required: asterisk after label

### Tables
- Row height: 40px
- Header: sticky, bold, muted background
- Hover: subtle background change
- Actions: right-aligned, icon buttons

### Cards
- Padding: space-lg
- Border: 1px solid border color
- Radius: radius-lg
- No shadow (or subtle)

## Layout Rules

### Page Structure
- Max width: 1440px
- Sidebar: 240px (collapsed: 64px)
- Content padding: space-xl

### Grid
- Columns: 12
- Gutter: space-md
- Responsive: stack below 768px

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| [Date] | Use 4px spacing base | Aligns with 8pt grid, allows density |
| [Date] | Inter for UI text | Excellent legibility at small sizes |
```

## shadcn/ui Integration

### Tailwind Config Alignment

```typescript
// tailwind.config.ts
export default {
  theme: {
    extend: {
      spacing: {
        'xs': '0.25rem',   // 4px
        'sm': '0.5rem',    // 8px
        'md': '0.75rem',   // 12px
        'lg': '1rem',      // 16px
        'xl': '1.5rem',    // 24px
      },
      fontSize: {
        'xs': ['0.6875rem', { lineHeight: '1.4' }],   // 11px
        'sm': ['0.8125rem', { lineHeight: '1.5' }],   // 13px
        'base': ['0.875rem', { lineHeight: '1.5' }],  // 14px
      },
      borderRadius: {
        'sm': '0.25rem',  // 4px
        'md': '0.375rem', // 6px
        'lg': '0.5rem',   // 8px
      },
    },
  },
}
```

### Component Customization

```typescript
// components/ui/button.tsx - customized for density
const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1",
  {
    variants: {
      size: {
        sm: "h-8 px-3 text-xs",     // 32px - dense
        default: "h-9 px-4",         // 36px
        lg: "h-10 px-6",             // 40px
        icon: "h-8 w-8",             // 32px square
      },
    },
    defaultVariants: {
      size: "default",
    },
  }
)
```

## Audit Checklist

When reviewing UI for consistency:

### Spacing
- [ ] All spacing uses defined tokens (no magic numbers)
- [ ] Consistent padding in similar components
- [ ] Proper visual hierarchy through spacing

### Typography
- [ ] Font sizes from scale only
- [ ] Consistent heading levels
- [ ] Proper line heights

### Colors
- [ ] All colors from palette
- [ ] Sufficient contrast (WCAG AA minimum)
- [ ] Consistent semantic usage (primary, destructive, etc.)

### Components
- [ ] Buttons follow size/variant standards
- [ ] Forms have consistent structure
- [ ] Tables use standard row heights
- [ ] Cards have uniform padding/radius

### Layout
- [ ] Grid alignment maintained
- [ ] Responsive breakpoints consistent
- [ ] Max-width respected

## Commands

```
/interface-design:status    - Show current design system
/interface-design:audit     - Check code for consistency violations
/interface-design:extract   - Extract patterns from existing code
/interface-design:init      - Create .interface-design/system.md
```

## Anti-Patterns

❌ **BAD: Magic numbers**
```tsx
<div className="p-[13px] mt-[7px]">
```

✅ **GOOD: Design tokens**
```tsx
<div className="p-md mt-sm">
```

❌ **BAD: Inconsistent sizing**
```tsx
<Button className="h-8">Save</Button>
<Button className="h-10">Cancel</Button> {/* Same context, different sizes */}
```

✅ **GOOD: Consistent sizing**
```tsx
<Button size="sm">Save</Button>
<Button size="sm">Cancel</Button>
```

❌ **BAD: Ad-hoc colors**
```tsx
<span className="text-[#666]">Subtitle</span>
```

✅ **GOOD: Semantic colors**
```tsx
<span className="text-muted-foreground">Subtitle</span>
```

## Resources

- [shadcn/ui](https://ui.shadcn.com/)
- [Radix UI Primitives](https://www.radix-ui.com/)
- [Tailwind CSS](https://tailwindcss.com/)
- [8pt Grid System](https://spec.fm/specifics/8-pt-grid)
