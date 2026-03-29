"""Post-generation path validation.

Validates the actual OHLC paths produced by the generator -- a second line
of defence complementing the pre-generation model validation.

Usage in the MC runner:
    collector = PathValidationCollector()
    for batch in generator.generate_paths(...):
        collector.add_batch(batch, base_tf)
        # ... run backtests ...
    report = collector.finalize(historical_base_df)
"""

from __future__ import annotations

import numpy as np
import polars as pl
from scipy import stats
from scipy.stats import kurtosis as _kurtosis, skew as _skew


class PathValidationCollector:
    """Incrementally collects statistics from generated path batches.

    Memory-efficient: stores pooled arrays of returns/ranges/body_pos
    rather than full OHLC DataFrames.
    """

    def __init__(self) -> None:
        # Pooled per-bar statistics
        self._returns: list[float] = []
        self._ranges: list[float] = []
        self._body_pos: list[float] = []

        # Per-path level metrics
        self._terminal_prices: list[float] = []
        self._initial_prices: list[float] = []
        self._path_max_dd: list[float] = []

        # Structural integrity counters
        self._total_bars = 0
        self._ohlc_violations = 0
        self._negative_prices = 0
        self._nan_inf_count = 0
        self._zero_range_bars = 0

        self._n_paths = 0

    def add_batch(self, batch: list[dict[str, pl.DataFrame]], base_tf: str) -> None:
        """Extract validation statistics from one batch of generated paths."""
        for path_dict in batch:
            if base_tf not in path_dict:
                continue
            df = path_dict[base_tf]
            self._n_paths += 1

            o = df["open"].to_numpy().astype(np.float64)
            h = df["high"].to_numpy().astype(np.float64)
            lo = df["low"].to_numpy().astype(np.float64)
            c = df["close"].to_numpy().astype(np.float64)

            n_bars = len(df)
            self._total_bars += n_bars

            # --- Structural checks ---
            nan_inf = int(np.sum(~np.isfinite(o)) + np.sum(~np.isfinite(h))
                         + np.sum(~np.isfinite(lo)) + np.sum(~np.isfinite(c)))
            self._nan_inf_count += nan_inf

            neg = int(np.sum(o < 0) + np.sum(h < 0)
                      + np.sum(lo < 0) + np.sum(c < 0))
            self._negative_prices += neg

            tol = 1e-6
            ohlc_ok = ((h >= np.maximum(o, c) - tol)
                       & (lo <= np.minimum(o, c) + tol))
            self._ohlc_violations += int(np.sum(~ohlc_ok))

            zero_range = int(np.sum(np.abs(h - lo) < 1e-12))
            self._zero_range_bars += zero_range

            # --- Per-bar statistics (skip first bar -- no return) ---
            if n_bars > 1:
                rets = np.diff(c) / (c[:-1] + 1e-10)
                finite_mask = np.isfinite(rets)
                self._returns.extend(rets[finite_mask].tolist())

                rng = (h[1:] - lo[1:]) / (c[1:] + 1e-10)
                finite_rng = np.isfinite(rng) & (rng >= 0)
                self._ranges.extend(rng[finite_rng].tolist())

                bar_range = h - lo + 1e-10
                bp = (c - lo) / bar_range
                valid_bp = (bp >= 0) & (bp <= 1) & np.isfinite(bp)
                self._body_pos.extend(bp[valid_bp].tolist())

            # --- Path-level metrics ---
            if n_bars > 0:
                self._initial_prices.append(float(c[0]))
                self._terminal_prices.append(float(c[-1]))
                # Max drawdown of close prices
                cummax = np.maximum.accumulate(c)
                dd = (cummax - c) / (cummax + 1e-10)
                self._path_max_dd.append(float(np.max(dd)))

    def finalize(self, historical_df: pl.DataFrame) -> dict:
        """Compare collected path statistics against historical data.

        Returns a structured validation report.
        """
        if self._n_paths == 0:
            return _empty_report()

        # Historical reference data
        hist_c = historical_df["close"].to_numpy().astype(np.float64)
        hist_h = historical_df["high"].to_numpy().astype(np.float64)
        hist_lo = historical_df["low"].to_numpy().astype(np.float64)

        hist_returns = np.diff(hist_c) / (hist_c[:-1] + 1e-10)
        hist_ranges = (hist_h[1:] - hist_lo[1:]) / (hist_c[1:] + 1e-10)
        hist_bp = (hist_c - hist_lo) / (hist_h - hist_lo + 1e-10)
        hist_bp = hist_bp[(hist_bp >= 0) & (hist_bp <= 1) & np.isfinite(hist_bp)]

        synth_returns = np.array(self._returns)
        synth_ranges = np.array(self._ranges)
        synth_bp = np.array(self._body_pos)

        # --- Statistical tests ---
        returns_ks = _safe_ks(hist_returns, synth_returns)
        ranges_ks = _safe_ks(hist_ranges, synth_ranges)
        body_ks = _safe_ks(hist_bp, synth_bp)

        # Kurtosis
        hist_kurt = float(_kurtosis(hist_returns, fisher=True)) if len(hist_returns) > 10 else 0.0
        synth_kurt = float(_kurtosis(synth_returns, fisher=True)) if len(synth_returns) > 10 else 0.0
        kurt_ratio = synth_kurt / hist_kurt if abs(hist_kurt) > 0.01 else 1.0

        # Skewness
        hist_skew = float(_skew(hist_returns)) if len(hist_returns) > 10 else 0.0
        synth_skew = float(_skew(synth_returns)) if len(synth_returns) > 10 else 0.0

        # Tail frequency (>3 sigma)
        hist_tail = _tail_freq(hist_returns, 3.0)
        synth_tail = _tail_freq(synth_returns, 3.0)
        tail_ratio = synth_tail / hist_tail if hist_tail > 0.001 else 1.0

        # Vol clustering MAE
        hist_acf = _autocorr_abs(hist_returns, 10)
        synth_acf = _autocorr_abs(synth_returns, 10)
        vol_mae = _mae(hist_acf, synth_acf)

        # --- Path-level analysis ---
        terminal_arr = np.array(self._terminal_prices)
        initial_arr = np.array(self._initial_prices)
        dd_arr = np.array(self._path_max_dd)

        terminal_returns = (terminal_arr - initial_arr) / (initial_arr + 1e-10)
        pct_positive = float(np.mean(terminal_returns > 0)) if len(terminal_returns) > 0 else 0.5
        mean_terminal_ret = float(np.mean(terminal_returns)) if len(terminal_returns) > 0 else 0.0
        terminal_cv = (float(np.std(terminal_arr)) / float(np.mean(terminal_arr))
                       if len(terminal_arr) > 0 and np.mean(terminal_arr) > 0 else 0.0)

        degenerate = int(np.sum(terminal_arr <= 0))
        extreme_dd = int(np.sum(dd_arr > 0.99))

        # --- Scoring ---
        score = 0
        max_score = 10
        diagnostics = []

        # Structural integrity (weight 2)
        violation_rate = self._ohlc_violations / max(self._total_bars, 1)
        total_structural = self._ohlc_violations + self._negative_prices + self._nan_inf_count
        structural_rate = total_structural / max(self._total_bars, 1)
        if structural_rate < 0.001:
            score += 2
        else:
            diagnostics.append(
                f"Structural issues: {total_structural} problems in "
                f"{self._total_bars} bars ({structural_rate:.4%}). "
                f"OHLC violations={self._ohlc_violations}, "
                f"negative prices={self._negative_prices}, "
                f"NaN/Inf={self._nan_inf_count}."
            )

        # Returns KS (weight 2)
        if returns_ks["statistic"] < 0.10:
            score += 2
        else:
            diagnostics.append(
                f"Path returns KS failed (D={returns_ks['statistic']:.4f}): "
                f"generated path return distribution diverges from historical."
            )

        # Ranges KS (weight 1)
        if ranges_ks["statistic"] < 0.10:
            score += 1
        else:
            diagnostics.append(
                f"Path ranges KS failed (D={ranges_ks['statistic']:.4f}): "
                f"generated candle ranges diverge from historical."
            )

        # Body position KS (weight 1)
        if body_ks["statistic"] < 0.10:
            score += 1
        else:
            diagnostics.append(
                f"Path body position KS failed (D={body_ks['statistic']:.4f}): "
                f"candle body placement in generated paths diverges."
            )

        # Kurtosis ratio (weight 1)
        if 0.5 < kurt_ratio < 2.0 and not np.isnan(kurt_ratio):
            score += 1
        else:
            diagnostics.append(
                f"Path kurtosis ratio {kurt_ratio:.2f} outside [0.5, 2.0]: "
                f"generated paths have {'heavier' if kurt_ratio > 1 else 'lighter'} "
                f"tails than historical."
            )

        # Tail frequency (weight 1)
        if 0.3 < tail_ratio < 3.0 and not np.isnan(tail_ratio):
            score += 1
        else:
            diagnostics.append(
                f"Path tail frequency ratio {tail_ratio:.2f} outside [0.3, 3.0]: "
                f"extreme events {'over' if tail_ratio > 1 else 'under'}-represented "
                f"(hist={hist_tail:.4f}, synth={synth_tail:.4f})."
            )

        # Vol clustering MAE (weight 1)
        if vol_mae < 0.15:
            score += 1
        else:
            diagnostics.append(
                f"Path vol clustering MAE={vol_mae:.3f} > 0.15: "
                f"volatility autocorrelation structure in generated paths "
                f"doesn't match historical."
            )

        # Path sanity (weight 1)
        degen_rate = degenerate / max(self._n_paths, 1)
        extreme_rate = extreme_dd / max(self._n_paths, 1)
        if degen_rate < 0.01 and extreme_rate < 0.01:
            score += 1
        else:
            diagnostics.append(
                f"Path sanity: {degenerate} degenerate paths (price<=0), "
                f"{extreme_dd} extreme drawdown paths (DD>99%) "
                f"out of {self._n_paths}."
            )

        # Quality rating
        if score >= 8:
            quality = "good"
        elif score >= 5:
            quality = "acceptable"
        else:
            quality = "poor"

        return {
            "quality": quality,
            "score": score,
            "max_score": max_score,
            "diagnostics": diagnostics,
            "structural": {
                "total_bars": self._total_bars,
                "ohlc_violations": self._ohlc_violations,
                "negative_prices": self._negative_prices,
                "nan_inf_count": self._nan_inf_count,
                "zero_range_bars": self._zero_range_bars,
                "violation_rate": float(violation_rate),
            },
            "statistical": {
                "returns_ks": returns_ks,
                "ranges_ks": ranges_ks,
                "body_pos_ks": body_ks,
                "kurtosis": {
                    "historical": hist_kurt,
                    "synthetic": synth_kurt,
                    "ratio": kurt_ratio,
                },
                "skewness": {
                    "historical": hist_skew,
                    "synthetic": synth_skew,
                    "difference": abs(synth_skew - hist_skew),
                },
                "tail_frequency": {
                    "historical": hist_tail,
                    "synthetic": synth_tail,
                    "ratio": tail_ratio,
                },
                "vol_clustering_mae": float(vol_mae),
            },
            "path_level": {
                "n_paths": self._n_paths,
                "degenerate_paths": degenerate,
                "extreme_dd_paths": extreme_dd,
                "pct_positive_terminal": float(pct_positive),
                "terminal_price_cv": float(terminal_cv),
                "mean_terminal_return": float(mean_terminal_ret),
            },
        }


