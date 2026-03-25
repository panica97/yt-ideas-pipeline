"""
Chain-Aware Warmup Utilities

Computes warmup requirements for indicators that may be chained (one indicator's
output feeds into another as input via price_* referencing an indCode).

When indicators are chained, warmups must be summed along the dependency chain
rather than taking the max of individual warmups.

Example:
    RSI(30) -> SMA(7)  where SMA's price_1 = 'RSI_30_1m'
    Non-chained: max(30, 7) = 30 bars   (insufficient)
    Chained:     30 + 7     = 37 bars   (correct)

Non-chained strategies are unaffected — the functions produce identical results
when no chains exist.
"""

import math
from typing import Dict, List, Callable

from _03_price_utils import timeframe_to_minutes


# OHLCV source names that are never treated as indicator chains
_OHLCV_SOURCES = frozenset({'open', 'high', 'low', 'close', 'volume'})


def compute_chained_warmup(
    indicators: List[Dict],
    effective_lookback_fn: Callable[[str, Dict], int]
) -> int:
    """
    Compute the maximum effective warmup across all indicators in a single timeframe,
    accounting for indicator chaining.

    An indicator is chained when any of its price_* parameters references another
    indicator's indCode in the same timeframe list.

    Args:
        indicators: List of indicator dicts for one timeframe.
                    Each dict has 'indicator', 'params', and optionally 'indCode'.
        effective_lookback_fn: Callable(indicator_name, params) -> int returning
                               warmup bars for a single indicator.

    Returns:
        Maximum effective warmup across all indicators (minimum 1).
    """
    if not indicators:
        return 1

    # Build indCode -> indicator dict mapping for chain lookups.
    # indCode may be at the top level of the indicator dict OR inside params.
    ind_by_code: Dict[str, Dict] = {}
    for ind in indicators:
        code = ind.get('indCode', '') or ind.get('params', {}).get('indCode', '')
        if code:
            ind_by_code[code] = ind

    def _get_ind_code(ind: Dict) -> str:
        """Extract indCode from indicator dict (top-level or inside params)."""
        return ind.get('indCode', '') or ind.get('params', {}).get('indCode', '')

    # Build own-warmup cache
    def _own_warmup(ind: Dict) -> int:
        name = ind.get('indicator', '')
        params = ind.get('params', {})
        w = effective_lookback_fn(name, params)
        return w if isinstance(w, int) and w > 0 else 1

    # Memoized effective warmup with chain walking
    memo: Dict[str, int] = {}
    visiting: set = set()  # Cycle detection

    def _effective(ind: Dict) -> int:
        code = _get_ind_code(ind)
        if code and code in memo:
            return memo[code]

        # Circular dependency detection
        if code and code in visiting:
            raise ValueError(
                f"Circular indicator dependency detected involving indCode '{code}'. "
                f"Check price_* references in your indicator chain."
            )

        if code:
            visiting.add(code)

        own = _own_warmup(ind)
        params = ind.get('params', {})

        # Find parent: check all price_* params for indCode references
        parent_warmup = 0
        for key, val in params.items():
            if not key.startswith('price_'):
                continue
            if not isinstance(val, str):
                continue
            # Skip OHLCV sources
            if val.lower() in _OHLCV_SOURCES:
                continue
            # Check if this references another indicator's indCode
            if val in ind_by_code:
                parent_ind = ind_by_code[val]
                # Avoid self-reference
                if parent_ind is not ind:
                    parent_warmup = max(parent_warmup, _effective(parent_ind))

        result = own + parent_warmup
        if code:
            memo[code] = result
            visiting.discard(code)
        return result

    max_warmup = 0
    for ind in indicators:
        max_warmup = max(max_warmup, _effective(ind))

    return max(1, max_warmup)


def compute_max_lookback_with_chains(
    ind_list: Dict[str, List[Dict]],
    primary_tf: str,
    effective_lookback_fn: Callable[[str, Dict], int]
) -> int:
    """
    Compute maximum lookback period across all timeframes, accounting for
    indicator chaining.

    Replaces the non-chained _get_max_lookback() logic.

    Args:
        ind_list: Dict mapping timeframe -> list of indicator dicts.
        primary_tf: Primary timeframe string (e.g., '5 mins').
        effective_lookback_fn: Callable(indicator_name, params) -> int.

    Returns:
        Max lookback in primary-TF bars (minimum 50 if no indicators found).
    """
    primary_minutes = timeframe_to_minutes(primary_tf)
    if primary_minutes <= 0:
        primary_minutes = 5

    max_lookback_primary = 0
    for tf, indicators in ind_list.items():
        tf_minutes = timeframe_to_minutes(tf)
        warmup_tf = compute_chained_warmup(indicators, effective_lookback_fn)
        warmup_minutes = warmup_tf * tf_minutes
        warmup_primary = int(math.ceil(warmup_minutes / primary_minutes))
        max_lookback_primary = max(max_lookback_primary, warmup_primary)

    return max_lookback_primary if max_lookback_primary > 0 else 50


def compute_warmup_bars_with_chains(
    ind_list: Dict[str, List[Dict]],
    max_shift: int,
    primary_tf: str,
    effective_lookback_fn: Callable[[str, Dict], int]
) -> int:
    """
    Compute warmup bars for all timeframes, accounting for indicator chaining.

    Replaces the non-chained _compute_warmup_bars() logic.

    Args:
        ind_list: Dict mapping timeframe -> list of indicator dicts.
        max_shift: Effective max shift from strategy conditions.
        primary_tf: Primary timeframe string.
        effective_lookback_fn: Callable(indicator_name, params) -> int.

    Returns:
        Warmup bars in primary-TF units (minimum 2).
    """
    primary_minutes = timeframe_to_minutes(primary_tf)
    if primary_minutes <= 0:
        primary_minutes = 5

    required_minutes = 0
    for tf, indicators in ind_list.items():
        tf_minutes = timeframe_to_minutes(tf)
        max_tp = compute_chained_warmup(indicators, effective_lookback_fn)
        needed_bars_tf = max_tp + (1 + max_shift)
        required_minutes = max(required_minutes, needed_bars_tf * tf_minutes)

    warmup_primary = int(math.ceil(required_minutes / primary_minutes))
    return max(2, warmup_primary)
