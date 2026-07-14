---
name: logging-loguru
description: Structured logging with loguru - configuration, formatting, rotation, and integration with standard logging. Use when setting up logging or debugging.
---

# Logging with Loguru

**Core Rule:** Use loguru for all logging. Intercept standard logging from libraries.

## Why Loguru over Standard Logging?

| Feature | logging | loguru |
|---------|---------|--------|
| Configuration | Complex | Simple |
| Stack traces | Basic | With variables |
| File rotation | Manual | Built-in |
| Colors | Manual | Automatic |
| Setup | Multiple handlers | One logger |

## Basic Usage

```python
from loguru import logger

# That's it - no configuration needed!
logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
logger.critical("Critical message")
```

## Project Configuration

Create `src/core/logging.py`:

```python
import sys
from loguru import logger

def setup_logging(
    level: str = "INFO",
    json_logs: bool = False,
    log_file: str | None = None,
) -> None:
    """Configure loguru for the application."""

    # Remove default handler
    logger.remove()

    # Console output format
    if json_logs:
        # JSON format for production/aggregation
        format_string = "{message}"
        logger.add(
            sys.stdout,
            format=format_string,
            level=level,
            serialize=True,  # JSON output
        )
    else:
        # Human-readable for development
        format_string = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )
        logger.add(
            sys.stdout,
            format=format_string,
            level=level,
            colorize=True,
        )

    # File output with rotation
    if log_file:
        logger.add(
            log_file,
            rotation="10 MB",      # Rotate at 10 MB
            retention="7 days",    # Keep 7 days
            compression="gz",      # Compress old logs
            level=level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        )
```

## Intercept Standard Logging

Libraries use standard logging. Intercept them into loguru:

```python
import logging
from loguru import logger

class InterceptHandler(logging.Handler):
    """Redirect standard logging to loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding loguru level
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where the logged message originated
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )

def intercept_standard_logging() -> None:
    """Redirect all standard logging to loguru."""
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Intercept specific loggers
    for name in ["uvicorn", "uvicorn.access", "uvicorn.error", "sqlalchemy"]:
        logging.getLogger(name).handlers = [InterceptHandler()]
```

## FastAPI Integration

```python
# src/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from loguru import logger

from src.core.logging import setup_logging, intercept_standard_logging
from src.core.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown."""
    # Setup logging on startup
    setup_logging(
        level=settings.LOG_LEVEL,
        json_logs=settings.ENVIRONMENT == "production",
        log_file="logs/app.log" if settings.ENVIRONMENT != "test" else None,
    )
    intercept_standard_logging()

    logger.info("Application starting", extra={"version": settings.VERSION})
    yield
    logger.info("Application shutting down")

app = FastAPI(lifespan=lifespan)
```

## Structured Logging (Context)

```python
from loguru import logger

# Add context to all subsequent logs
with logger.contextualize(user_id=user.id, request_id=request_id):
    logger.info("Processing request")
    # All logs here include user_id and request_id
    process_data()
    logger.info("Request completed")

# Or bind permanently
user_logger = logger.bind(user_id=user.id)
user_logger.info("User action")
```

## Exception Logging

```python
from loguru import logger

# Automatic exception logging with variables
@logger.catch  # Decorator catches and logs exceptions
def risky_function():
    x = 1 / 0

# Or in try/except
try:
    risky_operation()
except Exception:
    logger.exception("Operation failed")  # Logs full traceback with variables
```

## Log Levels

| Level | When to Use |
|-------|-------------|
| TRACE | Detailed debugging |
| DEBUG | Diagnostic info |
| INFO | Normal operations |
| SUCCESS | Operation completed |
| WARNING | Something unexpected |
| ERROR | Error occurred |
| CRITICAL | System failure |

## Testing with Loguru

```python
import pytest
from loguru import logger

@pytest.fixture
def caplog(caplog):
    """Capture loguru logs in pytest."""
    handler_id = logger.add(
        caplog.handler,
        format="{message}",
        level=0,
    )
    yield caplog
    logger.remove(handler_id)

def test_logs_user_creation(caplog):
    create_user({"email": "test@example.com"})

    assert "User created" in caplog.text
```

## Configuration via Environment

```python
# src/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False
    LOG_FILE: str | None = None
    ENVIRONMENT: str = "development"

    class Config:
        env_file = ".env"
```

## Anti-Patterns

**NEVER:**
```python
# BAD - print for debugging
print(f"User: {user}")

# BAD - string concatenation (security risk)
logger.info("User " + user_input + " logged in")

# BAD - logging sensitive data
logger.info(f"Password: {password}")
```

**ALWAYS:**
```python
# GOOD - use logger
logger.debug("User data", user=user)

# GOOD - use format string
logger.info("User {} logged in", user_id)

# GOOD - redact sensitive data
logger.info("Login attempt", user=user_id)  # No password
```

## Quick Reference

```python
from loguru import logger

# Basic
logger.info("Message")
logger.info("Message with {}", variable)
logger.info("Named: {name}", name=value)

# Context
with logger.contextualize(request_id="abc"):
    logger.info("In context")

# Exception
logger.exception("Error occurred")

# Bind for reuse
user_log = logger.bind(user_id=123)
user_log.info("User action")

# Catch decorator
@logger.catch
def may_fail():
    pass
```

Sources:
- [loguru GitHub](https://github.com/Delgan/loguru)
- [loguru vs logging](https://dev.to/leapcell/python-logging-loguru-vs-logging-1f55)
