"""Statistical tests for strategy significance and distribution comparison."""

from __future__ import annotations

import numpy as np
from scipy import stats as sp_stats


def test_strategy_significance(pnls: np.ndarray) -> dict:
    """T-test: is the mean trade PnL significantly different from zero?

    Returns t_statistic, p_value, is_significant_95, is_significant_99,
    n_trades, mean_pnl, std_pnl.
    """
    n = len(pnls)
    mean_pnl = float(np.mean(pnls))
    std_pnl = float(np.std(pnls, ddof=1)) if n > 1 else 0.0

    if std_pnl < 1e-15 or n < 2:
        return {
            "t_statistic": 0.0,
            "p_value": 1.0,
            "is_significant_95": False,
            "is_significant_99": False,
            "n_trades": n,
            "mean_pnl": mean_pnl,
            "std_pnl": std_pnl,
            "required_trades_95": None,
        }

    t_stat = mean_pnl / (std_pnl / np.sqrt(n))
    p_value = float(2.0 * sp_stats.t.sf(abs(t_stat), df=n - 1))

    required_trades_95 = ((1.96 * std_pnl / mean_pnl) ** 2) if mean_pnl != 0 else None

    return {
        "t_statistic": float(t_stat),
        "p_value": p_value,
        "is_significant_95": p_value < 0.05,
        "is_significant_99": p_value < 0.01,
        "n_trades": n,
        "mean_pnl": mean_pnl,
        "std_pnl": std_pnl,
        "required_trades_95": float(required_trades_95) if required_trades_95 is not None else None,
    }


def permutation_test(
    pnls: np.ndarray,
    n_permutations: int = 10_000,
    seed: int | None = None,
) -> dict:
    """Non-parametric permutation test for strategy significance.

    Randomly flips signs of PnLs to build a null distribution, then
    computes what fraction of random totals exceed the actual total.
    """
    rng = np.random.default_rng(seed)
    actual_total = float(np.sum(pnls))
    abs_pnls = np.abs(pnls)
    n = len(pnls)

    # Vectorised: (n_permutations, n) matrix of random signs
    signs = rng.choice([-1.0, 1.0], size=(n_permutations, n))
    random_totals = np.sum(signs * abs_pnls, axis=1)

    p_value = float(np.mean(random_totals >= actual_total))

    return {
        "p_value": p_value,
        "actual_total": actual_total,
        "random_mean": float(np.mean(random_totals)),
        "random_std": float(np.std(random_totals)),
    }


def compare_distributions(
    historical: np.ndarray,
    synthetic: np.ndarray,
) -> dict:
    """KS test + moment comparison between historical and synthetic data."""
    ks_result = sp_stats.ks_2samp(historical, synthetic)

    return {
        "ks_statistic": float(ks_result.statistic),
        "ks_p_value": float(ks_result.pvalue),
        "mean_diff": float(np.mean(synthetic) - np.mean(historical)),
        "std_diff": float(np.std(synthetic) - np.std(historical)),
        "skew_diff": float(sp_stats.skew(synthetic) - sp_stats.skew(historical)),
        "kurtosis_diff": float(sp_stats.kurtosis(synthetic) - sp_stats.kurtosis(historical)),
    }


def kelly_criterion(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
) -> dict:
    """Kelly criterion for optimal position sizing.

    Parameters
    ----------
    win_rate : probability of winning trade (0-1)
    avg_win  : average winning trade PnL (positive)
    avg_loss : average losing trade PnL (positive magnitude)

    Returns
    -------
    dict with kelly_fraction, half_kelly
    """
    if avg_loss <= 0 or avg_win <= 0:
        return {"kelly_fraction": 0.0, "half_kelly": 0.0, "edge": 0.0}

    b = avg_win / avg_loss
    q = 1.0 - win_rate
    kelly = win_rate - q / b

    edge = win_rate * avg_win - (1.0 - win_rate) * avg_loss

    return {
        "kelly_fraction": float(kelly),
        "half_kelly": float(kelly / 2.0),
        "edge": float(edge),
    }
