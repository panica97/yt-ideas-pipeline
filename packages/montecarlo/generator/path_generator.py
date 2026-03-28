"""
SyntheticOHLCGenerator — combines GJR-GARCH(1,1) + OHLCStructureModel + RegimeDetector
to produce multi-timeframe synthetic OHLC paths for Monte Carlo simulation.

Advanced features:
- GJR-GARCH with Hansen's skewed Student-t innovations
- Merton-style jump diffusion
- 2-state Markov regime switching (normal / stressed)
- Range-return correlation in OHLC structure
- Gap mixture model for overnight jumps
"""

from __future__ import annotations

import numpy as np
import polars as pl
from datetime import datetime, timedelta
from typing import Dict, Generator, List, Optional

from ..config import MonteCarloConfig
from .garch import GJR_GARCH
from .ohlc_structure import OHLCStructureModel
from .regime import RegimeDetector


# ---- Timeframe helpers ----

_TF_MINUTES: dict[str, int] = {
    "1 min": 1,
    "1 minute": 1,
    "5 mins": 5,
    "5 minutes": 5,
    "15 mins": 15,
    "15 minutes": 15,
    "30 mins": 30,
    "30 minutes": 30,
    "1 hour": 60,
    "2 hours": 120,
    "4 hours": 240,
    "1 day": 1440,
}


def _parse_tf_minutes(tf: str) -> int:
    """Convert a human-readable timeframe string to minutes."""
    tf_lower = tf.strip().lower()
    if tf_lower in _TF_MINUTES:
        return _TF_MINUTES[tf_lower]
    # Try simple parsing: "N min(s)", "N hour(s)", "N day(s)"
    parts = tf_lower.split()
    if len(parts) == 2:
        n = int(parts[0])
        unit = parts[1].rstrip("s")
        if unit in ("min", "minute"):
            return n
        if unit in ("hour",):
            return n * 60
        if unit in ("day",):
            return n * 1440
    raise ValueError(f"Unknown timeframe: {tf!r}")


def _aggregate_to_tf(base_df: pl.DataFrame, base_minutes: int, target_minutes: int) -> pl.DataFrame:
    """Aggregate a base-TF DataFrame to a higher timeframe using Polars.

    The base_df must have a 'date' column of type Datetime.
    """
    if target_minutes <= base_minutes:
        return base_df

    every = f"{target_minutes}m"
    agg = (
        base_df
        .sort("date")
        .group_by_dynamic("date", every=every)
        .agg(
            pl.col("open").first().alias("open"),
            pl.col("high").max().alias("high"),
            pl.col("low").min().alias("low"),
            pl.col("close").last().alias("close"),
            pl.col("volume").sum().alias("volume"),
        )
        .sort("date")
    )
    return agg


def _lowest_timeframe(timeframes: List[str]) -> str:
    """Return the timeframe with the smallest duration from a list."""
    return min(timeframes, key=lambda tf: _parse_tf_minutes(tf))


