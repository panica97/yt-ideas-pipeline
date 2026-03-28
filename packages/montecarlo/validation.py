"""Validation utilities for OHLC data and model quality.

Enhanced tests:
- OHLC integrity
- KS tests (returns, ranges, body position)
- Kurtosis comparison
- Skewness comparison
- Leverage effect test (asymmetric vol response)
- Jump detection test (tail frequency beyond 3 sigma)
- Volatility clustering (multi-lag autocorrelation + fit test)
- Regime consistency test
- Weighted quality scoring with diagnostics
"""

from __future__ import annotations

import numpy as np
import polars as pl
from scipy import stats

from .config import MonteCarloConfig


def validate_ohlc(df: pl.DataFrame, tolerance: float = 1e-6) -> dict:
    """Check OHLC consistency: H >= O, H >= C, L <= O, L <= C.

    Returns dict with total, valid, violations, details.
    """
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    c = df["close"].to_numpy()

    h_ge_o = h >= o - tolerance
    h_ge_c = h >= c - tolerance
    l_le_o = lo <= o + tolerance
    l_le_c = lo <= c + tolerance
    all_valid = h_ge_o & h_ge_c & l_le_o & l_le_c

    return {
        "total": len(df),
        "valid": bool(np.all(all_valid)),
        "violations": int(np.sum(~all_valid)),
        "details": {
            "high_ge_open_violations": int(np.sum(~h_ge_o)),
            "high_ge_close_violations": int(np.sum(~h_ge_c)),
            "low_le_open_violations": int(np.sum(~l_le_o)),
            "low_le_close_violations": int(np.sum(~l_le_c)),
        },
    }


