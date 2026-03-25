"""
Metrics Calculation and Reporting

Provides utilities for calculating performance metrics and generating
backtest reports.
"""

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import polars as pl

from _00_constants import ExitReason


def _generate_folder_name(base_path: str, strat_code: int, custom_name: Optional[str] = None) -> str:
    """
    Generate a folder name with format {strat_code}_{name} or {strat_code}_{XXX}.

    Args:
        base_path: Parent directory where folder will be created
        strat_code: Strategy code (e.g., 1001 for original, 10011 for modified)
        custom_name: Optional custom name to append after strat_code

    Returns:
        Folder name (not full path)
    """
    if custom_name:
        # Sanitize custom name: replace spaces with underscores, remove special chars
        safe_name = re.sub(r'[^\w\-]', '_', custom_name)
        return f"{strat_code}_{safe_name}"

    # Auto-generate: {strat_code}_XXX format (exactly 3 digits)
    next_id = 1
    if os.path.exists(base_path):
        # Match folders starting with this strat_code followed by 3-digit ID
        pattern = re.compile(rf'^{strat_code}_(\d{{3}})$')
        for entry in os.listdir(base_path):
            match = pattern.match(entry)
            if match:
                existing_id = int(match.group(1))
                next_id = max(next_id, existing_id + 1)

    return f"{strat_code}_{next_id:03d}"


