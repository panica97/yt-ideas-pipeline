#!/usr/bin/env python
"""
main.py - Central entry point for IBKR-BACKTEST

Usage:
    Single-strategy mode:
        python main.py --mode single --strategy 1001 --start 2015-01-01 --end 2024-12-31

    Portfolio mode (explicit strategies):
        python main.py --mode portfolio --strategies 1001 1002 1003 --start 2015-01-01 --end 2024-12-31

    Portfolio mode (all active strategies):
        python main.py --mode portfolio --all --start 2015-01-01 --end 2024-12-31 --equity 100000

    Portfolio mode (filter by symbol):
        python main.py --mode portfolio --symbol MNQ --start 2015-01-01 --end 2024-12-31 --equity 100000

    With options:
        python main.py --mode single --strategy 1001 --start 2015-01-01 --end 2024-12-31 --verbose

Examples:
    # Run all active strategies
    python main.py --mode portfolio --all --start 2024-01-01 --end 2024-12-31 --equity 100000

    # Run all MNQ strategies
    python main.py --mode portfolio --symbol MNQ --start 2024-01-01 --end 2024-12-31 --equity 100000

    # Run specific strategies
    python main.py --mode portfolio --strategies 1001 1002 --start 2024-01-01 --end 2024-12-31

    # Single strategy with position sizing
    python main.py --mode single --strategy 1001 --start 2024-01-01 --end 2024-12-31 \\
        --equity 100000 --sizing rpo --risk 0.02

    # Verbose output with slippage and commission
    python main.py --mode single --strategy 1001 --start 2024-01-01 --end 2024-12-31 \\
        --verbose --slippage 2 --commission 0.62
"""
import argparse
import sys
import os
import json
from pathlib import Path
from typing import List

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import log paths from constants (used as fallback if env var not set)
from constants import PORTFOLIO_LOGS_PATH as DEFAULT_PORTFOLIO_LOGS_PATH
from logger import get_logger

_logger = get_logger("main")

# Add engine directory to path
ENGINE_PATH = str(PROJECT_ROOT / 'engine')
if ENGINE_PATH not in sys.path:
    sys.path.insert(0, ENGINE_PATH)