# ======================================================================
# Helpers
# ======================================================================

def _safe_ks(a: np.ndarray, b: np.ndarray) -> dict:
    """KS 2-sample test with empty-array guard."""
    if len(a) > 0 and len(b) > 0:
        result = stats.ks_2samp(a, b)
        return {"statistic": float(result.statistic), "p_value": float(result.pvalue)}
    return {"statistic": float("nan"), "p_value": float("nan")}


def _tail_freq(arr: np.ndarray, threshold_sigma: float = 3.0) -> float:
    if len(arr) < 10:
        return 0.0
    sigma = np.std(arr)
    return float(np.mean(np.abs(arr - np.mean(arr)) > threshold_sigma * sigma))


def _autocorr_abs(arr: np.ndarray, max_lag: int = 10) -> list[float]:
    a = np.abs(arr)
    if len(a) < max_lag + 10:
        return [0.0] * max_lag
    a_demean = a - np.mean(a)
    c0 = np.sum(a_demean ** 2)
    if c0 < 1e-15:
        return [0.0] * max_lag
    result = []
    for lag in range(1, max_lag + 1):
        ck = np.sum(a_demean[:-lag] * a_demean[lag:])
        result.append(float(ck / c0))
    return result


def _mae(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 1.0
    n = min(len(a), len(b))
    return float(np.mean(np.abs(np.array(a[:n]) - np.array(b[:n]))))


def _empty_report() -> dict:
    return {
        "quality": "unknown",
        "score": 0,
        "max_score": 10,
        "diagnostics": ["No paths were generated for validation."],
        "structural": {
            "total_bars": 0, "ohlc_violations": 0,
            "negative_prices": 0, "nan_inf_count": 0,
            "zero_range_bars": 0, "violation_rate": 0.0,
        },
        "statistical": {
            "returns_ks": {"statistic": float("nan"), "p_value": float("nan")},
            "ranges_ks": {"statistic": float("nan"), "p_value": float("nan")},
            "body_pos_ks": {"statistic": float("nan"), "p_value": float("nan")},
            "kurtosis": {"historical": 0, "synthetic": 0, "ratio": 1.0},
            "skewness": {"historical": 0, "synthetic": 0, "difference": 0},
            "tail_frequency": {"historical": 0, "synthetic": 0, "ratio": 1.0},
            "vol_clustering_mae": 0.0,
        },
        "path_level": {
            "n_paths": 0, "degenerate_paths": 0, "extreme_dd_paths": 0,
            "pct_positive_terminal": 0.0, "terminal_price_cv": 0.0,
            "mean_terminal_return": 0.0,
        },
    }
