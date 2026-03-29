"""
MonteCarloRunner -- orchestrates path-based and trade-shuffle Monte Carlo simulations.

Path-based mode:
  1. Loads historical data via DataPreprocessor
  2. Fits SyntheticOHLCGenerator (GARCH + OHLC structure)
  3. Runs baseline backtest on historical data
  4. Generates synthetic OHLC paths in batches
  5. Runs BT_Manager on each path with preloaded_data
  6. Aggregates results via MonteCarloAggregator

Trade-shuffle mode:
  1. Takes existing trade PnLs
  2. Runs TradeShuffler (simple or block bootstrap)
  3. Aggregates via MonteCarloAggregator
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import time
import numpy as np
import polars as pl
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ..config import MonteCarloConfig
from ..generator.path_generator import SyntheticOHLCGenerator
from ..shuffler.trade_shuffler import TradeShuffler
from ..analysis.aggregator import MonteCarloAggregator
from ..path_validation import PathValidationCollector


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


def _get_engine_path() -> str:
    """Resolve the backtest-engine/engine directory."""
    return str(Path(__file__).resolve().parent.parent.parent / 'backtest-engine' / 'engine')


def _get_engine_root() -> str:
    """Resolve the backtest-engine root directory."""
    return str(Path(__file__).resolve().parent.parent.parent / 'backtest-engine')


_worker_bt_cls = None  # set once per worker process by _init_worker


def _init_worker(engine_path: str, engine_root: str) -> None:
    """Initializer for each worker process in the pool.

    Adds engine paths to sys.path and imports BT_Manager once.
    Called exactly once per worker process (not per task).
    """
    global _worker_bt_cls
    for p in (engine_path, engine_root):
        if p not in sys.path:
            sys.path.insert(0, p)
    from _10_backtester import BT_Manager
    _worker_bt_cls = BT_Manager


def _run_path_worker(bt_kwargs: dict) -> dict:
    """Run a single backtest in a worker process.

    Uses the BT_Manager class cached by _init_worker.
    Returns a result dict with status and backtest output.
    """
    try:
        bt = _worker_bt_cls(**bt_kwargs)
        bt_result = bt.run()
        return {'status': 'ok', 'result': bt_result}
    except Exception as exc:
        return {'status': 'error', 'error': str(exc)}


class MonteCarloRunner:
    """Orchestrates Monte Carlo simulations using the backtest engine."""

    def __init__(
        self,
        strategy_id: int,
        stratOBJ,
        hist_data_path: str,
        strategies_path: Optional[str] = None,
        initial_equity: float = 100_000,
        position_sizing: str = 'fixed',
        risk_per_operation: float = 0.02,
        fixed_volume: int = 1,
        max_volume: Optional[int] = None,
        slippage_ticks: float = 1.5,
        comm_per_contract: float = 0.62,
        custom_indicators_dir: Optional[str] = None,
    ):
        self.strategy_id = strategy_id
        self.stratOBJ = stratOBJ
        self.hist_data_path = hist_data_path
        self.strategies_path = strategies_path
        self.initial_equity = initial_equity
        self.position_sizing = position_sizing
        self.risk_per_operation = risk_per_operation
        self.fixed_volume = fixed_volume
        self.max_volume = max_volume
        self.slippage_ticks = slippage_ticks
        self.comm_per_contract = comm_per_contract
        self.custom_indicators_dir = custom_indicators_dir

    # ------------------------------------------------------------------
    # Path-based Monte Carlo
    # ------------------------------------------------------------------

    @staticmethod
    def _auto_batch_size(n_paths: int) -> int:
        """Calculate optimal batch size from path count.

        Targets ~4 batches for good progress granularity, capped at 500
        to limit peak memory usage.
        """
        return min(500, max(4, n_paths // 4))

    def run_path_based(
        self,
        n_paths: int,
        sim_bars: int = MonteCarloConfig.DEFAULT_SIM_BARS,
        fit_years: int = MonteCarloConfig.DEFAULT_FIT_YEARS,
        n_workers: Optional[int] = None,
        batch_size: Optional[int] = None,
        seed: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """Run path-based Monte Carlo simulation.

        Fits the model on maximum available history (or last `fit_years`),
        then generates `sim_bars`-length synthetic OHLC paths and runs
        the backtest engine on each.

        Returns a dict with aggregated statistics, baseline comparison,
        model params, and failure info.
        """
        if batch_size is None:
            batch_size = self._auto_batch_size(n_paths)

        t0 = time.time()
        self._report_phase("initializing", "Loading backtest engine...")

        # Runtime imports from backtest-engine
        engine_path = _get_engine_path()
        engine_root = _get_engine_root()
        for p in (engine_path, engine_root):
            if p not in sys.path:
                sys.path.insert(0, p)

        from _01_data_processor import DataPreprocessor
        from _10_backtester import BT_Manager

        # --- 1. Load ALL historical data (or last fit_years) ---
        self._report_phase("loading_data", "Loading historical data...")
        t1 = time.time()
        preprocessor = DataPreprocessor(data_folder=self.hist_data_path)
        ind_list = self.stratOBJ.ind_list(self.strategy_id)
        timeframes = list(ind_list.keys())
        symbol = self.stratOBJ.symbol(self.strategy_id)
        print(f"  Strategy {self.strategy_id}: symbol={symbol}, timeframes={timeframes}")

        # Compute fitting start date from fit_years (0 = all available)
        fit_start_date = None
        if fit_years > 0:
            from datetime import timedelta
            fit_start_dt = datetime.now() - timedelta(days=fit_years * 365)
            fit_start_date = fit_start_dt.strftime("%Y-%m-%d")
            print(f"  Fitting window: {fit_start_date} to present ({fit_years} years)")
        else:
            print(f"  Fitting window: all available data")

        # Load full data for all timeframes within fitting window
        hist_data_all = preprocessor.load_and_resample(
            symbol=symbol,
            timeframes=timeframes,
            start_date=fit_start_date,
            end_date=None,
        )
        print(f"  Historical data loaded in {time.time() - t1:.1f}s")

        # --- 1b. Load extended data for baseline if start_date is before fit window ---
        baseline_data_start = fit_start_date  # default: baseline uses same data
        if start_date and fit_start_date:
            if start_date < fit_start_date:
                print(f"  Baseline start {start_date} is before fit window {fit_start_date}, "
                      f"loading extended data for baseline...")
                baseline_hist_data = preprocessor.load_and_resample(
                    symbol=symbol,
                    timeframes=timeframes,
                    start_date=start_date,
                    end_date=end_date,
                )
                baseline_data_start = start_date
                print(f"  WARNING: Baseline window ({start_date} to {end_date}) extends "
                      f"before model fitting window ({fit_start_date}). Model was fitted "
                      f"on different data than the baseline period.")
                # Validate extended data has expected range
                ext_base_tf = list(baseline_hist_data.keys())[0]
                ext_dates = baseline_hist_data[ext_base_tf]["date"]
                if len(ext_dates) > 0:
                    ext_start_actual = str(ext_dates[0].date())
                    if ext_start_actual > start_date:
                        print(f"  WARNING: Baseline data starts at {ext_start_actual}, "
                              f"later than requested {start_date}. Data may be incomplete.")
            else:
                baseline_hist_data = hist_data_all
        elif start_date and not fit_start_date:
            # fit_years=0 (all data) -- no truncation, reuse same data
            baseline_hist_data = hist_data_all
        else:
            baseline_hist_data = hist_data_all

        # --- 2. Fit generator on raw 1-min data (full fitting window) ---
        self._report_phase("fitting_model", "Fitting GARCH + OHLC model...")
        t2 = time.time()
        generator = SyntheticOHLCGenerator()
        raw_1min = preprocessor.load_csv(symbol)
        if fit_start_date:
            raw_1min = raw_1min.filter(
                pl.col("date") >= datetime.strptime(fit_start_date, "%Y-%m-%d")
            )
        print(f"  Raw 1-min data: {len(raw_1min)} rows")
        generator.fit(raw_1min, timeframes)
        print(f"  Model fitted in {time.time() - t2:.1f}s")

        base_tf = generator.base_timeframe

        # --- Derive baseline window ---
        # If start_date/end_date are provided, filter to that exact date range
        # (matching the original backtest period). Otherwise fall back to
        # "last sim_bars trading days" of all data.
        # Use baseline_hist_data (which may have extended range) instead of
        # hist_data_all (which is limited to the fit window).
        base_df_all = baseline_hist_data[base_tf]

        # Count unique trading dates to derive bars-per-day
        base_dates = base_df_all["date"].dt.date()
        unique_days = base_dates.unique()
        n_trading_days = len(unique_days)
        bars_per_day = len(base_df_all) / max(n_trading_days, 1)

        if start_date and end_date:
            # Date-range mode: filter to the exact backtest period
            bl_start_filter = datetime.strptime(start_date, "%Y-%m-%d")
            bl_end_filter = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59
            )
            baseline_slice = base_df_all.filter(
                (pl.col("date") >= bl_start_filter) &
                (pl.col("date") <= bl_end_filter)
            )
            if len(baseline_slice) == 0:
                raise ValueError(
                    f"No data found for baseline date range {start_date} to {end_date}"
                )
            n_periods = len(baseline_slice)
            baseline_start = start_date
            baseline_end = end_date
            # Override sim_bars to match the actual number of bars in the date range
            actual_trading_days = len(baseline_slice["date"].dt.date().unique())
            sim_bars = actual_trading_days
            print(f"  Base timeframe: {base_tf} ({bars_per_day:.1f} bars/day)")
            print(f"  Baseline window (date-filtered): {baseline_start} to {baseline_end}")
            print(f"  Baseline: {n_periods} {base_tf} bars, "
                  f"{actual_trading_days} trading days")
        else:
            # Fallback: last sim_bars trading days
            # Convert sim_bars (trading days) to base_tf bar count
            n_periods = round(sim_bars * bars_per_day)
            n_periods = min(n_periods, len(base_df_all))
            if n_periods < round(sim_bars * bars_per_day):
                actual_days = round(n_periods / bars_per_day)
                print(f"  WARNING: Only {n_trading_days} trading days available, "
                      f"using {actual_days} instead of requested {sim_bars}")

            baseline_slice = base_df_all.tail(n_periods)
            baseline_start = str(baseline_slice[0, "date"].date())
            baseline_end = str(baseline_slice[-1, "date"].date())

            print(f"  Base timeframe: {base_tf} ({bars_per_day:.1f} bars/day)")
            print(f"  Simulation: {sim_bars} trading days = {n_periods} {base_tf} bars")
            print(f"  Baseline window: {baseline_start} to {baseline_end} "
                  f"(last {n_periods} of {len(base_df_all)} bars)")

        # Create baseline data: filter all timeframes to baseline window
        baseline_data = {}
        bl_start_dt = datetime.strptime(baseline_start, "%Y-%m-%d")
        bl_end_dt = datetime.strptime(baseline_end, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )
        for tf, df in baseline_hist_data.items():
            baseline_data[tf] = df.filter(
                (pl.col("date") >= bl_start_dt) &
                (pl.col("date") <= bl_end_dt)
            )
        base_df = baseline_data[base_tf]

        # Validate model fit quality against full fitting data (not just baseline)
        from ..validation import validate_model_fit
        validation_paths = MonteCarloConfig.VALIDATION_TEST_PATHS
        fit_quality = validate_model_fit(generator, base_df_all, n_test_paths=validation_paths) if validation_paths > 0 else None
        if fit_quality is not None:
            q_score = fit_quality.get('quality_score', '?')
            q_max = fit_quality.get('max_score', '?')
            print(f"  Model fit quality: {fit_quality['overall_quality']} "
                  f"(score {q_score}/{q_max})")
            diags = fit_quality.get('diagnostics', [])
            if diags:
                for diag in diags:
                    print(f"  - {diag}")
        else:
            print(f"  Model fit validation: skipped")

        # --- 3. Run baseline backtest on baseline window ---
        self._report_phase("baseline_backtest", "Running baseline backtest...")
        t3 = time.time()
        baseline_result = self._run_backtest(
            BT_Manager, preloaded_data=baseline_data,
            start_override=baseline_start, end_override=baseline_end,
        )
        baseline_metrics = baseline_result.get('metrics', {})
        baseline_metrics['total_pnl'] = baseline_result.get('total_pnl', 0)
        baseline_metrics['trade_count'] = len(baseline_result.get('trades', []))
        baseline_metrics['avg_trade_pnl'] = baseline_metrics['total_pnl'] / baseline_metrics['trade_count'] if baseline_metrics['trade_count'] else 0
        baseline_metrics['initial_equity'] = baseline_result.get('initial_equity')
        baseline_metrics['final_equity'] = baseline_result.get('final_equity')
        baseline_duration = time.time() - t3
        print(f"  Baseline: {baseline_metrics['trade_count']} trades, "
              f"PnL=${baseline_metrics['total_pnl']:.2f}, "
              f"completed in {baseline_duration:.1f}s")

        # --- 4. Generate paths and run backtests ---
        self._report_phase("mc_simulation", f"Starting Monte Carlo: {n_paths} paths...")
        aggregator = MonteCarloAggregator()

        # Store historical close prices from baseline window for comparison chart
        hist_close = base_df["close"].to_numpy().astype(np.float64)
        aggregator.set_historical_close(hist_close)

        completed = 0
        failed = 0
        total = n_paths

        # True parallelism via multiprocessing (each process has its own GIL).
        # Default: cpu_count - 1 to leave a core for the coordinator process
        # and the orchestrator.  Orchestrator can override via n_workers to
        # account for other concurrent jobs sharing the machine.
        cpu = os.cpu_count() or 4
        max_workers = n_workers if n_workers is not None else max(1, cpu - 1)
        max_workers = max(1, min(max_workers, cpu))
        print(f"  Config: {n_paths} paths, {n_periods} periods, "
              f"batch_size={batch_size}, workers={max_workers} (multiprocessing)")
        t_sim_start = time.time()

        # Adaptive per-path timeout (with true parallelism, paths run
        # concurrently so the timeout is genuinely per-path, not per-wave)
        path_timeout = max(60, int(baseline_duration * 10))
        print(f"  Per-path timeout: {path_timeout}s (baseline: {baseline_duration:.1f}s)")

        # Build shared backtest kwargs (BT_Manager already imported above)
        bt_kwargs_base = {
            'strategy': self.strategy_id,
            'stratOBJ': self.stratOBJ,
            'start': baseline_start,
            'end': baseline_end,
            'initial_equity': self.initial_equity,
            'position_sizing': self.position_sizing,
            'risk_per_operation': self.risk_per_operation,
            'fixed_volume': self.fixed_volume,
            'slippage_ticks': self.slippage_ticks,
            'comm_per_contract': self.comm_per_contract,
            'custom_indicators_dir': self.custom_indicators_dir,
            'verbose': False,
            'silent': True,
        }
        if self.max_volume is not None:
            bt_kwargs_base['max_volume'] = self.max_volume

        batch_num = 0
        path_validator = PathValidationCollector()

        # Create a single process pool for the entire simulation.
        # _init_worker runs once per worker process, importing BT_Manager.
        with ProcessPoolExecutor(
            max_workers=max_workers,
            initializer=_init_worker,
            initargs=(engine_path, engine_root),
        ) as executor:

            for batch in generator.generate_paths(
                n_paths=n_paths,
                n_periods=n_periods,
                strategy_timeframes=timeframes,
                seed=seed,
                batch_size=batch_size,
                start_date=baseline_start,
            ):
                batch_num += 1
                n_batch = len(batch)
                batch_t0 = time.time()
                batch_ok = 0
                batch_fail = 0

                # Extract close prices before launching workers.
                # Prepend initial_price so synthetic paths start at exactly
                # the same price as historical (whose first element is
                # closes[0] = initial_price).
                batch_close_prices = []
                for pd in batch:
                    try:
                        close_arr = pd[base_tf]["close"].to_numpy().astype(np.float64)
                        batch_close_prices.append(
                            np.concatenate([[generator.initial_price], close_arr])
                        )
                    except Exception:
                        batch_close_prices.append(None)

                # Collect path statistics for post-generation validation
                path_validator.add_batch(batch, base_tf)

                # Submit all paths in this batch to the process pool
                futures = {}
                for ri in range(n_batch):
                    bt_kwargs = {**bt_kwargs_base, 'preloaded_data': batch[ri]}
                    future = executor.submit(_run_path_worker, bt_kwargs)
                    futures[future] = ri

                # Collect results as they complete (true parallelism)
                results = [None] * n_batch
                for future in as_completed(futures):
                    ri = futures[future]
                    try:
                        results[ri] = future.result(timeout=path_timeout)
                    except Exception as exc:
                        results[ri] = {'status': 'error', 'error': str(exc)}

                # Process results
                for ri, res in enumerate(results):
                    if res['status'] == 'error':
                        failed += 1
                        batch_fail += 1
                        completed += 1
                        err_msg = res.get('error', '')
                        if 'timed out' in err_msg.lower():
                            print(f"    Path {completed}/{total}: TIMEOUT", flush=True)
                        else:
                            print(f"    Path {completed}/{total}: ERROR {err_msg[:80]}",
                                  flush=True)
                        continue

                    result = res['result']
                    trades = result.get('trades', [])

                    if len(trades) == 0:
                        failed += 1
                        batch_fail += 1
                        completed += 1
                        print(f"    Path {completed}/{total}: 0 trades (skipped)",
                              flush=True)
                        continue

                    metrics = result.get('metrics', {})
                    metrics['total_pnl'] = result.get('total_pnl', 0)
                    metrics['trade_count'] = len(trades)
                    metrics['avg_trade_pnl'] = metrics['total_pnl'] / len(trades) if trades else 0

                    equity_curve = None
                    eq_hist = result.get('equity_history')
                    if eq_hist:
                        equity_curve = np.array([e['equity'] for e in eq_hist], dtype=np.float64)

                    path_close = batch_close_prices[ri] if ri < len(batch_close_prices) else None
                    aggregator.add_result(metrics, equity_curve, path_close)
                    completed += 1
                    batch_ok += 1

                batch_elapsed = time.time() - batch_t0
                total_elapsed = time.time() - t_sim_start
                remaining = (total_elapsed / max(completed, 1)) * (total - completed)
                pct = 100.0 * completed / total
                print(f"  Batch {batch_num}: {batch_ok} ok, {batch_fail} failed "
                      f"({batch_elapsed:.1f}s) | Progress: {completed}/{total} "
                      f"({pct:.0f}%) [{failed} failed] | ETA: {remaining:.0f}s",
                      flush=True)
                self._report_progress(completed, total, progress_callback)

        # --- 5. Validate generated paths ---
        path_quality = path_validator.finalize(base_df)
        pq_score = path_quality.get('score', '?')
        pq_max = path_quality.get('max_score', '?')
        print(f"  Path validation: {path_quality['quality']} "
              f"(score {pq_score}/{pq_max})")
        pq_diags = path_quality.get('diagnostics', [])
        if pq_diags:
            for diag in pq_diags:
                print(f"  - {diag}")

        # --- 6. Compute statistics ---
        self._report_phase("computing_stats", "Computing statistics...")
        sim_duration = time.time() - t_sim_start
        print(f"  Simulation completed in {sim_duration:.1f}s "
              f"({completed - failed} successful, {failed} failed)")

        stats = aggregator.compute_statistics()
        stats['n_failed'] = failed
        stats['failure_rate'] = failed / total if total > 0 else 0.0

        # Check failure rate
        if stats['failure_rate'] > MonteCarloConfig.MAX_FAILURE_RATE:
            print(
                f"  WARNING: High failure rate {stats['failure_rate']:.1%} "
                f"(threshold: {MonteCarloConfig.MAX_FAILURE_RATE:.0%})"
            )

        # --- 6. Compare to baseline ---
        comparison = aggregator.compare_to_actual(baseline_metrics)
        total_duration = time.time() - t0
        self._report_phase("done", f"Done in {total_duration:.0f}s")
        print(f"  Total MC duration: {total_duration:.1f}s")

        return {
            'mode': 'path_based',
            'n_paths': n_paths,
            'n_periods': n_periods,
            'sim_bars': sim_bars,
            'fit_years': fit_years,
            'baseline_window': f"{baseline_start} to {baseline_end}",
            'n_completed': stats.get('n_completed', 0),
            'n_failed': failed,
            'failure_rate': stats['failure_rate'],
            'statistics': aggregator.to_storage_format(),
            'baseline_metrics': baseline_metrics,
            'comparison': comparison,
            'model_params': generator.get_model_params(),
            'model_fit_quality': fit_quality,
            'path_validation': path_quality,
        }

    # ------------------------------------------------------------------
    # Trade-shuffle Monte Carlo
    # ------------------------------------------------------------------

    def run_trade_shuffle(
        self,
        trades: List[dict],
        initial_equity: float,
        n_paths: int = MonteCarloConfig.DEFAULT_SHUFFLE_PATHS,
        mode: str = 'simple',
        block_size: int = MonteCarloConfig.DEFAULT_BLOCK_SIZE,
        seed: Optional[int] = None,
    ) -> dict:
        """Run trade-shuffle Monte Carlo simulation.

        Shuffles existing trade PnLs to build equity curve distributions.

        Returns a dict with aggregated statistics and comparison.
        """
        if not trades:
            raise ValueError("No trades provided for trade shuffle")

        shuffler = TradeShuffler(trades, initial_equity)
        shuffle_output = shuffler.shuffle(
            n_paths=n_paths,
            mode=mode,
            block_size=block_size,
            seed=seed,
        )

        aggregator = MonteCarloAggregator()
        aggregator.add_shuffle_results(shuffle_output)
        stats = aggregator.to_storage_format()
        comparison = aggregator.compare_to_actual({})

        return {
            'mode': 'trade_shuffle',
            'n_paths': n_paths,
            'shuffle_mode': mode,
            'block_size': block_size if mode == 'block' else None,
            'n_trades': len(trades),
            'initial_equity': initial_equity,
            'statistics': stats,
            'comparison': comparison,
        }

    # ------------------------------------------------------------------
    # Save results
    # ------------------------------------------------------------------

    def save_results(self, results: dict, output_dir: str) -> str:
        """Save MC results to output directory.

        Creates:
          - mc_summary.json: aggregated statistics
          - mc_model_params.json: GARCH + OHLC model params (path-based only)

        Returns the output directory path.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # Summary
        summary = _sanitize_for_json({
            'mode': results.get('mode'),
            'n_paths': results.get('n_paths'),
            'n_completed': results.get('n_completed', results.get('statistics', {}).get('n_completed')),
            'n_failed': results.get('n_failed', 0),
            'failure_rate': results.get('failure_rate', 0.0),
            'statistics': results.get('statistics', {}),
            'comparison': results.get('comparison', {}),
            'baseline_metrics': results.get('baseline_metrics', {}),
        })
        with open(out / 'mc_summary.json', 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        # Model params (path-based only)
        if results.get('model_params'):
            model_data = {
                'model_params': results['model_params'],
                'model_fit_quality': results.get('model_fit_quality', {}),
                'path_validation': results.get('path_validation', {}),
            }
            with open(out / 'mc_model_params.json', 'w') as f:
                json.dump(model_data, f, indent=2, default=str)

        return str(out)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_backtest(
        self,
        BT_Manager_cls,
        preloaded_data: Dict,
        suppress_output: bool = False,
        start_override: Optional[str] = None,
        end_override: Optional[str] = None,
    ) -> dict:
        """Run a single backtest, optionally suppressing stdout."""
        bt_kwargs = {
            'strategy': self.strategy_id,
            'stratOBJ': self.stratOBJ,
            'start': start_override or '',
            'end': end_override or '',
            'initial_equity': self.initial_equity,
            'position_sizing': self.position_sizing,
            'risk_per_operation': self.risk_per_operation,
            'fixed_volume': self.fixed_volume,
            'slippage_ticks': self.slippage_ticks,
            'comm_per_contract': self.comm_per_contract,
            'custom_indicators_dir': self.custom_indicators_dir,
            'preloaded_data': preloaded_data,
            'verbose': False,
        }
        if self.max_volume is not None:
            bt_kwargs['max_volume'] = self.max_volume

        if suppress_output:
            with contextlib.redirect_stdout(io.StringIO()):
                bt = BT_Manager_cls(**bt_kwargs)
                return bt.run()
        else:
            bt = BT_Manager_cls(**bt_kwargs)
            return bt.run()

    @staticmethod
    def _report_progress(completed: int, total: int, callback: Optional[Callable] = None) -> None:
        """Report progress via callback and stdout marker."""
        if callback is not None:
            callback(completed, total)
        print(f"###MC_PROGRESS###{{\"completed\": {completed}, \"total\": {total}}}###MC_PROGRESS_END###")

    @staticmethod
    def _report_phase(phase: str, message: str) -> None:
        """Report phase change via stdout marker for the orchestrator to parse."""
        print(f"###MC_PHASE###{phase}###MC_PHASE_END###")
        print(f"[MC] {message}", flush=True)