def apply_overrides_to_strategy(stratOBJ, strategy_id: int, overrides: dict) -> None:
    """Apply parameter overrides to a strategy at runtime.

    Modifies the strategy object in-place to change parameter values
    for stress testing variations.

    Overrides format (normalized timeframes - underscores instead of spaces):
    {
        "ind_list.4_hours.0.params.timePeriod_1": 25,
        "stop_loss_init.indicator_params.multiple": 1.8,
        "stop_loss_mgmt.breakeven.action": true
    }

    NOTE: Timeframe keys use underscores (e.g., "4_hours" not "4 hours") to
    ensure clean dot-notation parsing. The function denormalizes them back
    to original format when accessing the strategy object.

    Args:
        stratOBJ: StratOBJ instance with loaded strategies
        strategy_id: Strategy ID to modify
        overrides: Dict mapping param_path to new value
    """
    import re

    # Find the internal strategy storage - stratOBJ uses 'strats' dict internally
    if hasattr(stratOBJ, 'strats') and strategy_id in stratOBJ.strats:
        strat_wrapper = stratOBJ.strats[strategy_id]
    elif hasattr(stratOBJ, '_strategies') and strategy_id in stratOBJ._strategies:
        strat_wrapper = stratOBJ._strategies[strategy_id]
    else:
        raise AttributeError(
            f"Cannot find strategy {strategy_id} in stratOBJ. "
            f"Available attributes: {[a for a in dir(stratOBJ) if not a.startswith('__')]}"
        )

    # StrategyData wraps the actual data - find the internal storage
    # Try common patterns for internal data storage
    if hasattr(strat_wrapper, 'data') and isinstance(strat_wrapper.data, dict):
        strat = strat_wrapper.data
    elif hasattr(strat_wrapper, '_data') and isinstance(strat_wrapper._data, dict):
        strat = strat_wrapper._data
    elif hasattr(strat_wrapper, '__dict__'):
        strat = strat_wrapper.__dict__
    else:
        strat = strat_wrapper

    def normalize_path(path: str) -> str:
        """Normalize override path to consistent dot-notation.

        Handles both formats the frontend may produce:
          - Bracket notation: "ind_list.4 hours[0].params.timePeriod_1"
          - Dot notation:     "ind_list.4_hours.0.params.timePeriod_1"

        Converts bracket indices [N] to .N and spaces to underscores so
        that splitting on '.' yields clean parts.
        """
        # Convert bracket indices to dot notation: "foo[0].bar" -> "foo.0.bar"
        path = re.sub(r'\[(\d+)\]', r'.\1', path)
        # Normalize spaces in timeframe keys to underscores: "4 hours" -> "4_hours"
        # This is reversed by denormalize_key() when doing dict lookups
        path = path.replace(' ', '_')
        # Remove any double dots from the conversions
        while '..' in path:
            path = path.replace('..', '.')
        return path

    def denormalize_key(key: str) -> str:
        """Convert normalized timeframe key back to original format."""
        # Known timeframe patterns: 1_min, 4_hours, 1_hour, 5_min, etc.
        return re.sub(r'(\d+)_(\w+)', lambda m: f'{m.group(1)} {m.group(2)}', key)

    def get_nested(obj, key):
        """Get nested value, handling objects, dicts, and lists."""
        lookup_key = denormalize_key(key)

        # Try dict access first (use 'in' to handle falsy values correctly)
        if isinstance(obj, dict):
            if lookup_key in obj:
                return obj[lookup_key]
            if key in obj:
                return obj[key]
            raise KeyError(
                f"Key '{key}' (or '{lookup_key}') not found in dict. "
                f"Available: {list(obj.keys())[:10]}"
            )

        # Try list index
        if isinstance(obj, list):
            return obj[int(key)]

        # Try attribute access with both normalized and denormalized keys
        if hasattr(obj, lookup_key):
            return getattr(obj, lookup_key)
        if hasattr(obj, key):
            return getattr(obj, key)

        # Try __dict__ access (for StrategyData objects)
        if hasattr(obj, '__dict__'):
            d = obj.__dict__
            if lookup_key in d:
                return d[lookup_key]
            if key in d:
                return d[key]

        # Provide diagnostic info for debugging
        available = []
        if hasattr(obj, '__dict__'):
            available = list(obj.__dict__.keys())
        elif isinstance(obj, dict):
            available = list(obj.keys())
        raise AttributeError(
            f"Cannot access '{key}' (or '{lookup_key}') on {type(obj).__name__}. "
            f"Available: {available[:10]}{'...' if len(available) > 10 else ''}"
        )

    for path, value in overrides.items():
        path = normalize_path(path)
        parts = path.split('.')
        obj = strat

        # Navigate to parent of target
        for part in parts[:-1]:
            obj = get_nested(obj, part)

        # Set final value
        final_key = parts[-1]
        lookup_key = denormalize_key(final_key)

        def _coerce(existing, new_val):
            """Preserve original type: cast float->int when appropriate."""
            if isinstance(existing, int) and isinstance(new_val, float):
                if new_val == int(new_val):
                    return int(new_val)
            return new_val

        if isinstance(obj, dict):
            # Try denormalized key first, then original
            if lookup_key in obj:
                obj[lookup_key] = _coerce(obj[lookup_key], value)
            else:
                obj[final_key] = _coerce(obj.get(final_key), value)
        elif isinstance(obj, list):
            obj[int(final_key)] = value
        elif hasattr(obj, '__dict__'):
            # For StrategyData objects, modify __dict__ directly
            if lookup_key in obj.__dict__:
                obj.__dict__[lookup_key] = _coerce(obj.__dict__[lookup_key], value)
            elif final_key in obj.__dict__:
                obj.__dict__[final_key] = _coerce(obj.__dict__[final_key], value)
            else:
                setattr(obj, final_key, value)
        else:
            setattr(obj, final_key, value)


def get_all_active_strategies(stratOBJ) -> List[int]:
    """
    Discover all active strategies from StratOBJ.

    A strategy is considered active if it has a valid symbol configuration.
    Invalid strategies are logged and skipped.

    Args:
        stratOBJ: StratOBJ instance with loaded strategies

    Returns:
        List of valid strategy IDs
    """
    active = []
    skipped = []

    for strat_id in stratOBJ.strat_codes():
        try:
            symbol = stratOBJ.symbol(strat_id)
            if symbol and symbol.strip():
                active.append(strat_id)
            else:
                skipped.append((strat_id, "no symbol configured"))
        except Exception as e:
            skipped.append((strat_id, str(e)))

    if skipped:
        print(f"Skipped {len(skipped)} invalid strategies:")
        for strat_id, reason in skipped[:5]:  # Show first 5
            print(f"  - Strategy {strat_id}: {reason}")
        if len(skipped) > 5:
            print(f"  ... and {len(skipped) - 5} more")

    return sorted(active)


