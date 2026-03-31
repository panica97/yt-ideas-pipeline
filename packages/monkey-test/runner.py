"""Monkey Test runner -- main orchestrator and CLI entry point.

Runs the backtest engine to obtain real trades, then generates N random-entry
simulations on the same OHLC data and compares performance distributions.

Usage::

    python -m packages.monkey_test.runner \
        --strategy 1001 \
        --n-sims 1000 \
        --mode A \
        --hist-data-path /path/to/hist_data \
        --strategies-path /path/to/Strategies \
        --start 2020-01-01 \
        --end 2024-12-31 \
        --metrics-json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Ensure packages/ and the monkey-test dir are on sys.path so both sibling
# packages (backtest-engine, ibkr-core) and local modules are importable.
# The on-disk directory is ``monkey-test`` (hyphen), but Python imports need
# underscores.  We add the directory itself so ``import extractor`` works,
# and also register it as ``monkey_test`` in sys.modules for any code that
# tries ``from monkey_test.xxx import ...``.
# ---------------------------------------------------------------------------
_PACKAGES_DIR = str(Path(__file__).resolve().parent.parent)
_SELF_DIR = str(Path(__file__).resolve().parent)
for _p in (_PACKAGES_DIR, _SELF_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_for_json(obj: Any) -> Any:
    """Replace NaN/Inf float values with None for valid JSON."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj


def _report_progress(completed: int, total: int) -> None:
    """Emit a progress marker that the worker can parse."""
    print(
        f'###MC_PROGRESS###'
        f'{{"completed": {completed}, "total": {total}}}'
        f'###MC_PROGRESS_END###',
        flush=True,
    )


# ---------------------------------------------------------------------------
# Core run logic
# ---------------------------------------------------------------------------

