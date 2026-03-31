"""Generate random entries for monkey simulations.

Each call produces a set of (entry_idx, exit_idx, holding_bars) tuples
respecting the no-overlap constraint (one open trade at a time).
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np


def generate_random_entries(
    n_bars: int,
    n_trades: int,
    max_bars: int,
    holding_distribution: List[int],
    mode: str,
    rng: np.random.Generator,
) -> List[Tuple[int, int, int]]:
    """Return a list of (entry_idx, exit_idx, holding_bars) with no overlap.

    Parameters
    ----------
    n_bars : int
        Total number of bars in the OHLC series.
    n_trades : int
        Desired number of trades to place.
    max_bars : int
        Maximum holding period (also used as the fixed duration in mode B).
    holding_distribution : list[int]
        Empirical distribution of bars_held from the real strategy.
    mode : str
        "A" = sample holding from distribution; "B" = always max_bars.
    rng : numpy.random.Generator
        Seeded random generator for reproducibility.

    Returns
    -------
    list of (entry_idx, exit_idx, holding_bars)
        Placed trades sorted by entry_idx.  May be fewer than *n_trades*
        if overlaps prevent full placement.
    """
    # Valid entry candidates: exclude last max_bars bars so every trade
    # can complete within the series.
    last_valid = n_bars - max_bars - 1
    if last_valid < 0:
        return []

    # Candidate bar indices for entry — sample a subset instead of shuffling all
    sample_size = min(n_trades * 3, last_valid + 1)  # 3x buffer for overlap losses
    candidates = rng.choice(np.arange(0, last_valid + 1), size=sample_size, replace=False)

    holding_arr = np.asarray(holding_distribution, dtype=np.int64)

    trades: List[Tuple[int, int, int]] = []
    # Track occupied ranges to enforce no-overlap
    # We iterate candidates and skip any that fall inside an open trade.
    occupied_until = -1  # bar index until which the current trade is open

    # Sort placed trades as we go so we can efficiently check overlap.
    # Strategy: collect valid entries greedily, then sort.
    placed: List[Tuple[int, int, int]] = []

    for entry_idx in candidates:
        if len(placed) >= n_trades:
            break

        # Determine holding period
        if mode == "B":
            hold = max_bars
        else:
            hold = int(rng.choice(holding_arr))
            hold = min(hold, max_bars)  # cap at max_bars

        exit_idx = entry_idx + hold
        if exit_idx >= n_bars:
            continue  # would exceed data

        placed.append((int(entry_idx), int(exit_idx), int(hold)))

    if not placed:
        return []

    # Sort by entry and remove overlapping trades greedily
    placed.sort(key=lambda t: t[0])
    result: List[Tuple[int, int, int]] = []
    free_after = -1
    for entry, exit_, hold in placed:
        if entry > free_after:
            result.append((entry, exit_, hold))
            free_after = exit_
            if len(result) >= n_trades:
                break

    return result
