"""
Trading Hours Validation

Provides schedule-based validation for trading entries and exits based on
strategy-defined trading hours.
"""

import logging
from datetime import time as dt_time
from typing import Any, Dict, Optional

_logger = logging.getLogger(__name__)


class TradingHoursValidator:
    """
    Validates trading times against entry/exit schedules.

    Handles overnight windows (e.g., 22:00-06:00) where valid times span midnight.
    """

    def __init__(self, stratOBJ: Any, strategy: int):
        """
        Args:
            stratOBJ: StratOBJ instance with strategy definitions
            strategy: Strategy ID
        """
        self.stratOBJ = stratOBJ
        self.strategy = strategy

    def is_within_schedule(self, bar_datetime: Any, schedule: Dict[str, str]) -> bool:
        """
        Check if datetime falls within a schedule window.

        Handles overnight windows (e.g., 22:00-06:00 means valid if time >= 22:00 OR <= 06:00).

        Args:
            bar_datetime: Datetime to check
            schedule: Dict with 'start' and 'end' keys as 'HH:MM' strings

        Returns:
            True if within window, False otherwise
        """
        try:
            start_str = schedule.get('start', '00:00')
            end_str = schedule.get('end', '23:59')

            start_parts = start_str.split(':')
            end_parts = end_str.split(':')

            start_time = dt_time(int(start_parts[0]), int(start_parts[1]) if len(start_parts) > 1 else 0)
            end_time = dt_time(int(end_parts[0]), int(end_parts[1]) if len(end_parts) > 1 else 0)

            # Extract time from bar_datetime
            if hasattr(bar_datetime, 'time'):
                current_time = bar_datetime.time()
            elif hasattr(bar_datetime, 'hour'):
                current_time = dt_time(bar_datetime.hour, bar_datetime.minute if hasattr(bar_datetime, 'minute') else 0)
            else:
                return True  # Can't parse, allow trading

            # Handle overnight windows (e.g., 22:00 - 06:00)
            if start_time <= end_time:
                return start_time <= current_time <= end_time
            else:
                # Overnight: either after start OR before end
                return current_time >= start_time or current_time <= end_time

        except (ValueError, TypeError, AttributeError) as e:
            # If parsing fails, allow trading (fail-safe) but warn
            _logger.warning("Failed to parse trading schedule %s: %s. Allowing trading.", schedule, e)
            return True

    def is_entry_allowed(self, bar_datetime: Any) -> bool:
        """
        Check if strategy can OPEN a new position at given bar time.

        Uses stratOBJ.get_entry_schedule() to match live trading behavior.

        Args:
            bar_datetime: Bar datetime to check

        Returns:
            True if entry is allowed, False otherwise
        """
        entry_schedule = self.stratOBJ.get_entry_schedule(self.strategy)

        if entry_schedule is None:
            return True  # No restrictions

        return self.is_within_schedule(bar_datetime, entry_schedule)

    def is_exit_allowed(self, bar_datetime: Any) -> bool:
        """
        Check if strategy can CLOSE a position at given bar time (discretionary exits).

        Uses stratOBJ.get_exit_schedule() to match live trading behavior.
        Note: SL/TP are always active regardless of this check.

        Args:
            bar_datetime: Bar datetime to check

        Returns:
            True if exit is allowed, False otherwise
        """
        exit_schedule = self.stratOBJ.get_exit_schedule(self.strategy)

        if exit_schedule is None:
            return True  # No restrictions

        return self.is_within_schedule(bar_datetime, exit_schedule)