def run_monkey_test(
    strategy_id: int,
    start_date: str,
    end_date: str,
    n_sims: int = 1000,
    mode: str = "A",
    hist_data_path: Optional[str] = None,
    strategies_path: Optional[str] = None,
    seed: Optional[int] = None,
    histogram_bins: int = 30,
    progress_every: int = 50,
) -> Dict[str, Any]:
    """Execute a full monkey-test run and return the result dict.

    Steps
    -----
    1. Load strategy via ``ibkr_core.StratOBJ`` and run the backtest engine
       to obtain the real trades.
    2. Extract trade parameters (n_trades, holding distribution, direction).
    3. Load OHLC close prices for the simulation period.
    4. Run *n_sims* random-entry simulations.
    5. Aggregate and compare to the real strategy.
    """
    t0 = time.time()

    # ---- resolve default paths ----
    engine_root = Path(__file__).resolve().parent.parent / "backtest-engine"
    engine_path = engine_root / "engine"

    if hist_data_path is None:
        hist_data_path = str(engine_root / "hist_data")
    if strategies_path is None:
        strategies_path = str(engine_root / "Strategies")

    # Put engine dirs on sys.path so BT_Manager imports work
    for p in (str(engine_path), str(engine_root)):
        if p not in sys.path:
            sys.path.insert(0, p)

    # ---- 1. Run the real backtest ----
    print("[MonkeyTest] Loading strategy definitions...", flush=True)
    from ibkr_core import StratOBJ  # type: ignore[import-untyped]

    strat_obj = StratOBJ().upload(strategies_folder=strategies_path, connect_ib=False)

    from _10_backtester import BT_Manager  # type: ignore[import-untyped]

    print(f"[MonkeyTest] Running real backtest for strategy {strategy_id} "
          f"({start_date} to {end_date})...", flush=True)

    bt = BT_Manager(
        strategy=strategy_id,
        stratOBJ=strat_obj,
        start=start_date,
        end=end_date,
        hist_data_path=hist_data_path,
        verbose=False,
        silent=True,
    )
    bt_result = bt.run()

    trades = bt_result.get("trades", [])
    if not trades:
        raise RuntimeError("Real backtest produced 0 trades -- cannot run monkey test.")

    print(f"[MonkeyTest] Real backtest: {len(trades)} trades, "
          f"PnL={bt_result.get('total_pnl', 0):.2f}", flush=True)

    # ---- 2. Extract trade parameters ----
    from extractor import extract_trade_params  # noqa: E402

    params = extract_trade_params(trades)
    n_trades = params["n_trades"]
    holding_distribution = params["holding_distribution"]
    max_bars = params["max_bars"]
    direction = params["direction"]
    trade_pnls = params["trade_pnls"]

    print(f"[MonkeyTest] Extracted: n_trades={n_trades}, max_bars={max_bars}, "
          f"direction={direction}, mode={mode}", flush=True)

    # ---- 3. Get OHLC close prices ----
    # The BT_Manager loaded and resampled all data into self.full_data.
    # The primary timeframe is the one the strategy trades on.
    primary_tf = strat_obj.process_freq(strategy_id)
    primary_df = bt.full_data.get(primary_tf)

    if primary_df is None or len(primary_df) == 0:
        raise RuntimeError(
            f"No OHLC data found for primary timeframe '{primary_tf}' after backtest."
        )

    # Extract close prices as numpy array
    ohlc_closes = primary_df["close"].to_numpy().astype(np.float64)
    n_bars = len(ohlc_closes)

    print(f"[MonkeyTest] OHLC data: {n_bars} bars on {primary_tf}", flush=True)

    # ---- 4. Compute real strategy metrics ----
    from metrics import compute_metrics  # noqa: E402

    real_pnl_arr = np.array(trade_pnls, dtype=np.float64)
    real_equity = np.cumsum(real_pnl_arr)
    real_metrics = compute_metrics(real_pnl_arr, real_equity)

    print(f"[MonkeyTest] Real metrics: net_profit={real_metrics['net_profit']:.2f}, "
          f"return_dd={real_metrics['return_dd']:.4f}, "
          f"win_rate={real_metrics['win_rate']:.2%}", flush=True)

    # ---- 5. Run N simulations ----
    from generator import generate_random_entries  # noqa: E402
    from simulator import simulate_one  # noqa: E402

    # Early exit: check if ANY trades can be placed
    available_bars = n_bars - max_bars - 1
    if available_bars < 1:
        print(f"[MonkeyTest] ERROR: Period too short — {n_bars} bars available, "
              f"need at least {max_bars + 2} for one trade. Skipping simulations.",
              flush=True)
        return {
            "error": f"Period too short: {n_bars} bars, need >= {max_bars + 2}",
            "real_strategy": real_metrics,
            "n_simulations": 0,
            "sim_results": [],
            "warnings": [f"Zero valid entry bars ({n_bars} bars, max_bars={max_bars})"],
            "percentile": None,
            "p_value": None,
            "n_trades_requested": n_trades,
            "n_trades_actual": 0,
        }

    rng = np.random.default_rng(seed)

    sim_results: List[Dict[str, float]] = []
    t_sim = time.time()

    print(f"[MonkeyTest] Starting {n_sims} simulations...", flush=True)
    for i in range(n_sims):
        entries = generate_random_entries(
            n_bars=n_bars,
            n_trades=n_trades,
            max_bars=max_bars,
            holding_distribution=holding_distribution,
            mode=mode,
            rng=rng,
        )
        result = simulate_one(ohlc_closes, entries, direction)
        sim_results.append(result)

        if (i + 1) % progress_every == 0 or (i + 1) == n_sims:
            _report_progress(i + 1, n_sims)

    sim_duration = time.time() - t_sim
    print(f"[MonkeyTest] Simulations done in {sim_duration:.1f}s "
          f"({n_sims / max(sim_duration, 0.001):.0f} sims/sec)", flush=True)

    # ---- 6. Aggregate ----
    from aggregator import aggregate_results  # noqa: E402

    result = aggregate_results(
        sim_results=sim_results,
        real_metrics=real_metrics,
        mode=mode,
        n_trades_requested=n_trades,
        histogram_bins=histogram_bins,
    )

    total_duration = time.time() - t0
    print(f"[MonkeyTest] Complete in {total_duration:.1f}s. "
          f"Percentile={result.get('percentile')}, p_value={result.get('p_value')}",
          flush=True)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monkey Test — random-entry robustness simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--strategy", type=int, required=True,
                        help="Strategy ID to test")
    parser.add_argument("--n-sims", type=int, default=1000,
                        help="Number of simulations (default: 1000)")
    parser.add_argument("--mode", choices=["A", "B"], default="A",
                        help="Holding period mode: A=empirical, B=max_bars (default: A)")
    parser.add_argument("--hist-data-path", type=str, default=None,
                        help="Path to historical data folder")
    parser.add_argument("--strategies-path", type=str, default=None,
                        help="Path to strategies folder")
    parser.add_argument("--start", type=str, required=True,
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, required=True,
                        help="End date (YYYY-MM-DD)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducibility")
    parser.add_argument("--histogram-bins", type=int, default=30,
                        help="Number of histogram bins (default: 30)")
    parser.add_argument("--metrics-json", action="store_true",
                        help="Output JSON result via stdout markers")
    parser.add_argument("--save", action="store_true",
                        help="Save result JSON to disk")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory (used with --save)")

    args = parser.parse_args()

    print(f"{'=' * 60}")
    print("Monkey Test — Random Entry Robustness Simulation")
    print(f"{'=' * 60}")
    print(f"  Strategy:    {args.strategy}")
    print(f"  Period:      {args.start} to {args.end}")
    print(f"  Simulations: {args.n_sims}")
    print(f"  Mode:        {args.mode}")
    print(f"  Seed:        {args.seed}")
    print(f"{'=' * 60}")

    try:
        result = run_monkey_test(
            strategy_id=args.strategy,
            start_date=args.start,
            end_date=args.end,
            n_sims=args.n_sims,
            mode=args.mode,
            hist_data_path=args.hist_data_path,
            strategies_path=args.strategies_path,
            seed=args.seed,
            histogram_bins=args.histogram_bins,
        )
    except Exception as exc:
        print(f"[MonkeyTest] FATAL: {exc}", flush=True)
        sys.exit(1)

    # Human-readable summary
    print(f"\n{'=' * 60}")
    print("Monkey Test Results")
    print(f"{'=' * 60}")
    real = result.get("real_strategy", {})
    print(f"  Real strategy:")
    print(f"    Net Profit:    {real.get('net_profit', 0):.2f}")
    print(f"    Return/DD:     {real.get('return_dd', 0):.4f}")
    print(f"    Win Rate:      {real.get('win_rate', 0):.2%}")
    print(f"    Profit Factor: {real.get('profit_factor', 0):.4f}")
    print(f"  Monkey distribution ({result.get('n_simulations', 0)} sims):")
    print(f"    Percentile:    {result.get('percentile')}")
    print(f"    p-value:       {result.get('p_value')}")
    n_actual = result.get("n_trades_actual", "?")
    n_req = result.get("n_trades_requested", "?")
    print(f"    Trades placed: {n_actual} / {n_req} requested")
    for w in result.get("warnings", []):
        print(f"    WARNING: {w}")
    print(f"{'=' * 60}\n")

    if args.metrics_json:
        clean = _sanitize_for_json(result)
        json_str = json.dumps(clean, default=str)
        print(f"###METRICS_JSON_START###{json_str}###METRICS_JSON_END###", flush=True)

    if args.save:
        output_dir = args.output_dir or str(Path.cwd() / "monkey_results")
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        result_file = out_path / "monkey_test_result.json"
        clean = _sanitize_for_json(result)
        with open(result_file, "w") as f:
            json.dump(clean, f, indent=2, default=str)
        print(f"Results saved to: {result_file}")


if __name__ == "__main__":
    main()