class MetricsCalculator:
    """
    Calculates performance metrics from a list of trades.
    """

    def __init__(self, trades: List[Dict], start_date: str, end_date: str, multiplier: float,
                 initial_equity: Optional[float] = None):
        """
        Args:
            trades: List of trade dictionaries
            start_date: Backtest start date (YYYY-MM-DD)
            end_date: Backtest end date (YYYY-MM-DD)
            multiplier: Contract multiplier for notional value calculation
            initial_equity: Starting account equity (used for percentage return calculations)
        """
        self.trades = trades
        self.start_date = start_date
        self.end_date = end_date
        self.multiplier = multiplier
        self.initial_equity = initial_equity

    def calculate(self) -> Dict:
        """
        Calculate all performance metrics.

        Returns:
            Dict of metrics
        """
        if not self.trades:
            return self._empty_metrics()

        pnls = [t['pnl'] for t in self.trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]  # Strictly negative (excludes breakeven)
        breakeven_trades = [p for p in pnls if p == 0]

        # Calculate total slippage and commission
        total_slippage = sum(t.get('slippage_cost', 0) for t in self.trades)
        total_commission = sum(t.get('commission', 0) for t in self.trades)
        total_gross_pnl = sum(t.get('gross_pnl', t['pnl']) for t in self.trades)

        # Calculate drawdown from cumulative PnL (equity-based if initial_equity available)
        cumulative_pnls = [t['cumulative_pnl'] for t in self.trades]
        max_dd = self._calculate_max_drawdown(cumulative_pnls, self.initial_equity)

        total_pnl = sum(pnls)

        # Calculate winning and losing streaks
        winning_streaks, losing_streaks = self._calculate_streaks(pnls)

        max_winning_streak = max(winning_streaks) if winning_streaks else 0
        avg_winning_streak = np.mean(winning_streaks) if winning_streaks else 0
        max_losing_streak = max(losing_streaks) if losing_streaks else 0
        avg_losing_streak = np.mean(losing_streaks) if losing_streaks else 0

        # Calculate Return/Drawdown ratio
        return_drawdown_ratio = abs(total_pnl / max_dd) if max_dd > 0 else 0

        # Calculate average entry value for percentage normalization
        entry_values = [t['entry_price'] * t['position_size'] * t['multiplier'] for t in self.trades]
        avg_entry_value = np.mean(entry_values) if entry_values else 1

        # Calculate percentage metrics
        avg_win = np.mean(wins) if wins else 0
        avg_win_pct = (avg_win / avg_entry_value) * 100 if avg_entry_value > 0 else 0
        avg_loss_abs = abs(np.mean(losses)) if losses else 0
        avg_loss = -avg_loss_abs
        avg_loss_pct = (avg_loss_abs / avg_entry_value) * 100 if avg_entry_value > 0 else 0
        max_dd_pct = (max_dd / avg_entry_value) * 100 if avg_entry_value > 0 else 0

        # Calculate PPR (Profit Per Risk / Average Profit per Operation)
        win_rate_decimal = len(wins) / len(self.trades) if self.trades else 0
        ppr = total_pnl / len(self.trades) if self.trades else 0

        # Calculate average initial risk per operation (SL distance in $)
        # Skip trades with no SL configured (initial_sl_level is None)
        initial_risks = []
        for t in self.trades:
            if t['initial_sl_level'] is None:
                continue
            if t['side'] == 'long':
                risk = (t['entry_price'] - t['initial_sl_level']) * t['position_size'] * t['multiplier']
            else:  # short
                risk = (t['initial_sl_level'] - t['entry_price']) * t['position_size'] * t['multiplier']
            initial_risks.append(abs(risk))
        avg_initial_risk = np.mean(initial_risks) if initial_risks else 0

        # Calculate R/R% (ratio between average profit per operation and average risk per operation)
        rr_percent = (ppr / avg_initial_risk) * 100 if avg_initial_risk > 0 else 0

        # Calculate Kelly Criterion
        b = avg_win / avg_loss_abs if avg_loss_abs > 0 else 0
        p = win_rate_decimal
        q = 1 - p
        kelly_fraction = ((p * b) - q) / b if b > 0 else 0
        half_kelly = kelly_fraction / 2

        # Calculate SQN (System Quality Number)
        avg_trade = np.mean(pnls) if pnls else 0
        std_trade = np.std(pnls, ddof=1) if len(pnls) > 1 else 0
        if std_trade > 0:
            sqn = (np.sqrt(len(pnls)) * avg_trade / std_trade)
        elif avg_trade > 0:
            sqn = float('inf')
        elif avg_trade < 0:
            sqn = float('-inf')
        else:
            sqn = 0.0

        # Calculate time-based metrics
        start = datetime.strptime(self.start_date, '%Y-%m-%d')
        end = datetime.strptime(self.end_date, '%Y-%m-%d')
        days_in_backtest = (end - start).days
        # 365.25 accounts for leap years -- standard convention in finance
        years_in_backtest = days_in_backtest / 365.25
        avg_trades_year = len(self.trades) / years_in_backtest if years_in_backtest > 0 else 0

        # Calculate average bars active
        bars_held = [t['bars_held'] for t in self.trades]
        avg_bars_active = np.mean(bars_held) if bars_held else 0

        # Calculate annualized return
        annualized_return = total_pnl / years_in_backtest if years_in_backtest > 0 else 0
        annualized_return_pct = (annualized_return / avg_entry_value) * 100 if avg_entry_value > 0 else 0

        # Compute per-trade percentage returns for Sharpe/Sortino
        # Walk cumulative PnL to reconstruct equity at each trade entry
        pct_returns = []
        running_equity = self.initial_equity
        for t in self.trades:
            if running_equity and running_equity > 0:
                pct_returns.append(t['pnl'] / running_equity)
            else:
                # Fallback: use notional value if no initial_equity
                notional = t['entry_price'] * t['position_size'] * t['multiplier']
                pct_returns.append(t['pnl'] / notional if notional > 0 else 0.0)
            if running_equity is not None:
                running_equity += t['pnl']

        # Calculate Sharpe Ratio (using percentage returns, annualized)
        # Sharpe = (mean_return / std_return) * sqrt(trades_per_year)
        if len(pct_returns) > 1 and avg_trades_year > 0:
            mean_return = np.mean(pct_returns)
            std_return = np.std(pct_returns, ddof=1)
            sharpe_ratio = (mean_return / std_return) * np.sqrt(avg_trades_year) if std_return > 0 else 0
        else:
            sharpe_ratio = 0

        # Calculate Sortino Ratio (using downside deviation of percentage returns)
        # Sortino = (mean_return / downside_std) * sqrt(trades_per_year)
        downside_pct_returns = [r for r in pct_returns if r < 0]
        if len(downside_pct_returns) > 1 and avg_trades_year > 0:
            downside_std = np.std(downside_pct_returns, ddof=1)
            if downside_std > 0:
                mean_return = np.mean(pct_returns)
                sortino_ratio = (mean_return / downside_std) * np.sqrt(avg_trades_year)
            else:
                sortino_ratio = 0
        else:
            sortino_ratio = 0.0

        # Calculate daily-return Sharpe Ratio (industry standard: sqrt(252) annualization)
        # Groups trade PnLs by exit date, builds daily equity returns over weekdays
        daily_pnl_map = {}
        for t in self.trades:
            exit_dt = t.get('exit_date')
            if exit_dt is None:
                continue
            if isinstance(exit_dt, datetime):
                day = exit_dt.date()
            elif isinstance(exit_dt, str):
                day = datetime.strptime(exit_dt[:10], '%Y-%m-%d').date()
            else:
                day = exit_dt
            daily_pnl_map[day] = daily_pnl_map.get(day, 0.0) + t['pnl']

        # Build weekday series (Mon-Fri) over the backtest period
        daily_returns = []
        if daily_pnl_map and years_in_backtest > 0:
            current_day = start.date()
            end_day = end.date()
            equity = self.initial_equity or avg_entry_value
            while current_day <= end_day:
                if current_day.weekday() < 5:  # Mon-Fri
                    pnl = daily_pnl_map.get(current_day, 0.0)
                    if equity > 0:
                        daily_returns.append(pnl / equity)
                    else:
                        daily_returns.append(0.0)
                    equity += pnl
                current_day += timedelta(days=1)

        if len(daily_returns) > 1:
            mean_dr = np.mean(daily_returns)
            std_dr = np.std(daily_returns, ddof=1)
            sharpe_ratio_daily = (mean_dr / std_dr) * np.sqrt(252) if std_dr > 0 else 0
        else:
            sharpe_ratio_daily = 0

        # Count exit reasons
        exit_reasons = [t['exit_reason'] for t in self.trades]
        sl_exits = exit_reasons.count(ExitReason.SL)
        sl_be_exits = exit_reasons.count(ExitReason.SL_BE)
        sl_tsl_exits = exit_reasons.count(ExitReason.SL_TSL)
        tp_exits = exit_reasons.count(ExitReason.TP)
        num_bars_exits = exit_reasons.count(ExitReason.NUM_BARS)
        exit_cond_exits = exit_reasons.count(ExitReason.EXIT_CONDITION)
        backtest_end_exits = exit_reasons.count(ExitReason.BACKTEST_END)

        # Count BE/TSL activations
        be_triggered_count = sum(1 for t in self.trades if t.get('be_triggered', False))
        tsl_activated_count = sl_tsl_exits

        # Calculate position size statistics
        position_sizes = [t['position_size'] for t in self.trades]
        avg_position_size = np.mean(position_sizes) if position_sizes else 0
        min_position_size = min(position_sizes) if position_sizes else 0
        max_position_size = max(position_sizes) if position_sizes else 0
        total_contracts_traded = sum(position_sizes) if position_sizes else 0

        return {
            'total_trades': len(self.trades),
            'winning_trades': len(wins),
            'losing_trades': len(losses),
            'breakeven_trades': len(breakeven_trades),
            'win_rate': (len(wins) / len(self.trades)) * 100 if self.trades else 0,
            'total_pnl': total_pnl,
            'total_gross_pnl': total_gross_pnl,
            'total_slippage': total_slippage,
            'total_commission': total_commission,
            'avg_win': avg_win,
            'avg_win_pct': avg_win_pct,
            'avg_loss': avg_loss,
            'avg_loss_pct': avg_loss_pct,
            'profit_factor': abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else 0,
            'max_drawdown': max_dd,
            'max_drawdown_pct': max_dd_pct,
            'max_winning_streak': max_winning_streak,
            'avg_winning_streak': avg_winning_streak,
            'max_losing_streak': max_losing_streak,
            'avg_losing_streak': avg_losing_streak,
            'return_drawdown_ratio': return_drawdown_ratio,
            'ppr': ppr,
            'avg_initial_risk': avg_initial_risk,
            'rr_percent': rr_percent,
            'kelly_fraction': kelly_fraction,
            'half_kelly': half_kelly,
            'sqn': sqn,
            'sharpe_ratio': sharpe_ratio,
            'sharpe_ratio_daily': sharpe_ratio_daily,
            'sortino_ratio': sortino_ratio,
            'avg_trades_year': avg_trades_year,
            'avg_bars_active': avg_bars_active,
            'annualized_return': annualized_return,
            'annualized_return_pct': annualized_return_pct,
            'sl_exits': sl_exits,
            'sl_be_exits': sl_be_exits,
            'sl_tsl_exits': sl_tsl_exits,
            'tp_exits': tp_exits,
            'num_bars_exits': num_bars_exits,
            'exit_condition_exits': exit_cond_exits,
            'backtest_end_exits': backtest_end_exits,
            'be_triggered_count': be_triggered_count,
            'tsl_activated_count': tsl_activated_count,
            'avg_position_size': avg_position_size,
            'min_position_size': min_position_size,
            'max_position_size': max_position_size,
            'total_contracts_traded': total_contracts_traded,
        }

    def _calculate_max_drawdown(self, cumulative_pnls: List[float],
                               initial_equity: Optional[float] = None) -> float:
        """Calculate maximum drawdown from cumulative PnL series.

        When initial_equity is provided, converts to an equity curve so the peak
        starts at the actual account value rather than 0. This prevents
        underestimating drawdown when the first trades are winners.
        """
        if initial_equity is not None and initial_equity > 0:
            # Convert cumulative PnL to equity curve
            peak = initial_equity
            max_dd = 0
            for cum_pnl in cumulative_pnls:
                equity = initial_equity + cum_pnl
                if equity > peak:
                    peak = equity
                dd = peak - equity
                max_dd = max(max_dd, dd)
            return max_dd
        else:
            peak = 0
            max_dd = 0
            for cum_pnl in cumulative_pnls:
                if cum_pnl > peak:
                    peak = cum_pnl
                dd = peak - cum_pnl
                max_dd = max(max_dd, dd)
            return max_dd

    def _calculate_streaks(self, pnls: List[float]) -> tuple:
        """
        Calculate winning and losing streaks.

        Breakeven trades (pnl == 0) break both winning and losing streaks
        but do not start a new streak themselves.
        """
        winning_streaks = []
        losing_streaks = []
        current_streak = 0
        current_type = None

        for pnl in pnls:
            if pnl > 0:  # Winning trade
                if current_type == 'win':
                    current_streak += 1
                else:
                    # End previous losing streak if any
                    if current_type == 'loss' and current_streak > 0:
                        losing_streaks.append(current_streak)
                    current_streak = 1
                    current_type = 'win'
            elif pnl < 0:  # Losing trade (strictly negative)
                if current_type == 'loss':
                    current_streak += 1
                else:
                    # End previous winning streak if any
                    if current_type == 'win' and current_streak > 0:
                        winning_streaks.append(current_streak)
                    current_streak = 1
                    current_type = 'loss'
            else:  # Breakeven trade (pnl == 0) - breaks any streak
                # End current streak
                if current_type == 'win' and current_streak > 0:
                    winning_streaks.append(current_streak)
                elif current_type == 'loss' and current_streak > 0:
                    losing_streaks.append(current_streak)
                # Reset - breakeven doesn't start a new streak
                current_streak = 0
                current_type = None

        # Append final streak
        if current_type == 'win' and current_streak > 0:
            winning_streaks.append(current_streak)
        elif current_type == 'loss' and current_streak > 0:
            losing_streaks.append(current_streak)

        return winning_streaks, losing_streaks

    def _empty_metrics(self) -> Dict:
        """Return empty metrics when no trades."""
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'breakeven_trades': 0,
            'win_rate': 0.0,
            'total_pnl': 0.0,
            'total_gross_pnl': 0.0,
            'total_slippage': 0.0,
            'total_commission': 0.0,
            'total_return_pct': 0.0,
            'avg_win': 0.0,
            'avg_win_pct': 0.0,
            'avg_loss': 0.0,
            'avg_loss_pct': 0.0,
            'profit_factor': 0.0,
            'max_drawdown': 0.0,
            'max_drawdown_pct': 0.0,
            'max_winning_streak': 0,
            'avg_winning_streak': 0.0,
            'max_losing_streak': 0,
            'avg_losing_streak': 0.0,
            'return_drawdown_ratio': 0.0,
            'ppr': 0.0,
            'avg_initial_risk': 0.0,
            'rr_percent': 0.0,
            'kelly_fraction': 0.0,
            'half_kelly': 0.0,
            'sqn': 0.0,
            'sharpe_ratio': 0.0,
            'sortino_ratio': 0.0,
            'avg_trades_year': 0.0,
            'avg_bars_active': 0.0,
            'annualized_return': 0.0,
            'annualized_return_pct': 0.0,
            'sl_exits': 0,
            'sl_be_exits': 0,
            'sl_tsl_exits': 0,
            'tp_exits': 0,
            'num_bars_exits': 0,
            'exit_condition_exits': 0,
            'backtest_end_exits': 0,
            'be_triggered_count': 0,
            'tsl_activated_count': 0,
            'avg_position_size': 0.0,
            'min_position_size': 0,
            'max_position_size': 0,
            'total_contracts_traded': 0,
        }


