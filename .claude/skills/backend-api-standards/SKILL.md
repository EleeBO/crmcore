---
name: backend-api-standards
description: RESTful API design with proper HTTP methods, status codes, versioning, and error handling. Use when creating or modifying API endpoints.
---

# Backend API Standards

**Core Rule:** Resource-based URLs, correct HTTP methods and status codes, consistent response format.

## When to Use

- Creating or modifying API endpoints
- Designing URL structures
- Implementing error handling
- Adding pagination, filtering, sorting

## RESTful URL Design

### HTTP Methods

| Method | Purpose | Example |
|--------|---------|---------|
| GET | Read resource(s) | `GET /users/123` |
| POST | Create resource | `POST /users` |
| PUT | Replace resource | `PUT /users/123` |
| PATCH | Partial update | `PATCH /users/123` |
| DELETE | Remove resource | `DELETE /users/123` |

### URL Patterns

```
# Collections (plural nouns)
GET    /users           # List all users
POST   /users           # Create user

# Single resource
GET    /users/{id}      # Get user
PUT    /users/{id}      # Replace user
PATCH  /users/{id}      # Update user
DELETE /users/{id}      # Delete user

# Nested resources (max 2 levels)
GET    /users/{id}/orders        # User's orders
POST   /users/{id}/orders        # Create order for user
GET    /users/{id}/orders/{oid}  # Specific order
```

### Query Parameters

```
# Filtering
GET /users?status=active&role=admin

# Sorting
GET /users?sort=created_at&order=desc

# Pagination
GET /users?page=2&limit=50
GET /users?offset=100&limit=50

# Search
GET /users?q=john
```

## HTTP Status Codes

### Success (2xx)

```python
# 200 OK - Successful GET, PUT, PATCH
return {"data": user}

# 201 Created - Successful POST
return {"data": user}, 201, {"Location": f"/users/{user.id}"}

# 204 No Content - Successful DELETE
return "", 204
```

### Client Errors (4xx)

```python
# 400 Bad Request - Invalid input
{"error": {"code": "INVALID_INPUT", "message": "Email format invalid"}}

# 401 Unauthorized - Not authenticated
{"error": {"code": "UNAUTHORIZED", "message": "Token required"}}

# 403 Forbidden - Authenticated but not allowed
{"error": {"code": "FORBIDDEN", "message": "Admin access required"}}

# 404 Not Found - Resource doesn't exist
{"error": {"code": "NOT_FOUND", "message": "User not found"}}

# 409 Conflict - Duplicate or constraint violation
{"error": {"code": "CONFLICT", "message": "Email already exists"}}

# 422 Unprocessable Entity - Validation failure
{"error": {"code": "VALIDATION_ERROR", "details": [...]}}
```

### Server Errors (5xx)

```python
# 500 Internal Server Error - Unexpected error
{"error": {"code": "INTERNAL_ERROR", "message": "Something went wrong"}}

# 503 Service Unavailable - Temporary downtime
{"error": {"code": "SERVICE_UNAVAILABLE", "message": "Try again later"}}
```

## Response Format

### Success Response

```json
{
  "data": {
    "id": 123,
    "name": "John"
  },
  "meta": {
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```

### List Response with Pagination

```json
{
  "data": [...],
  "pagination": {
    "page": 2,
    "limit": 50,
    "total": 250,
    "pages": 5
  }
}
```

### Error Response

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input",
    "details": [
      {"field": "email", "message": "Invalid email format"},
      {"field": "password", "message": "Minimum 8 characters"}
    ]
  }
}
```

## API Versioning

```
# URL versioning (recommended)
/v1/users
/v2/users

# Header versioning (alternative)
Accept: application/vnd.api.v1+json
```

### When to Version

**New version needed:**
- Breaking changes to request/response format
- Removing fields or endpoints
- Changing field types

**No new version needed:**
- Adding optional fields
- Adding new endpoints
- Bug fixes

## Rate Limiting

Include headers in responses:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1640995200
```

Return `429 Too Many Requests` when exceeded.

## FastAPI Example

```python
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/v1/users", tags=["users"])

class UserCreate(BaseModel):
    email: str
    name: str

class UserResponse(BaseModel):
    id: int
    email: str
    name: str

@router.get("/", response_model=list[UserResponse])
async def list_users(
    status: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100)
):
    """List users with optional filtering and pagination."""
    ...

@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(data: UserCreate):
    """Create a new user."""
    ...

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int):
    """Get user by ID."""
    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(404, detail="User not found")
    return user
```

## Checklist

Before completing API work:

- [ ] URLs use plural nouns for collections
- [ ] HTTP methods match operations
- [ ] Status codes are accurate
- [ ] Response format is consistent
- [ ] Error responses include code and message
- [ ] Pagination for list endpoints
- [ ] Validation at API boundary
- [ ] No internal errors exposed to clients
