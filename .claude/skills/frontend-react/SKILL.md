---
name: Frontend React/Next.js Standards
description: React and Next.js development standards with TypeScript. Use when building UI components, pages, or frontend features. Triggered by "create component", "add page", "React", "Next.js", "frontend".
---

# Frontend React/Next.js Standards

## Project Structure (Next.js App Router)

```
src/
├── app/
│   ├── (auth)/
│   │   ├── login/page.tsx
│   │   └── register/page.tsx
│   ├── (dashboard)/
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── api/
│   │   └── users/route.ts
│   ├── layout.tsx
│   ├── page.tsx
│   └── globals.css
├── components/
│   ├── ui/                # Base components
│   │   ├── button.tsx
│   │   ├── input.tsx
│   │   └── card.tsx
│   └── features/          # Feature components
│       ├── user-card.tsx
│       └── dashboard-nav.tsx
├── hooks/
│   ├── use-user.ts
│   └── use-debounce.ts
├── lib/
│   ├── utils.ts
│   └── api.ts
└── types/
    └── index.ts
```

## Component Pattern

```tsx
import { type FC } from 'react'
import { cn } from '@/lib/utils'

interface ButtonProps {
  variant?: 'default' | 'secondary' | 'destructive' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  className?: string
  onClick?: () => void
  children: React.ReactNode
}

export const Button: FC<ButtonProps> = ({
  variant = 'default',
  size = 'md',
  disabled = false,
  className,
  onClick,
  children,
}) => {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'inline-flex items-center justify-center rounded-md font-medium transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2',
        'disabled:pointer-events-none disabled:opacity-50',
        {
          'bg-primary text-primary-foreground hover:bg-primary/90': variant === 'default',
          'bg-secondary text-secondary-foreground hover:bg-secondary/80': variant === 'secondary',
          'bg-destructive text-destructive-foreground hover:bg-destructive/90': variant === 'destructive',
          'hover:bg-accent hover:text-accent-foreground': variant === 'ghost',
        },
        {
          'h-8 px-3 text-sm': size === 'sm',
          'h-10 px-4': size === 'md',
          'h-12 px-6 text-lg': size === 'lg',
        },
        className
      )}
    >
      {children}
    </button>
  )
}
```

## Server Component (Default)

```tsx
// app/users/page.tsx
import { UserList } from '@/components/features/user-list'
import { getUsers } from '@/lib/api'

export default async function UsersPage() {
  const users = await getUsers()

  return (
    <main className="container py-8">
      <h1 className="text-3xl font-bold mb-6">Users</h1>
      <UserList users={users} />
    </main>
  )
}
```

## Client Component (When Needed)

```tsx
'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'

interface CounterProps {
  initialValue?: number
}

export function Counter({ initialValue = 0 }: CounterProps) {
  const [count, setCount] = useState(initialValue)

  return (
    <div className="flex items-center gap-4">
      <Button onClick={() => setCount(c => c - 1)}>-</Button>
      <span className="text-xl font-mono">{count}</span>
      <Button onClick={() => setCount(c => c + 1)}>+</Button>
    </div>
  )
}
```

## Custom Hook Pattern

```tsx
import { useState, useEffect } from 'react'

interface UseUserResult {
  user: User | null
  isLoading: boolean
  error: Error | null
  refetch: () => Promise<void>
}

export function useUser(userId: string): UseUserResult {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)

  const fetchUser = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const response = await fetch(`/api/users/${userId}`)
      if (!response.ok) throw new Error('Failed to fetch user')
      const data = await response.json()
      setUser(data)
    } catch (e) {
      setError(e instanceof Error ? e : new Error('Unknown error'))
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchUser()
  }, [userId])

  return { user, isLoading, error, refetch: fetchUser }
}
```

## Form Pattern

```tsx
'use client'

import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

const schema = z.object({
  email: z.string().email('Invalid email'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
})

type FormData = z.infer<typeof schema>

export function LoginForm() {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
  })

  const onSubmit = async (data: FormData) => {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })

    if (!response.ok) {
      // Handle error
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div>
        <Input
          type="email"
          placeholder="Email"
          {...register('email')}
          aria-invalid={errors.email ? 'true' : 'false'}
        />
        {errors.email && (
          <p className="text-sm text-destructive mt-1">{errors.email.message}</p>
        )}
      </div>

      <div>
        <Input
          type="password"
          placeholder="Password"
          {...register('password')}
          aria-invalid={errors.password ? 'true' : 'false'}
        />
        {errors.password && (
          <p className="text-sm text-destructive mt-1">{errors.password.message}</p>
        )}
      </div>

      <Button type="submit" disabled={isSubmitting} className="w-full">
        {isSubmitting ? 'Signing in...' : 'Sign In'}
      </Button>
    </form>
  )
}
```

## Testing Pattern

```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LoginForm } from './login-form'

describe('LoginForm', () => {
  it('shows validation errors for empty fields', async () => {
    render(<LoginForm />)

    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByText(/invalid email/i)).toBeInTheDocument()
    })
  })

  it('submits form with valid data', async () => {
    const user = userEvent.setup()
    render(<LoginForm />)

    await user.type(screen.getByPlaceholderText(/email/i), 'test@example.com')
    await user.type(screen.getByPlaceholderText(/password/i), 'password123')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByText(/signing in/i)).toBeInTheDocument()
    })
  })
})
```

## TypeScript Config

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "exactOptionalPropertyTypes": true
  }
}
```
