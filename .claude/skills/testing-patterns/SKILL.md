---
name: Testing Patterns
description: Testing strategies and patterns for Python and TypeScript. Use when writing tests, setting up test infrastructure, or debugging test failures. Triggered by "write test", "add tests", "testing", "pytest", "jest", "test coverage".
---

# Testing Patterns

## TDD Workflow

```
RED → GREEN → REFACTOR

1. Write a failing test that describes expected behavior
2. Write minimal code to make test pass
3. Refactor while keeping tests green
```

## Python Testing (pytest)

### Test Structure

```python
# tests/unit/test_user_service.py
import pytest
from unittest.mock import Mock, AsyncMock

from src.services.user_service import UserService
from src.schemas.user import UserCreate


class TestUserService:
    """Tests for UserService."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> UserService:
        """Create service instance with mocked dependencies."""
        return UserService(mock_db)

    async def test_create_user_success(
        self,
        service: UserService,
        mock_db: AsyncMock,
    ) -> None:
        """Creating user with valid data returns new user."""
        # Arrange
        user_data = UserCreate(
            email="test@example.com",
            name="Test User",
            password="securepass123",
        )
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        result = await service.create(user_data)

        # Assert
        assert result.email == user_data.email
        assert result.name == user_data.name
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_create_user_duplicate_email_raises(
        self,
        service: UserService,
        mock_db: AsyncMock,
    ) -> None:
        """Creating user with existing email raises error."""
        # Arrange
        user_data = UserCreate(
            email="existing@example.com",
            name="Test User",
            password="securepass123",
        )
        mock_db.execute.return_value.scalar_one_or_none.return_value = Mock()

        # Act & Assert
        with pytest.raises(UserExistsError):
            await service.create(user_data)
```

### Fixtures (conftest.py)

```python
# tests/conftest.py
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.main import app
from src.core.database import Base, get_db


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_session() -> AsyncSession:
    """Create test database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession)
    async with async_session() as session:
        yield session


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    """Create test client with overridden dependencies."""
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
```

### Parametrized Tests

```python
@pytest.mark.parametrize(
    "email,expected_valid",
    [
        ("user@example.com", True),
        ("user@sub.example.com", True),
        ("invalid", False),
        ("@example.com", False),
        ("user@", False),
    ],
)
def test_email_validation(email: str, expected_valid: bool) -> None:
    """Email validation handles various formats correctly."""
    result = validate_email(email)
    assert result == expected_valid
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=term-missing

# Run specific test file
uv run pytest tests/unit/test_user.py -v

# Run tests matching pattern
uv run pytest -k "test_create"

# Run failed tests only
uv run pytest --lf

# Run with parallel execution
uv run pytest -n auto
```

## TypeScript Testing (Jest)

### Component Test

```tsx
// __tests__/components/Button.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Button } from '@/components/ui/button'

describe('Button', () => {
  it('renders children correctly', () => {
    render(<Button>Click me</Button>)

    expect(screen.getByRole('button')).toHaveTextContent('Click me')
  })

  it('calls onClick when clicked', async () => {
    const handleClick = jest.fn()
    const user = userEvent.setup()

    render(<Button onClick={handleClick}>Click me</Button>)
    await user.click(screen.getByRole('button'))

    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('is disabled when disabled prop is true', () => {
    render(<Button disabled>Click me</Button>)

    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('applies variant classes correctly', () => {
    render(<Button variant="destructive">Delete</Button>)

    expect(screen.getByRole('button')).toHaveClass('bg-destructive')
  })
})
```

### Hook Test

```tsx
// __tests__/hooks/useDebounce.test.ts
import { renderHook, act } from '@testing-library/react'
import { useDebounce } from '@/hooks/use-debounce'

describe('useDebounce', () => {
  beforeEach(() => {
    jest.useFakeTimers()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  it('returns initial value immediately', () => {
    const { result } = renderHook(() => useDebounce('initial', 500))

    expect(result.current).toBe('initial')
  })

  it('debounces value changes', () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebounce(value, 500),
      { initialProps: { value: 'initial' } }
    )

    rerender({ value: 'updated' })
    expect(result.current).toBe('initial')

    act(() => {
      jest.advanceTimersByTime(500)
    })

    expect(result.current).toBe('updated')
  })
})
```

### API Mocking

