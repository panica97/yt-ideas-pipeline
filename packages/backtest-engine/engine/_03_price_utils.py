"""
Price and Timeframe Utilities

Provides common utility functions for price extraction, rounding, and timeframe conversion
used throughout the backtesting engine.
"""

import logging
import re
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Any, Dict, Optional

_logger = logging.getLogger(__name__)


def extract_scalar(value: Any) -> Any:
    """
    Extract scalar value from Series/list/array-like objects.

    Replaces the pattern: value[0] if hasattr(value, '__getitem__') else value

    Args:
        value: Value that may be a scalar or array-like

    Returns:
        Scalar value (first element if array-like, otherwise the value itself)

    Raises:
        IndexError: If value is an empty array-like object
    """
    if hasattr(value, '__getitem__') and not isinstance(value, (str, bytes)):
        # Check for empty array-like objects
        if hasattr(value, '__len__') and len(value) == 0:
            raise IndexError("Cannot extract scalar from empty array-like object")
        return value[0]
    return value


def extract_ohlc(bar: Any) -> Dict[str, float]:
    """
    Extract OHLC values from a bar as a dictionary.

    Args:
        bar: Bar data with open, high, low, close columns

    Returns:
        Dict with 'open', 'high', 'low', 'close' keys as floats
    """
    return {
        'open': float(extract_scalar(bar['open'])),
        'high': float(extract_scalar(bar['high'])),
        'low': float(extract_scalar(bar['low'])),
        'close': float(extract_scalar(bar['close']))
    }


def extract_bar_datetime(bar: Any) -> Any:
    """
    Extract datetime from a bar.

    Args:
        bar: Bar data with date column

    Returns:
        Datetime value
    """
    return extract_scalar(bar['date'])


def round_price(price: float, direction: str, min_tick: Optional[float]) -> float:
    """
    Round price to minTick precision, favoring positive PnL.

    Args:
        price: Price to round
        direction: 'long' or 'short'
        min_tick: Minimum tick size for the instrument

    Returns:
        Rounded price aligned to minTick
    """
    if min_tick is None or min_tick <= 0:
        return price  # No rounding if minTick not defined

    # Convert to Decimal for precise arithmetic
    price_decimal = Decimal(str(price))
    tick_decimal = Decimal(str(min_tick))

    # Round up for LONG (slightly higher SL = safer), down for SHORT
    dir_lower = direction.lower()
    if dir_lower in ('long', 'buy'):
        # Ceiling: round up to next tick
        rounded_price = (price_decimal / tick_decimal).quantize(Decimal('1'), rounding=ROUND_CEILING) * tick_decimal
    elif dir_lower in ('short', 'sell'):
        # Floor: round down to next tick
        rounded_price = (price_decimal / tick_decimal).quantize(Decimal('1'), rounding=ROUND_FLOOR) * tick_decimal
    else:
        _logger.warning("round_price: unknown direction '%s', defaulting to FLOOR rounding", direction)
        rounded_price = (price_decimal / tick_decimal).quantize(Decimal('1'), rounding=ROUND_FLOOR) * tick_decimal

    return float(rounded_price)


def timeframe_to_minutes(timeframe: str) -> int:
    """
    Convert timeframe label to minutes.

    Canonical format: ``"<N> <unit>"`` where unit is one of
    secs/mins/hour/hours/day/days/week/weeks/month/months
    (e.g. ``'5 mins'``, ``'1 hour'``, ``'4 hours'``, ``'1 day'``).

    Args:
        timeframe: Timeframe string (e.g., '5 mins', '1 hour', '4 hours')

    Returns:
        Number of minutes (default 5 if parsing fails)
    """
    if not timeframe:
        _logger.warning("timeframe_to_minutes: empty timeframe string, defaulting to 5 minutes")
        return 5

    tf = timeframe.strip().lower()
    m = re.match(r"^(\d+)\s*(sec|secs|second|seconds|min|mins|minute|minutes|hour|hours|day|days|week|weeks|month|months)$", tf)
    if not m:
        _logger.warning("timeframe_to_minutes: could not parse '%s', defaulting to 5 minutes", timeframe)
        return 5

    value = int(m.group(1))
    unit = m.group(2)

    if unit.startswith('sec') or unit.startswith('second'):
        return max(1, int(round(value / 60)))
    if unit.startswith('min'):
        return value
    if unit.startswith('hour'):
        return value * 60
    if unit.startswith('day'):
        return value * 1440
    if unit.startswith('week'):
        return value * 10080
    if unit.startswith('month'):
        return value * 43200

    return 5
