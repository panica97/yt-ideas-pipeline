"""
Portfolio Metrics Calculation

Provides PortfolioMetricsCalculator for calculating portfolio-level risk and performance
metrics from equity curve and multi-strategy trade data.

Key metrics:
- Sharpe ratio (annualized)
- Max drawdown (absolute and percentage)
- Aggregate statistics across all strategies
- Correlation matrix between strategies
"""

from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, List, Tuple, Optional

import numpy as np

from engine._11_portfolio_state import EquitySnapshot


@dataclass
class PortfolioMetrics:
    """
    Portfolio-level performance metrics.

    Computed from equity curve and aggregated trades across all strategies.
    """
    sharpe_ratio: float
    max_drawdown: float  # Absolute dollars
    max_drawdown_pct: float  # Percentage
    total_pnl: float
    total_return_pct: float
    total_trades: int
    win_rate: float
    winning_trades: int
    losing_trades: int
    profit_factor: float  # Gross Profit / Gross Loss
    correlation_matrix: Dict[str, Dict[str, float]]
    # Loss correlation fields
    loss_correlation_matrix: Dict[str, Dict[str, float]]  # Correlation of losses only
    concurrent_loss_days: int  # Days where 2+ strategies lost
    max_concurrent_losses: int  # Max strategies losing same day


