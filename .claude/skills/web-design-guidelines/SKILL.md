---
name: Web Design Guidelines
description: 100+ web design rules for accessibility, performance, and UX from Vercel. Use when reviewing UI code, checking accessibility, or auditing design patterns. Triggered by "check accessibility", "review UI", "design audit", "UX review", "a11y check".
source: https://github.com/vercel-labs/agent-skills
---

# Web Design Guidelines (Vercel)

100+ rules for accessibility, performance, and UX.

## Accessibility (a11y)

### Semantic HTML
```tsx
// BAD
<div onClick={handleClick}>Click me</div>

// GOOD
<button onClick={handleClick}>Click me</button>
```

### Keyboard Navigation
```tsx
// All interactive elements must be focusable
<button>Focusable by default</button>

// Custom interactive elements need tabIndex
<div
  role="button"
  tabIndex={0}
  onClick={handleClick}
  onKeyDown={(e) => e.key === 'Enter' && handleClick()}
>
  Custom button
</div>
```

### ARIA Labels
```tsx
// Icon-only buttons need labels
<button aria-label="Close dialog">
  <XIcon />
</button>

// Form inputs need labels
<label htmlFor="email">Email</label>
<input id="email" type="email" />

// Or use aria-label
<input aria-label="Search" type="search" />
```

### Focus Management
```tsx
// Trap focus in modals
import { FocusTrap } from '@headlessui/react'

<FocusTrap>
  <dialog open>
    <h2>Modal Title</h2>
    <button>Action</button>
    <button>Close</button>
  </dialog>
</FocusTrap>
```

### Color Contrast
```css
/* Minimum contrast ratios (WCAG 2.1 AA) */
/* Normal text: 4.5:1 */
/* Large text (18px+ or 14px bold): 3:1 */
/* UI components: 3:1 */

/* Tools: */
/* - Chrome DevTools > Lighthouse */
/* - axe DevTools extension */
```

### Screen Reader Support
```tsx
// Live regions for dynamic content
<div aria-live="polite" aria-atomic="true">
  {message}
</div>

// Hidden text for screen readers only
<span className="sr-only">
  Opens in new tab
</span>
```

## Performance

### Image Optimization
```tsx
// Next.js Image component
import Image from 'next/image'

<Image
  src="/hero.jpg"
  alt="Hero image"
  width={1200}
  height={600}
  priority  // LCP image
  placeholder="blur"
  blurDataURL={blurHash}
/>
```

### Lazy Loading
```tsx
// Images below fold
<Image loading="lazy" ... />

// Components
const HeavyComponent = dynamic(() => import('./Heavy'), {
  loading: () => <Skeleton />
})
```

### Font Optimization
```tsx
// next/font (automatic optimization)
import { Inter } from 'next/font/google'

const inter = Inter({ subsets: ['latin'] })

export default function Layout({ children }) {
  return (
    <html className={inter.className}>
      <body>{children}</body>
    </html>
  )
}
```

### Animation Performance
```css
/* Use transform and opacity (GPU accelerated) */
.animate {
  transform: translateX(100px);
  opacity: 0.5;
  transition: transform 0.3s, opacity 0.3s;
}

/* Avoid animating */
/* - width, height */
/* - top, left, right, bottom */
/* - margin, padding */
```

### Reduce Motion
```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

## UX Patterns

### Focus States
```css
/* Always visible focus indicators */
button:focus-visible {
  outline: 2px solid var(--focus-color);
  outline-offset: 2px;
}

/* Don't remove outlines */
button:focus {
  outline: none; /* BAD */
}
```

### Form Validation
```tsx
// Inline validation with clear errors
<div>
  <label htmlFor="email">Email</label>
  <input
    id="email"
    type="email"
    aria-invalid={errors.email ? 'true' : 'false'}
    aria-describedby={errors.email ? 'email-error' : undefined}
  />
  {errors.email && (
    <p id="email-error" role="alert" className="text-destructive">
      {errors.email.message}
    </p>
  )}
</div>
```

### Loading States
```tsx
// Button loading state
<button disabled={isLoading}>
  {isLoading ? (
    <>
      <Spinner className="mr-2" />
      Saving...
    </>
  ) : (
    'Save'
  )}
</button>

// Skeleton loading
<div className="animate-pulse">
  <div className="h-4 bg-muted rounded w-3/4 mb-2" />
  <div className="h-4 bg-muted rounded w-1/2" />
</div>
```

### Empty States
```tsx
function EmptyState({ onAction }) {
  return (
    <div className="text-center py-12">
      <EmptyIcon className="mx-auto h-12 w-12 text-muted-foreground" />
      <h3 className="mt-2 text-lg font-medium">No items yet</h3>
      <p className="mt-1 text-muted-foreground">
        Get started by creating your first item.
      </p>
      <button onClick={onAction} className="mt-4">
        Create Item
      </button>
    </div>
  )
}
```

### Error States
```tsx
function ErrorState({ error, onRetry }) {
  return (
    <div role="alert" className="text-center py-12">
      <AlertIcon className="mx-auto h-12 w-12 text-destructive" />
      <h3 className="mt-2 text-lg font-medium">Something went wrong</h3>
      <p className="mt-1 text-muted-foreground">
        {error.message}
      </p>
      <button onClick={onRetry} className="mt-4">
        Try Again
      </button>
    </div>
  )
}
```

### Responsive Design
```css
/* Mobile-first breakpoints */
/* Default: mobile */
/* sm: 640px */
/* md: 768px */
/* lg: 1024px */
/* xl: 1280px */

.container {
  padding: 1rem;      /* mobile */
}

@media (min-width: 768px) {
  .container {
    padding: 2rem;    /* tablet+ */
  }
}
```

## Checklist

### Accessibility
- [ ] All images have alt text
- [ ] Color contrast meets WCAG AA (4.5:1)
- [ ] Keyboard navigation works
- [ ] Focus indicators visible
- [ ] Form inputs have labels
- [ ] Error messages announced to screen readers
- [ ] Skip link to main content

### Performance
- [ ] Images optimized (WebP, proper sizes)
- [ ] Fonts preloaded or using next/font
- [ ] No layout shift (CLS < 0.1)
- [ ] LCP image has priority
- [ ] Heavy components lazy loaded

### UX
- [ ] Loading states for async operations
- [ ] Error states with retry option
- [ ] Empty states with guidance
- [ ] Form validation is inline
- [ ] Animations respect prefers-reduced-motion