def filter_strategies_by_symbol(stratOBJ, symbol: str) -> List[int]:
    """
    Filter strategies by trading symbol.

    Args:
        stratOBJ: StratOBJ instance with loaded strategies
        symbol: Symbol to filter by (e.g., 'MNQ', '@ES')

    Returns:
        List of strategy IDs trading the given symbol
    """
    matching = []
    target_symbol = symbol.upper().strip()

    for strat_id in stratOBJ.strat_codes():
        try:
            strat_symbol = stratOBJ.symbol(strat_id)
            if strat_symbol and strat_symbol.upper().strip() == target_symbol:
                matching.append(strat_id)
        except Exception:
            continue

    return sorted(matching)


def main():
    """Main entry point for IBKR-BACKTEST."""
    parser = argparse.ArgumentParser(
        description='IBKR Backtesting Engine - Run single-strategy or portfolio backtests',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Mode selection
    parser.add_argument(
        '--mode', '-m',
        choices=['single', 'portfolio'],
        required=True,
        help='Backtest mode: single strategy or portfolio (multiple strategies)'
    )

    # Single-strategy args
    parser.add_argument(
        '--strategy', '-s',
        type=int,
        help='Strategy ID (required for single mode)'
    )

    # Portfolio args
    parser.add_argument(
        '--strategies',
        nargs='+',
        type=int,
        help='Strategy IDs for portfolio mode (space-separated)'
    )
    parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Run all active strategies (portfolio mode only)'
    )
    parser.add_argument(
        '--symbol',
        type=str,
        help='Filter strategies by symbol, e.g., MNQ (portfolio mode only)'
    )

    # Date range
    parser.add_argument(
        '--start',
        type=str,
        required=True,
        help='Start date in YYYY-MM-DD format'
    )
    parser.add_argument(
        '--end',
        type=str,
        required=True,
        help='End date in YYYY-MM-DD format'
    )

    # Account settings
    parser.add_argument(
        '--equity',
        type=float,
        default=100000,
        help='Initial equity in dollars (default: 100000)'
    )

    # Execution settings
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--slippage',
        type=float,
        default=1.5,
        help='Slippage in ticks per side (default: 1.5)'
    )
    parser.add_argument(
        '--commission',
        type=float,
        default=0.62,
        help='Commission per contract per side (default: 0.62)'
    )

    # Position sizing (primarily for single mode)
    parser.add_argument(
        '--sizing',
        choices=['fixed', 'rpo', 'half_kelly'],
        default='fixed',
        help='Position sizing mode: fixed, rpo (risk per operation), or half_kelly'
    )
    parser.add_argument(
        '--risk',
        type=float,
        default=0.02,
        help='Risk per operation as decimal (for rpo mode, default: 0.02 = 2%%)'
    )
    parser.add_argument(
        '--volume',
        type=int,
        default=1,
        help='Fixed volume in contracts (for fixed mode, default: 1)'
    )
    parser.add_argument(
        '--max-volume',
        type=int,
        default=None,
        help='Maximum contracts per trade (default: no limit)'
    )

    # Trading hours
    parser.add_argument(
        '--enforce-hours',
        action='store_true',
        help='Enforce strategy trading hours restrictions'
    )

    # Debug/testing options
    parser.add_argument(
        '--stop-after',
        type=int,
        default=0,
        help='Stop backtest after N trades (0 = run full backtest, default: 0)'
    )

    # Output options
    parser.add_argument(
        '--save',
        action='store_true',
        help='Save results to logs_backtest folder'
    )

    # Stress test parameter overrides
    parser.add_argument(
        '--param-overrides',
        type=str,
        default=None,
        help='Path to JSON file with parameter overrides for stress testing'
    )
    parser.add_argument(
        '--name',
        type=str,
        default=None,
        help='Custom name for the backtest folder (format: YYYYMMDD_{name})'
    )
    parser.add_argument(
        '--dashboard',
        action='store_true',
        help='Launch dashboard after backtest (single mode requires --save; portfolio mode launches directly)'
    )
    parser.add_argument(
        '--metrics-json',
        action='store_true',
        help='Output metrics as JSON to stdout (for stress testing - no files saved)'
    )
    parser.add_argument(
        '--hist-data-path',
        type=str,
        default=str(PROJECT_ROOT / 'hist_data'),
        help='Path to historical data folder (default: hist_data relative to engine dir)'
    )
    parser.add_argument(
        '--strategies-path',
        type=str,
        default=str(PROJECT_ROOT / 'Strategies'),
        help='Path to strategies folder (default: Strategies relative to engine dir)'
    )
    parser.add_argument(
        '--custom-indicators-dir',
        type=str,
        default=None,
        help='Path to custom indicator modules (default: ibkr_core built-in directory)'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.mode == 'single' and not args.strategy:
        parser.error("--strategy is required for single mode")

    # Portfolio mode argument validation
    if args.mode == 'portfolio':
        # Check mutually exclusive options
        options_count = sum([
            bool(args.strategies),
            args.all,
            bool(args.symbol)
        ])

        if options_count == 0:
            parser.error("Portfolio mode requires --strategies, --all, or --symbol")
        if options_count > 1:
            parser.error("--strategies, --all, and --symbol are mutually exclusive")

    # Validate sizing mode requires equity for dynamic sizing
    if args.sizing in ('rpo', 'half_kelly') and args.equity <= 0:
        parser.error(f"--equity must be positive for {args.sizing} position sizing")

    # Load strategy definitions
    from ibkr_core import StratOBJ

    strategies_path = args.strategies_path
    print(f"Loading strategy definitions from {strategies_path}...")
    stratOBJ = StratOBJ().upload(strategies_folder=strategies_path, connect_ib=False)

    # Resolve strategies for portfolio mode
    if args.mode == 'portfolio':
        if args.all:
            args.strategies = get_all_active_strategies(stratOBJ)
            if not args.strategies:
                print("Error: No active strategies found")
                sys.exit(1)
            print(f"Discovered {len(args.strategies)} active strategies: {args.strategies}")
        elif args.symbol:
            args.strategies = filter_strategies_by_symbol(stratOBJ, args.symbol)
            if not args.strategies:
                print(f"Error: No strategies found for symbol '{args.symbol}'")
                sys.exit(1)
            print(f"Found {len(args.strategies)} strategies for {args.symbol}: {args.strategies}")

    if args.mode == 'single':
        run_single_strategy(args, stratOBJ)
    else:
        run_portfolio(args, stratOBJ)


def run_single_strategy(args, stratOBJ):
    """
    Run single-strategy backtest using existing BT_Manager.

    Args:
        args: Parsed command line arguments
        stratOBJ: StratOBJ instance with loaded strategies
    """
    import json

    from engine._10_backtester import BT_Manager

    # Apply parameter overrides if provided (for stress testing)
    if args.param_overrides:
        overrides_path = Path(args.param_overrides)
        if not overrides_path.exists():
            print(f"Error: Overrides file not found: {overrides_path}")
            sys.exit(1)
        with open(overrides_path, 'r') as f:
            overrides = json.load(f)
        apply_overrides_to_strategy(stratOBJ, args.strategy, overrides)
        print(f"Applied {len(overrides)} parameter overrides from {overrides_path}")

    # Build kwargs based on sizing mode
    bt_kwargs = {
        'strategy': args.strategy,
        'stratOBJ': stratOBJ,
        'start': args.start,
        'end': args.end,
        'verbose': args.verbose,
        'slippage_ticks': args.slippage,
        'comm_per_contract': args.commission,
        'position_sizing': args.sizing,
        'enforce_trading_hours': args.enforce_hours,
        'stop_after': args.stop_after,
        'hist_data_path': args.hist_data_path,
        'custom_indicators_dir': args.custom_indicators_dir,
    }

    # Add equity-related options based on sizing mode
    if args.sizing == 'fixed':
        bt_kwargs['fixed_volume'] = args.volume
        if args.equity and args.equity != 100000:
            # Only set initial_equity if explicitly provided and not default
            bt_kwargs['initial_equity'] = args.equity
    else:
        # RPO or half_kelly require equity
        bt_kwargs['initial_equity'] = args.equity
        bt_kwargs['risk_per_operation'] = args.risk

    if args.max_volume:
        bt_kwargs['max_volume'] = args.max_volume

    bt = BT_Manager(**bt_kwargs)

    try:
        results = bt.run()
    except Exception:
        _logger.error("Single-strategy backtest failed for strategy %s", args.strategy, exc_info=True)
        raise

    # Output metrics as JSON for stress testing (machine-readable)
    if args.metrics_json:
        metrics_output = results.get('metrics', {})
        # Add key fields for stress test results
        metrics_output['total_pnl'] = results.get('total_pnl', 0)
        metrics_output['initial_equity'] = results.get('initial_equity')
        metrics_output['final_equity'] = results.get('final_equity')
        metrics_output['trade_count'] = len(results.get('trades', []))
        # Use special marker so we can find it in stdout
        print(f"###METRICS_JSON_START###{json.dumps(metrics_output)}###METRICS_JSON_END###")

    if args.save:
        folder = bt.save_results(backtest_name=args.name)
        print(f"\nResults saved to: {folder}")

        if args.dashboard:
            print("\nLaunching Streamlit dashboard...")
            print(f"Run: streamlit run streamlit_app/app.py")
            print(f"Then select the backtest from: {folder}")

    return results


def run_portfolio(args, stratOBJ):
    """
    Run portfolio backtest using PortfolioOrchestrator.

    Multiple strategies advance through time together with synchronized
    equity and margin tracking.
    """
    from engine._12_portfolio_orchestrator import PortfolioOrchestrator

    orchestrator = PortfolioOrchestrator(
        strategies=args.strategies,
        stratOBJ=stratOBJ,
        start=args.start,
        end=args.end,
        initial_equity=args.equity,
        verbose=args.verbose,
        slippage_ticks=args.slippage,
        comm_per_contract=args.commission,
        max_volume=args.max_volume,
        enforce_trading_hours=args.enforce_hours,
        hist_data_path=args.hist_data_path,
        position_sizing=args.sizing,
        fixed_volume=getattr(args, 'volume', 1) or 1,
        risk_per_operation=args.risk,
        custom_indicators_dir=args.custom_indicators_dir,
    )

    try:
        results = orchestrator.run()
    except Exception:
        _logger.error("Portfolio backtest failed for strategies %s", args.strategies, exc_info=True)
        raise

    # Print per-strategy summary
    print("\n=== Per-Strategy Summary ===")
    for strat_id, trades in results['strategy_trades'].items():
        if not trades:
            print(f"Strategy {strat_id}: No trades")
            continue

        total_pnl = sum(t['pnl'] for t in trades)
        wins = sum(1 for t in trades if t['pnl'] > 0)
        losses = sum(1 for t in trades if t['pnl'] <= 0)
        win_rate = (wins / len(trades) * 100) if trades else 0

        print(f"Strategy {strat_id}: {len(trades)} trades | "
              f"PnL: ${total_pnl:+,.2f} | "
              f"Win Rate: {win_rate:.1f}%")

    # Output metrics as JSON (machine-readable, used by worker orchestrator)
    if args.metrics_json:
        pm = results.get('portfolio_metrics', {})
        metrics_output = {
            'total_pnl': pm.get('total_pnl', 0),
            'total_trades': pm.get('total_trades', 0),
            'win_rate': pm.get('win_rate', 0),
            'sharpe_ratio': pm.get('sharpe_ratio', 0),
            'max_drawdown': pm.get('max_drawdown', 0),
            'max_drawdown_pct': pm.get('max_drawdown_pct', 0),
            'initial_equity': results.get('initial_equity'),
            'final_equity': results.get('final_equity'),
        }
        print(f"###METRICS_JSON_START###{json.dumps(metrics_output)}###METRICS_JSON_END###")

    # Save results if requested
    saved_folder = None
    if args.save:
        # Check for env var first (set by integration test runner), else use default
        portfolio_logs_path = os.getenv('PORTFOLIO_LOGS_PATH') or str(DEFAULT_PORTFOLIO_LOGS_PATH)
        saved_folder = orchestrator.save_results(portfolio_logs_path, backtest_name=args.name)
        print(f"\nResults saved to: {saved_folder}")

    # Launch dashboard if requested
    if args.dashboard:
        print("\nLaunching Streamlit dashboard...")
        print(f"Run: streamlit run streamlit_app/app.py")
        if saved_folder:
            print(f"Then select the portfolio from: {saved_folder}")

    return results


def _serialize_portfolio_results(results: dict) -> dict:
    """
    Serialize portfolio results for dashboard consumption.

    Converts EquitySnapshot objects to dicts for JSON compatibility.

    Args:
        results: Raw results from PortfolioOrchestrator.run()

    Returns:
        Serialized results dict
    """
    from datetime import datetime

    serialized = dict(results)

    # Serialize equity_curve (list of EquitySnapshot dataclass objects)
    if 'equity_curve' in results:
        serialized['equity_curve'] = [
            {
                'timestamp': snap.timestamp.isoformat() if isinstance(snap.timestamp, datetime) else snap.timestamp,
                'equity': snap.equity,
                'margin_used': snap.margin_used,
                'open_position_count': snap.open_position_count,
                'margin_utilization_pct': snap.margin_utilization_pct,
            }
            for snap in results['equity_curve']
        ]

    return serialized


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise  # Let argparse exit codes propagate
    except Exception:
        _logger.error("Unhandled exception in main", exc_info=True)
        raise
