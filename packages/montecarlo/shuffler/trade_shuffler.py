"""
Trade Shuffler — Monte Carlo via trade resampling.

Supports simple (random permutation) and block (block bootstrap) modes.
All computation is vectorised with numpy for performance.
"""

from __future__ import annotations

import numpy as np
from typing import List

from ..config import MonteCarloConfig


class TradeShuffler:
    """Shuffle existing trade PnLs to produce equity curve distributions."""

    def __init__(self, trades: List[dict], initial_equity: float) -> None:
        self.pnls = np.array([t["pnl"] for t in trades], dtype=np.float64)
        self.initial_equity = float(initial_equity)
        self.n_trades = len(self.pnls)

    def shuffle(
        self,
        n_paths: int = MonteCarloConfig.DEFAULT_SHUFFLE_PATHS,
        mode: str = "simple",
        block_size: int = MonteCarloConfig.DEFAULT_BLOCK_SIZE,
        seed: int | None = None,
    ) -> dict:
        """Run Monte Carlo trade shuffling.

        Parameters
        ----------
        n_paths : number of shuffled equity curves to generate
        mode : 'simple' (random permutation) or 'block' (block bootstrap)
        block_size : number of consecutive trades per block (block mode only)
        seed : random seed for reproducibility

        Returns
        -------
        dict with equity_curves, max_drawdowns, final_equities, sharpe_ratios,
        and actual_* comparisons.
        """
        rng = np.random.default_rng(seed)

        if mode == "block":
            pnl_matrix = self._block_shuffle(n_paths, block_size, rng)
        else:
            pnl_matrix = self._simple_shuffle(n_paths, rng)

        # Build equity curves: shape (n_paths, n_trades + 1)
        equity_curves = np.zeros((n_paths, self.n_trades + 1))
        equity_curves[:, 0] = self.initial_equity
        equity_curves[:, 1:] = self.initial_equity + np.cumsum(pnl_matrix, axis=1)

        # Max drawdowns
        running_max = np.maximum.accumulate(equity_curves, axis=1)
        drawdowns = (equity_curves - running_max) / (running_max + 1e-10)
        max_drawdowns = np.min(drawdowns, axis=1)

        # Final equities
        final_equities = equity_curves[:, -1]

        # Sharpe ratios (per path, using trade PnLs)
        means = np.mean(pnl_matrix, axis=1)
        stds = np.std(pnl_matrix, axis=1)
        stds = np.maximum(stds, 1e-10)
        sharpe_ratios = means / stds

        # Total returns per path
        total_returns = (final_equities - self.initial_equity) / self.initial_equity

        # Max drawdown durations per path
        max_drawdown_durations = np.zeros(n_paths, dtype=np.int64)
        for i in range(n_paths):
            ec = equity_curves[i]
            peak_idx = 0
            max_dur = 0
            for j in range(1, len(ec)):
                if ec[j] >= ec[peak_idx]:
                    peak_idx = j
                else:
                    dur = j - peak_idx
                    if dur > max_dur:
                        max_dur = dur
            max_drawdown_durations[i] = max_dur

        # Actual (original order)
        actual_equity = np.concatenate(
            [[self.initial_equity], self.initial_equity + np.cumsum(self.pnls)]
        )
        actual_running_max = np.maximum.accumulate(actual_equity)
        actual_dd = (actual_equity - actual_running_max) / (actual_running_max + 1e-10)
        actual_max_dd = float(np.min(actual_dd))
        actual_total_return = float((actual_equity[-1] - self.initial_equity) / self.initial_equity)

        return {
            "equity_curves": equity_curves,
            "max_drawdowns": max_drawdowns,
            "final_equities": final_equities,
            "sharpe_ratios": sharpe_ratios,
            "total_returns": total_returns,
            "max_drawdown_durations": max_drawdown_durations,
            "actual_equity_curve": actual_equity,
            "actual_max_drawdown": actual_max_dd,
            "actual_final_equity": float(actual_equity[-1]),
            "actual_total_return": actual_total_return,
        }

    def _simple_shuffle(self, n_paths: int, rng: np.random.Generator) -> np.ndarray:
        """Random permutation of PnLs for each path. Shape (n_paths, n_trades)."""
        pnl_matrix = np.tile(self.pnls, (n_paths, 1))
        for i in range(n_paths):
            rng.shuffle(pnl_matrix[i])
        return pnl_matrix

    def _block_shuffle(
        self, n_paths: int, block_size: int, rng: np.random.Generator
    ) -> np.ndarray:
        """Block bootstrap: resample blocks of consecutive trades with replacement.

        Uses wrapping so each block always has exactly block_size elements,
        then truncates the concatenated result to n_trades.
        """
        n_blocks = int(np.ceil(self.n_trades / block_size))
        pnl_matrix = np.zeros((n_paths, self.n_trades))

        # Pre-build a doubled PnL array for wrap-around block extraction
        pnls_wrap = np.tile(self.pnls, 2)

        for i in range(n_paths):
            starts = rng.integers(0, self.n_trades, size=n_blocks)
            blocks = []
            for s in starts:
                blocks.append(pnls_wrap[s : s + block_size])
            concatenated = np.concatenate(blocks)
            pnl_matrix[i] = concatenated[: self.n_trades]

        return pnl_matrix
