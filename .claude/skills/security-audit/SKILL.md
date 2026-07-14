---
name: Security Audit
description: Security audit and vulnerability detection for Python and TypeScript. Use when reviewing code for security issues, checking for vulnerabilities, or implementing secure patterns. Triggered by "security audit", "check vulnerabilities", "security review", "find security issues".
---

# Security Audit Skill

## Quick Audit Commands

```bash
# Python - dependency vulnerabilities
uv pip audit

# Python - static analysis
bandit -r src/ -f json

# Python - secret detection
detect-secrets scan . --all-files

# JavaScript - dependency vulnerabilities
npm audit

# JavaScript - secret detection
gitleaks detect --source . --verbose
```

## OWASP Top 10 Review

### A01: Broken Access Control

**Check for:** Missing authorization on endpoints

```python
# GOOD - with authorization check
@app.get("/users/{user_id}")
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user)
):
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(403, "Forbidden")
    return await db.get_user(user_id)
```

### A02: Cryptographic Failures

**Secure password hashing:**
```python
from argon2 import PasswordHasher

ph = PasswordHasher()
hashed = ph.hash(password)

# Verify
try:
    ph.verify(hashed, password)
except VerifyMismatchError:
    raise InvalidCredentials()
```

### A03: Injection

**SQL Injection prevention:**
```python
# GOOD - parameterized queries
query = "SELECT * FROM users WHERE email = :email"
result = await db.execute(query, {"email": email})
```

**Command execution - use subprocess with list args:**
```python
import subprocess
# GOOD - list arguments, no shell
subprocess.run(["ping", "-c", "4", hostname], check=True)
```

### A04: Insecure Design

**Rate limiting:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/login")
@limiter.limit("5/minute")
async def login(request: Request):
    ...
```

### A05: Security Misconfiguration

**Security headers:**
```python
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://myapp.com"],
    allow_methods=["GET", "POST"],
)
```

### A06: Vulnerable Components

```bash
# Check dependencies
uv pip audit
npm audit --audit-level=high
```

### A07: Authentication Failures

**Secure JWT:**
```python
from jose import jwt, JWTError
from datetime import datetime, timedelta

def create_access_token(data: dict, expires: timedelta) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + expires
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")
```

### A09: Logging & Monitoring

**Secure logging:**
```python
import structlog
logger = structlog.get_logger()

# Log security events (never log passwords/tokens)
logger.info("user_login", user_id=user.id, ip=request.client.host)
```

### A10: SSRF Prevention

```python
from urllib.parse import urlparse

ALLOWED_HOSTS = {"api.example.com", "cdn.example.com"}

def validate_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.hostname in ALLOWED_HOSTS
```

## Audit Report Template

```markdown
# Security Audit Report

**Project:** [Name]
**Date:** YYYY-MM-DD

## Summary
- Critical: X | High: X | Medium: X | Low: X

## Findings

### [CRITICAL] Finding Title
- **Location:** `path/to/file.py:123`
- **Description:** What was found
- **Impact:** What could happen
- **Recommendation:** How to fix

## Remediation Priority
1. Critical - Immediate
2. High - 7 days
3. Medium - 30 days
4. Low - Next sprint
```
