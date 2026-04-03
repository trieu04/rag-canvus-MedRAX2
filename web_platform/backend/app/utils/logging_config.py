"""
Logging Configuration

Centralized logging setup for the application.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime

# Create logs directory
LOGS_DIR = Path(__file__).parent.parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Create log file with timestamp
LOG_FILE = LOGS_DIR / f"medrax_{datetime.now().strftime('%Y%m%d')}.log"


def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Set up application logging with both file and console handlers.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger("medrax")
    logger.setLevel(getattr(logging, level.upper()))

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Create formatters
    detailed_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    simple_formatter = logging.Formatter("%(levelname)s - %(message)s")

    # Console handler (INFO and above)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)

    # File handler (DEBUG and above)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)

    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # Also route uvicorn's own loggers (HTTP access, errors) to the same file
    # so all logs end up in one place rather than stdout-only.
    for uvicorn_logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uv_logger = logging.getLogger(uvicorn_logger_name)
        if not any(isinstance(h, logging.FileHandler) for h in uv_logger.handlers):
            uv_logger.addHandler(file_handler)

    return logger


# Global logger instance
logger = setup_logging()