class BacktestReporter:
    """
    Generates reports and saves backtest results.
    """

    def __init__(
        self,
        strategy: int,
        symbol: str,
        start_date: str,
        end_date: str,
        trades: List[Dict],
        stratOBJ: Any,
        verbose: bool = False,
        # Position sizing parameters
        position_sizing_mode: str = 'fixed',
        initial_equity: Optional[float] = None,
        final_equity: Optional[float] = None,
        fixed_volume: int = 1,
        risk_per_operation: float = 0.02,
        max_volume: Optional[int] = None,
        # Candles data for visualization
        candles_df: Optional[pl.DataFrame] = None,
        primary_timeframe: Optional[str] = None,
        # Multi-timeframe data for dashboard
        full_data: Optional[Dict[str, pl.DataFrame]] = None,
        # Strategy file metadata
        strategy_filename: Optional[str] = None
    ):
        """
        Args:
            strategy: Strategy ID
            symbol: Symbol traded
            start_date: Backtest start date
            end_date: Backtest end date
            trades: List of trade dictionaries
            stratOBJ: StratOBJ instance
            verbose: Enable verbose output
            position_sizing_mode: 'fixed', 'rpo', or 'half_kelly'
            initial_equity: Starting account equity
            final_equity: Ending account equity
            fixed_volume: Number of contracts for fixed mode
            risk_per_operation: Risk percentage for RPO mode
            max_volume: Maximum contracts per trade
            candles_df: Primary timeframe OHLCV data for visualization
            primary_timeframe: Primary timeframe string (e.g., '1H')
            full_data: All timeframe OHLCV data for dashboard visualization
            strategy_filename: Strategy source filename (e.g., '1001_ADX_30_mod.py')
        """
        self.strategy = strategy
        self.symbol = symbol
        self.strategy_filename = strategy_filename
        self.start_date = start_date
        self.end_date = end_date
        self.trades = trades
        self.stratOBJ = stratOBJ
        self.verbose = verbose
        # Position sizing attributes
        self.position_sizing_mode = position_sizing_mode
        self.initial_equity = initial_equity
        self.final_equity = final_equity
        self.fixed_volume = fixed_volume
        self.risk_per_operation = risk_per_operation
        self.max_volume = max_volume
        # Visualization data
        self.candles_df = candles_df
        self.primary_timeframe = primary_timeframe
        # Multi-timeframe data
        self.full_data = full_data

    def print_summary(self, metrics: Dict) -> None:
        """Print backtest summary to console."""
        print(f"\nExit Methods:")
        print(f"  Stop Loss (Original): {metrics['sl_exits']}")
        print(f"  Stop Loss (BE): {metrics['sl_be_exits']}")
        print(f"  Stop Loss (TSL): {metrics['sl_tsl_exits']}")
        print(f"  Take Profit: {metrics['tp_exits']}")
        print(f"  Max Bars: {metrics['num_bars_exits']}")
        print(f"  Exit Condition: {metrics['exit_condition_exits']}")
        if metrics['backtest_end_exits'] > 0:
            print(f"  Backtest End: {metrics['backtest_end_exits']}")

        # BE/TSL activation stats
        if metrics['be_triggered_count'] > 0 or metrics['tsl_activated_count'] > 0:
            print(f"\nBE/TSL Statistics:")
            if metrics['total_trades'] > 0:
                print(f"  BE Triggered: {metrics['be_triggered_count']} trades ({metrics['be_triggered_count']/metrics['total_trades']*100:.1f}%)")
            else:
                print(f"  BE Triggered: 0")
            print(f"  TSL Activated: {metrics['tsl_activated_count']} trades")

        print(f"\nTotal Trades: {metrics['total_trades']}")
        print(f"Winning Trades: {metrics['winning_trades']}")
        print(f"Losing Trades: {metrics['losing_trades']}")
        if metrics.get('breakeven_trades', 0) > 0:
            print(f"Breakeven Trades: {metrics['breakeven_trades']}")
        print(f"Win Rate: {metrics['win_rate']:.2f}%")
        print(f"Total PnL: ${metrics['total_pnl']:+,.2f}")
        if metrics['total_slippage'] > 0 or metrics['total_commission'] > 0:
            print(f"  Gross PnL: ${metrics['total_gross_pnl']:+,.2f}")
            print(f"  Total Slippage: -${metrics['total_slippage']:,.2f}")
            print(f"  Total Commission: -${metrics['total_commission']:,.2f}")
        print(f"Avg Win: {metrics['avg_win_pct']:+.2f}%")
        print(f"Avg Loss: {metrics['avg_loss_pct']:+.2f}%")
        print(f"Profit Factor: {metrics['profit_factor']:.2f}")
        print(f"Max Drawdown: {metrics['max_drawdown_pct']:.2f}%")
        print(f"Return/DD Ratio: {metrics['return_drawdown_ratio']:.2f}")

        print(f"\nStreak Analysis:")
        print(f"  Max Winning Streak: {metrics['max_winning_streak']}")
        print(f"  Avg Winning Streak: {metrics['avg_winning_streak']:.2f}")
        print(f"  Max Losing Streak: {metrics['max_losing_streak']}")
        print(f"  Avg Losing Streak: {metrics['avg_losing_streak']:.2f}")

        print(f"\nAdvanced Metrics:")
        print(f"  PPR (Avg Profit/Operation): ${metrics['ppr']:+,.2f}")
        print(f"  Avg Initial Risk: ${metrics['avg_initial_risk']:,.2f}")
        print(f"  R/R% (Reward/Risk Ratio): {metrics['rr_percent']:+.2f}%")
        print(f"  SQN (System Quality Number): {metrics['sqn']:.2f}")
        print(f"  Avg Trades/Year: {metrics['avg_trades_year']:.1f}")
        print(f"  Avg Bars Active: {metrics['avg_bars_active']:.1f}")
        print(f"  Annualized Return: {metrics['annualized_return_pct']:+.2f}%")

        # Position Sizing Section
        print(f"\nPosition Sizing:")
        print(f"  Mode: {self.position_sizing_mode.upper()}")
        if self.position_sizing_mode == 'fixed':
            print(f"  Fixed Volume: {self.fixed_volume} contract(s)")
        elif self.position_sizing_mode == 'rpo':
            print(f"  Risk Per Operation: {self.risk_per_operation * 100:.1f}%")
        elif self.position_sizing_mode == 'half_kelly':
            print(f"  Using Half-Kelly with max_rpo from strategy config")
        if self.max_volume:
            print(f"  Max Volume Limit: {self.max_volume}")
        print(f"  Avg Position Size: {metrics.get('avg_position_size', 0):.2f}")
        print(f"  Min Position Size: {metrics.get('min_position_size', 0)}")
        print(f"  Max Position Size: {metrics.get('max_position_size', 0)}")
        print(f"  Total Contracts Traded: {metrics.get('total_contracts_traded', 0)}")

    def save_results(
        self,
        output_folder: str,
        slippage_ticks: float = 0.0,
        comm_per_contract: float = 0.0,
        save_all_timeframes: bool = True,
        backtest_name: Optional[str] = None
    ) -> str:
        """
        Save backtest results to per-backtest subfolder.

        Output structure:
            {output_folder}/{strategy}/{YYYYMMDD_XXX}/
                trades.parquet       - Trade records
                metrics.json         - Performance metrics + strategy config
                candles.parquet      - Primary timeframe OHLCV data
                candles_1_hour.parquet - Additional timeframe (if save_all_timeframes=True)
                candles_4_hour.parquet - Additional timeframe (if save_all_timeframes=True)
                ...

        Args:
            output_folder: Base output folder path
            slippage_ticks: Slippage in ticks (for reporting)
            comm_per_contract: Commission per contract (for reporting)
            save_all_timeframes: If True, save candles for all timeframes (for dashboard)
            backtest_name: Optional custom name for the backtest folder

        Returns:
            str: Path to the backtest folder (for visualization)
        """
        # Create per-backtest subfolder: {base_strategy}/{strat_code_name}/
        # Modified strategies (e.g., 10011) go in base folder (1001)
        strategy_str = str(self.strategy)
        base_strategy = strategy_str[:4] if len(strategy_str) > 4 else strategy_str
        strategy_folder = os.path.join(output_folder, base_strategy)
        folder_name = _generate_folder_name(strategy_folder, self.strategy, backtest_name)
        backtest_folder = os.path.join(strategy_folder, folder_name)
        os.makedirs(backtest_folder, exist_ok=True)

        # Timestamp for metrics
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Save trades to Parquet
        if self.trades:
            trades_df = pl.DataFrame(self.trades)
            trades_path = os.path.join(backtest_folder, "trades.parquet")
            trades_df.write_parquet(trades_path)
            if self.verbose:
                print(f"\nTrades saved to: {trades_path}")

        # Save candles for visualization
        if save_all_timeframes and self.full_data:
            # Save all timeframes for dashboard
            for tf, df in self.full_data.items():
                if df is not None and len(df) > 0:
                    # Clean timeframe name for filename: "1 hour" -> "1_hour"
                    tf_clean = tf.replace(' ', '_').lower()
                    candles_path = os.path.join(backtest_folder, f"candles_{tf_clean}.parquet")
                    df.write_parquet(candles_path)
                    if self.verbose:
                        print(f"Candles ({tf}) saved to: {candles_path}")
        elif self.candles_df is not None and len(self.candles_df) > 0:
            # Fallback: save only primary timeframe
            candles_path = os.path.join(backtest_folder, "candles.parquet")
            self.candles_df.write_parquet(candles_path)
            if self.verbose:
                print(f"Candles saved to: {candles_path}")

        # Calculate metrics
        multiplier = self.stratOBJ.multiplier(self.strategy)
        calculator = MetricsCalculator(self.trades, self.start_date, self.end_date, multiplier,
                                       initial_equity=self.initial_equity)
        metrics = calculator.calculate()

        # Calculate slippage amount (ticks * minTick)
        min_tick = self.stratOBJ.minTick(self.strategy) or 0.25
        slippage_amount = round(slippage_ticks * min_tick, 3)

        # Round all metrics to 3 decimals (clamp inf to large finite for JSON compat)
        def _safe_round(v):
            if not isinstance(v, float):
                return v
            if v == float('inf'):
                return 9999.999
            if v == float('-inf'):
                return -9999.999
            return round(v, 3)

        rounded_metrics = {k: _safe_round(v) for k, v in metrics.items()}

        # Build strategy config for dashboard
        strategy_config = self._build_strategy_config()

        # Save metrics to JSON
        metrics_json = os.path.join(backtest_folder, "metrics.json")
        metrics_data = {
            'strategy': self.strategy,
            'strategy_filename': self.strategy_filename,
            'symbol': self.symbol,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'timestamp': timestamp,
            'primary_timeframe': self.primary_timeframe,
            'slippage_amount': slippage_amount,
            'comm_per_contract': round(comm_per_contract, 3),
            'position_sizing': {
                'mode': self.position_sizing_mode,
                'fixed_volume': self.fixed_volume,
                'risk_per_operation': round(self.risk_per_operation, 4),
                'max_volume': self.max_volume,
            },
            'metrics': rounded_metrics,
            'strategy_config': strategy_config
        }
        # Add equity info if available
        if self.initial_equity:
            metrics_data['equity'] = {
                'initial': self.initial_equity,
                'final': self.final_equity,
            }

        with open(metrics_json, 'w') as f:
            json.dump(metrics_data, f, indent=2)

        if self.verbose:
            print(f"Metrics saved to: {metrics_json}")

        return backtest_folder

    def _build_strategy_config(self) -> Dict:
        """Build strategy configuration dict for dashboard."""
        try:
            return {
                'ind_list': self.stratOBJ.ind_list(self.strategy),
                'long_conds': self.stratOBJ.long_conds(self.strategy),
                'short_conds': self.stratOBJ.short_conds(self.strategy),
                'exit_conds': self.stratOBJ.exit_conds(self.strategy),
                'process_freq': self.stratOBJ.process_freq(self.strategy),
                'stop_loss_mgmt': self.stratOBJ.stop_loss_mgmt(self.strategy),
            }
        except Exception:
            # Return empty config if stratOBJ methods fail
            return {}

    def print_data_slice(
        self,
        bar_idx: int,
        current_bar: Any,
        window_data: Dict[str, pl.DataFrame],
        event_type: str,
        signal: Dict,
        ref_price: float,
        position_state: Optional[Dict] = None
    ) -> None:
        """
        Print detailed data slice for debugging.

        Args:
            bar_idx: Current bar index
            current_bar: Current bar data
            window_data: Window data with indicators
            event_type: 'ENTRY' or 'EXIT'
            signal: Signal dictionary
            ref_price: Reference price
            position_state: Optional dict with position info (side, entry_price, sl_level, tp_level, bars_in_position)
        """
        from _03_price_utils import extract_scalar

        print(f"\n{'='*80}")
        print(f"{'='*80}")
        print(f"{'='*80}")
        print(f"{event_type} DATA SLICE - Bar {bar_idx}")

        # Print current bar OHLC
        bar_date = extract_scalar(current_bar['date'])
        bar_open = extract_scalar(current_bar['open'])
        bar_high = extract_scalar(current_bar['high'])
        bar_low = extract_scalar(current_bar['low'])
        bar_close = extract_scalar(current_bar['close'])

        print(f"Date: {bar_date}")
        print(f"OHLC: O={bar_open:.2f} H={bar_high:.2f} L={bar_low:.2f} C={bar_close:.2f}")
        print(f"Ref Price: {ref_price:.2f}\n")

        # Configure polars to print full dataframes
        with pl.Config(
            tbl_rows=-1,
            tbl_cols=-1,
            fmt_str_lengths=100
        ):
            for tf, df in window_data.items():
                if len(df) > 0:
                    print(f"\n>>> Timeframe: {tf} ({len(df)} bars)")
                    print(df)

        # Print conditions being evaluated
        if event_type == 'ENTRY':
            if signal.get('long'):
                long_conds = self.stratOBJ.long_conds(self.strategy)
                print(f"\nLong Conditions:")
                conds_df = pl.DataFrame(long_conds)
                print(conds_df)
            if signal.get('short'):
                short_conds = self.stratOBJ.short_conds(self.strategy)
                print(f"\nShort Conditions:")
                conds_df = pl.DataFrame(short_conds)
                print(conds_df)
        elif event_type == 'EXIT':
            exit_conds = self.stratOBJ.exit_conds(self.strategy)
            print(f"  Exit Conditions:")
            conds_df = pl.DataFrame(exit_conds)
            print(conds_df)
            if position_state:
                print(f"  Position Side: {position_state.get('side')}")
                print(f"  Entry Price: {position_state.get('entry_price', 0):.2f}")
                print(f"  SL Level: {position_state.get('sl_level', 0):.2f}")
                print(f"  TP Level: {position_state.get('tp_level', 0):.2f}")
                print(f"  Bars in Position: {position_state.get('bars_in_position', 0)}")

        print(f"{'='*80}\n")