def validate_model_fit(
    generator,
    historical_df: pl.DataFrame,
    n_test_paths: int = 50,
) -> dict:
    """Generate test paths and compare statistical properties to historical data.

    Uses weighted scoring system:
      - KS returns:       weight 3
      - Kurtosis ratio:   weight 3
      - KS ranges:        weight 2
      - Vol clustering:   weight 2
      - KS body position: weight 1
      - ATR ratio:        weight 1
      - Regime consistency: weight 1
      - Skewness:         weight 1
      - Leverage effect:  weight 1

    Total possible score = 15.  good >= 12, acceptable >= 8, poor < 8.
    """
    hist_closes = historical_df["close"].to_numpy().astype(np.float64)
    hist_returns = np.diff(hist_closes) / hist_closes[:-1]
    hist_highs = historical_df["high"].to_numpy().astype(np.float64)
    hist_lows = historical_df["low"].to_numpy().astype(np.float64)
    hist_ranges = (hist_highs[1:] - hist_lows[1:]) / (hist_closes[1:] + 1e-10)

    # Generate test paths through the full pipeline (regime switching +
    # variance targeting) so the validation measures the actual output.
    n_periods = len(hist_returns)
    synth_returns_all = []
    synth_ranges_all = []
    synth_body_pos_all = []

    base_tf = generator.base_timeframe
    for batch in generator.generate_paths(
        n_paths=n_test_paths,
        n_periods=n_periods,
        strategy_timeframes=[base_tf],
        seed=42,
        batch_size=n_test_paths,
    ):
        for path_dict in batch:
            df = path_dict[base_tf]
            c = df["close"].to_numpy().astype(np.float64)
            h = df["high"].to_numpy().astype(np.float64)
            lo = df["low"].to_numpy().astype(np.float64)

            rets = np.diff(c) / c[:-1]
            synth_returns_all.extend(rets.tolist())

            path_ranges = (h[1:] - lo[1:]) / (c[1:] + 1e-10)
            synth_ranges_all.extend(path_ranges.tolist())

            body_pos = (c - lo) / (h - lo + 1e-10)
            valid_bp = body_pos[(body_pos >= 0) & (body_pos <= 1)]
            synth_body_pos_all.extend(valid_bp.tolist())

    synth_returns_arr = np.array(synth_returns_all)
    synth_ranges_arr = np.array(synth_ranges_all)

    # Filter NaN/Inf values that can arise from extreme GARCH paths
    synth_returns_arr = synth_returns_arr[np.isfinite(synth_returns_arr)]
    synth_ranges_arr = synth_ranges_arr[np.isfinite(synth_ranges_arr)]

    # KS tests (guard against empty arrays)
    if len(synth_returns_arr) > 0 and len(hist_returns) > 0:
        ks_returns = stats.ks_2samp(hist_returns, synth_returns_arr)
    else:
        ks_returns = type('KS', (), {'statistic': float('nan'), 'pvalue': float('nan')})()
    if len(synth_ranges_arr) > 0 and len(hist_ranges) > 0:
        ks_ranges = stats.ks_2samp(hist_ranges, synth_ranges_arr)
    else:
        ks_ranges = type('KS', (), {'statistic': float('nan'), 'pvalue': float('nan')})()

    # Body position KS test
    hist_body_pos = (hist_closes[1:] - hist_lows[1:]) / (hist_highs[1:] - hist_lows[1:] + 1e-10)
    hist_body_pos = hist_body_pos[(hist_body_pos >= 0) & (hist_body_pos <= 1)]
    synth_body_pos_arr = np.array(synth_body_pos_all)
    synth_body_pos_arr = synth_body_pos_arr[np.isfinite(synth_body_pos_arr)]
    if len(synth_body_pos_arr) > 0 and len(hist_body_pos) > 0:
        ks_body = stats.ks_2samp(hist_body_pos, synth_body_pos_arr)
    else:
        ks_body = type('KS', (), {'statistic': float('nan'), 'pvalue': float('nan')})()

    # Fat tails / kurtosis comparison (excess kurtosis)
    from scipy.stats import kurtosis as _kurtosis, skew as _skew
    hist_kurt = float(_kurtosis(hist_returns, fisher=True))
    synth_kurt = float(_kurtosis(synth_returns_arr, fisher=True)) if len(synth_returns_arr) > 0 else 0.0
    kurtosis_ratio = synth_kurt / hist_kurt if abs(hist_kurt) > 0.01 else 1.0

    # Skewness comparison
    hist_skew = float(_skew(hist_returns))
    synth_skew = float(_skew(synth_returns_arr)) if len(synth_returns_arr) > 0 else 0.0
    skewness_diff = abs(synth_skew - hist_skew)

    # Leverage effect test
    leverage_test = _test_leverage_effect(hist_returns, synth_returns_arr)

    # Jump detection test
    jump_test = _test_jump_frequency(hist_returns, synth_returns_arr)

    # Multi-lag volatility clustering
    hist_vol_cluster = _autocorr_abs_multi(hist_returns, 10)
    synth_vol_cluster = _autocorr_abs_multi(synth_returns_arr, 10)

    # Vol clustering fit: mean absolute error across lags
    vol_cluster_mae = _vol_clustering_mae(hist_vol_cluster, synth_vol_cluster)

    # ATR comparison
    hist_mean_range = float(np.mean(hist_ranges))
    synth_mean_range = float(np.mean(synth_ranges_arr)) if len(synth_ranges_arr) > 0 else 0.0
    atr_ratio = synth_mean_range / hist_mean_range if hist_mean_range > 0 else 1.0

    # Anderson-Darling test (diagnostic only — more tail-sensitive than KS)
    ad_test = _test_anderson_darling(hist_returns, synth_returns_arr)

    # Regime consistency test
    regime_test = _test_regime_consistency(hist_returns, synth_returns_arr)

    # ------------------------------------------------------------------
    # Weighted quality scoring with diagnostics
    # ------------------------------------------------------------------
    threshold = MonteCarloConfig.KS_TEST_THRESHOLD
    ks_practical = MonteCarloConfig.KS_PRACTICAL_THRESHOLD
    diagnostics = []
    score = 0
    max_score = 15  # sum of all weights

    def _ks_passes(pval: float, stat: float) -> bool:
        """KS test passes if p-value is above threshold OR the KS statistic
        is below the practical significance threshold.  With large samples
        (50K+ returns), even trivially small distribution differences produce
        p < 0.05 while the KS statistic shows the CDFs agree to within a
        few percent.  Standard simulation-validation practice is to use the
        statistic with a practical significance cutoff."""
        if np.isnan(pval) or np.isnan(stat):
            return False
        # Classical p-value test (dominant for small samples)
        if pval >= threshold:
            return True
        # Practical significance: CDFs agree within ks_practical at every point
        return stat < ks_practical

    # Returns KS (weight 3)
    if _ks_passes(ks_returns.pvalue, ks_returns.statistic):
        score += 3
    else:
        diagnostics.append(
            f"Returns KS failed (p={ks_returns.pvalue:.4f}, D={ks_returns.statistic:.4f}): "
            f"synthetic return distribution differs significantly from historical."
        )

    # Kurtosis ratio (weight 3)
    if not (np.isnan(kurtosis_ratio) or kurtosis_ratio < 0.5 or kurtosis_ratio > 2.0):
        score += 3
    else:
        diagnostics.append(
            f"Kurtosis ratio {kurtosis_ratio:.2f} outside [0.5, 2.0]: "
            f"synthetic has {'more' if kurtosis_ratio > 1 else 'fewer'} "
            f"extreme moves than historical "
            f"(hist={hist_kurt:.1f}, synth={synth_kurt:.1f})."
        )

    # Ranges KS (weight 2)
    if _ks_passes(ks_ranges.pvalue, ks_ranges.statistic):
        score += 2
    else:
        diagnostics.append(
            f"Ranges KS failed (p={ks_ranges.pvalue:.2e}, D={ks_ranges.statistic:.4f}): "
            f"candle range distribution mismatch (ATR ratio={atr_ratio:.3f})."
        )

    # Vol clustering fit (weight 2)
    # Adaptive threshold: longer data has more structural breaks, making
    # exact autocorrelation matching harder.  Scale mildly above 1000 bars.
    n_hist_bars = len(hist_returns)
    vol_mae_thresh = MonteCarloConfig.VOL_CLUSTERING_MAE_THRESHOLD
    if n_hist_bars > 1000:
        vol_mae_thresh += 0.025 * np.log2(n_hist_bars / 1000.0)
    if vol_cluster_mae <= vol_mae_thresh:
        score += 2
    else:
        diagnostics.append(
            f"Vol clustering MAE={vol_cluster_mae:.3f} > {vol_mae_thresh:.3f}: "
            f"synthetic does not reproduce the historical autocorrelation "
            f"structure of |returns|."
        )

    # Body position KS (weight 1)
    if _ks_passes(ks_body.pvalue, ks_body.statistic):
        score += 1
    else:
        diagnostics.append(
            f"Body position KS failed (p={ks_body.pvalue:.2e}, D={ks_body.statistic:.4f}): "
            f"candle body placement distribution differs."
        )

    # ATR ratio (weight 1)
    if not (np.isnan(atr_ratio) or abs(atr_ratio - 1.0) > 0.3):
        score += 1
    else:
        diagnostics.append(
            f"ATR ratio {atr_ratio:.3f}: synthetic ranges "
            f"{'wider' if atr_ratio > 1 else 'narrower'} than historical "
            f"(>30% deviation)."
        )

    # Regime consistency (weight 1)
    disp_ratio = regime_test.get("dispersion_ratio", 1.0)
    if 0.5 < disp_ratio < 2.0:
        score += 1
    else:
        diagnostics.append(
            f"Regime consistency ratio {disp_ratio:.2f}: synthetic vol "
            f"dispersion doesn't match historical regime patterns."
        )

    # Skewness (weight 1)
    if not (np.isnan(skewness_diff) or skewness_diff > 1.0):
        score += 1
    else:
        diagnostics.append(
            f"Skewness mismatch: diff={skewness_diff:.2f} "
            f"(hist={hist_skew:.3f}, synth={synth_skew:.3f})."
        )

    # Leverage effect (weight 1)
    if not leverage_test["mismatch"]:
        score += 1
    else:
        diagnostics.append(
            f"Leverage effect sign mismatch: historical={leverage_test['historical_leverage']:.3f}, "
            f"synthetic={leverage_test['synthetic_leverage']:.3f}."
        )

    # Rating from weighted score
    if score >= 12:
        rating = "good"
    elif score >= 8:
        rating = "acceptable"
    else:
        rating = "poor"

    # Legacy issue count for backward compatibility
    n_issues = max_score - score

    # Subsample synthetic for frontend histograms
    max_sample = 2000
    if len(synth_returns_arr) > max_sample:
        rng_sub = np.random.default_rng(0)
        synth_ret_sample = rng_sub.choice(synth_returns_arr, max_sample, replace=False)
    else:
        synth_ret_sample = synth_returns_arr

    if len(synth_ranges_arr) > max_sample:
        rng_sub2 = np.random.default_rng(1)
        synth_rng_sample = rng_sub2.choice(synth_ranges_arr, max_sample, replace=False)
    else:
        synth_rng_sample = synth_ranges_arr

    # QQ plot: historical returns vs normal distribution
    sorted_hist = np.sort(hist_returns)
    n_qq = len(sorted_hist)
    theoretical_quantiles = stats.norm.ppf(np.linspace(0.01, 0.99, n_qq))

    return {
        "overall_quality": rating,
        "quality_score": score,
        "max_score": max_score,
        "n_issues": n_issues,
        "diagnostics": diagnostics,
        "returns_ks": {
            "statistic": float(ks_returns.statistic),
            "p_value": float(ks_returns.pvalue),
        },
        "ranges_ks": {
            "statistic": float(ks_ranges.statistic),
            "p_value": float(ks_ranges.pvalue),
        },
        "body_pos_ks": {
            "statistic": float(ks_body.statistic),
            "p_value": float(ks_body.pvalue),
        },
        "kurtosis": {
            "historical": hist_kurt,
            "synthetic": synth_kurt,
            "ratio": kurtosis_ratio,
        },
        "skewness": {
            "historical": hist_skew,
            "synthetic": synth_skew,
            "difference": skewness_diff,
        },
        "leverage_effect": leverage_test,
        "jump_test": jump_test,
        "anderson_darling": ad_test,
        "regime_consistency": regime_test,
        "vol_clustering": {
            "lags": list(range(1, 11)),
            "historical": hist_vol_cluster,
            "synthetic": synth_vol_cluster,
            "mae": vol_cluster_mae,
        },
        "distributions": {
            "returns": {
                "historical": hist_returns.tolist(),
                "synthetic": synth_ret_sample.tolist(),
            },
            "ranges": {
                "historical": hist_ranges.tolist(),
                "synthetic": synth_rng_sample.tolist(),
            },
        },
        "qq_plot": {
            "theoretical": theoretical_quantiles.tolist(),
            "sample": sorted_hist.tolist(),
        },
        "atr_ratio": atr_ratio,
    }


