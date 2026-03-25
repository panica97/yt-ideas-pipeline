"""
Portfolio Reporter Module

Saves portfolio backtest results to disk in a structured folder format.
Uses Parquet for large datasets (trades, equity curve, candles) and JSON for configuration/metrics.

Output structure:
    logs_portfolio/{name or XXX}/
        config.json                          - Backtest configuration
        trades.parquet                       - All trades from all strategies
        equity_curve.parquet                 - Portfolio equity snapshots
        portfolio_metrics.json               - Performance metrics and correlations
        strategies/{strategy_id}/
            trades.parquet                   - Per-strategy trade records
        candles/{symbol}_{timeframe}.parquet - OHLCV data per symbol/timeframe
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import polars as pl

from engine._11_portfolio_state import EquitySnapshot


def _generate_folder_name(base_path: str, custom_name: Optional[str] = None) -> str:
    """
    Generate a folder name: {name} or {XXX} (incremental).

    Args:
        base_path: Parent directory where folder will be created
        custom_name: Optional custom name for the folder

    Returns:
        Folder name (not full path)
    """
    if custom_name:
        # Sanitize custom name: replace spaces with underscores, remove special chars
        safe_name = re.sub(r'[^\w\-]', '_', custom_name)
        return safe_name

    # Auto-generate: XXX format (exactly 3 digits, incremental)
    next_id = 1
    if os.path.exists(base_path):
        for entry in os.listdir(base_path):
            # Match 3-digit folders
            if os.path.isdir(os.path.join(base_path, entry)) and entry.isdigit():
                existing_id = int(entry)
                next_id = max(next_id, existing_id + 1)

    return f"{next_id:03d}"


class PortfolioReporter:
    """
    Saves portfolio backtest results to disk.

    Handles serialization of dataclasses and converts data to Parquet/JSON formats
    for efficient storage and retrieval.
    """

    def __init__(
        self,
        results: Dict[str, Any],
        stratOBJ: Any,
        start_date: str,
        end_date: str,
        initial_equity: float,
        strategies: List[int],
        slippage_ticks: float = 0.0,
        comm_per_contract: float = 0.0,
        enforce_trading_hours: bool = False,
        max_volume: Optional[int] = None,
        full_data: Optional[Dict[str, Dict[str, pl.DataFrame]]] = None,
        verbose: bool = False
    ):
        """
        Initialize the portfolio reporter.

        Args:
            results: Results dict from PortfolioOrchestrator.run()
            stratOBJ: StratOBJ instance with strategy definitions
            start_date: Backtest start date 'YYYY-MM-DD'
            end_date: Backtest end date 'YYYY-MM-DD'
            initial_equity: Starting portfolio equity
            strategies: List of strategy IDs
            slippage_ticks: Slippage in ticks per side
            comm_per_contract: Commission per contract per side
            enforce_trading_hours: Whether trading hours were enforced
            max_volume: Maximum contracts per trade
            full_data: Dict of symbol -> timeframe -> DataFrame (candles)
            verbose: Print progress messages
        """
        self.results = results
        self.stratOBJ = stratOBJ
        self.start_date = start_date
        self.end_date = end_date
        self.initial_equity = initial_equity
        self.strategies = strategies
        self.slippage_ticks = slippage_ticks
        self.comm_per_contract = comm_per_contract
        self.enforce_trading_hours = enforce_trading_hours
        self.max_volume = max_volume
        self.full_data = full_data or {}
        self.verbose = verbose

    def save_results(self, output_folder: str, backtest_name: Optional[str] = None) -> str:
        """
        Save all portfolio results to disk.

        Args:
            output_folder: Base output folder (e.g., 'logs_portfolio')
            backtest_name: Optional custom name for the backtest folder

        Returns:
            Path to the created backtest folder
        """
        # Create folder with YYYYMMDD_XXX format or custom name
        folder_name = _generate_folder_name(output_folder, backtest_name)
        backtest_folder = os.path.join(output_folder, folder_name)
        os.makedirs(backtest_folder, exist_ok=True)

        if self.verbose:
            print(f"\nSaving portfolio results to: {backtest_folder}")

        # Save all components
        self._save_config(backtest_folder)
        self._save_trades(backtest_folder)
        self._save_equity_curve(backtest_folder)
        self._save_portfolio_metrics(backtest_folder)
        self._save_strategy_details(backtest_folder)
        self._save_candles(backtest_folder)

        if self.verbose:
            print(f"Portfolio results saved successfully")

        return backtest_folder

    def _save_config(self, folder: str) -> None:
        """Save backtest configuration to JSON."""
        # Build strategy info
        strategy_info = {}
        for strat_id in self.strategies:
            try:
                strategy_info[str(strat_id)] = {
                    'symbol': self.stratOBJ.symbol(strat_id),
                    'strat_name': self.stratOBJ.strat_name(strat_id),
                    'process_freq': self.stratOBJ.process_freq(strat_id),
                    'multiplier': self.stratOBJ.multiplier(strat_id),
                    'min_tick': self.stratOBJ.minTick(strat_id),
                }
            except Exception:
                strategy_info[str(strat_id)] = {'symbol': 'unknown'}

        config = {
            'backtest_type': 'portfolio',
            'strategies': self.strategies,
            'strategy_info': strategy_info,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'initial_equity': self.initial_equity,
            'final_equity': self.results.get('final_equity', self.initial_equity),
            'parameters': {
                'slippage_ticks': self.slippage_ticks,
                'comm_per_contract': self.comm_per_contract,
                'enforce_trading_hours': self.enforce_trading_hours,
                'max_volume': self.max_volume,
            },
            'timestamp': datetime.now().isoformat(),
        }

        config_path = os.path.join(folder, 'config.json')
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        if self.verbose:
            print(f"  Config saved: {config_path}")

    def _save_trades(self, folder: str) -> None:
        """Save all trades to Parquet."""
        all_trades = self.results.get('trades', [])

        if not all_trades:
            if self.verbose:
                print("  No trades to save")
            return

        # Convert trades to DataFrame
        # Need to handle nested dicts and datetime objects
        trades_cleaned = []
        for trade in all_trades:
            cleaned = self._clean_trade_record(trade)
            trades_cleaned.append(cleaned)

        trades_df = pl.DataFrame(trades_cleaned)

        # Sort by exit_date
        if 'exit_date' in trades_df.columns:
            trades_df = trades_df.sort('exit_date')

        trades_path = os.path.join(folder, 'trades.parquet')
        trades_df.write_parquet(trades_path)

        if self.verbose:
            print(f"  Trades saved: {trades_path} ({len(trades_df)} trades)")

    def _clean_trade_record(self, trade: Dict) -> Dict:
        """
        Clean a trade record for serialization.

        Flattens nested dicts and converts datetime objects to ISO strings.
        """
        cleaned = {}

        for key, value in trade.items():
            if isinstance(value, dict):
                # Flatten nested dicts with prefix
                for sub_key, sub_value in value.items():
                    flat_key = f"{key}_{sub_key}"
                    cleaned[flat_key] = self._serialize_value(sub_value)
            else:
                cleaned[key] = self._serialize_value(value)

        return cleaned

    def _serialize_value(self, value: Any) -> Any:
        """Serialize a value for storage."""
        if isinstance(value, datetime):
            return value.isoformat()
        elif hasattr(value, 'isoformat'):  # date objects
            return value.isoformat()
        return value

    def _save_equity_curve(self, folder: str) -> None:
        """Save equity curve to Parquet."""
        equity_curve = self.results.get('equity_curve', [])

        if not equity_curve:
            if self.verbose:
                print("  No equity curve to save")
            return

        # Convert EquitySnapshot objects to dicts
        snapshots = []
        for snap in equity_curve:
            snapshots.append(self._serialize_equity_snapshot(snap))

        equity_df = pl.DataFrame(snapshots)

        equity_path = os.path.join(folder, 'equity_curve.parquet')
        equity_df.write_parquet(equity_path)

        if self.verbose:
            print(f"  Equity curve saved: {equity_path} ({len(equity_df)} snapshots)")

    def _serialize_equity_snapshot(self, snap: EquitySnapshot) -> Dict:
        """Convert EquitySnapshot dataclass to dict."""
        return {
            'timestamp': snap.timestamp.isoformat() if isinstance(snap.timestamp, datetime) else snap.timestamp,
            'equity': snap.equity,
            'unrealized_pnl': snap.unrealized_pnl,
            'margin_used': snap.margin_used,
            'open_position_count': snap.open_position_count,
            'margin_utilization_pct': snap.margin_utilization_pct,
            'open_risk': snap.open_risk,
        }

    def _save_portfolio_metrics(self, folder: str) -> None:
        """Save portfolio metrics to JSON."""
        portfolio_metrics = self.results.get('portfolio_metrics', {})
        strategy_contributions = self.results.get('strategy_contributions', {})

        metrics_data = {
            'portfolio_metrics': portfolio_metrics,
            'strategy_contributions': {
                str(k): v for k, v in strategy_contributions.items()
            },
            'summary': {
                'total_trades': portfolio_metrics.get('total_trades', 0),
                'total_pnl': portfolio_metrics.get('total_pnl', 0),
                'total_return_pct': portfolio_metrics.get('total_return_pct', 0),
                'sharpe_ratio': portfolio_metrics.get('sharpe_ratio', 0),
                'max_drawdown': portfolio_metrics.get('max_drawdown', 0),
                'max_drawdown_pct': portfolio_metrics.get('max_drawdown_pct', 0),
                'win_rate': portfolio_metrics.get('win_rate', 0),
                # Loss correlation metrics
                'concurrent_loss_days': portfolio_metrics.get('concurrent_loss_days', 0),
                'max_concurrent_losses': portfolio_metrics.get('max_concurrent_losses', 0),
            },
            # Loss correlation matrix stored separately for dashboard use
            'loss_correlation_matrix': portfolio_metrics.get('loss_correlation_matrix', {}),
        }

        metrics_path = os.path.join(folder, 'portfolio_metrics.json')
        with open(metrics_path, 'w') as f:
            json.dump(metrics_data, f, indent=2)

        if self.verbose:
            print(f"  Portfolio metrics saved: {metrics_path}")

    def _save_strategy_details(self, folder: str) -> None:
        """Save per-strategy trade details to Parquet."""
        strategy_trades = self.results.get('strategy_trades', {})

        if not strategy_trades:
            return

        strategies_folder = os.path.join(folder, 'strategies')
        os.makedirs(strategies_folder, exist_ok=True)

        for strat_id, trades in strategy_trades.items():
            if not trades:
                continue

            strat_folder = os.path.join(strategies_folder, str(strat_id))
            os.makedirs(strat_folder, exist_ok=True)

            # Clean and save trades
            trades_cleaned = [self._clean_trade_record(t) for t in trades]
            trades_df = pl.DataFrame(trades_cleaned)

            if 'exit_date' in trades_df.columns:
                trades_df = trades_df.sort('exit_date')

            trades_path = os.path.join(strat_folder, 'trades.parquet')
            trades_df.write_parquet(trades_path)

            if self.verbose:
                print(f"  Strategy {strat_id} trades saved: {trades_path} ({len(trades_df)} trades)")

    def _save_candles(self, folder: str) -> None:
        """Save OHLCV candles per symbol/timeframe to Parquet."""
        if not self.full_data:
            return

        candles_folder = os.path.join(folder, 'candles')
        os.makedirs(candles_folder, exist_ok=True)

        for symbol, timeframes in self.full_data.items():
            for tf, df in timeframes.items():
                if df is None or len(df) == 0:
                    continue

                # Clean timeframe name for filename: "4 hours" -> "4_hours"
                tf_clean = tf.replace(' ', '_').lower()
                filename = f"{symbol}_{tf_clean}.parquet"
                candles_path = os.path.join(candles_folder, filename)

                df.write_parquet(candles_path)

                if self.verbose:
                    print(f"  Candles saved: {candles_path} ({len(df)} bars)")


def load_portfolio_results(folder: str) -> Dict[str, Any]:
    """
    Load portfolio results from a saved folder.

    Args:
        folder: Path to the portfolio backtest folder

    Returns:
        Results dict compatible with dashboard and analysis

    Raises:
        FileNotFoundError: If required files are missing
    """
    results = {}

    # Load config
    config_path = os.path.join(folder, 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
        results['strategies'] = config.get('strategies', [])
        results['initial_equity'] = config.get('initial_equity', 0)
        results['final_equity'] = config.get('final_equity', 0)
        results['config'] = config

    # Load trades
    trades_path = os.path.join(folder, 'trades.parquet')
    if os.path.exists(trades_path):
        trades_df = pl.read_parquet(trades_path)
        results['trades'] = trades_df.to_dicts()

    # Load equity curve
    equity_path = os.path.join(folder, 'equity_curve.parquet')
    if os.path.exists(equity_path):
        equity_df = pl.read_parquet(equity_path)
        # Convert to list of dicts (dashboard expects this format)
        results['equity_curve'] = equity_df.to_dicts()

    # Load portfolio metrics
    metrics_path = os.path.join(folder, 'portfolio_metrics.json')
    if os.path.exists(metrics_path):
        with open(metrics_path, 'r') as f:
            metrics_data = json.load(f)
        results['portfolio_metrics'] = metrics_data.get('portfolio_metrics', {})
        results['strategy_contributions'] = metrics_data.get('strategy_contributions', {})

    # Load per-strategy trades
    strategies_folder = os.path.join(folder, 'strategies')
    if os.path.exists(strategies_folder):
        strategy_trades = {}
        for strat_folder in os.listdir(strategies_folder):
            strat_path = os.path.join(strategies_folder, strat_folder, 'trades.parquet')
            if os.path.exists(strat_path):
                strat_df = pl.read_parquet(strat_path)
                try:
                    strat_id = int(strat_folder)
                except ValueError:
                    strat_id = strat_folder
                strategy_trades[strat_id] = strat_df.to_dicts()
        results['strategy_trades'] = strategy_trades

    # Load candles (optional - only if needed for visualization)
    candles_folder = os.path.join(folder, 'candles')
    if os.path.exists(candles_folder):
        candles = {}
        for filename in os.listdir(candles_folder):
            if filename.endswith('.parquet'):
                candles_path = os.path.join(candles_folder, filename)
                # Parse filename: {symbol}_{timeframe}.parquet
                name_parts = filename.replace('.parquet', '').rsplit('_', 1)
                if len(name_parts) >= 2:
                    # Handle cases like "MNQ_4_hours" -> symbol="MNQ", tf="4_hours"
                    # Find last underscore that separates symbol from timeframe
                    base_name = filename.replace('.parquet', '')
                    # Try to detect common timeframe patterns
                    for tf_pattern in ['1_minute', '5_minutes', '15_minutes', '30_minutes',
                                       '1_hour', '2_hours', '4_hours', '8_hours', '1_day']:
                        if base_name.endswith(tf_pattern):
                            symbol = base_name[:-len(tf_pattern)-1]  # -1 for underscore
                            tf = tf_pattern.replace('_', ' ')
                            if symbol not in candles:
                                candles[symbol] = {}
                            candles[symbol][tf] = pl.read_parquet(candles_path)
                            break
        results['candles'] = candles

    return results
