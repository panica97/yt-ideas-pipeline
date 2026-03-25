"""KAMA -- Kaufman Adaptive Moving Average.

A moving average that adapts to market noise using an Efficiency Ratio.
When the market trends strongly (high ER), KAMA moves quickly; during
choppy conditions (low ER), it barely moves.

Reference: Perry J. Kaufman, "Trading Systems and Methods"

This module is the reference implementation for the custom indicator
framework. It demonstrates the required function signature:

    def calculate(prices: pl.DataFrame, ind_args: dict) -> np.ndarray

Strategy JSON example:
    {
        "indicator": "KAMA",
        "params": {
            "price_1": "close",
            "warmup": 30,
            "indCode": "KAMA_10",
            "period": 10,
            "fast_period": 2,
            "slow_period": 30
        },
        "custom": {
            "module": "kama.py",
            "function": "calculate"
        }
    }
"""
from __future__ import annotations

import numpy as np
import polars as pl


def calculate(prices: pl.DataFrame, ind_args: dict) -> np.ndarray:
    """Calculate Kaufman Adaptive Moving Average.

    Args:
        prices: Polars DataFrame with OHLCV columns.
        ind_args: Strategy params dict. Reads:
            - price_1: column name for price source (default "close")
            - period: ER lookback (default 10)
            - fast_period: fast EMA constant period (default 2)
            - slow_period: slow EMA constant period (default 30)

    Returns:
        np.ndarray of KAMA values, same length as prices.
    """
    col = ind_args.get("price_1", "close")
    period = int(ind_args.get("period", 10))
    fast_period = int(ind_args.get("fast_period", 2))
    slow_period = int(ind_args.get("slow_period", 30))

    if period < 2:
        raise ValueError(f"KAMA period must be >= 2, got {period}")
    if fast_period < 1:
        raise ValueError(f"KAMA fast_period must be >= 1, got {fast_period}")
    if slow_period < 1:
        raise ValueError(f"KAMA slow_period must be >= 1, got {slow_period}")

    close = prices[col].to_numpy().astype(float)
    n = len(close)
    kama = np.full(n, np.nan)

    fast_sc = 2.0 / (fast_period + 1)
    slow_sc = 2.0 / (slow_period + 1)

    if n <= period:
        return kama

    kama[period - 1] = close[period - 1]

    for i in range(period, n):
        direction = abs(close[i] - close[i - period])
        volatility = np.sum(np.abs(np.diff(close[i - period:i + 1])))

        er = direction / volatility if volatility != 0 else 0.0
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        kama[i] = kama[i - 1] + sc * (close[i] - kama[i - 1])

    return kama