class SyntheticOHLCGenerator:
    """Fit GJR-GARCH + OHLC + Regime models on historical data and generate
    synthetic multi-timeframe OHLC paths with regime switching."""

    def __init__(self) -> None:
        self.garch = GJR_GARCH()
        self.ohlc_model = OHLCStructureModel()
        self.regime_detector = RegimeDetector()
        self.initial_price: float | None = None
        self.base_timeframe: str | None = None
        self._base_minutes: int = 1440
        self._historical_std: float | None = None  # for variance targeting

        # Per-regime GARCH models (fitted if regime switching is active)
        self.regime_garch: List[GJR_GARCH] = []
        self._regime_switching_active: bool = False

        # Intraday vol seasonality (Phase 3)
        self._seasonal_vol: np.ndarray | None = None

        # Regime-conditional OHLC models (Phase 4)
        self._regime_ohlc: Optional[List[OHLCStructureModel]] = None

        # Regime assignments from last simulation batch
        self._last_regimes: np.ndarray | None = None

    # ------------------------------------------------------------------
    # Fitting
    # ------------------------------------------------------------------

    def fit(self, historical_1min: pl.DataFrame, strategy_timeframes: List[str], verbose: bool = False) -> SyntheticOHLCGenerator:
        """Fit GJR-GARCH, OHLC structure, and regime detector.

        Parameters
        ----------
        historical_1min : Polars DataFrame with 1-minute OHLCV data.
        strategy_timeframes : List of timeframe strings (e.g. ["1 hour", "4 hours"]).
                              The lowest timeframe is used as the base for fitting.
        """
        self.base_timeframe = _lowest_timeframe(strategy_timeframes)
        base_minutes = _parse_tf_minutes(self.base_timeframe)
        self._base_minutes = base_minutes

        # Resample 1-min data to base timeframe
        base_tf_df = _aggregate_to_tf(historical_1min, 1, base_minutes)

        closes = base_tf_df["close"].to_numpy().astype(np.float64)
        returns = np.diff(closes) / closes[:-1]

        self.initial_price = float(closes[0])
        self._historical_std = float(np.std(returns))

        # Store historical mean raw range ratio for ATR targeting
        hist_highs = base_tf_df["high"].to_numpy().astype(np.float64)
        hist_lows = base_tf_df["low"].to_numpy().astype(np.float64)
        raw_ranges = (hist_highs[1:] - hist_lows[1:]) / (closes[1:] + 1e-10)
        raw_ranges = raw_ranges[np.isfinite(raw_ranges) & (raw_ranges > 0)]
        self._hist_mean_raw_range = float(np.mean(raw_ranges))

        # 1. Fit global GJR-GARCH (always — provides fallback)
        self.garch.fit(returns, verbose=verbose)

        # 2. Fit OHLC structure model (use GARCH in-sample sigma for normalisation)
        garch_sigma = self.garch.in_sample_sigma(returns)
        self.ohlc_model.fit(
            base_tf_df, tf_minutes=base_minutes, verbose=verbose,
            garch_sigma=garch_sigma,
        )

        # 3. Fit regime detector with min_duration derived from timeframe
        min_duration = max(10, min(50, round(
            MonteCarloConfig.MIN_REGIME_DURATION_HOURS * 60 / base_minutes
        )))
        if (MonteCarloConfig.AUTO_SELECT_REGIME_STATES
                and len(returns) >= MonteCarloConfig.MIN_BARS_FOR_3_STATES):
            self.regime_detector = RegimeDetector.fit_best(
                returns,
                max_states=MonteCarloConfig.MAX_REGIME_STATES,
                min_bars_for_3=MonteCarloConfig.MIN_BARS_FOR_3_STATES,
                min_duration=min_duration,
                verbose=verbose,
            )
        else:
            self.regime_detector.fit(returns, min_duration=min_duration, verbose=verbose)

        # 4. Fit per-regime GARCH models if regime switching is meaningful
        self._fit_regime_garch(returns, verbose)

        # 5. Fit intraday vol seasonality for sub-daily timeframes
        if (MonteCarloConfig.SEASONAL_VOL_ENABLED
                and base_minutes < 1440):
            self._fit_seasonal_vol(returns, base_minutes, verbose)

        # 6. Fit regime-conditional OHLC if regime switching is active
        if (MonteCarloConfig.OHLC_REGIME_CONDITIONAL
                and self._regime_switching_active
                and self.regime_detector.regime_labels is not None):
            self._fit_regime_ohlc(base_tf_df, base_minutes, verbose, returns)

        # 7. Post-fit kurtosis refinement using full pipeline
        if MonteCarloConfig.KURTOSIS_POST_FIT_REFINEMENT:
            self._post_fit_kurtosis_refinement(returns, verbose)

        return self

    def _fit_regime_garch(self, returns: np.ndarray, verbose: bool) -> None:
        """Fit separate GJR-GARCH models for each regime (supports N states)."""
        if not self.regime_detector._fitted:
            self._regime_switching_active = False
            return

        labels = self.regime_detector.regime_labels
        if labels is None:
            self._regime_switching_active = False
            return

        n_states = self.regime_detector.n_states
        min_obs = max(50, MonteCarloConfig.MIN_REGIME_OBSERVATIONS // 2)

        # Check each regime has sufficient observations
        regime_stds = []
        for k in range(n_states):
            r_k = returns[labels == k]
            if len(r_k) < min_obs:
                self._regime_switching_active = False
                if verbose:
                    counts = ", ".join(
                        f"R{j}={int(np.sum(labels == j))}" for j in range(n_states)
                    )
                    print(f"  Regime GARCH: insufficient per-regime data "
                          f"({counts}), using global model")
                return
            regime_stds.append(float(np.std(r_k)))

        # Volatility ratio: max vol / min vol across all regimes
        vol_ratio = max(regime_stds) / (min(regime_stds) + 1e-10)
        if vol_ratio < 1.2:
            self._regime_switching_active = False
            if verbose:
                print(f"  Regime GARCH: regimes too similar (vol ratio={vol_ratio:.2f}), "
                      f"using global model")
            return

        # Persistence check: adaptive thresholds interpolated per regime
        base_minutes = getattr(self, '_base_minutes', 1440)
        if MonteCarloConfig.REGIME_PERSISTENCE_ADAPTIVE:
            tf_adj = 0.12 * (base_minutes / 1440.0 - 1.0)
            min_p_normal = max(0.55, min(0.85, 0.80 + tf_adj))
            min_p_stressed = max(0.40, min(0.70,
                MonteCarloConfig.MIN_REGIME_PERSISTENCE_STRESSED + tf_adj))
        else:
            min_p_normal = MonteCarloConfig.MIN_REGIME_PERSISTENCE
            min_p_stressed = MonteCarloConfig.MIN_REGIME_PERSISTENCE_STRESSED

        for k in range(n_states):
            p_k = float(self.regime_detector.transition_matrix[k, k])
            # Interpolate: regime 0 (calmest) uses min_p_normal,
            # last regime (most stressed) uses min_p_stressed
            frac = k / max(n_states - 1, 1)
            min_p_k = min_p_normal * (1.0 - frac) + min_p_stressed * frac
            if p_k < min_p_k:
                self._regime_switching_active = False
                if verbose:
                    print(f"  Regime GARCH: persistence too low for regime {k} "
                          f"({p_k:.3f} < {min_p_k:.3f}), using global model")
                return

        # Fit per-regime models
        self.regime_garch = []
        for k in range(n_states):
            regime_returns = returns[labels == k]
            try:
                garch_k = GJR_GARCH()
                garch_k.fit(regime_returns, verbose=False)
                self.regime_garch.append(garch_k)
            except Exception:
                self.regime_garch.append(self.garch)

        # Fix degenerate per-regime fits: if GARCH collapsed (no vol
        # clustering or thin tails), substitute the global GARCH's dynamics
        # rescaled to match the regime's variance level.
        for k in range(n_states):
            g = self.regime_garch[k]
            persistence = g.alpha + g.gamma / 2.0 + g.beta
            degenerate = persistence < 0.3 or g.nu > 40
            if degenerate and self.garch is not None:
                r_k = returns[labels == k]
                regime_var = float(np.var(r_k))
                regime_mu = float(np.mean(r_k))
                scaled = self._scale_global_garch(regime_var)
                scaled.mu = regime_mu
                self.regime_garch[k] = scaled
                if verbose:
                    print(f"  Regime GARCH R{k}: degenerate fit "
                          f"(persist={persistence:.3f}, nu={g.nu:.1f}), "
                          f"substituted scaled global GARCH")

        self._regime_switching_active = True

        if verbose:
            print(f"  Regime GARCH: active ({n_states}-state, vol ratio={vol_ratio:.2f})")
            for k in range(n_states):
                g = self.regime_garch[k]
                print(f"    R{k}: alpha={g.alpha:.4f}, gamma={g.gamma:.4f}, "
                      f"beta={g.beta:.4f}, nu={g.nu:.2f}, lam={g.lam:.4f}")

    def _scale_global_garch(self, regime_var: float) -> GJR_GARCH:
        """Create a copy of the global GARCH with omega rescaled so that
        its long-run variance (in original space) matches *regime_var*.

        This preserves the global model's vol-clustering dynamics (alpha,
        gamma, beta) and tail shape (nu, lam) while targeting the correct
        variance level for the regime.
        """
        import copy
        g = copy.copy(self.garch)
        # returns_std for this regime
        g.returns_std = float(np.sqrt(regime_var))
        # In standardised space, long_run_var = 1.0 (variance targeting).
        # omega_std = (1 - alpha - gamma/2 - beta) * long_run_var
        persistence = g.alpha + g.gamma / 2.0 + g.beta
        g.omega = max(1e-8, (1.0 - persistence)) * 1.0  # LRV = 1.0 in std space
        g.long_run_var = 1.0
        return g

    # ------------------------------------------------------------------
    # Intraday vol seasonality (Phase 3)
    # ------------------------------------------------------------------

    def _fit_seasonal_vol(
        self,
        returns: np.ndarray,
        base_minutes: int,
        verbose: bool,
    ) -> None:
        """Fit multiplicative periodic vol factor for sub-daily timeframes.

        Groups |returns|^2 by bar-of-day and normalises to produce a
        seasonal multiplier vector of length bars_per_day.  During
        simulation, GARCH variance is scaled by this factor.
        """
        bars_per_day = round(24 * 60 / base_minutes)
        if bars_per_day < MonteCarloConfig.SEASONAL_MIN_BARS_PER_DAY:
            self._seasonal_vol = None
            return

        sq_ret = returns ** 2
        n = len(sq_ret)
        if n < bars_per_day * 5:
            self._seasonal_vol = None
            return

        # Group by bar-of-day position and compute mean squared return
        group_var = np.zeros(bars_per_day)
        group_count = np.zeros(bars_per_day)
        for i in range(n):
            idx = i % bars_per_day
            group_var[idx] += sq_ret[i]
            group_count[idx] += 1

        group_count = np.maximum(group_count, 1)
        group_var /= group_count

        mean_var = np.mean(group_var)
        if mean_var < 1e-15:
            self._seasonal_vol = None
            return

        # Seasonal multiplier: normalised so mean = 1.0
        seasonal = group_var / mean_var

        # Dampen extremes to prevent over-fitting
        seasonal = np.clip(seasonal, 0.5, 2.0)
        seasonal /= np.mean(seasonal)  # re-normalise after clipping

        self._seasonal_vol = seasonal

        if verbose:
            print(f"  Seasonal vol: {bars_per_day} bars/day, "
                  f"range [{seasonal.min():.2f}, {seasonal.max():.2f}]")

    # ------------------------------------------------------------------
    # Regime-conditional OHLC (Phase 4)
    # ------------------------------------------------------------------

    def _fit_regime_ohlc(
        self,
        base_tf_df: pl.DataFrame,
        base_minutes: int,
        verbose: bool,
        returns: np.ndarray | None = None,
    ) -> None:
        """Fit separate OHLC structure models for each regime.

        Computes all OHLC features (gaps, ranges, body_pos, wick) on the
        FULL consecutive DataFrame using global GARCH sigma, then splits
        the pre-computed feature arrays by regime label.  This avoids the
        non-consecutive bar problem where filtering the DataFrame by regime
        creates multi-bar gaps that corrupt gap and range calculations.
        """
        labels = self.regime_detector.regime_labels
        if labels is None:
            self._regime_ohlc = None
            return

        n_bars = len(base_tf_df)
        n_labels = len(labels)
        if n_labels < n_bars - 1:
            self._regime_ohlc = None
            return

        if returns is None or len(returns) != n_bars - 1:
            self._regime_ohlc = None
            return

        # --- Compute OHLC features on full consecutive data ---
        closes = base_tf_df["close"].to_numpy().astype(np.float64)
        opens = base_tf_df["open"].to_numpy().astype(np.float64)
        highs = base_tf_df["high"].to_numpy().astype(np.float64)
        lows = base_tf_df["low"].to_numpy().astype(np.float64)

        # Use global GARCH sigma (always consecutive, always aligned)
        garch_sigma = self.garch.in_sample_sigma(returns)
        rolling_vol = np.maximum(garch_sigma, 1e-10)

        # All features have length N-1, aligned with returns and labels
        prev_close = closes[:-1]
        o = opens[1:]
        h = highs[1:]
        lo = lows[1:]
        c = closes[1:]

        # Normalised gaps: (open - prev_close) / (prev_close * vol)
        all_gaps = (o - prev_close) / (prev_close * rolling_vol + 1e-10)

        # Normalised ranges: (high - low) / (close * vol)
        hl_range = h - lo
        all_ranges = hl_range / (c * rolling_vol + 1e-10)

        # Body position: (close - low) / (high - low)
        all_body_pos = np.clip((c - lo) / (hl_range + 1e-10), 0.01, 0.99)

        # Upper wick: (high - max(open, close)) / (high - low)
        max_oc = np.maximum(o, c)
        all_upper_wick = np.clip((h - max_oc) / (hl_range + 1e-10), 0.01, 0.99)

        # --- Split by regime and fit ---
        n_states = self.regime_detector.n_states
        self._regime_ohlc = []
        for k in range(n_states):
            mask = labels == k
            n_regime = int(np.sum(mask))

            if n_regime < 100:
                self._regime_ohlc.append(self.ohlc_model)
                continue

            ohlc_k = OHLCStructureModel()
            try:
                ohlc_k.fit_from_arrays(
                    gaps=all_gaps[mask],
                    ranges=all_ranges[mask],
                    body_pos=all_body_pos[mask],
                    upper_wick=all_upper_wick[mask],
                    returns=returns[mask],
                )
                self._regime_ohlc.append(ohlc_k)
            except Exception:
                self._regime_ohlc.append(self.ohlc_model)

        if verbose:
            for k in range(n_states):
                m = self._regime_ohlc[k]
                rp = m.range_params
                if rp:
                    print(f"  OHLC R{k}: range gamma "
                          f"shape={rp[0]:.3f}, scale={rp[2]:.3f}")

    # ------------------------------------------------------------------
    # Post-fit kurtosis refinement (Phase 7)
    # ------------------------------------------------------------------

    def _post_fit_kurtosis_refinement(
        self,
        hist_returns: np.ndarray,
        verbose: bool,
    ) -> None:
        """Refine nu across all GARCH models so the full pipeline's kurtosis
        matches historical.

        The per-GARCH kurtosis calibration (step 1) only uses GARCH.simulate(),
        which excludes regime switching, seasonal vol, and variance targeting.
        This post-fit step generates paths through the complete pipeline and
        adjusts ALL GARCH nu values by a common factor until the combined
        kurtosis ratio falls within [0.8, 1.2].
        """
        from scipy.stats import kurtosis as _kurtosis

        target_lo, target_hi = MonteCarloConfig.GARCH_KURTOSIS_TARGET_RATIO
        hist_kurt = float(_kurtosis(hist_returns, fisher=True))
        if abs(hist_kurt) < 0.5:
            return  # near-Gaussian, nothing to calibrate

        n_test = MonteCarloConfig.KURTOSIS_POST_FIT_PATHS
        n_periods = len(hist_returns)

        def _measure_pipeline_kurtosis(seed: int = 42) -> float:
            """Generate paths through full pipeline, measure kurtosis ratio."""
            all_rets = []
            for batch in self.generate_paths(
                n_paths=n_test,
                n_periods=n_periods,
                strategy_timeframes=[self.base_timeframe],
                seed=seed,
                batch_size=n_test,
            ):
                for path_dict in batch:
                    df = path_dict[self.base_timeframe]
                    c = df["close"].to_numpy().astype(np.float64)
                    rets = np.diff(c) / c[:-1]
                    all_rets.extend(rets.tolist())

            arr = np.array(all_rets)
            arr = arr[np.isfinite(arr)]
            if len(arr) < 100:
                return 1.0
            synth_kurt = float(_kurtosis(arr, fisher=True))
            return synth_kurt / hist_kurt if abs(hist_kurt) > 0.01 else 1.0

        # Measure current ratio
        current_ratio = _measure_pipeline_kurtosis(seed=42)
        if target_lo <= current_ratio <= target_hi:
            if verbose:
                print(f"  Post-fit kurtosis: ratio={current_ratio:.3f} "
                      f"already in [{target_lo}, {target_hi}]")
            return

        # Collect all GARCH models whose nu we'll adjust together
        all_garch = [self.garch]
        if self._regime_switching_active and self.regime_garch:
            all_garch.extend(self.regime_garch)
        original_nus = [g.nu for g in all_garch]

        nu_lb = MonteCarloConfig.GARCH_NU_LOWER_BOUND

        def _apply_nu_scale(scale: float) -> None:
            """Scale all GARCH nu values by a common factor."""
            for g, orig_nu in zip(all_garch, original_nus):
                g.nu = max(nu_lb, min(50.0, orig_nu * scale))

        # Binary search on the nu scale factor
        # ratio < target → tails too thin → need lower nu → scale < 1.0
        # ratio > target → tails too fat  → need higher nu → scale > 1.0
        scale_lo, scale_hi = 0.3, 3.0
        best_scale = 1.0
        best_dist = abs(current_ratio - 1.0)

        for iteration in range(10):
            scale_mid = (scale_lo + scale_hi) / 2.0
            _apply_nu_scale(scale_mid)
            ratio = _measure_pipeline_kurtosis(seed=42 + iteration)
            dist = abs(ratio - 1.0)

            if dist < best_dist:
                best_dist = dist
                best_scale = scale_mid

            if target_lo <= ratio <= target_hi:
                best_scale = scale_mid
                break

            if ratio < target_lo:
                # Tails too thin → lower nu → lower scale
                scale_hi = scale_mid
            else:
                # Tails too fat → higher nu → higher scale
                scale_lo = scale_mid

            if scale_hi - scale_lo < 0.05:
                break

        # Apply best scale
        _apply_nu_scale(best_scale)
        final_ratio = _measure_pipeline_kurtosis(seed=99)

        if verbose:
            nu_strs = ", ".join(f"{g.nu:.2f}" for g in all_garch)
            if target_lo <= final_ratio <= target_hi:
                print(f"  Post-fit kurtosis: ratio {current_ratio:.3f} -> "
                      f"{final_ratio:.3f}, nu=[{nu_strs}] (scale={best_scale:.3f})")
            else:
                print(f"  Post-fit kurtosis: ratio {current_ratio:.3f} -> "
                      f"{final_ratio:.3f} (target [{target_lo}, {target_hi}] "
                      f"not reached), nu=[{nu_strs}]")

    # ------------------------------------------------------------------
    # Path generation (generator yielding batches)
    # ------------------------------------------------------------------

    def generate_paths(
        self,
        n_paths: int,
        n_periods: int,
        strategy_timeframes: List[str],
        seed: int | None = None,
        batch_size: int = MonteCarloConfig.DEFAULT_BATCH_SIZE,
        start_date: str | None = None,
    ) -> Generator[List[Dict[str, pl.DataFrame]], None, None]:
        """Yield batches of synthetic multi-TF paths with regime switching.

        Each yielded item is a list of dicts, one per path in the batch.
        Each dict maps timeframe string -> Polars DataFrame with columns:
        date, open, high, low, close, volume.
        """
        import time as _time

        base_minutes = _parse_tf_minutes(self.base_timeframe)
        target_tfs = {tf: _parse_tf_minutes(tf) for tf in strategy_timeframes}

        rng = np.random.default_rng(seed)
        generated = 0
        max_retries = 5
        max_total_attempts = n_paths * 10
        total_attempts = 0
        batch_idx = 0
        MAX_BATCH_TIME = 120
        neg_price_skips = 0

        while generated < n_paths:
            current_batch = min(batch_size, n_paths - generated)
            batch_idx += 1
            batch_t0 = _time.time()
            batch_seed = int(rng.integers(2**31))

            try:
                if self._regime_switching_active:
                    sim_returns, sim_sigma2, batch_regimes = self._simulate_with_regimes(
                        n_periods, current_batch, rng
                    )
                    self._last_regimes = batch_regimes
                else:
                    sim_returns, sim_sigma2 = self.garch.simulate(
                        n_periods, current_batch, seed=batch_seed
                    )
                    self._last_regimes = None
            except Exception as exc:
                print(f"  WARNING: GARCH simulation failed (batch {batch_idx}): {exc}",
                      flush=True)
                total_attempts += current_batch
                if total_attempts > max_total_attempts:
                    break
                continue

            # Apply intraday vol seasonality: multiply variance by
            # periodic factor so that e.g. US-open bars are wider.
            seasonal = getattr(self, '_seasonal_vol', None)
            if seasonal is not None:
                bars_per_day = len(seasonal)
                for t in range(n_periods):
                    factor = seasonal[t % bars_per_day]
                    sim_sigma2[:, t] *= factor
                    sim_returns[:, t] *= np.sqrt(factor)

            # NOTE: Post-hoc variance targeting was removed (Phase 1 fix).
            # GARCH MLE variance targeting already ensures correct unconditional
            # variance.  The post-hoc scaling was compressing kurtosis, destroying
            # vol clustering, and flattening regime structure.

            # Warn on non-finite values
            n_nonfinite = sim_returns.size - int(np.sum(np.isfinite(sim_returns)))
            if n_nonfinite > 0:
                print(f"  WARNING: {n_nonfinite} non-finite values in batch {batch_idx}",
                      flush=True)

            batch_results: List[Dict[str, pl.DataFrame]] = []

            for i in range(current_batch):
                total_attempts += 1
                if total_attempts > max_total_attempts:
                    break

                elapsed = _time.time() - batch_t0
                if elapsed > MAX_BATCH_TIME:
                    print(f"  WARNING: Batch {batch_idx} generation timeout "
                          f"({elapsed:.0f}s)", flush=True)
                    break

                path_returns = sim_returns[i]
                path_sigma2 = sim_sigma2[i]
                close_prices = self.initial_price * np.cumprod(1.0 + path_returns)

                # Retry negative-price paths
                if np.any(close_prices <= 0):
                    found_valid = False
                    for _retry in range(max_retries):
                        retry_rng_seed = int(rng.integers(2**31))
                        retry_ret, retry_s2 = self.garch.simulate(n_periods, 1, seed=retry_rng_seed)
                        retry_close = self.initial_price * np.cumprod(1.0 + retry_ret[0])
                        if not np.any(retry_close <= 0):
                            path_returns = retry_ret[0]
                            path_sigma2 = retry_s2[0]
                            close_prices = retry_close
                            found_valid = True
                            break
                    if not found_valid:
                        neg_price_skips += 1
                        continue

                prev_closes = np.concatenate([[self.initial_price], close_prices[:-1]])
                vols = np.sqrt(np.maximum(path_sigma2, 1e-10))

                # Select OHLC model: regime-conditional if available
                regime_ohlc = getattr(self, '_regime_ohlc', None)
                if (regime_ohlc is not None
                        and self._regime_switching_active
                        and hasattr(self, '_last_regimes')
                        and self._last_regimes is not None):
                    # Per-bar regime assignment for this path
                    path_regimes = self._last_regimes[i]
                    n_regime_states = self.regime_detector.n_states
                    # Generate OHLC per-regime and merge
                    opens = np.empty_like(close_prices)
                    highs = np.empty_like(close_prices)
                    lows = np.empty_like(close_prices)

                    for k in range(n_regime_states):
                        mask_k = path_regimes == k
                        if not np.any(mask_k):
                            continue
                        o_k, h_k, l_k, _ = regime_ohlc[k].generate_batch(
                            close_prices[mask_k],
                            prev_closes[mask_k],
                            vols[mask_k],
                            path_returns[mask_k],
                            rng=rng,
                        )
                        opens[mask_k] = o_k
                        highs[mask_k] = h_k
                        lows[mask_k] = l_k
                    closes = close_prices
                else:
                    opens, highs, lows, closes = self.ohlc_model.generate_batch(
                        close_prices, prev_closes, vols, path_returns, rng=rng
                    )

                # ATR targeting: correct range bias so synthetic ATR matches
                # historical.  With post-hoc variance targeting removed,
                # this is the only range correction and can use full scaling.
                hist_mr = getattr(self, '_hist_mean_raw_range', None)
                if hist_mr is not None and hist_mr > 0:
                    raw_range = (highs - lows) / (closes + 1e-10)
                    synth_mr = float(np.mean(raw_range[raw_range > 0]))
                    if synth_mr > 1e-10:
                        atr_scale = hist_mr / synth_mr
                        # Only apply if correction is meaningful (within 2x)
                        if 0.5 < atr_scale < 2.0:
                            # Scale around close to preserve body position
                            old_range = highs - lows
                            new_range = old_range * atr_scale
                            bp = (closes - lows) / (old_range + 1e-10)
                            lows = closes - bp * new_range
                            highs = lows + new_range
                            # Re-enforce OHLC constraints after scaling
                            highs = np.maximum(highs, np.maximum(opens, closes))
                            lows = np.minimum(lows, np.minimum(opens, closes))

                epoch = datetime.strptime(start_date, "%Y-%m-%d") if start_date else datetime(2020, 1, 1)
                dates = [epoch + timedelta(minutes=base_minutes * t) for t in range(n_periods)]

                base_df = pl.DataFrame({
                    "date": dates,
                    "open": opens,
                    "high": highs,
                    "low": lows,
                    "close": closes,
                    "volume": np.full(n_periods, MonteCarloConfig.DEFAULT_SYNTHETIC_VOLUME, dtype=np.float64),
                }).cast({"date": pl.Datetime("us")})

                path_dict: Dict[str, pl.DataFrame] = {}
                for tf_name, tf_min in target_tfs.items():
                    if tf_min == base_minutes:
                        path_dict[tf_name] = base_df
                    else:
                        path_dict[tf_name] = _aggregate_to_tf(base_df, base_minutes, tf_min)

                batch_results.append(path_dict)

            if batch_results:
                yield batch_results

            generated += len(batch_results)

            if total_attempts > max_total_attempts:
                print(f"  WARNING: Max generation attempts reached ({max_total_attempts})",
                      flush=True)
                break

        if neg_price_skips > 0:
            print(f"  Skipped {neg_price_skips} paths (negative prices after retries)",
                  flush=True)

    def _simulate_with_regimes(
        self,
        n_periods: int,
        n_paths: int,
        rng: np.random.Generator,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Simulate returns using regime-switching GJR-GARCH (N states).

        Works in original (non-standardized) return space so that regime
        transitions carry variance correctly across regimes with different
        mean/std scales.  Each regime's GARCH parameters are converted to
        original space: omega_orig = omega_std * returns_std^2.

        Returns
        -------
        returns  : (n_paths, n_periods)
        sigma2   : (n_paths, n_periods)
        regimes  : (n_paths, n_periods) int array of regime indices
        """
        from .garch import skewed_t_rvs

        n_states = len(self.regime_garch)

        # Generate regime sequences
        regimes = self.regime_detector.simulate_regimes(n_periods, n_paths, rng)

        returns = np.zeros((n_paths, n_periods))
        sigma2 = np.zeros((n_paths, n_periods))

        # Pre-compute original-space omega and long-run variance per regime
        omega_orig = []
        lrv_orig = []
        for k in range(n_states):
            g = self.regime_garch[k]
            std2 = g.returns_std ** 2
            omega_orig.append(g.omega * std2)
            lrv_orig.append(g.long_run_var * std2)

        # Initial variance in original return space
        for k in range(n_states):
            mask_k = regimes[:, 0] == k
            if np.any(mask_k):
                sigma2[mask_k, 0] = lrv_orig[k]

        # Pre-generate innovations for each regime (unit-variance skewed-t)
        innovations = [
            skewed_t_rvs(
                self.regime_garch[k].nu,
                self.regime_garch[k].lam,
                (n_paths, n_periods),
                rng,
            )
            for k in range(n_states)
        ]

        # Pre-generate jump components in original scale
        jump_components = []
        drift_adj = []
        for k in range(n_states):
            g = self.regime_garch[k]
            has_jumps = g.jump_prob is not None and g.jump_prob > 0.001
            if has_jumps:
                jump_mask = rng.uniform(size=(n_paths, n_periods)) < g.jump_prob
                jump_sizes = rng.normal(
                    g.jump_mean,
                    g.jump_std if g.jump_std > 0 else 1e-6,
                    size=(n_paths, n_periods),
                )
                jump_components.append(jump_mask * jump_sizes)
                drift_adj.append(g.jump_prob * g.jump_mean)
            else:
                jump_components.append(np.zeros((n_paths, n_periods)))
                drift_adj.append(0.0)

        # Variance cap in original space: 50x the largest regime's LRV
        sigma2_cap = 50.0 * max(lrv_orig)
        blend_rate = MonteCarloConfig.REGIME_TRANSITION_BLEND

        for t in range(n_periods):
            # Damp variance on regime transitions: blend sigma2 toward the
            # new regime's long-run variance to prevent cross-regime
            # variance contamination.
            if t > 0:
                transitions = regimes[:, t] != regimes[:, t - 1]
                if np.any(transitions):
                    for k in range(n_states):
                        mask_trans = transitions & (regimes[:, t] == k)
                        if np.any(mask_trans):
                            sigma2[mask_trans, t] = (
                                blend_rate * lrv_orig[k]
                                + (1.0 - blend_rate) * sigma2[mask_trans, t]
                            )

            for k in range(n_states):
                mask = regimes[:, t] == k
                if not np.any(mask):
                    continue

                g = self.regime_garch[k]
                phi = getattr(g, 'phi', 0.0) or 0.0
                sigma_t = np.sqrt(sigma2[mask, t])
                ar_term = phi * (returns[mask, t - 1] - g.mu) if (t > 0 and phi != 0.0) else 0.0
                returns[mask, t] = (
                    g.mu - drift_adj[k]
                    + ar_term
                    + sigma_t * innovations[k][mask, t]
                    + jump_components[k][mask, t]
                )

            if t < n_periods - 1:
                for k in range(n_states):
                    mask = regimes[:, t] == k
                    if not np.any(mask):
                        continue

                    g = self.regime_garch[k]
                    phi = getattr(g, 'phi', 0.0) or 0.0
                    ar_term = phi * (returns[mask, t - 1] - g.mu) if (t > 0 and phi != 0.0) else 0.0
                    eps = returns[mask, t] - g.mu - ar_term
                    eps2 = eps ** 2
                    leverage = g.gamma * eps2 * (eps < 0)
                    sigma2[mask, t + 1] = (
                        omega_orig[k]
                        + g.alpha * eps2
                        + leverage
                        + g.beta * sigma2[mask, t]
                    )
                    sigma2[mask, t + 1] = np.clip(
                        sigma2[mask, t + 1], 1e-10, sigma2_cap
                    )

        return returns, sigma2, regimes

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_paths(self, paths: List[Dict[str, pl.DataFrame]], n_sample: int = 50) -> dict:
        """Quick quality check on a sample of generated paths."""
        from ..validation import validate_ohlc

        base_tf = self.base_timeframe
        sampled = paths[:n_sample]

        ohlc_valid = 0
        ohlc_total = 0
        all_returns = []
        all_ranges = []

        for path_dict in sampled:
            df = path_dict[base_tf]
            result = validate_ohlc(df)
            ohlc_valid += result["total"] - result["violations"]
            ohlc_total += result["total"]

            c = df["close"].to_numpy().astype(np.float64)
            h = df["high"].to_numpy().astype(np.float64)
            lo = df["low"].to_numpy().astype(np.float64)

            rets = np.diff(c) / c[:-1]
            all_returns.extend(rets.tolist())
            rng = (h[1:] - lo[1:]) / (c[1:] + 1e-10)
            all_ranges.extend(rng.tolist())

        return {
            "n_sampled": len(sampled),
            "ohlc_valid_pct": ohlc_valid / ohlc_total if ohlc_total > 0 else 0.0,
            "returns_mean": float(np.mean(all_returns)),
            "returns_std": float(np.std(all_returns)),
            "ranges_mean": float(np.mean(all_ranges)),
        }

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def get_model_params(self) -> dict:
        params = {
            "garch": self.garch.to_dict(),
            "ohlc_model": self.ohlc_model.to_dict(),
            "regime": self.regime_detector.to_dict(),
            "regime_switching_active": self._regime_switching_active,
            "initial_price": self.initial_price,
            "base_timeframe": self.base_timeframe,
            "historical_std": self._historical_std,
        }

        if self._regime_switching_active and self.regime_garch:
            params["regime_garch"] = [g.to_dict() for g in self.regime_garch]

        # Seasonal vol multipliers
        seasonal = getattr(self, '_seasonal_vol', None)
        if seasonal is not None:
            params["seasonal_vol"] = seasonal.tolist()

        # Regime-conditional OHLC active flag
        regime_ohlc = getattr(self, '_regime_ohlc', None)
        params["regime_conditional_ohlc"] = regime_ohlc is not None

        return params