# ======================================================================
# Internal test functions
# ======================================================================

def _autocorr_abs_multi(arr: np.ndarray, max_lag: int = 10) -> list:
    """Multi-lag autocorrelation of |returns|."""
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


def _vol_clustering_mae(
    hist_autocorr: list,
    synth_autocorr: list,
) -> float:
    """Mean absolute error between historical and synthetic vol autocorrelation."""
    if not hist_autocorr or not synth_autocorr:
        return 1.0
    n = min(len(hist_autocorr), len(synth_autocorr))
    h = np.array(hist_autocorr[:n])
    s = np.array(synth_autocorr[:n])
    return float(np.mean(np.abs(h - s)))


def _test_leverage_effect(
    hist_returns: np.ndarray,
    synth_returns: np.ndarray,
) -> dict:
    """Test leverage effect: negative returns should predict higher future volatility.

    Computes correlation between r_t and r_{t+1}^2 for both historical and
    synthetic (Bouchaud et al., 2001).  The squared formulation is more
    sensitive to the asymmetric volatility response than |r_{t+1}|.
    Markets typically show negative correlation (leverage effect).
    """
    def _leverage_corr(r: np.ndarray) -> float:
        if len(r) < 20:
            return 0.0
        corr = np.corrcoef(r[:-1], r[1:] ** 2)[0, 1]
        return float(corr) if np.isfinite(corr) else 0.0

    hist_lev = _leverage_corr(hist_returns)
    synth_lev = _leverage_corr(synth_returns)

    # Mismatch if historical has negative leverage but synthetic doesn't
    mismatch = (hist_lev < -0.05 and synth_lev > 0.05)

    return {
        "historical_leverage": hist_lev,
        "synthetic_leverage": synth_lev,
        "mismatch": mismatch,
        "description": (
            "Leverage effect: correlation between r_t and r_{t+1}^2 "
            "(Bouchaud et al., 2001). Negative values indicate that negative "
            "returns predict higher future volatility (typical in equity/futures "
            "markets)."
        ),
    }


