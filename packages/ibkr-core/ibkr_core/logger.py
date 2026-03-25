# ibkr_core/logger.py - standalone adapter (clean-room, not extracted from _98_InfraLogger.py)

import logging

_logger = None


def get_logger():
    """
    Get the singleton logger adapter instance.

    Returns a _LoggerAdapter with log_info(), log_error(), and log_warning()
    methods matching the call signatures used across all ibkr_core modules.

    Thread-safe: Python's module-level global + logging module handle concurrency.
    """
    global _logger
    if _logger is None:
        _logger = _LoggerAdapter()
    return _logger


class _LoggerAdapter:
    """
    Thin adapter around Python's standard logging module.

    Provides the same interface as InfraLogger's logging methods without any
    infrastructure dependencies (no file I/O to logs/, no database writes).
    """

    def __init__(self):
        self._log = logging.getLogger('ibkr_core')
        self._log.setLevel(logging.INFO)

        # Only add handler if none exist (prevent duplicates on repeated imports)
        if not self._log.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
            handler.setFormatter(formatter)
            self._log.addHandler(handler)

    def log_info(self, category: str, message: str) -> None:
        """Log at INFO level with [category] message format."""
        self._log.info('[%s] %s', category, message)

    def log_error(self, component: str, error: str, error_code: int = None) -> None:
        """Log at ERROR level. Includes error_code when provided."""
        if error_code is not None:
            self._log.error('[%s] Error %s: %s', component, error_code, error)
        else:
            self._log.error('[%s] %s', component, error)

    def log_warning(self, component: str, message: str) -> None:
        """Log at WARNING level with [component] message format."""
        self._log.warning('[%s] %s', component, message)
