"""Unified logging setup using loguru."""

import sys
from pathlib import Path

from loguru import logger

# Log file lives next to this module: backend/logs/app.log
_LOG_DIR = Path(__file__).resolve().parent / "logs"
_LOG_FILE = _LOG_DIR / "app.log"

_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
    "{level: <8} | "
    "{name}:{function}:{line} | "
    "{message}"
)


def setup_logging(level: str = "INFO") -> None:
    """Configure loguru for structured logging."""
    logger.remove()

    # stderr sink (coloured)
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "{message}"
        ),
        colorize=True,
    )

    # file sink (plain text, rotated)
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.add(
        _LOG_FILE,
        level=level,
        format=_FORMAT,
        colorize=False,
        rotation="10 MB",
        retention="7 days",
        compression="gz",
    )


__all__ = ["logger", "setup_logging"]