def _test_jump_frequency(
    hist_returns: np.ndarray,
    synth_returns: np.ndarray,
    threshold_sigma: float = 3.0,
) -> dict:
    """Compare tail frequency: fraction of returns beyond threshold_sigma standard deviations.

    Tests whether the model captures extreme events (jumps).
    """
    def _tail_freq(r: np.ndarray, threshold: float) -> float:
        if len(r) < 10:
            return 0.0
        sigma = np.std(r)
        return float(np.mean(np.abs(r - np.mean(r)) > threshold * sigma))

    hist_freq = _tail_freq(hist_returns, threshold_sigma)
    synth_freq = _tail_freq(synth_returns, threshold_sigma)

    ratio = synth_freq / hist_freq if hist_freq > 0.001 else 1.0

    return {
        "historical_tail_freq": hist_freq,
        "synthetic_tail_freq": synth_freq,
        "ratio": ratio,
        "threshold_sigma": threshold_sigma,
        "description": (
            f"Fraction of returns beyond {threshold_sigma} sigma. "
            f"Ratio near 1.0 means synthetic captures extreme events well."
        ),
    }


def _test_regime_consistency(
    hist_returns: np.ndarray,
    synth_returns: np.ndarray,
    window: int = 20,
) -> dict:
    """Test whether synthetic data shows regime-like volatility clustering.

    Compares the distribution of rolling volatility between historical and synthetic.
    Markets show distinct vol regimes; good synthetic data should too.
    """
    def _rolling_vol_stats(r: np.ndarray, w: int) -> dict:
        if len(r) < w + 10:
            return {"mean": 0.0, "std": 0.0, "ratio_high_low": 1.0}
        rolling = np.array([np.std(r[i:i + w]) for i in range(len(r) - w)])
        q25 = np.percentile(rolling, 25)
        q75 = np.percentile(rolling, 75)
        ratio = q75 / q25 if q25 > 1e-10 else 1.0
        return {
            "mean": float(np.mean(rolling)),
            "std": float(np.std(rolling)),
            "ratio_high_low": float(ratio),
        }

    hist_stats = _rolling_vol_stats(hist_returns, window)
    synth_stats = _rolling_vol_stats(synth_returns, window)

    # Regime dispersion ratio: how much vol varies over time
    hist_disp = hist_stats["ratio_high_low"]
    synth_disp = synth_stats["ratio_high_low"]
    disp_ratio = synth_disp / hist_disp if hist_disp > 0.01 else 1.0

    return {
        "historical": hist_stats,
        "synthetic": synth_stats,
        "dispersion_ratio": disp_ratio,
        "description": (
            "Volatility dispersion ratio (Q75/Q25 of rolling vol). "
            "Higher values indicate distinct vol regimes. "
            "Ratio near 1.0 means synthetic matches historical regime patterns."
        ),
    }


