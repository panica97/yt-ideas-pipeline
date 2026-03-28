"""
OHLC Structure Model — decomposes candles into gap / range / body / wick
distributions and reconstructs synthetic candles from Close + volatility.

Enhanced features:
- Separate Beta distributions for body position on up vs down days
- Range-return correlation: larger moves produce wider candles
- Gap mixture model: Normal base + fat-tailed component for overnight jumps
"""

from __future__ import annotations

import numpy as np
import polars as pl
from scipy import stats
from typing import Tuple


class OHLCStructureModel:
    """Fits and generates OHLC structure from statistical decomposition."""

    def __init__(self) -> None:
        # Gap model (mixture of 2 Normals: base + jump)
        self.gap_mean: float | None = None
        self.gap_std: float | None = None
        self.gap_jump_mean: float | None = None       # fat-tail component mean
        self.gap_jump_std: float | None = None        # fat-tail component std
        self.gap_jump_weight: float | None = None     # mixing weight for jump component

        # Range model
        self.range_params: tuple | None = None        # Gamma (shape, loc=0, scale)
        self.range_return_corr: float | None = None   # correlation between range and |return|
        self.range_return_slope: float | None = None  # linear slope for range ~ |return|
        self.range_return_intercept: float | None = None

        # Body position
        self.body_up_params: tuple | None = None      # Beta for positive returns
        self.body_down_params: tuple | None = None    # Beta for negative returns

        # Wick
        self.upper_wick_params: tuple | None = None   # Beta

    # ------------------------------------------------------------------
    # Fitting
    # ------------------------------------------------------------------

    def fit(
        self,
        df: pl.DataFrame,
        tf_minutes: int = 1440,
        verbose: bool = False,
        garch_sigma: np.ndarray | None = None,
    ) -> OHLCStructureModel:
        """Fit OHLC structure model from historical Polars DataFrame.

        Expected columns: open, high, low, close (lowercase).

        Parameters
        ----------
        df : Historical OHLC DataFrame.
        tf_minutes : Bar duration in minutes (e.g. 60 for 1-hour, 1440 for
                     daily).
        garch_sigma : Optional array of GARCH conditional standard deviations
                      aligned with returns (length = len(df) - 1).  When
                      provided, ranges and gaps are normalised by this instead
                      of a rolling-window volatility.  This ensures fitting and
                      generation use the **same** volatility concept, preventing
                      the ATR-ratio blow-up seen with long historical windows
                      where rolling vol diverges from GARCH sigma.
        """
        closes = df["close"].to_numpy().astype(np.float64)
        opens = df["open"].to_numpy().astype(np.float64)
        highs = df["high"].to_numpy().astype(np.float64)
        lows = df["low"].to_numpy().astype(np.float64)

        # Returns
        rets = np.diff(closes) / closes[:-1]
        global_std = np.std(rets) if np.std(rets) > 0 else 1e-8

        if garch_sigma is not None and len(garch_sigma) == len(rets):
            # Use GARCH conditional sigma for normalisation — matches
            # the volatility used during synthetic generation exactly.
            rolling_vol = np.maximum(garch_sigma, 1e-10)
            self._vol_window = 0  # sentinel: GARCH-based
        else:
            # Fallback: adaptive rolling window
            _TARGET_VOL_HOURS = 230
            window = max(20, min(500, round(_TARGET_VOL_HOURS * 60 / tf_minutes)))
            self._vol_window = window

            rolling_vol = np.full(len(rets), global_std)
            if len(rets) > window:
                from numpy.lib.stride_tricks import sliding_window_view
                windowed = sliding_window_view(rets, window)
                vol_values = np.std(windowed[:-1], axis=1)
                rolling_vol[window:] = np.where(vol_values > 0, vol_values, global_std)

        if verbose:
            vol_src = "GARCH sigma" if (garch_sigma is not None and len(garch_sigma) == len(rets)) else f"rolling({self._vol_window})"
            print(f"  OHLC structure: tf={tf_minutes}min, vol source={vol_src}")

        # Work with indices 1..N-1 (need previous close)
        prev_close = closes[:-1]
        o = opens[1:]
        h = highs[1:]
        lo = lows[1:]
        c = closes[1:]
        r = rets

        # --- 1. Gap ratio (normalised) with mixture model ---
        gaps = (o - prev_close) / (prev_close * rolling_vol + 1e-10)
        gaps = gaps[np.isfinite(gaps)]
        self._fit_gap_mixture(gaps)

        # --- 2. Range ratio with return correlation ---
        hl_range = h - lo
        ranges = hl_range / (c * rolling_vol + 1e-10)
        mask_r = np.isfinite(ranges) & (ranges > 0)
        ranges_valid = ranges[mask_r]
        self.range_params = stats.gamma.fit(ranges_valid, floc=0)

        # Range-return correlation: wider candles on larger moves
        abs_rets = np.abs(r)
        if len(ranges) == len(abs_rets):
            valid = mask_r & np.isfinite(abs_rets)
            if np.sum(valid) > 20:
                corr = np.corrcoef(abs_rets[valid], ranges[valid])[0, 1]
                self.range_return_corr = float(corr) if np.isfinite(corr) else 0.0

                # Fit linear relationship: range = slope * |return| + intercept
                from numpy.polynomial.polynomial import polyfit
                coeffs = polyfit(abs_rets[valid], ranges[valid], deg=1)
                self.range_return_intercept = float(coeffs[0])
                self.range_return_slope = float(coeffs[1])
            else:
                self.range_return_corr = 0.0
                self.range_return_slope = 0.0
                self.range_return_intercept = float(np.mean(ranges_valid))
        else:
            self.range_return_corr = 0.0
            self.range_return_slope = 0.0
            self.range_return_intercept = float(np.mean(ranges_valid))

        # --- 3. Body position: (C - L) / (H - L), split by return sign ---
        body_pos = (c - lo) / (hl_range + 1e-10)
        body_pos_valid = np.isfinite(body_pos)
        bp = np.clip(body_pos, 0.01, 0.99)

        up_mask = body_pos_valid & (r > 0)
        down_mask = body_pos_valid & (r <= 0)

        bp_up = bp[up_mask] if np.sum(up_mask) > 10 else bp[body_pos_valid]
        bp_down = bp[down_mask] if np.sum(down_mask) > 10 else bp[body_pos_valid]

        self.body_up_params = stats.beta.fit(bp_up, floc=0, fscale=1)
        self.body_down_params = stats.beta.fit(bp_down, floc=0, fscale=1)

        # --- 4. Upper wick ratio: (H - max(O,C)) / (H-L) ---
        max_oc = np.maximum(o, c)
        upper_wick = (h - max_oc) / (hl_range + 1e-10)
        upper_wick = upper_wick[np.isfinite(upper_wick)]
        upper_wick = np.clip(upper_wick, 0.01, 0.99)
        self.upper_wick_params = stats.beta.fit(upper_wick, floc=0, fscale=1)

        # Store mean normalised range for ATR targeting during generation
        self._hist_mean_norm_range = float(np.mean(ranges_valid))

        return self

    def fit_from_arrays(
        self,
        gaps: np.ndarray,
        ranges: np.ndarray,
        body_pos: np.ndarray,
        upper_wick: np.ndarray,
        returns: np.ndarray,
    ) -> OHLCStructureModel:
        """Fit OHLC distributions from pre-computed normalised feature arrays.

        This avoids recomputing features from a filtered (non-consecutive)
        DataFrame, which would produce incorrect multi-bar gap returns.
        The caller is responsible for computing features on the full
        consecutive data and splitting by regime label.

        Parameters
        ----------
        gaps : normalised gap ratios (open - prev_close) / (prev_close * vol)
        ranges : normalised range ratios (high - low) / (close * vol)
        body_pos : body position ratios (close - low) / (high - low), clipped [0.01, 0.99]
        upper_wick : upper wick ratios (high - max(open,close)) / (high - low), clipped [0.01, 0.99]
        returns : simple returns, same length, for up/down split
        """
        # --- 1. Gap mixture ---
        gaps_finite = gaps[np.isfinite(gaps)]
        if len(gaps_finite) > 5:
            self._fit_gap_mixture(gaps_finite)
        else:
            self.gap_mean = 0.0
            self.gap_std = 1e-4
            self.gap_jump_weight = 0.0

        # --- 2. Range (Gamma) with return correlation ---
        mask_r = np.isfinite(ranges) & (ranges > 0)
        ranges_valid = ranges[mask_r]
        if len(ranges_valid) > 10:
            self.range_params = stats.gamma.fit(ranges_valid, floc=0)
        else:
            self.range_params = (2.0, 0.0, 1.0)

        abs_rets = np.abs(returns)
        if len(ranges) == len(abs_rets):
            valid = mask_r & np.isfinite(abs_rets)
            if np.sum(valid) > 20:
                corr = np.corrcoef(abs_rets[valid], ranges[valid])[0, 1]
                self.range_return_corr = float(corr) if np.isfinite(corr) else 0.0
                from numpy.polynomial.polynomial import polyfit
                coeffs = polyfit(abs_rets[valid], ranges[valid], deg=1)
                self.range_return_intercept = float(coeffs[0])
                self.range_return_slope = float(coeffs[1])
            else:
                self.range_return_corr = 0.0
                self.range_return_slope = 0.0
                self.range_return_intercept = float(np.mean(ranges_valid)) if len(ranges_valid) > 0 else 1.0
        else:
            self.range_return_corr = 0.0
            self.range_return_slope = 0.0
            self.range_return_intercept = float(np.mean(ranges_valid)) if len(ranges_valid) > 0 else 1.0

        # --- 3. Body position (Beta, split by return sign) ---
        bp = np.clip(body_pos, 0.01, 0.99)
        bp_valid = np.isfinite(bp)
        up_mask = bp_valid & (returns > 0)
        down_mask = bp_valid & (returns <= 0)

        bp_up = bp[up_mask] if np.sum(up_mask) > 10 else bp[bp_valid]
        bp_down = bp[down_mask] if np.sum(down_mask) > 10 else bp[bp_valid]

        if len(bp_up) > 5:
            self.body_up_params = stats.beta.fit(bp_up, floc=0, fscale=1)
        else:
            self.body_up_params = (2.0, 2.0, 0.0, 1.0)
        if len(bp_down) > 5:
            self.body_down_params = stats.beta.fit(bp_down, floc=0, fscale=1)
        else:
            self.body_down_params = (2.0, 2.0, 0.0, 1.0)

        # --- 4. Upper wick (Beta) ---
        uw = np.clip(upper_wick, 0.01, 0.99)
        uw_valid = uw[np.isfinite(uw)]
        if len(uw_valid) > 5:
            self.upper_wick_params = stats.beta.fit(uw_valid, floc=0, fscale=1)
        else:
            self.upper_wick_params = (2.0, 5.0, 0.0, 1.0)

        # Store mean normalised range for ATR targeting
        self._hist_mean_norm_range = float(np.mean(ranges_valid)) if len(ranges_valid) > 0 else 1.0

        return self

    def _fit_gap_mixture(self, gaps: np.ndarray) -> None:
        """Fit a 2-component Gaussian mixture for gaps: base + jump.

        The jump component captures overnight gap jumps / earnings surprises.
        """
        # Base component: bulk of the data
        self.gap_mean = float(np.mean(gaps))
        self.gap_std = float(np.std(gaps))
        if self.gap_std < 1e-10:
            self.gap_std = 1e-4

        # Detect jump gaps: beyond 2.5 sigma
        threshold = 2.5 * self.gap_std
        is_jump = np.abs(gaps - self.gap_mean) > threshold
        n_jumps = int(np.sum(is_jump))

        if n_jumps >= 5:
            # Fit jump component
            jump_gaps = gaps[is_jump]
            self.gap_jump_mean = float(np.mean(jump_gaps))
            self.gap_jump_std = float(np.std(jump_gaps))
            if self.gap_jump_std < self.gap_std:
                self.gap_jump_std = self.gap_std * 2.0
            self.gap_jump_weight = float(n_jumps / len(gaps))

            # Re-fit base component excluding jumps
            base_gaps = gaps[~is_jump]
            if len(base_gaps) > 5:
                self.gap_mean = float(np.mean(base_gaps))
                self.gap_std = float(np.std(base_gaps))
        else:
            # No significant jump component
            self.gap_jump_mean = self.gap_mean
            self.gap_jump_std = self.gap_std * 3.0
            self.gap_jump_weight = 0.0

    # ------------------------------------------------------------------
    # Batch generation (vectorised)
    # ------------------------------------------------------------------

    def generate_batch(
        self,
        close_prices: np.ndarray,
        prev_closes: np.ndarray,
        volatilities: np.ndarray,
        returns: np.ndarray,
        rng: np.random.Generator | None = None,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Generate OHLC arrays for a batch of candles (vectorised).

        Parameters
        ----------
        close_prices : (n_paths, n_periods) or (n_periods,)
        prev_closes  : same shape — previous-bar close prices
        volatilities : same shape — conditional volatilities (sigma)
        returns      : same shape — log or simple returns (for sign detection)
        rng          : numpy Generator for reproducibility

        Returns
        -------
        opens, highs, lows, closes : arrays with same shape as inputs
        """
        if rng is None:
            rng = np.random.default_rng()

        shape = close_prices.shape
        closes = close_prices.copy()

        # Sample gap from mixture model
        gaps = self._sample_gaps(shape, rng)

        # Sample ranges with return correlation
        ranges = self._sample_ranges(shape, returns, rng)

        # Body position — select up/down params per element
        bp_up = stats.beta.rvs(
            *self.body_up_params, size=shape, random_state=rng.integers(2**31)
        )
        bp_down = stats.beta.rvs(
            *self.body_down_params, size=shape, random_state=rng.integers(2**31)
        )
        is_up = returns > 0
        body_pos = np.where(is_up, bp_up, bp_down)

        # Open from gap
        opens = prev_closes * (1.0 + gaps * volatilities)

        # Range scaled by volatility
        hl_range = ranges * closes * volatilities
        hl_range = np.maximum(hl_range, 1e-10)

        # Low from body position
        lows = closes - body_pos * hl_range
        highs = lows + hl_range

        # Enforce OHLC constraints
        highs = np.maximum(highs, np.maximum(opens, closes))
        lows = np.minimum(lows, np.minimum(opens, closes))

        return opens, highs, lows, closes

    def _sample_gaps(
        self,
        shape: Tuple,
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Sample gaps from mixture model: (1-w)*N(μ₁,σ₁) + w*N(μ₂,σ₂)."""
        if self.gap_jump_weight is None or self.gap_jump_weight < 0.001:
            # Pure normal — no jump component
            return rng.normal(self.gap_mean, self.gap_std, size=shape)

        # Mixture: base + jump
        base = rng.normal(self.gap_mean, self.gap_std, size=shape)
        jump = rng.normal(self.gap_jump_mean, self.gap_jump_std, size=shape)
        is_jump = rng.uniform(size=shape) < self.gap_jump_weight

        return np.where(is_jump, jump, base)

    def _sample_ranges(
        self,
        shape: Tuple,
        returns: np.ndarray,
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Sample ranges with return correlation.

        Base range from Gamma distribution, then adjust based on |return|
        to capture the empirical range-return correlation.
        """
        base_ranges = stats.gamma.rvs(
            *self.range_params, size=shape, random_state=rng.integers(2**31)
        )

        # Apply return-correlated adjustment if fitted
        if (self.range_return_corr is not None
                and abs(self.range_return_corr) > 0.05
                and self.range_return_slope is not None):
            # Linear adjustment: predicted_range = slope * |ret| + intercept
            abs_ret = np.abs(returns)
            predicted = self.range_return_slope * abs_ret + self.range_return_intercept

            # Blend: gamma_sample * (predicted / mean_gamma) with damping
            mean_gamma = self.range_params[0] * self.range_params[2]  # shape * scale
            if mean_gamma > 1e-10:
                # Damped blend: 50% gamma base + 50% correlation-adjusted
                adjustment = predicted / (mean_gamma + 1e-10)
                adjustment = np.clip(adjustment, 0.3, 3.0)  # prevent extreme scaling
                blended = base_ranges * (0.5 + 0.5 * adjustment)
                return np.maximum(blended, 1e-6)

        return base_ranges

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "vol_window": getattr(self, '_vol_window', 20),
            "gap_mean": self.gap_mean,
            "gap_std": self.gap_std,
            "gap_jump_mean": self.gap_jump_mean,
            "gap_jump_std": self.gap_jump_std,
            "gap_jump_weight": self.gap_jump_weight,
            "range_params": list(self.range_params) if self.range_params else None,
            "range_return_corr": self.range_return_corr,
            "range_return_slope": self.range_return_slope,
            "range_return_intercept": self.range_return_intercept,
            "body_up_params": list(self.body_up_params) if self.body_up_params else None,
            "body_down_params": list(self.body_down_params) if self.body_down_params else None,
            "upper_wick_params": list(self.upper_wick_params) if self.upper_wick_params else None,
            "hist_mean_norm_range": getattr(self, '_hist_mean_norm_range', None),
        }

    @classmethod
    def from_dict(cls, params: dict) -> OHLCStructureModel:
        obj = cls()
        obj.gap_mean = params["gap_mean"]
        obj.gap_std = params["gap_std"]
        obj.gap_jump_mean = params.get("gap_jump_mean")
        obj.gap_jump_std = params.get("gap_jump_std")
        obj.gap_jump_weight = params.get("gap_jump_weight", 0.0)
        obj.range_params = tuple(params["range_params"]) if params["range_params"] else None
        obj.range_return_corr = params.get("range_return_corr", 0.0)
        obj.range_return_slope = params.get("range_return_slope", 0.0)
        obj.range_return_intercept = params.get("range_return_intercept")
        obj.body_up_params = tuple(params["body_up_params"]) if params["body_up_params"] else None
        obj.body_down_params = tuple(params["body_down_params"]) if params["body_down_params"] else None
        obj.upper_wick_params = tuple(params["upper_wick_params"]) if params["upper_wick_params"] else None
        obj._hist_mean_norm_range = params.get("hist_mean_norm_range")
        return obj
