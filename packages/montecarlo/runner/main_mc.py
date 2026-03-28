#!/usr/bin/env python
"""Monte Carlo simulation CLI entry point.

Usage:
    Path-based mode:
        python main_mc.py --mode path_based --strategy 1001 --sim-bars 252 --n-paths 1000

    Trade-shuffle mode:
        python main_mc.py --mode trade_shuffle --trades-file trades.json --equity 100000 --n-paths 10000
"""

import argparse
import sys
import json
from pathlib import Path

# When run as a subprocess by the worker, ensure the montecarlo package
# is importable by adding the packages/ directory to sys.path.
_PACKAGES_DIR = str(Path(__file__).resolve().parent.parent.parent)
if _PACKAGES_DIR not in sys.path:
    sys.path.insert(0, _PACKAGES_DIR)


def main():
    parser = argparse.ArgumentParser(
        description='Monte Carlo Simulation Engine',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument('--mode', choices=['path_based', 'trade_shuffle'], required=True,
                        help='Simulation mode')
    parser.add_argument('--strategy', type=int, help='Strategy ID (required for path_based)')
    parser.add_argument('--sim-bars', type=int, default=252,
                        help='Number of daily bars to simulate per path (default: 252 ~ 1 year)')
    parser.add_argument('--fit-years', type=int, default=10,
                        help='Years of history for model fitting; 0 = all available (default: 10)')
    parser.add_argument('--n-paths', type=int, default=1000, help='Number of MC paths (default: 1000)')
    parser.add_argument('--batch-size', type=int, default=None,
                        help='Batch size for path generation (default: auto-calculated from n_paths)')
    parser.add_argument('--hist-data-path', type=str, default='',
                        help='Path to historical data folder')
    parser.add_argument('--strategies-path', type=str, default='',
                        help='Path to strategies folder')
    parser.add_argument('--equity', type=float, default=100000, help='Initial equity (default: 100000)')
    parser.add_argument('--sizing', choices=['fixed', 'rpo', 'half_kelly'], default='fixed',
                        help='Position sizing mode (default: fixed)')
    parser.add_argument('--risk', type=float, default=0.02, help='Risk per operation (default: 0.02)')
    parser.add_argument('--volume', type=int, default=1, help='Fixed volume in contracts (default: 1)')
    parser.add_argument('--max-volume', type=int, default=None, help='Max contracts per trade')
    parser.add_argument('--slippage', type=float, default=1.5, help='Slippage in ticks (default: 1.5)')
    parser.add_argument('--commission', type=float, default=0.62, help='Commission per contract (default: 0.62)')
    parser.add_argument('--trades-file', type=str,
                        help='Path to trades JSON file for trade_shuffle mode')
    parser.add_argument('--shuffle-mode', choices=['simple', 'block'], default='simple',
                        help='Shuffle mode (default: simple)')
    parser.add_argument('--block-size', type=int, default=5, help='Block size for block shuffle (default: 5)')
    parser.add_argument('--seed', type=int, default=None, help='Random seed for reproducibility')
    parser.add_argument('--save', action='store_true', help='Save results to output directory')
    parser.add_argument('--output-dir', type=str, default=None, help='Output directory for saved results')
    parser.add_argument('--metrics-json', action='store_true',
                        help='Output metrics as JSON to stdout (machine-readable)')
    parser.add_argument('--custom-indicators-dir', type=str, default=None,
                        help='Path to custom indicator modules')
    parser.add_argument('--workers', type=int, default=None,
                        help='Max parallel worker processes (default: cpu_count - 1)')

    args = parser.parse_args()

    if args.mode == 'path_based':
        _run_path_based(args)
    else:
        _run_trade_shuffle(args)


def _run_path_based(args):
    """Execute path-based Monte Carlo simulation."""
    if not args.strategy:
        print("Error: --strategy is required for path_based mode")
        sys.exit(1)

    # Resolve paths -- follow same pattern as backtest-engine/main.py
    engine_root = Path(__file__).resolve().parent.parent.parent / 'backtest-engine'

    hist_data_path = args.hist_data_path or str(engine_root / 'hist_data')
    strategies_path = args.strategies_path or str(engine_root / 'Strategies')

    fit_label = f"last {args.fit_years} years" if args.fit_years > 0 else "all available"
    print(f"{'='*60}")
    print(f"Monte Carlo Path-Based Simulation")
    print(f"{'='*60}")
    print(f"  Strategy:   {args.strategy}")
    print(f"  Sim bars:   {args.sim_bars} (daily bars per path)")
    print(f"  Fit window: {fit_label}")
    print(f"  Paths:      {args.n_paths}")
    print(f"  Batch size: {args.batch_size or 'auto'}")
    print(f"  Equity:     ${args.equity:,.0f}")
    print(f"  Sizing:     {args.sizing}")
    print(f"  Seed:       {args.seed}")
    print(f"  Hist data:  {hist_data_path}")
    print(f"{'='*60}")

    # Load strategy definitions
    from ibkr_core import StratOBJ

    print(f"[MC] Loading strategy definitions from {strategies_path}...")
    stratOBJ = StratOBJ().upload(strategies_folder=strategies_path, connect_ib=False)
    print(f"[MC] Strategies loaded successfully")

    from montecarlo.runner.mc_runner import MonteCarloRunner

    runner = MonteCarloRunner(
        strategy_id=args.strategy,
        stratOBJ=stratOBJ,
        hist_data_path=hist_data_path,
        strategies_path=strategies_path,
        initial_equity=args.equity,
        position_sizing=args.sizing,
        risk_per_operation=args.risk,
        fixed_volume=args.volume,
        max_volume=args.max_volume,
        slippage_ticks=args.slippage,
        comm_per_contract=args.commission,
        custom_indicators_dir=args.custom_indicators_dir,
    )

    results = runner.run_path_based(
        n_paths=args.n_paths,
        sim_bars=args.sim_bars,
        fit_years=args.fit_years,
        n_workers=args.workers,
        batch_size=args.batch_size,
        seed=args.seed,
    )

    _output_results(runner, results, args)


def _run_trade_shuffle(args):
    """Execute trade-shuffle Monte Carlo simulation."""
    if not args.trades_file:
        print("Error: --trades-file is required for trade_shuffle mode")
        sys.exit(1)

    trades_path = Path(args.trades_file)
    if not trades_path.exists():
        print(f"Error: Trades file not found: {trades_path}")
        sys.exit(1)

    if str(trades_path).endswith('.parquet'):
        import polars as pl_trades
        df_trades = pl_trades.read_parquet(trades_path)
        trades = df_trades.to_dicts()
    else:
        with open(trades_path, 'r') as f:
            trades = json.load(f)

    if not isinstance(trades, list) or not trades:
        print("Error: Trades file must contain a non-empty JSON array of trade objects")
        sys.exit(1)

    # Validate trades have 'pnl' field
    for i, t in enumerate(trades):
        if 'pnl' not in t:
            print(f"Error: Trade at index {i} missing 'pnl' field")
            sys.exit(1)

    from montecarlo.runner.mc_runner import MonteCarloRunner

    # For trade shuffle we don't need a full runner with strategy config,
    # but we create one with minimal params for the save_results interface
    runner = MonteCarloRunner(
        strategy_id=0,
        stratOBJ=None,
        hist_data_path='',
        initial_equity=args.equity,
    )

    results = runner.run_trade_shuffle(
        trades=trades,
        initial_equity=args.equity,
        n_paths=args.n_paths,
        mode=args.shuffle_mode,
        block_size=args.block_size,
        seed=args.seed,
    )

    _output_results(runner, results, args)


def _output_results(runner, results: dict, args):
    """Handle output: metrics JSON marker, save to disk."""
    summary = results.get('statistics', {})

    # Print human-readable summary
    n_completed = results.get('n_completed', 0)
    n_failed = results.get('n_failed', 0)
    mode = results.get('mode', 'unknown')
    print(f"\n{'='*60}")
    print(f"Monte Carlo Results ({mode})")
    print(f"{'='*60}")
    print(f"  Completed: {n_completed} / {results.get('n_paths', 0)}")
    print(f"  Failed:    {n_failed}")
    if n_completed > 0 and isinstance(summary, dict):
        pnl = summary.get('total_pnl', {})
        if isinstance(pnl, dict) and pnl.get('median') is not None:
            print(f"  Median PnL:    ${pnl['median']:,.2f}")
            print(f"  P5 PnL:        ${pnl.get('p5', 0):,.2f}")
            print(f"  P95 PnL:       ${pnl.get('p95', 0):,.2f}")
        dd = summary.get('max_drawdown_pct', {})
        if isinstance(dd, dict) and dd.get('median') is not None:
            print(f"  Median MaxDD:  {dd['median']:.1f}%")
    print(f"{'='*60}\n")

    if args.metrics_json:
        # Sanitize NaN/Inf values before JSON output
        clean_summary = _sanitize_for_json(summary)
        print(f"###METRICS_JSON_START###{json.dumps(clean_summary, default=str)}###METRICS_JSON_END###")

    if args.save:
        output_dir = args.output_dir
        if not output_dir:
            output_dir = str(Path.cwd() / 'mc_results')
        save_path = runner.save_results(results, output_dir)
        print(f"Results saved to: {save_path}")
        print(f"###MC_SAVED_FOLDER###{save_path}###MC_SAVED_FOLDER_END###")


def _sanitize_for_json(obj):
    """Replace NaN/Inf float values with None for valid JSON."""
    import math
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


if __name__ == '__main__':
    main()