def _test_anderson_darling(
    hist_returns: np.ndarray,
    synth_returns: np.ndarray,
    max_sample: int = 5000,
) -> dict:
    """Anderson-Darling k-sample test comparing return distributions.

    AD is more sensitive to tail differences than KS.  Reported as a
    diagnostic (not part of the quality score) so we can evaluate its
    usefulness before integrating into scoring.

    Large samples make AD overpowered (always rejects), so we subsample
    to *max_sample* per group for a meaningful statistic.
    """
    if len(hist_returns) < 20 or len(synth_returns) < 20:
        return {"statistic": float("nan"), "significance_level": float("nan"),
                "p_approx": float("nan"),
                "description": "Insufficient data for Anderson-Darling test."}

    # Subsample for tractable computation and meaningful p-values
    rng = np.random.default_rng(42)
    h = hist_returns if len(hist_returns) <= max_sample else rng.choice(hist_returns, max_sample, replace=False)
    s = synth_returns if len(synth_returns) <= max_sample else rng.choice(synth_returns, max_sample, replace=False)

    try:
        result = stats.anderson_ksamp([h, s])
        return {
            "statistic": float(result.statistic),
            "significance_level": float(result.significance_level),
            "p_approx": float(result.pvalue) if hasattr(result, 'pvalue') else float(result.significance_level),
            "description": (
                "Anderson-Darling k-sample test (tail-sensitive). "
                "Lower significance_level means distributions differ more. "
                "Subsampled to 5000 per group for meaningful p-values."
            ),
        }
    except Exception:
        return {"statistic": float("nan"), "significance_level": float("nan"),
                "p_approx": float("nan"),
                "description": "Anderson-Darling test failed."}


def validate_sufficient_data(
    df: pl.DataFrame,
    min_candles: int = 250,
) -> dict:
    """Check whether historical data is sufficient for reliable model fitting."""
    n = len(df)
    return {
        "sufficient": n >= min_candles,
        "n_candles": n,
        "min_required": min_candles,
    }