```tsx
// __tests__/hooks/useUser.test.ts
import { renderHook, waitFor } from '@testing-library/react'
import { useUser } from '@/hooks/use-user'

// Mock fetch globally
global.fetch = jest.fn()

describe('useUser', () => {
  beforeEach(() => {
    (fetch as jest.Mock).mockClear()
  })

  it('fetches and returns user data', async () => {
    const mockUser = { id: '1', name: 'John', email: 'john@example.com' }

    ;(fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => mockUser,
    })

    const { result } = renderHook(() => useUser('1'))

    expect(result.current.isLoading).toBe(true)

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.user).toEqual(mockUser)
    expect(result.current.error).toBeNull()
  })

  it('handles fetch error', async () => {
    ;(fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 404,
    })

    const { result } = renderHook(() => useUser('999'))

    await waitFor(() => {
      expect(result.current.error).not.toBeNull()
    })

    expect(result.current.user).toBeNull()
  })
})
```

## E2E Testing (Playwright)

```typescript
// e2e/login.spec.ts
import { test, expect } from '@playwright/test'

test.describe('Login Flow', () => {
  test('user can login with valid credentials', async ({ page }) => {
    await page.goto('/login')

    await page.fill('[name="email"]', 'user@example.com')
    await page.fill('[name="password"]', 'password123')
    await page.click('button[type="submit"]')

    await expect(page).toHaveURL('/dashboard')
    await expect(page.locator('h1')).toHaveText('Dashboard')
  })

  test('shows error for invalid credentials', async ({ page }) => {
    await page.goto('/login')

    await page.fill('[name="email"]', 'wrong@example.com')
    await page.fill('[name="password"]', 'wrongpassword')
    await page.click('button[type="submit"]')

    await expect(page.locator('[role="alert"]')).toContainText('Invalid credentials')
  })
})
```

## Property-Based Testing (Hypothesis)

Test properties/invariants instead of specific examples:

```python
from hypothesis import given, strategies as st

# BAD - Single example
def test_sort():
    assert sort([3, 1, 2]) == [1, 2, 3]

# GOOD - Property-based invariants
@given(st.lists(st.integers()))
def test_sort_maintains_elements(lst):
    result = sort(lst)
    assert sorted(result) == sorted(lst)  # Same elements

@given(st.lists(st.integers()))
def test_sort_is_ordered(lst):
    result = sort(lst)
    assert all(result[i] <= result[i+1] for i in range(len(result)-1))
```

### Property-Based Anti-Patterns

```python
# TRIVIAL - Checks nothing meaningful
@given(st.integers())
def test_process_returns_something(n):
    assert process(n) is not None  # BAD!

# TAUTOLOGY - Always true
@given(st.lists(st.integers()))
def test_length_equals_length(lst):
    assert len(process(lst)) == len(process(lst))  # BAD!

# REIMPLEMENTING - Tests nothing new
@given(st.integers(min_value=2))
def test_factorize_reimplemented(n):
    # Reimplements the function - BAD!
    expected = manual_factorize(n)
    assert factorize(n) == expected

# MEANINGFUL - Tests real invariant
@given(st.integers(min_value=2, max_value=10000))
def test_factorize_product_equals_input(n):
    factors = factorize(n)
    product = 1
    for f in factors:
        product *= f
    assert product == n  # GOOD!
```

## Test Scope Priority

| Priority | What | When |
|----------|------|------|
| 1 - Always | Critical paths, business logic | Every task |
| 2 - On Request | Edge cases, error handling | When asked |
| 3 - Defer | Exhaustive validation | Later |

## Test Naming Pattern

`test_<function>_<scenario>_<expected>`

```python
# GOOD
def test_checkout_with_valid_cart_creates_order():
def test_login_with_wrong_password_returns_401():

# BAD
def test_checkout():
def test_login():
```

## Coverage Requirements

| Type | Minimum |
|------|---------|
| Unit | 80% |
| Integration | 60% |
| E2E (critical) | 100% |

## Test Anti-Patterns to Avoid

1. **Testing implementation details** - Test behavior, not internal state
2. **Flaky tests** - Avoid sleep(), use proper waits
3. **Too many mocks** - Test real behavior where possible
4. **No assertions** - Every test must assert something
5. **Shared mutable state** - Reset state between tests
6. **Testing mock behavior** - Test real code, not configured mocks
7. **Test-only methods** - Use dependency injection instead
