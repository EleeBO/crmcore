---
name: devops-standards
description: Infrastructure standards with Docker multi-stage builds, security scanning, GitHub Actions CI/CD, and secrets management. Use when working with Docker, CI/CD, or deployment.
---

# DevOps Standards

**Core Rule:** Multi-stage Docker builds, mandatory security scanning, never hardcode secrets.

## When to Use

- Creating or modifying Dockerfiles
- Setting up CI/CD pipelines
- Configuring security scanning
- Managing secrets

## Docker Multi-Stage Builds

```dockerfile
# Build stage
FROM python:3.11-slim AS builder
WORKDIR /app
COPY pyproject.toml ./
RUN pip install uv && uv pip install --system -r pyproject.toml
COPY src/ ./src/

# Production stage
FROM python:3.11-slim AS production
WORKDIR /app

# Non-root user (REQUIRED)
RUN useradd -m -u 1000 appuser
USER appuser

# Copy from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /app/src ./src

# Health check
HEALTHCHECK --interval=30s --timeout=3s \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0"]
```

## Secrets Management

### Never

- Hardcode credentials in code
- Commit .env files
- Store secrets in plain text
- Use same secrets for all environments

### Always

- Use environment variables
- Use secrets manager (GitHub Secrets, AWS Secrets Manager)
- Rotate secrets regularly
- Different secrets per environment

## Security Scanning

### Pre-commit (Fast) - Gitleaks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.0
    hooks:
      - id: gitleaks
```

```bash
# Manual scan
gitleaks detect --source . -v
```

### CI/CD (Deep) - TruffleHog

```bash
# Deep scan with verification
trufflehog git file://. --only-verified
```

## GitHub Actions CI

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Gitleaks
        uses: gitleaks/gitleaks-action@v2

      - name: TruffleHog
        uses: trufflesecurity/trufflehog@main
        with:
          extra_args: --only-verified

  test:
    needs: security
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install and test
        run: |
          pip install uv
          uv pip install --system -r pyproject.toml
          ruff check .
          uv run pytest --cov=src --cov-fail-under=80
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t myapp:${{ github.sha }} .

      - name: Scan image with Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: myapp:${{ github.sha }}
          severity: HIGH,CRITICAL
```

## Health Checks

```python
# FastAPI example
from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter()

@router.get("/health")
async def health():
    """Liveness check."""
    return {"status": "healthy"}

@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    """Readiness check with dependencies."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not ready"}
        )
```

## Docker Compose

```yaml
version: '3.8'

services:
  api:
    build:
      context: ./apps/api
      target: production
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  db:
    image: postgres:16-alpine
    environment:
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready"]
      interval: 10s
      timeout: 5s
      retries: 5
```

## Tool Reference

| Tool | Purpose | When |
|------|---------|------|
| Gitleaks | Fast secret scan | Pre-commit |
| TruffleHog | Deep secret scan | CI/CD |
| Trivy | Container vulnerability scan | CI/CD |
| Hadolint | Dockerfile linting | Pre-commit |
| Bandit | Python security scan | CI/CD |

## Checklist

Before deploying:

- [ ] Multi-stage Docker build
- [ ] Non-root user in container
- [ ] Health checks configured
- [ ] Gitleaks passed
- [ ] TruffleHog passed (CI)
- [ ] No hardcoded secrets
- [ ] Environment variables documented
- [ ] Image versions pinned (not `latest`)
- [ ] Trivy scan passed
