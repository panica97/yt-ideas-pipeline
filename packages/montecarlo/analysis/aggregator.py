"""
MonteCarloAggregator — collects per-path results and computes
percentile distributions, risk metrics, confidence intervals,
and actual-vs-simulated comparisons.
"""

from __future__ import annotations

import numpy as np
from scipy import stats as sp_stats
from typing import Optional


class MonteCarloAggregator:
    """Accumulates Monte Carlo path results and computes aggregate statistics."""

    def __init__(self) -> None:
        self._metrics: list[dict] = []
        self._equity_curves: list[np.ndarray] = []
        self._close_paths: list[np.ndarray] = []
        self._historical_close: Optional[np.ndarray] = None
        self._shuffle_data: dict | None = None
        self._cached_stats: dict | None = None

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def add_result(
        self,
        metrics: dict,
        equity_curve: Optional[np.ndarray] = None,
        close_prices: Optional[np.ndarray] = None,
    ) -> None:
        """Add a single path's metrics (and optional equity curve / close prices)."""
        self._cached_stats = None
        self._metrics.append(metrics)
        if equity_curve is not None:
            self._equity_curves.append(equity_curve)
        if close_prices is not None:
            self._close_paths.append(close_prices)

    def set_historical_close(self, close_prices: np.ndarray) -> None:
        """Store historical close prices for comparison charts."""
        self._historical_close = close_prices

    def add_shuffle_results(self, shuffle_output: dict) -> None:
        """Ingest output from TradeShuffler.shuffle()."""
        self._cached_stats = None
        self._shuffle_data = shuffle_output

    # ------------------------------------------------------------------
    # Core aggregation
    # ------------------------------------------------------------------

    def compute_statistics(self) -> dict:
        """Compute per-metric percentile distributions, risk metrics,
        bootstrap confidence intervals, and equity curve percentiles.

        Results are cached -- subsequent calls return the same dict
        until new data is added via add_result / add_shuffle_results.
        """
        if self._cached_stats is not None:
            return self._cached_stats
        if self._shuffle_data is not None:
            result = self._compute_shuffle_statistics()
        else:
            result = self._compute_path_statistics()
        self._cached_stats = result
        return result

    def _compute_path_statistics(self) -> dict:
        n = len(self._metrics)
        if n == 0:
            return {"n_paths": 0, "n_completed": 0, "n_failed": 0}

        # Collect per-metric arrays
        metric_keys = [
            "total_pnl", "max_drawdown_pct", "sharpe_ratio", "win_rate",
            "profit_factor", "total_trades", "avg_trade_pnl", "sortino_ratio",
            "expectancy",
        ]

        arrays: dict[str, np.ndarray] = {}
        for key in metric_keys:
            vals = [m.get(key) for m in self._metrics if m.get(key) is not None]
            if vals:
                arrays[key] = np.array(vals, dtype=np.float64)

        # Raw per-path values for histogram and scatter visualizations
        raw = {}
        for key in ["total_pnl", "max_drawdown_pct", "sharpe_ratio", "win_rate", "profit_factor", "total_trades", "avg_trade_pnl"]:
            if key in arrays:
                raw[key] = arrays[key].tolist()

        result: dict = {
            "n_paths": n,
            "n_completed": n,
            "n_failed": 0,
        }

        result["raw_metrics"] = raw

        for key, arr in arrays.items():
            result[key] = self._percentile_summary(arr)

        # Risk metrics (from total_pnl and max_drawdown_pct)
        risk = self._compute_risk_metrics(arrays)

        # Ulcer index from equity curves
        if self._equity_curves:
            all_ulcer = []
            for ec in self._equity_curves:
                running_max = np.maximum.accumulate(ec)
                dd_pct = (ec - running_max) / (running_max + 1e-10)
                all_ulcer.append(float(np.sqrt(np.mean(dd_pct ** 2))))
            risk["ulcer_index"] = float(np.mean(all_ulcer))
        else:
            risk["ulcer_index"] = None

        result["risk_metrics"] = risk

        # Confidence intervals (bootstrap)
        result["confidence_intervals"] = self._compute_confidence_intervals(arrays)

        # Equity curve percentiles + sampled paths
        if self._equity_curves:
            result["equity_curve_percentiles"] = self._compute_equity_percentiles()
            result["drawdown_curve_percentiles"] = self._compute_drawdown_percentiles()
            result["sampled_paths"] = self._sample_equity_curves(max_sample=50)

        # Close price paths for price comparison chart
        if self._close_paths:
            result["sampled_close_paths"] = self._sample_close_paths(max_sample=30)
        if self._historical_close is not None:
            result["historical_close"] = self._historical_close.tolist()

        return result

    def _compute_shuffle_statistics(self) -> dict:
        sd = self._shuffle_data
        eq = sd["equity_curves"]      # (n_paths, n_trades+1)
        mdd = sd["max_drawdowns"]     # (n_paths,)
        fe = sd["final_equities"]     # (n_paths,)
        sr = sd["sharpe_ratios"]      # (n_paths,)

        total_returns = (fe - eq[:, 0]) / (eq[:, 0] + 1e-10)

        result: dict = {
            "n_paths": len(mdd),
            "n_completed": len(mdd),
            "n_failed": 0,
            "total_return": self._percentile_summary(total_returns),
            "max_drawdown": self._percentile_summary(mdd),
            "sharpe_ratio": self._percentile_summary(sr),
            "final_equity": self._percentile_summary(fe),
        }

        # Risk from shuffle
        result["risk_metrics"] = {
            "prob_negative_return": float(np.mean(total_returns < 0)),
            "prob_dd_10": float(np.mean(mdd < -0.10)),
            "prob_dd_20": float(np.mean(mdd < -0.20)),
            "prob_dd_30": float(np.mean(mdd < -0.30)),
            "prob_dd_50": float(np.mean(mdd < -0.50)),
            "var_95": float(np.percentile(total_returns, 5)),
            "cvar_95": float(np.mean(total_returns[total_returns <= np.percentile(total_returns, 5)])) if len(total_returns) > 0 else 0.0,
        }

        # Ulcer index from shuffle equity curves
        running_max = np.maximum.accumulate(eq, axis=1)
        dd_pct = (eq - running_max) / (running_max + 1e-10)
        ulcer_per_path = np.sqrt(np.mean(dd_pct ** 2, axis=1))
        result["risk_metrics"]["ulcer_index"] = float(np.mean(ulcer_per_path))

        # Raw per-path values for histogram visualizations
        result["raw_metrics"] = {
            "total_return": total_returns.tolist(),
            "max_drawdown": mdd.tolist(),
            "sharpe_ratio": sr.tolist(),
        }

        # Equity percentiles
        pcts = [5, 25, 50, 75, 95]
        eq_pcts = {}
        for p in pcts:
            eq_pcts[f"p{p}"] = np.percentile(eq, p, axis=0).tolist()
        result["equity_curve_percentiles"] = eq_pcts

        # Drawdown curve percentiles
        running_max_eq = np.maximum.accumulate(eq, axis=1)
        dd_curves = (eq - running_max_eq) / (running_max_eq + 1e-10) * 100
        dd_pcts = {}
        for p in pcts:
            dd_pcts[f"p{p}"] = np.percentile(dd_curves, p, axis=0).tolist()
        result["drawdown_curve_percentiles"] = dd_pcts

        # Sampled paths for fan chart overlay
        max_sample = min(50, len(eq))
        rng = np.random.default_rng(0)
        idx = rng.choice(len(eq), max_sample, replace=False) if len(eq) > max_sample else np.arange(len(eq))
        result["sampled_paths"] = eq[idx].tolist()

        return result

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    def compare_to_actual(self, actual_metrics: dict) -> dict:
        """Determine where the actual backtest falls in the MC distribution."""
        comparisons: dict = {}

        metric_map = {
            "return_percentile": "total_pnl",
            "drawdown_percentile": "max_drawdown_pct",
            "sharpe_percentile": "sharpe_ratio",
        }

        for label, key in metric_map.items():
            vals = [m.get(key) for m in self._metrics if m.get(key) is not None]
            actual_val = actual_metrics.get(key)
            if vals and actual_val is not None:
                arr = np.array(vals, dtype=np.float64)
                pctile = float(np.mean(arr <= actual_val) * 100)
                comparisons[label] = pctile
            else:
                comparisons[label] = None

        # Shuffle comparison
        if self._shuffle_data is not None and "actual_final_equity" in self._shuffle_data:
            fe = self._shuffle_data["final_equities"]
            actual_fe = self._shuffle_data["actual_final_equity"]
            comparisons["return_percentile"] = float(np.mean(fe <= actual_fe) * 100)

            mdd = self._shuffle_data["max_drawdowns"]
            actual_mdd = self._shuffle_data["actual_max_drawdown"]
            comparisons["drawdown_percentile"] = float(np.mean(mdd <= actual_mdd) * 100)

        # Assessment
        ret_pct = comparisons.get("return_percentile")
        if ret_pct is not None:
            if ret_pct > 90:
                assessment = "lucky"
                overfitting_risk = "high"
            elif ret_pct < 10:
                assessment = "unlucky"
                overfitting_risk = "low"
            else:
                assessment = "typical"
                overfitting_risk = "medium" if ret_pct > 75 else "low"
        else:
            assessment = "unknown"
            overfitting_risk = "unknown"

        comparisons["assessment"] = assessment
        comparisons["overfitting_risk"] = overfitting_risk

        return comparisons

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def to_storage_format(self) -> dict:
        """Convert computed statistics to JSON-safe format."""
        stats = self.compute_statistics()
        return _numpy_to_native(stats)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _percentile_summary(arr: np.ndarray) -> dict:
        if len(arr) == 0:
            return {}
        return {
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
            "median": float(np.median(arr)),
            "p5": float(np.percentile(arr, 5)),
            "p10": float(np.percentile(arr, 10)),
            "p25": float(np.percentile(arr, 25)),
            "p75": float(np.percentile(arr, 75)),
            "p90": float(np.percentile(arr, 90)),
            "p95": float(np.percentile(arr, 95)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "skewness": float(sp_stats.skew(arr)),
            "kurtosis": float(sp_stats.kurtosis(arr)),
        }

    def _compute_risk_metrics(self, arrays: dict[str, np.ndarray]) -> dict:
        risk: dict = {}
        if "total_pnl" in arrays:
            pnl = arrays["total_pnl"]
            risk["prob_negative_return"] = float(np.mean(pnl < 0))
            risk["var_95"] = float(np.percentile(pnl, 5))
            tail = pnl[pnl <= np.percentile(pnl, 5)]
            risk["cvar_95"] = float(np.mean(tail)) if len(tail) > 0 else 0.0

        if "max_drawdown_pct" in arrays:
            # max_drawdown_pct is a positive percentage (e.g. 15.0 = 15%)
            dd = arrays["max_drawdown_pct"]
            risk["prob_dd_10"] = float(np.mean(dd > 10))
            risk["prob_dd_20"] = float(np.mean(dd > 20))
            risk["prob_dd_30"] = float(np.mean(dd > 30))
            risk["prob_dd_50"] = float(np.mean(dd > 50))

        return risk

    def _compute_confidence_intervals(self, arrays: dict[str, np.ndarray]) -> dict:
        ci: dict = {}
        rng = np.random.default_rng(0)
        n_boot = 10_000

        for label, key in [("return_95_ci", "total_pnl"), ("sharpe_95_ci", "sharpe_ratio"), ("drawdown_95_ci", "max_drawdown_pct")]:
            if key in arrays:
                arr = arrays[key]
                # Vectorised bootstrap: sample all indices at once
                indices = rng.integers(0, len(arr), size=(n_boot, len(arr)))
                boot_means = np.mean(arr[indices], axis=1)
                ci[label] = [
                    float(np.percentile(boot_means, 2.5)),
                    float(np.percentile(boot_means, 97.5)),
                ]

        return ci

    def _compute_equity_percentiles(self) -> dict:
        # Pad/truncate to same length
        max_len = max(len(ec) for ec in self._equity_curves)
        padded = np.full((len(self._equity_curves), max_len), np.nan)
        for i, ec in enumerate(self._equity_curves):
            padded[i, : len(ec)] = ec

        pcts = [5, 25, 50, 75, 95]
        result = {}
        for p in pcts:
            result[f"p{p}"] = np.nanpercentile(padded, p, axis=0).tolist()
        return result

    def _compute_drawdown_percentiles(self) -> dict:
        """Compute running drawdown percentage percentiles across all equity curves."""
        max_len = max(len(ec) for ec in self._equity_curves)
        padded = np.full((len(self._equity_curves), max_len), np.nan)
        for i, ec in enumerate(self._equity_curves):
            padded[i, : len(ec)] = ec

        # Compute running max drawdown percentage for each path
        running_max = np.fmax.accumulate(padded, axis=1)
        dd_pct = (padded - running_max) / (running_max + 1e-10) * 100

        pcts = [5, 25, 50, 75, 95]
        result = {}
        for p in pcts:
            result[f"p{p}"] = np.nanpercentile(dd_pct, p, axis=0).tolist()
        return result

    def _sample_equity_curves(self, max_sample: int = 50) -> list:
        """Return a random sample of equity curves for fan chart background."""
        n = len(self._equity_curves)
        if n == 0:
            return []
        rng = np.random.default_rng(0)
        idx = rng.choice(n, min(max_sample, n), replace=False) if n > max_sample else range(n)
        return [self._equity_curves[i].tolist() for i in idx]

    def _sample_close_paths(self, max_sample: int = 30) -> list:
        """Return a random sample of synthetic close price paths."""
        n = len(self._close_paths)
        if n == 0:
            return []
        rng = np.random.default_rng(1)  # different seed from equity sampler
        idx = rng.choice(n, min(max_sample, n), replace=False) if n > max_sample else range(n)
        return [self._close_paths[i].tolist() for i in idx]


def _numpy_to_native(obj):
    """Recursively convert numpy types to Python native for JSON serialisation."""
    if isinstance(obj, dict):
        return {k: _numpy_to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_numpy_to_native(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj
