# Coding Standards

## General Principles

1. **Readability over cleverness** - Code is read more than written
2. **Explicit over implicit** - Be clear about intent
3. **Consistency** - Follow existing patterns in the codebase
4. **Small functions** - Single responsibility, easy to test

## Python Standards

### Style
- Follow PEP 8
- Use ruff for linting and formatting
- Maximum line length: 88 characters (black default)

### Type Hints
```python
# Required on all functions
def process_user(user_id: int, options: dict[str, Any] | None = None) -> User:
    ...
```

### Docstrings
```python
def create_order(items: list[Item], user: User) -> Order:
    """Create a new order for the given user.

    Args:
        items: List of items to include in the order.
        user: The user placing the order.

    Returns:
        The created order instance.

    Raises:
        ValidationError: If items list is empty.
        InsufficientStockError: If any item is out of stock.
    """
```

### Error Handling
```python
# Be specific with exceptions
try:
    result = risky_operation()
except SpecificError as e:
    logger.error("Operation failed", error=str(e))
    raise
except Exception:
    logger.exception("Unexpected error")
    raise
```

## TypeScript Standards

### Strict Mode
```json
// tsconfig.json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitReturns": true
  }
}
```

### No Any
```typescript
// BAD
function process(data: any): any { ... }

// GOOD
function process<T extends Record<string, unknown>>(data: T): ProcessedData { ... }
```

### Component Structure
```tsx
// Props interface first
interface ButtonProps {
  variant: 'primary' | 'secondary';
  onClick: () => void;
  children: React.ReactNode;
}

// Destructure props
export const Button: FC<ButtonProps> = ({ variant, onClick, children }) => {
  return (
    <button className={styles[variant]} onClick={onClick}>
      {children}
    </button>
  );
};
```

## File Organization

### Python
```
src/
├── api/          # HTTP endpoints
├── models/       # Database models
├── schemas/      # Pydantic DTOs
├── services/     # Business logic
├── repositories/ # Data access
└── utils/        # Helpers
```

### TypeScript/React
```
src/
├── app/          # Next.js pages
├── components/
│   ├── ui/       # Base components
│   └── features/ # Feature components
├── hooks/        # Custom hooks
├── lib/          # Utilities
└── types/        # Type definitions
```

## Naming Conventions

| Item | Python | TypeScript |
|------|--------|------------|
| Files | `snake_case.py` | `kebab-case.ts` |
| Classes | `PascalCase` | `PascalCase` |
| Functions | `snake_case` | `camelCase` |
| Constants | `SCREAMING_SNAKE` | `SCREAMING_SNAKE` |
| Components | N/A | `PascalCase` |
