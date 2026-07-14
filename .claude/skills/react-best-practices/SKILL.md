---
name: React Best Practices
description: 57 React optimization rules from Vercel. Use when reviewing React components, optimizing performance, or checking for common mistakes. Triggered by "review React", "optimize component", "React performance", "check React code".
source: https://github.com/vercel-labs/agent-skills
---

# React Best Practices (Vercel)

57 rules across 8 priority categories for React optimization.

## Critical: Eliminating Waterfalls

### 1. Parallel Data Fetching
```tsx
// BAD - sequential (waterfall)
const user = await getUser(id)
const posts = await getPosts(user.id)

// GOOD - parallel
const [user, posts] = await Promise.all([
  getUser(id),
  getPosts(id)
])
```

### 2. Start Fetching Early
```tsx
// BAD - fetch inside component
function UserProfile({ userId }) {
  const [user, setUser] = useState(null)
  useEffect(() => {
    fetchUser(userId).then(setUser)
  }, [userId])
}

// GOOD - fetch at route level (Next.js)
// app/users/[id]/page.tsx
export default async function UserPage({ params }) {
  const user = await getUser(params.id)
  return <UserProfile user={user} />
}
```

### 3. Use Suspense for Streaming
```tsx
// GOOD - parallel with Suspense
function Dashboard() {
  return (
    <div>
      <Suspense fallback={<UserSkeleton />}>
        <UserInfo />
      </Suspense>
      <Suspense fallback={<StatsSkeleton />}>
        <Stats />
      </Suspense>
    </div>
  )
}
```

## Critical: Bundle Size

### 4. Direct Imports
```tsx
// BAD - imports entire library
import { Button } from 'ui-library'

// GOOD - direct import
import Button from 'ui-library/Button'
```

### 5. Dynamic Import Heavy Components
```tsx
// GOOD - lazy load heavy components
const Chart = dynamic(() => import('./Chart'), {
  loading: () => <ChartSkeleton />,
  ssr: false
})
```

### 6. Analyze Bundle
```bash
# Next.js
ANALYZE=true npm run build

# Generic
npx source-map-explorer 'build/**/*.js'
```

## High: Server-Side Performance

### 7. Use React.cache for Deduplication
```tsx
import { cache } from 'react'

const getUser = cache(async (id: string) => {
  return await db.user.findUnique({ where: { id } })
})

// Multiple calls in same request = single DB query
```

### 8. Minimize Client Data
```tsx
// BAD - sending all fields to client
const user = await getFullUser(id)
return <UserCard user={user} />

// GOOD - select only needed fields
const user = await db.user.findUnique({
  where: { id },
  select: { name: true, avatar: true }
})
```

## Medium: Re-render Optimization

### 9. Memoize Expensive Computations
```tsx
// GOOD
const sortedItems = useMemo(
  () => items.sort((a, b) => a.name.localeCompare(b.name)),
  [items]
)
```

### 10. Stable Callback References
```tsx
// GOOD
const handleClick = useCallback((id: string) => {
  setSelected(id)
}, [])
```

### 11. Avoid Inline Objects in Props
```tsx
// BAD - new object every render
<Component style={{ color: 'red' }} />

// GOOD - stable reference
const style = useMemo(() => ({ color: 'red' }), [])
<Component style={style} />
```

### 12. Split Context by Update Frequency
```tsx
// GOOD - separate contexts
const UserContext = createContext(null)      // rarely changes
const UIContext = createContext(null)         // frequently changes
```

### 13. Use Suspense Boundaries
```tsx
// GOOD - isolate loading states
<Suspense fallback={<Spinner />}>
  <Comments postId={id} />
</Suspense>
```

## Medium: Rendering Performance

### 14. Use useTransition for Non-Urgent Updates
```tsx
const [isPending, startTransition] = useTransition()

function handleSearch(query: string) {
  startTransition(() => {
    setSearchResults(filterResults(query))
  })
}
```

### 15. Virtualize Long Lists
```tsx
import { FixedSizeList } from 'react-window'

<FixedSizeList
  height={400}
  itemCount={items.length}
  itemSize={50}
>
  {({ index, style }) => (
    <div style={style}>{items[index].name}</div>
  )}
</FixedSizeList>
```

### 16. Avoid Layout Thrashing
```tsx
// BAD - read then write repeatedly
elements.forEach(el => {
  const height = el.offsetHeight  // read
  el.style.height = height + 10   // write
})

// GOOD - batch reads, then writes
const heights = elements.map(el => el.offsetHeight)
elements.forEach((el, i) => {
  el.style.height = heights[i] + 10
})
```

## Lower: JavaScript Performance

### 17. Use Map/Set for Lookups
```tsx
// BAD - O(n) lookup
const hasItem = items.find(i => i.id === id)

// GOOD - O(1) lookup
const itemMap = new Map(items.map(i => [i.id, i]))
const hasItem = itemMap.has(id)
```

### 18. Hoist RegExp
```tsx
// BAD - creates new RegExp every call
function validate(email: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

// GOOD - create once
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
function validate(email: string) {
  return EMAIL_REGEX.test(email)
}
```

## Component Patterns

### 19. Prefer Server Components
```tsx
// Default: Server Component (no 'use client')
async function ProductList() {
  const products = await getProducts()
  return <ul>{products.map(p => <li key={p.id}>{p.name}</li>)}</ul>
}

// Only add 'use client' when needed:
// - useState, useEffect, event handlers
// - Browser APIs
// - Third-party client libraries
```

### 20. Composition Over Props Drilling
```tsx
// BAD - drilling props
<Parent user={user}>
  <Child user={user}>
    <GrandChild user={user} />
  </Child>
</Parent>

// GOOD - composition
<Parent>
  <Child>
    <GrandChild user={user} />
  </Child>
</Parent>
```

## Quick Checklist

- [ ] No waterfall data fetching
- [ ] Bundle size analyzed
- [ ] Heavy components lazy loaded
- [ ] Lists virtualized if > 100 items
- [ ] Expensive computations memoized
- [ ] Server Components used by default
- [ ] Suspense boundaries around async
- [ ] Context split by update frequency
