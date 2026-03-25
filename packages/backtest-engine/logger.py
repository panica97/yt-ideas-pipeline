"""
Centralized logging for IBKR-BACKTEST.

Provides a daily rotating file logger that writes to logs_system/{YYYY-MM-DD}.log.
All errors from the backtest engine and Streamlit app are captured here.

Usage:
    from logger import get_logger
    logger = get_logger(__name__)
    logger.error("Something went wrong", exc_info=True)
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

from constants import SYSTEM_LOGS_PATH

# Module-level flag to avoid duplicate handler setup
_initialized = False


def _setup_root_logger() -> None:
    """Configure the root logger with a daily file handler and console handler."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    # Ensure logs_system folder exists
    SYSTEM_LOGS_PATH.mkdir(parents=True, exist_ok=True)

    # Daily log file: logs_system/2024-01-15.log
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = SYSTEM_LOGS_PATH / f"{today}.log"

    # Format: timestamp | level | module | message
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler — captures WARNING and above
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(formatter)

    # Console handler — only ERROR and above (avoid cluttering stdout)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.ERROR)
    console_handler.setFormatter(formatter)

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.addHandler(file_handler)
    root.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger with the daily file handler configured.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        Configured logging.Logger instance.
    """
    _setup_root_logger()
    return logging.getLogger(name)