class PortfolioMetricsCalculator:
    """
    Calculates portfolio-level metrics from equity curve and strategy trades.

    Usage:
        calculator = PortfolioMetricsCalculator(
            equity_curve=portfolio_state.equity_curve,
            strategy_trades={1001: trades_1, 1002: trades_2},
            initial_equity=100000,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31)
        )
        metrics = calculator.calculate()
    """

    def __init__(
        self,
        equity_curve: List[EquitySnapshot],
        strategy_trades: Dict[int, List[Dict]],
        initial_equity: float,
        start_date: datetime,
        end_date: datetime
    ):
        """
        Args:
            equity_curve: List of EquitySnapshot from portfolio backtest
            strategy_trades: Dict mapping strategy_id to list of trade dicts
            initial_equity: Starting portfolio equity
            start_date: Backtest start date
            end_date: Backtest end date
        """
        self.equity_curve = equity_curve
        self.strategy_trades = strategy_trades
        self.initial_equity = initial_equity
        self.start_date = start_date
        self.end_date = end_date

    def calculate(self) -> PortfolioMetrics:
        """
        Calculate all portfolio-level metrics.

        Returns:
            PortfolioMetrics dataclass with all computed values
        """
        sharpe = self._calculate_sharpe_ratio()
        max_dd, max_dd_pct = self._calculate_max_drawdown()
        agg_stats = self._calculate_aggregate_stats()
        correlation = self._calculate_correlation_matrix()
        loss_correlation = self._calculate_loss_correlation_matrix()
        concurrent_loss_days, max_concurrent_losses = self._calculate_concurrent_loss_stats()

        # Calculate total return percentage
        final_equity = self.equity_curve[-1].equity if self.equity_curve else self.initial_equity
        total_return_pct = ((final_equity - self.initial_equity) / self.initial_equity) * 100 if self.initial_equity > 0 else 0.0

        return PortfolioMetrics(
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            total_pnl=agg_stats['total_pnl'],
            total_return_pct=total_return_pct,
            total_trades=agg_stats['total_trades'],
            win_rate=agg_stats['win_rate'],
            winning_trades=agg_stats['winning_trades'],
            losing_trades=agg_stats['losing_trades'],
            profit_factor=agg_stats['profit_factor'],
            correlation_matrix=correlation,
            loss_correlation_matrix=loss_correlation,
            concurrent_loss_days=concurrent_loss_days,
            max_concurrent_losses=max_concurrent_losses
        )

    def _calculate_sharpe_ratio(self) -> float:
        """
        Calculate annualized Sharpe ratio from equity curve.

        Uses percentage returns between snapshots and auto-detects
        periods per year from actual timestamp data.

        Returns:
            Annualized Sharpe ratio, or 0.0 if insufficient data
        """
        # Need at least 3 snapshots to get 2 returns for sample std (ddof=1)
        if len(self.equity_curve) < 3:
            return 0.0

        # Extract equity values
        equities = np.array([snap.equity for snap in self.equity_curve])

        # Calculate percentage returns
        returns = np.diff(equities) / equities[:-1]

        # Guard against insufficient returns for sample std
        if len(returns) < 2:
            return 0.0

        std_returns = np.std(returns, ddof=1)  # Sample std
        if std_returns == 0:
            return 0.0

        mean_return = np.mean(returns)

        # Auto-detect periods per year from timestamps
        periods_per_year = self._estimate_periods_per_year()

        # Annualize: sharpe * sqrt(periods_per_year)
        sharpe = (mean_return / std_returns) * np.sqrt(periods_per_year)

        return float(sharpe)

    def _estimate_periods_per_year(self) -> float:
        """
        Estimate periods per year from equity curve timestamps.

        Counts bars in equity curve and divides by years in backtest.

        Returns:
            Estimated periods per year (minimum 1.0)
        """
        if len(self.equity_curve) < 2:
            return 252.0  # Default to daily

        # Calculate years in backtest
        days_in_backtest = (self.end_date - self.start_date).days
        if days_in_backtest <= 0:
            return 252.0

        years_in_backtest = days_in_backtest / 365.25
        if years_in_backtest <= 0:
            return 252.0

        # Periods per year = number of bars / years
        periods_per_year = len(self.equity_curve) / years_in_backtest

        return max(1.0, periods_per_year)

    def _calculate_max_drawdown(self) -> Tuple[float, float]:
        """
        Calculate maximum drawdown from equity curve.

        Uses running maximum (peak) to find largest peak-to-trough decline.

        Returns:
            Tuple of (max_drawdown_dollars, max_drawdown_pct)
        """
        if len(self.equity_curve) < 1:
            return 0.0, 0.0

        equities = np.array([snap.equity for snap in self.equity_curve])

        if len(equities) == 1:
            return 0.0, 0.0

        # Calculate running peak
        running_max = np.maximum.accumulate(equities)

        # Calculate drawdowns
        drawdowns = running_max - equities

        # Find max drawdown
        max_dd_idx = np.argmax(drawdowns)
        max_dd = float(drawdowns[max_dd_idx])

        # Calculate percentage based on peak at that point
        peak_at_max_dd = running_max[max_dd_idx]
        max_dd_pct = (max_dd / peak_at_max_dd) * 100 if peak_at_max_dd > 0 else 0.0

        return max_dd, max_dd_pct

    def _calculate_aggregate_stats(self) -> Dict:
        """
        Calculate aggregate statistics across all strategies.

        Flattens all trades from strategy_trades and computes totals.

        Returns:
            Dict with total_trades, total_pnl, win_rate, winning_trades, losing_trades
        """
        # Flatten all trades
        all_trades = []
        for strategy_id, trades in self.strategy_trades.items():
            all_trades.extend(trades)

        if not all_trades:
            return {
                'total_trades': 0,
                'total_pnl': 0.0,
                'win_rate': 0.0,
                'winning_trades': 0,
                'losing_trades': 0,
                'profit_factor': 0.0
            }

        # Calculate stats
        pnl_values = [t.get('pnl', 0) for t in all_trades]
        total_pnl = sum(pnl_values)
        winning_trades = sum(1 for pnl in pnl_values if pnl > 0)
        losing_trades = sum(1 for pnl in pnl_values if pnl < 0)
        total_trades = len(all_trades)
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0.0

        # Calculate profit factor: Gross Profit / Gross Loss
        gross_profit = sum(pnl for pnl in pnl_values if pnl > 0)
        gross_loss = abs(sum(pnl for pnl in pnl_values if pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

        return {
            'total_trades': total_trades,
            'total_pnl': total_pnl,
            'win_rate': win_rate,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'profit_factor': profit_factor
        }

    def _calculate_correlation_matrix(self) -> Dict[str, Dict[str, float]]:
        """
        Calculate pairwise correlation matrix between strategies.

        Groups trades by exit date to build daily PnL series per strategy,
        then computes correlation coefficients.

        Returns:
            Nested dict: {"strat_1001": {"strat_1001": 1.0, "strat_1002": 0.5, ...}, ...}
            Returns empty dict if fewer than 2 strategies
        """
        strategy_ids = list(self.strategy_trades.keys())

        if len(strategy_ids) < 2:
            return {}

        # Build daily PnL per strategy
        daily_pnl: Dict[int, Dict[date, float]] = {}
        all_dates: set = set()

        for strategy_id, trades in self.strategy_trades.items():
            daily_pnl[strategy_id] = {}
            for trade in trades:
                exit_dt = trade.get('exit_date')
                if exit_dt is None:
                    continue

                # Handle both datetime and date types
                if isinstance(exit_dt, datetime):
                    exit_d = exit_dt.date()
                elif isinstance(exit_dt, date):
                    exit_d = exit_dt
                else:
                    continue

                pnl = trade.get('pnl', 0)
                daily_pnl[strategy_id][exit_d] = daily_pnl[strategy_id].get(exit_d, 0) + pnl
                all_dates.add(exit_d)

        if not all_dates:
            return {}

        # Align to common date set (sorted)
        sorted_dates = sorted(all_dates)

        # Build PnL arrays for each strategy (0 for dates with no trades)
        pnl_arrays: Dict[int, np.ndarray] = {}
        for strategy_id in strategy_ids:
            pnl_series = [daily_pnl[strategy_id].get(d, 0.0) for d in sorted_dates]
            pnl_arrays[strategy_id] = np.array(pnl_series)

        # Calculate correlation matrix
        correlation_matrix: Dict[str, Dict[str, float]] = {}

        for i, strat_i in enumerate(strategy_ids):
            key_i = f"strat_{strat_i}"
            correlation_matrix[key_i] = {}

            for j, strat_j in enumerate(strategy_ids):
                key_j = f"strat_{strat_j}"

                if i == j:
                    correlation_matrix[key_i][key_j] = 1.0
                else:
                    arr_i = pnl_arrays[strat_i]
                    arr_j = pnl_arrays[strat_j]

                    # Use np.corrcoef to calculate correlation
                    # Handle NaN (return 0.0)
                    if len(arr_i) < 2:
                        corr = 0.0
                    else:
                        corr_matrix = np.corrcoef(arr_i, arr_j)
                        corr = corr_matrix[0, 1]
                        if np.isnan(corr):
                            corr = 0.0

                    correlation_matrix[key_i][key_j] = float(corr)

        return correlation_matrix

    def _calculate_loss_correlation_matrix(self) -> Dict[str, Dict[str, float]]:
        """
        Calculate pairwise correlation matrix using only losing trades (pnl < 0).

        This helps identify if strategies tend to lose money at the same time,
        which is crucial for portfolio risk management.

        Returns:
            Nested dict: {"strat_1001": {"strat_1001": 1.0, "strat_1002": 0.5, ...}, ...}
            Returns empty dict if fewer than 2 strategies
        """
        strategy_ids = list(self.strategy_trades.keys())

        if len(strategy_ids) < 2:
            return {}

        # Build daily loss amounts per strategy (only negative PnL)
        daily_losses: Dict[int, Dict[date, float]] = {}
        all_dates: set = set()

        for strategy_id, trades in self.strategy_trades.items():
            daily_losses[strategy_id] = {}
            for trade in trades:
                pnl = trade.get('pnl', 0)
                if pnl >= 0:
                    continue  # Only consider losses

                exit_dt = trade.get('exit_date')
                if exit_dt is None:
                    continue

                # Handle both datetime and date types
                if isinstance(exit_dt, datetime):
                    exit_d = exit_dt.date()
                elif isinstance(exit_dt, date):
                    exit_d = exit_dt
                else:
                    continue

                # Accumulate losses (as positive values for correlation)
                daily_losses[strategy_id][exit_d] = daily_losses[strategy_id].get(exit_d, 0) + abs(pnl)
                all_dates.add(exit_d)

        if not all_dates:
            return {}

        # Align to common date set (sorted)
        sorted_dates = sorted(all_dates)

        # Build loss arrays for each strategy (0 for dates with no losses)
        loss_arrays: Dict[int, np.ndarray] = {}
        for strategy_id in strategy_ids:
            loss_series = [daily_losses[strategy_id].get(d, 0.0) for d in sorted_dates]
            loss_arrays[strategy_id] = np.array(loss_series)

        # Calculate correlation matrix
        loss_correlation_matrix: Dict[str, Dict[str, float]] = {}

        for i, strat_i in enumerate(strategy_ids):
            key_i = f"strat_{strat_i}"
            loss_correlation_matrix[key_i] = {}

            for j, strat_j in enumerate(strategy_ids):
                key_j = f"strat_{strat_j}"

                if i == j:
                    loss_correlation_matrix[key_i][key_j] = 1.0
                else:
                    arr_i = loss_arrays[strat_i]
                    arr_j = loss_arrays[strat_j]

                    # Only calculate correlation if both have some losses
                    if np.sum(arr_i > 0) < 2 or np.sum(arr_j > 0) < 2:
                        corr = 0.0
                    else:
                        corr_matrix = np.corrcoef(arr_i, arr_j)
                        corr = corr_matrix[0, 1]
                        if np.isnan(corr):
                            corr = 0.0

                    loss_correlation_matrix[key_i][key_j] = float(corr)

        return loss_correlation_matrix

    def _calculate_concurrent_loss_stats(self) -> Tuple[int, int]:
        """
        Count days where multiple strategies had losses simultaneously.

        Returns:
            Tuple of (concurrent_loss_days, max_concurrent_losses)
            - concurrent_loss_days: Days where 2+ strategies lost
            - max_concurrent_losses: Maximum number of strategies losing on same day
        """
        strategy_ids = list(self.strategy_trades.keys())

        if len(strategy_ids) < 2:
            return 0, 0

        # Build set of loss dates per strategy
        loss_dates_by_strategy: Dict[int, set] = {sid: set() for sid in strategy_ids}

        for strategy_id, trades in self.strategy_trades.items():
            for trade in trades:
                pnl = trade.get('pnl', 0)
                if pnl >= 0:
                    continue  # Only consider losses

                exit_dt = trade.get('exit_date')
                if exit_dt is None:
                    continue

                if isinstance(exit_dt, datetime):
                    exit_d = exit_dt.date()
                elif isinstance(exit_dt, date):
                    exit_d = exit_dt
                else:
                    continue

                loss_dates_by_strategy[strategy_id].add(exit_d)

        # Count concurrent losses per day
        all_loss_dates = set()
        for dates in loss_dates_by_strategy.values():
            all_loss_dates.update(dates)

        concurrent_loss_days = 0
        max_concurrent_losses = 0

        for d in all_loss_dates:
            losing_strategies = sum(1 for sid in strategy_ids if d in loss_dates_by_strategy[sid])
            if losing_strategies >= 2:
                concurrent_loss_days += 1
            max_concurrent_losses = max(max_concurrent_losses, losing_strategies)

        return concurrent_loss_days, max_concurrent_losses
