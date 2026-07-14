---
name: Backend Python Standards
description: Python backend development standards using uv, FastAPI/Django, pytest. Use when writing Python APIs, services, or backend logic. Triggered by "create API", "add endpoint", "Python service", "backend logic".
---

# Backend Python Standards

## Package Management

**Always use `uv` instead of pip:**

```bash
# Initialize project
uv init

# Add dependencies
uv add fastapi uvicorn sqlalchemy

# Add dev dependencies
uv add --dev pytest pytest-cov ruff mypy

# Run commands
uv run pytest
uv run python main.py
```

## Project Structure

```
src/
├── api/
│   ├── __init__.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── users.py
│   │   └── items.py
│   └── deps.py              # Dependency injection
├── models/
│   ├── __init__.py
│   └── user.py              # SQLAlchemy models
├── schemas/
│   ├── __init__.py
│   └── user.py              # Pydantic DTOs
├── services/
│   ├── __init__.py
│   └── user_service.py      # Business logic
├── repositories/
│   ├── __init__.py
│   └── user_repo.py         # Data access
└── core/
    ├── __init__.py
    ├── config.py            # Settings
    ├── database.py          # DB connection
    └── logging.py           # Loguru configuration
tests/
├── conftest.py              # Fixtures
├── unit/
└── integration/
```

## FastAPI Endpoint Pattern

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_current_user
from src.schemas.user import UserCreate, UserResponse
from src.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Create a new user."""
    service = UserService(db)
    return await service.create(user_data)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Get user by ID."""
    service = UserService(db)
    user = await service.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

## Pydantic Schemas

```python
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """Base user schema."""
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)


class UserCreate(UserBase):
    """Schema for creating a user."""
    password: str = Field(..., min_length=8)


class UserResponse(UserBase):
    """Schema for user response."""
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}
```

## Service Layer Pattern

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models.user import User
from src.schemas.user import UserCreate


class UserService:
    """User business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: UserCreate) -> User:
        """Create a new user."""
        user = User(
            email=data.email,
            name=data.name,
            password_hash=hash_password(data.password),
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def get_by_id(self, user_id: int) -> User | None:
        """Get user by ID."""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
```

## Testing Pattern

```python
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.main import app


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


class TestUserAPI:
    """User API tests."""

    async def test_create_user_success(
        self,
        client: AsyncClient,
        db: AsyncSession,
    ) -> None:
        """Creating a user with valid data returns 201."""
        response = await client.post(
            "/users/",
            json={
                "email": "test@example.com",
                "name": "Test User",
                "password": "securepass123",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "test@example.com"
        assert "id" in data

    async def test_create_user_invalid_email(
        self,
        client: AsyncClient,
    ) -> None:
        """Creating a user with invalid email returns 422."""
        response = await client.post(
            "/users/",
            json={
                "email": "invalid-email",
                "name": "Test User",
                "password": "securepass123",
            },
        )

        assert response.status_code == 422
```

## Error Handling

```python
from fastapi import HTTPException, status


class AppException(Exception):
    """Base application exception."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppException):
    """Resource not found."""

    def __init__(self, resource: str, id: int | str) -> None:
        super().__init__(f"{resource} with id {id} not found", 404)


class ValidationError(AppException):
    """Validation failed."""

    def __init__(self, message: str) -> None:
        super().__init__(message, 422)
```

## Logging with Loguru

**Use loguru instead of standard logging:**

```python
from loguru import logger

# Basic usage - no configuration needed
logger.info("Processing user {}", user_id)
logger.error("Failed to process", exc_info=True)

# With context
with logger.contextualize(request_id=request_id):
    logger.info("Handling request")
    process_request()

# Exception handling
@logger.catch
def may_fail():
    return 1 / 0
```

**Setup in FastAPI:**

```python
# src/core/logging.py
import sys
from loguru import logger

def setup_logging(level: str = "INFO", json_logs: bool = False):
    logger.remove()
    logger.add(
        sys.stdout,
        level=level,
        serialize=json_logs,  # JSON for production
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )

# src/main.py
from contextlib import asynccontextmanager
from src.core.logging import setup_logging

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(level=settings.LOG_LEVEL)
    logger.info("Starting application")
    yield
    logger.info("Shutting down")

app = FastAPI(lifespan=lifespan)
```

See `logging-loguru` skill for full configuration.

## Linting Commands

```bash
# Format code
uv run ruff format src/ tests/

# Check linting
uv run ruff check src/ tests/

# Fix auto-fixable issues
uv run ruff check --fix src/ tests/

# Type checking
uv run mypy src/

# Run tests
uv run pytest tests/ -v --cov=src
```
