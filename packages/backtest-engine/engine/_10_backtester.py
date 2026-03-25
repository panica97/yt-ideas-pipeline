"""
Main Backtesting Engine

Orchestrates the backtesting process using modular components for data processing,
position management, exit simulation, and metrics reporting.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import time
import math

import numpy as np
import polars as pl

from ibkr_core import StratOBJ, INDICATORS, Initial_SL_TP

# Import log path from project constants
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from constants import BACKTEST_LOGS_PATH
from logger import get_logger

_logger = get_logger("engine.backtester")

from _00_constants import ExitReason
from _01_data_processor import DataPreprocessor
from _02_strategy_manager import STRATEGY_BACKTEST
from _03_price_utils import extract_scalar, extract_ohlc, round_price, timeframe_to_minutes
from _03b_warmup_utils import compute_max_lookback_with_chains, compute_warmup_bars_with_chains
from _04_trading_hours import TradingHoursValidator
from _05_sl_tp_manager import SLTPConfig, SLTPManager
from _06_position_manager import Position, PositionManager
from _07_exit_simulation import ExitSimulator
from _08_metrics_reporter import MetricsCalculator, BacktestReporter
from _09_position_sizer import BacktestPositionSizer
from _16_vectorized_signals import compile_entry_signals

pl.Config.set_tbl_cols(-1) # Show all columns when printing Polars DataFrames

class BT_Manager:
    """
    Main Backtesting Engine

    Iterates through historical data bar-by-bar, checking for entry signals,
    managing positions, and tracking exits via SL/TP/num_bars/exit_conditions.
    """

    def __init__(
        self,
        strategy: int,
        stratOBJ: StratOBJ,
        start: str,
        end: str,
        symbol: Optional[str] = None,
        stop_after: int = 0,
        verbose: bool = False,
        verb_data: bool = False,
        trailing_step: float = 0.05,
        comm_per_contract: float = 0.0,
        slippage_ticks: float = 0.0,
        enforce_trading_hours: bool = False,
        # Account and Position Sizing Parameters
        initial_equity: Optional[float] = None,
        position_sizing: str = 'fixed',
        risk_per_operation: float = 0.02,
        fixed_volume: int = 1,
        max_volume: Optional[int] = None,
        # Modified strategy support
        strategy_filename: Optional[str] = None,
        # Data path
        hist_data_path: Optional[str] = None,
        # Custom indicators
        custom_indicators_dir: Optional[str] = None,
        # Preloaded data (for Monte Carlo synthetic paths)
        preloaded_data: Optional[Dict[str, 'pl.DataFrame']] = None,
        # Silent mode (suppresses ALL print output — used by MC runner)
        silent: bool = False,
    ):
        """
        Args:
            strategy: Strategy ID to backtest
            stratOBJ: StratOBJ instance with strategy definitions
            start: Start date 'YYYY-MM-DD'
            end: End date 'YYYY-MM-DD'
            symbol: Symbol to backtest (optional - derived from stratOBJ if not provided)
            stop_after: Number of trades to execute before stopping (0 = run full backtest)
            verbose: Print detailed progress
            verb_data: Print detailed data slices including indicators, prices, and conditions
            trailing_step: Step size for profit ratio quantization in trailing SL (default: 0.05 = 5%)
            comm_per_contract: Commission per contract per side (default: 0.0)
            slippage_ticks: Slippage in ticks per side (default: 0.0)
            enforce_trading_hours: If True, respect strategy trading_hours restrictions
            hist_data_path: Path to historical data folder (default: 'hist_data')
            initial_equity: Starting account equity (required for 'rpo' or 'half_kelly' modes)
            position_sizing: Sizing mode - 'fixed', 'rpo', or 'half_kelly' (mutually exclusive)
            risk_per_operation: Risk percentage for RPO mode (0.02 = 2%)
            fixed_volume: Number of contracts for fixed mode (default: 1)
            max_volume: Maximum contracts per trade (None = no limit)
            strategy_filename: Explicit filename stem for modified strategies (e.g., "1001_ADX_30_mod")
        """
        self.strategy = strategy
        self.stratOBJ = stratOBJ
        self.start = start
        self.end = end
        self.symbol = symbol if symbol else stratOBJ.symbol(strategy)
        self.stop_after = stop_after
        self.verbose = verbose
        self.verb_data = verb_data
        self.trailing_step = trailing_step
        self.comm_per_contract = comm_per_contract
        self.slippage_ticks = slippage_ticks
        self.enforce_trading_hours = enforce_trading_hours

        # Account and Position Sizing
        self.initial_equity = initial_equity
        self.current_equity = initial_equity if initial_equity else 0.0
        self.fixed_volume = max(1, fixed_volume)
        self.risk_per_operation = risk_per_operation
        self.max_volume = max_volume  # None means no limit
        self.position_sizing = position_sizing.lower().strip()

        # Validate position sizing mode
        if self.position_sizing not in ('fixed', 'rpo', 'half_kelly'):
            print(f"Warning: Unknown position sizing mode '{position_sizing}', using 'fixed'")
            self.position_sizing = 'fixed'

        # Validate that equity is provided for dynamic sizing modes
        if self.position_sizing in ('rpo', 'half_kelly') and not initial_equity:
            raise ValueError(f"initial_equity is required for position_sizing='{self.position_sizing}'")

        # Track equity history for analysis
        self.equity_history: List[Dict] = []

        # Store explicit strategy filename if provided (for modified strategies)
        self.strategy_filename = strategy_filename

        # Historical data path
        self.hist_data_path = hist_data_path or 'hist_data'

        # Custom indicators directory (None = use ibkr_core default)
        self._custom_indicators_dir = custom_indicators_dir

        # Preloaded synthetic data (bypasses CSV loading when provided)
        self._preloaded_data = preloaded_data

        # Silent mode — suppresses all print output (MC runner)
        self.silent = silent

        # Initialize position sizer
        self.position_sizer = BacktestPositionSizer(
            mode=self.position_sizing,
            fixed_volume=self.fixed_volume,
            risk_per_operation=self.risk_per_operation,
            max_volume=self.max_volume
        )

        # Initialize managers
        self.position_manager = PositionManager()
        self.trading_hours = TradingHoursValidator(stratOBJ, strategy)

        # Data storage
        self.full_data: Dict[str, pl.DataFrame] = {}
        self.precomputed_data: Optional[Dict[str, pl.DataFrame]] = None
        self.preprocessor = None
        self.timestamp_cache: Dict[str, Dict] = {}

        # Diagnostics
        self._window_skip_count = 0
        self._window_skip_reasons: Dict[str, int] = {
            'insufficient_rows': 0,
            'nulls': 0,
            'nans': 0,
        }
        self._window_skip_debug_prints = 0
        self._window_skip_debug_print_limit = 10

        # Cached values
        self._effective_max_shift = None
        self.extra_window_bars = 0

    @property
    def trades(self) -> List[Dict]:
        """Access trades from position manager."""
        return self.position_manager.trades

    @property
    def total_pnl(self) -> float:
        """Access total PnL from position manager."""
        return self.position_manager.total_pnl

    @property
    def position_open(self) -> bool:
        """Check if position is open."""
        return self.position_manager.is_open

    def run(self) -> Dict:
        """
        Execute the backtest.

        Returns:
            Dict with trades, metrics, and total_pnl
        """
        start_time = time.time()

        if not self.silent:
            print(f"=== Starting Backtest for Strategy {self.strategy} ===")
            print(f"Period: {self.start} to {self.end}")
            print(f"Symbol: {self.symbol}")

            # Print position sizing configuration
            if self.initial_equity:
                print(f"Initial Equity: ${self.initial_equity:,.2f}")
                print(f"Position Sizing: {self.position_sizing.upper()}")
                if self.position_sizing == 'rpo':
                    print(f"Risk Per Operation: {self.risk_per_operation * 100:.1f}%")
                elif self.position_sizing == 'half_kelly':
                    print(f"Using Half-Kelly with max_rpo from strategy config")
                if self.max_volume:
                    print(f"Max Volume: {self.max_volume} contracts")
            else:
                print(f"Position Size: {self.fixed_volume} contract(s) (fixed)")

        # Step 1: Load and prepare data
        self._load_data()

        # Step 2: Get strategy configuration
        ind_list = self.stratOBJ.ind_list(self.strategy)
        max_shift = self._compute_effective_max_shift()
        self._effective_max_shift = max_shift

        # Get primary timeframe
        primary_tf = self.stratOBJ.process_freq(self.strategy)
        primary_df = self.full_data[primary_tf]
        total_bars = len(primary_df)

        # Step 2b: Pre-compute indicators on full time series (once)
        self._precompute_indicators(ind_list, max_shift)

        # --- Phase 1 optimizations: cache invariants and build index maps ---
        self._cached_primary_tf = primary_tf
        self._cached_min_tick = self.stratOBJ.minTick(self.strategy)
        self._cached_multiplier = self.stratOBJ.multiplier(self.strategy)
        self._cached_exit_conds = self.stratOBJ.exit_conds(self.strategy)
        self._cached_tail_len = 1 + self._effective_max_shift

        # Build secondary TF index map for O(1) lookups (replaces O(n) .filter())
        self._build_secondary_tf_index_map(primary_tf)

        # Compute validation threshold (skip per-bar null/NaN checks past this bar)
        self._compute_validation_threshold(primary_tf)

        # Reusable strategy evaluators (avoid per-bar class instantiation)
        self._entry_evaluator = STRATEGY_BACKTEST(
            ib=None, stratsOBJ=self.stratOBJ, strat_id=self.strategy,
            entries=True, exits=False, all=False, logging=False, ind_data={}
        )
        self._exit_evaluator = STRATEGY_BACKTEST(
            ib=None, stratsOBJ=self.stratOBJ, strat_id=self.strategy,
            entries=False, exits=True, all=False, logging=False, ind_data={}
        )
        # --- End Phase 1 setup ---

        # Warmup: skip bars where indicators haven't converged
        warmup_bars = self._compute_warmup_bars(ind_list, max_shift, primary_tf)
        start_bar_idx = warmup_bars

        # --- Phase 3: Vectorized entry signal compilation ---
        t0_vec = time.time()
        long_mask, short_mask, long_complete, short_complete = compile_entry_signals(
            self.stratOBJ, self.strategy, self.precomputed_data,
            self._tf_index_map, primary_tf, total_bars
        )
        entry_mask = long_mask | short_mask
        # Can bypass _check_entry() entirely when all conditions were vectorized
        signals_complete = long_complete and short_complete
        vec_elapsed = time.time() - t0_vec

        if not self.silent:
            candidate_count = int(np.sum(entry_mask[start_bar_idx:]))
            loop_bars = total_bars - start_bar_idx
            skip_count = loop_bars - candidate_count
            print(f"Primary Timeframe: {primary_tf}")
            print(f"Total Bars: {total_bars}")
            print(f"Warmup Bars (skip): {start_bar_idx}")
            print(f"Validation skip after bar: {self._validation_skip_after}")
            print(f"Vectorized signals: {vec_elapsed:.3f}s | "
                  f"{candidate_count} candidates, {skip_count} flat bars skippable "
                  f"({'exact' if signals_complete else 'superset — fallback active'})")
            print(f"Starting main loop...\n")
        # --- End Phase 3 setup ---

        # Step 3: Main backtest loop (sparse iteration — Phase 3)
        try:
            for bar_idx in range(start_bar_idx, total_bars):
                if self.position_open:
                    # Must check every bar for exit (SL/TP, num_bars, exit conditions)
                    current_bar = primary_df[bar_idx]
                    bar_date = extract_scalar(current_bar['date'])
                    bar_ohlc = {
                        'open': float(extract_scalar(current_bar['open'])),
                        'high': float(extract_scalar(current_bar['high'])),
                        'low': float(extract_scalar(current_bar['low'])),
                        'close': float(extract_scalar(current_bar['close'])),
                    }
                    window_data = self._get_precomputed_slice(bar_idx, bar_date=bar_date)
                    if window_data is None:
                        self._check_exit(bar_idx, current_bar, None, bar_date=bar_date, bar_ohlc=bar_ohlc)
                    else:
                        self._check_exit(bar_idx, current_bar, window_data, bar_date=bar_date, bar_ohlc=bar_ohlc)

                elif entry_mask[bar_idx]:
                    # Entry candidate detected by vectorized signals
                    current_bar = primary_df[bar_idx]
                    bar_date = extract_scalar(current_bar['date'])
                    bar_open = float(extract_scalar(current_bar['open']))

                    if signals_complete and not self.verb_data:
                        # Fast path: all conditions vectorized, bypass _check_entry()
                        if self.enforce_trading_hours and not self.trading_hours.is_entry_allowed(bar_date):
                            continue
                        window_data = self._get_precomputed_slice(bar_idx, bar_date=bar_date)
                        if window_data is None:
                            continue
                        # Long takes priority (matches _check_entry behavior)
                        if long_mask[bar_idx]:
                            self._enter_position(bar_idx, current_bar, 'long', bar_open, window_data, bar_date=bar_date)
                        elif short_mask[bar_idx]:
                            self._enter_position(bar_idx, current_bar, 'short', bar_open, window_data, bar_date=bar_date)
                    else:
                        # Fallback: some conditions not vectorized or verb_data active
                        window_data = self._get_precomputed_slice(bar_idx, bar_date=bar_date)
                        if window_data is not None:
                            self._check_entry(bar_idx, current_bar, window_data, bar_date=bar_date, bar_open=bar_open)

                # else: SKIP — no position and no entry signal (Phase 3 sparse iteration)

                # Stop after N trades if requested
                if self.stop_after > 0 and len(self.trades) >= self.stop_after:
                    if self.verbose:
                        print(f"\nStopping after {self.stop_after} trade(s)")
                    break

            # Close any remaining open position
            if self.position_open:
                self._force_close_position(total_bars - 1, primary_df[total_bars - 1])
        except Exception:
            _logger.error("Error in backtest loop for strategy %s at bar %s", self.strategy, bar_idx, exc_info=True)
            raise

        # Calculate metrics
        multiplier = self._cached_multiplier
        calculator = MetricsCalculator(self.trades, self.start, self.end, multiplier,
                                       initial_equity=self.initial_equity)
        metrics = calculator.calculate()

        # Add equity-based metrics if account tracking enabled
        if self.initial_equity:
            total_return = self.current_equity - self.initial_equity
            total_return_pct = (total_return / self.initial_equity) * 100
            metrics['initial_equity'] = self.initial_equity
            metrics['final_equity'] = self.current_equity
            metrics['total_return'] = total_return
            metrics['total_return_pct'] = total_return_pct

            # Calculate max drawdown in equity terms
            if self.equity_history:
                peak_equity = self.initial_equity
                max_dd_equity = 0
                for eh in self.equity_history:
                    if eh['equity'] > peak_equity:
                        peak_equity = eh['equity']
                    dd = peak_equity - eh['equity']
                    max_dd_equity = max(max_dd_equity, dd)
                metrics['max_drawdown_equity'] = max_dd_equity
                metrics['max_drawdown_equity_pct'] = (max_dd_equity / self.initial_equity) * 100

        elapsed_time = time.time() - start_time

        if not self.silent:
            print(f"\n=== Backtest Complete ===")
            print(f"Time Elapsed: {elapsed_time:.2f} seconds")
            if self.verbose:
                total_iters = max(1, (total_bars - start_bar_idx))
                pct = 100.0 * (self._window_skip_count / total_iters)
                print(f"Window skips: {self._window_skip_count}/{total_iters} ({pct:.2f}%)")
                print(f"Skip reasons: {self._window_skip_reasons}")

            reporter = BacktestReporter(
                strategy=self.strategy,
                symbol=self.symbol,
                start_date=self.start,
                end_date=self.end,
                trades=self.trades,
                stratOBJ=self.stratOBJ,
                verbose=self.verbose,
                position_sizing_mode=self.position_sizing,
                initial_equity=self.initial_equity,
                final_equity=self.current_equity if self.initial_equity else None,
                fixed_volume=self.fixed_volume,
                risk_per_operation=self.risk_per_operation,
                max_volume=self.max_volume
            )
            reporter.print_summary(metrics)

            # Print equity summary if account tracking enabled
            if self.initial_equity:
                print(f"\n=== Account Summary ===")
                print(f"Initial Equity: ${self.initial_equity:,.2f}")
                print(f"Final Equity: ${self.current_equity:,.2f}")
                print(f"Total Return: ${metrics['total_return']:+,.2f} ({metrics['total_return_pct']:+.2f}%)")
                if 'max_drawdown_equity_pct' in metrics:
                    print(f"Max Drawdown: ${metrics['max_drawdown_equity']:,.2f} ({metrics['max_drawdown_equity_pct']:.2f}%)")

        return {
            'trades': self.trades,
            'metrics': metrics,
            'total_pnl': self.total_pnl,
            'initial_equity': self.initial_equity,
            'final_equity': self.current_equity if self.initial_equity else None,
            'equity_history': self.equity_history if self.initial_equity else None
        }

    def _load_data(self):
        """Load historical data from CSV files."""
        if self._preloaded_data is not None:
            self.full_data = {}
            for tf, df in self._preloaded_data.items():
                start_dt = pl.lit(self.start).str.to_date('%Y-%m-%d')
                end_dt = pl.lit(self.end).str.to_date('%Y-%m-%d')
                filtered = df.filter(
                    (pl.col('date').cast(pl.Date) >= start_dt) &
                    (pl.col('date').cast(pl.Date) <= end_dt)
                )
                self.full_data[tf] = filtered
                dates = filtered['date'].to_list()
                self.timestamp_cache[tf] = {d: i for i, d in enumerate(dates)}
            return

        self.preprocessor = DataPreprocessor(data_folder=self.hist_data_path)

        ind_list = self.stratOBJ.ind_list(self.strategy)
        timeframes = list(ind_list.keys())

        if self.verbose:
            print(f"Loading data for timeframes: {timeframes}")

        self.full_data = self.preprocessor.load_and_resample(
            symbol=self.symbol,
            timeframes=timeframes,
            start_date=self.start,
            end_date=self.end
        )

        # Validate data
        primary_tf = self.stratOBJ.process_freq(self.strategy)

        if self.verbose:
            print(f"\nData Validation:")
            for tf, df in self.full_data.items():
                first_date = df['date'][0]
                last_date = df['date'][-1]
                print(f"  {tf}: {len(df)} bars | Range: {first_date} to {last_date}")

                if tf != primary_tf:
                    primary_first = self.full_data[primary_tf]['date'][0]
                    primary_last = self.full_data[primary_tf]['date'][-1]
                    if first_date > primary_first or last_date < primary_last:
                        print(f"    WARNING: {tf} has incomplete coverage vs {primary_tf}")

        # Build timestamp-to-index cache
        if self.verbose:
            print(f"\nBuilding timestamp cache for fast lookups...")

        for tf, df in self.full_data.items():
            self.timestamp_cache[tf] = {
                date: idx for idx, date in enumerate(df['date'].to_list())
            }

        if self.verbose:
            print(f"  Cache built for {len(self.timestamp_cache)} timeframe(s)")

    def _precompute_indicators(self, ind_list: Dict, max_shift: int):
        """Compute all indicators once on the full time series.

        Replaces per-bar indicator recalculation. Indicators are computed on
        the complete dataset so infinite-memory indicators (EMA, RSI, MACD,
        ATR, ADX) are fully converged — equivalent to full-history computation.
        """
        t0 = time.time()
        self.precomputed_data = INDICATORS(
            ib=None,
            contract=None,
            ind_info=ind_list,
            marketData=self.full_data,
            max_shift=max_shift,
            extended_data=0,
            custom_indicators_dir=self._custom_indicators_dir,
        ).run_data()
        elapsed = time.time() - t0
        if not self.silent:
            print(f"Indicators pre-computed on full series in {elapsed:.3f}s")

    def _build_secondary_tf_index_map(self, primary_tf: str):
        """Build index maps for secondary timeframes using np.searchsorted.

        Replaces per-bar O(n) .filter(date <= ts) with O(1) index lookup.
        Maps each primary bar index to the row count in each secondary TF.
        """
        self._tf_index_map = {}
        primary_dates = self.precomputed_data[primary_tf]['date'].to_numpy()

        for tf, df in self.precomputed_data.items():
            if tf == primary_tf:
                continue
            tf_dates = df['date'].to_numpy()
            # searchsorted 'right' gives count of rows where date <= primary_date
            self._tf_index_map[tf] = np.searchsorted(tf_dates, primary_dates, side='right')

    def _compute_validation_threshold(self, primary_tf: str):
        """Find the bar index after which all indicator values are guaranteed valid.

        After pre-computation, nulls/NaNs only exist in warmup rows. Once past
        the last invalid row + tail_len, per-bar validation can be skipped.
        """
        tail_len = self._cached_tail_len
        max_threshold = 0

        for tf, df in self.precomputed_data.items():
            last_invalid = -1
            for col in df.columns:
                s = df[col]
                if s.null_count() > 0:
                    null_idx = np.nonzero(s.is_null().to_numpy())[0]
                    if len(null_idx) > 0:
                        last_invalid = max(last_invalid, int(null_idx[-1]))
                if s.dtype in (pl.Float32, pl.Float64):
                    try:
                        nan_idx = np.nonzero(np.isnan(s.to_numpy()))[0]
                        if len(nan_idx) > 0:
                            last_invalid = max(last_invalid, int(nan_idx[-1]))
                    except Exception:
                        pass

            if tf == primary_tf:
                threshold = last_invalid + tail_len
            elif tf in self._tf_index_map:
                sec_min_rows = last_invalid + tail_len + 1
                matches = np.where(self._tf_index_map[tf] >= sec_min_rows)[0]
                threshold = int(matches[0]) if len(matches) > 0 else len(self._tf_index_map[tf])
            else:
                threshold = 0

            max_threshold = max(max_threshold, threshold)

        self._validation_skip_after = max_threshold

    def _get_max_lookback(self, ind_list: Dict) -> int:
        """Get maximum lookback period from all indicators (chain-aware)."""
        primary_tf = self.stratOBJ.process_freq(self.strategy)
        return compute_max_lookback_with_chains(ind_list, primary_tf, self._effective_indicator_lookback)

    def _compute_warmup_bars(self, ind_list: Dict, max_shift: int, primary_tf: str) -> int:
        """Compute warmup bars for all timeframes (chain-aware)."""
        return compute_warmup_bars_with_chains(ind_list, max_shift, primary_tf, self._effective_indicator_lookback)

    def _compute_effective_max_shift(self) -> int:
        """Return max_shift that covers cross/direction lookback needs."""
        try:
            base_max_shift = int((self.stratOBJ.max_shift(self.strategy) or [0])[0] or 0)
        except Exception:
            base_max_shift = 0

        conds = []
        for getter_name in ('long_conds', 'short_conds', 'exit_conds'):
            try:
                getter = getattr(self.stratOBJ, getter_name, None)
                if getter is None:
                    continue
                clist = getter(self.strategy) or []
                if isinstance(clist, list):
                    conds.extend(clist)
            except Exception:
                continue

        required_tail_len = 1
        for c in conds:
            try:
                s1 = int(c.get('shift_1', 0) or 0)
            except Exception:
                s1 = 0
            try:
                s2 = int(c.get('shift_2', 0) or 0)
            except Exception:
                s2 = 0
            max_s = max(s1, s2)
            extra = self._cond_extra_bars(str(c.get('cond_type', '') or ''))
            required_tail_len = max(required_tail_len, 1 + max_s + extra)

        required_shift = max(0, required_tail_len - 1)
        return max(base_max_shift, required_shift)

    @staticmethod
    def _cond_extra_bars(cond_type: str) -> int:
        """Extra bars required beyond shift for conditions that read prior rows."""
        if cond_type in {'cross_ind_relation', 'cross_num_relation', 'cross_price_relation'}:
            return 1
        if cond_type == 'ind_direction':
            return 2
        return 0

    @staticmethod
    def _effective_indicator_lookback(indicator_name: str, params: Dict) -> int:
        """Return indicator warmup bars needed for stable values."""
        try:
            return INDICATORS()._required_warmup_bars(indicator_name, params)
        except Exception:
            time_periods = [
                value for key, value in (params or {}).items()
                if key.startswith('timePeriod') and isinstance(value, int)
            ]
            return max(time_periods) if time_periods else 1

    def _get_window_slice(self, bar_idx: int, window_size: int) -> Optional[Dict[str, pl.DataFrame]]:
        """Extract rolling window slice using timestamp-based filtering.

        Window alignment to match live trading:
        - Window includes current bar (bar_idx N) as shift 0 (like forming bar in live)
        - shift 1 = bar N-1 (signal bar, where conditions evaluate)
        - shift 2 = bar N-2, etc.
        - Conditions use shift >= 1, so having bar N in window is safe
        """
        primary_tf = self.stratOBJ.process_freq(self.strategy)
        # Include current bar as shift 0 (like forming bar in live trading)
        # Window ends at bar_idx (current bar), so shift 1 = bar_idx-1 (signal bar)
        window_end_idx = bar_idx
        current_timestamp = extract_scalar(self.full_data[primary_tf][window_end_idx]['date'])

        ind_list = self.stratOBJ.ind_list(self.strategy)
        max_shift = self._effective_max_shift

        raw_window_data: Dict[str, pl.DataFrame] = {}
        for tf, df in self.full_data.items():
            tf_data = df.filter(pl.col('date') <= current_timestamp)
            raw_window_data[tf] = tf_data.tail(window_size)

        window_data_with_indicators = INDICATORS(
            ib=None,
            contract=None,
            ind_info=ind_list,
            marketData=raw_window_data,
            max_shift=max_shift,
            extended_data=0,
            custom_indicators_dir=self._custom_indicators_dir,
        ).run()

        # Validate last rows
        tail_len = 1 + max_shift
        for tf, df in window_data_with_indicators.items():
            if df.is_empty() or len(df) < tail_len:
                self._window_skip_count += 1
                self._window_skip_reasons['insufficient_rows'] += 1
                if self.verbose and self._window_skip_debug_prints < self._window_skip_debug_print_limit:
                    self._window_skip_debug_prints += 1
                    print(f"[Window Skip] bar_idx={bar_idx} ts={current_timestamp} tf={tf}: len={len(df)} < tail_len={tail_len}")
                return None

            last_rows = df.tail(tail_len)
            for col in last_rows.columns:
                s = last_rows[col]
                if s.null_count() > 0:
                    self._window_skip_count += 1
                    self._window_skip_reasons['nulls'] += 1
                    if self.verbose and self._window_skip_debug_prints < self._window_skip_debug_print_limit:
                        self._window_skip_debug_prints += 1
                        print(f"[Window Skip] bar_idx={bar_idx} ts={current_timestamp} tf={tf}: nulls in col={col}")
                    return None
                if s.dtype in (pl.Float32, pl.Float64) and s.is_nan().any():
                    self._window_skip_count += 1
                    self._window_skip_reasons['nans'] += 1
                    if self.verbose and self._window_skip_debug_prints < self._window_skip_debug_print_limit:
                        self._window_skip_debug_prints += 1
                        print(f"[Window Skip] bar_idx={bar_idx} ts={current_timestamp} tf={tf}: NaNs in col={col}")
                    return None

        return window_data_with_indicators

    def _get_precomputed_slice(self, bar_idx: int, bar_date=None) -> Optional[Dict[str, pl.DataFrame]]:
        """Extract slice from pre-computed indicator data for current bar.

        Phase 1 optimizations:
        - Uses cached primary_tf and tail_len (Task 1.5)
        - Uses pre-built index map for O(1) secondary TF lookup (Task 1.3)
        - Skips null/NaN validation when past threshold (Task 1.1)
        - Accepts pre-extracted bar_date to avoid redundant extract_scalar (Task 1.4)
        """
        primary_tf = self._cached_primary_tf
        tail_len = self._cached_tail_len

        sliced = {}
        for tf, df in self.precomputed_data.items():
            if tf == primary_tf:
                tf_slice = df[:bar_idx + 1]
            else:
                # O(1) index lookup via pre-built map (Task 1.3)
                end_idx = int(self._tf_index_map[tf][bar_idx])
                tf_slice = df[:end_idx]
            sliced[tf] = tf_slice

        # Skip full validation when past threshold (Task 1.1)
        if bar_idx >= self._validation_skip_after:
            for tf, df_slice in sliced.items():
                if df_slice.is_empty() or len(df_slice) < tail_len:
                    self._window_skip_count += 1
                    self._window_skip_reasons['insufficient_rows'] += 1
                    return None
            return sliced

        # Full validation for bars in warmup zone
        if bar_date is None:
            bar_date = extract_scalar(self.full_data[primary_tf][bar_idx]['date'])

        for tf, df_slice in sliced.items():
            if df_slice.is_empty() or len(df_slice) < tail_len:
                self._window_skip_count += 1
                self._window_skip_reasons['insufficient_rows'] += 1
                if self.verbose and self._window_skip_debug_prints < self._window_skip_debug_print_limit:
                    self._window_skip_debug_prints += 1
                    print(f"[Window Skip] bar_idx={bar_idx} ts={bar_date} tf={tf}: len={len(df_slice)} < tail_len={tail_len}")
                return None

            last_rows = df_slice.tail(tail_len)
            for col in last_rows.columns:
                s = last_rows[col]
                if s.null_count() > 0:
                    self._window_skip_count += 1
                    self._window_skip_reasons['nulls'] += 1
                    if self.verbose and self._window_skip_debug_prints < self._window_skip_debug_print_limit:
                        self._window_skip_debug_prints += 1
                        print(f"[Window Skip] bar_idx={bar_idx} ts={bar_date} tf={tf}: nulls in col={col}")
                    return None
                if s.dtype in (pl.Float32, pl.Float64) and s.is_nan().any():
                    self._window_skip_count += 1
                    self._window_skip_reasons['nans'] += 1
                    if self.verbose and self._window_skip_debug_prints < self._window_skip_debug_print_limit:
                        self._window_skip_debug_prints += 1
                        print(f"[Window Skip] bar_idx={bar_idx} ts={bar_date} tf={tf}: NaNs in col={col}")
                    return None

        return sliced

    def _check_entry(self, bar_idx: int, current_bar, window_data: Dict[str, pl.DataFrame],
                     bar_date=None, bar_open=None):
        """Check for entry signals.

        Window alignment (matches live trading):
        - Window shift 0 = bar N (current bar, like forming bar in live)
        - Window shift 1 = bar N-1 (signal bar, where conditions evaluate)
        - Conditions use shift >= 1, so they read from bar N-1 (correct!)
        - Entry at bar N's open
        - ref_price = bar N's open (entry price)
        """
        # Check trading hours restrictions
        if self.enforce_trading_hours:
            bar_datetime = bar_date if bar_date is not None else extract_scalar(current_bar['date'])
            if not self.trading_hours.is_entry_allowed(bar_datetime):
                if self.verbose:
                    print(f"  [ENTRY BLOCKED] Bar {bar_idx} outside entry schedule")
                return

        # Reuse entry evaluator (Task 1.2) — update data, call process()
        self._entry_evaluator.ind_data = window_data
        _, _, strategies_dict, _ = self._entry_evaluator.process()

        signal = strategies_dict[self.strategy]

        # ref_price = entry bar's open (bar N) - matches live trading
        ref_price = bar_open if bar_open is not None else float(extract_scalar(current_bar['open']))

        # Print detailed data if verb_data enabled
        if self.verb_data and (signal['long'] or signal['short']):
            reporter = BacktestReporter(
                strategy=self.strategy,
                symbol=self.symbol,
                start_date=self.start,
                end_date=self.end,
                trades=self.trades,
                stratOBJ=self.stratOBJ,
                verbose=self.verbose
            )
            reporter.print_data_slice(bar_idx, current_bar, window_data, 'ENTRY', signal, ref_price)

        # Check for entry
        if signal['long']:
            self._enter_position(bar_idx, current_bar, 'long', ref_price, window_data, bar_date=bar_date)
        elif signal['short']:
            self._enter_position(bar_idx, current_bar, 'short', ref_price, window_data, bar_date=bar_date)

    def _enter_position(self, bar_idx: int, current_bar, side: str, ref_price: float,
                        window_data: Dict[str, pl.DataFrame], bar_date=None):
        """Enter a new position with gap validation."""
        # Calculate SL/TP
        signal_dict = {
            'strat_code': self.strategy,
            'long': side == 'long',
            'short': side == 'short',
            'exit': False
        }

        sl_tp_calculator = Initial_SL_TP(
            ib=None,
            stratOBJ=self.stratOBJ,
            signal_dict=signal_dict,
            entry_data={self.strategy: window_data},
            ref_price=ref_price,
            SL_market_data=None,
            TP_market_data=None
        )

        enriched_signal = sl_tp_calculator.generate()

        # Entry price = ref_price = bar open (already extracted in caller)
        bar_open = ref_price
        min_tick = self._cached_min_tick
        multiplier = self._cached_multiplier

        # Round SL and TP (None when no SL/TP method is configured)
        raw_sl = enriched_signal['SL_level']
        raw_tp = enriched_signal['TP_level']
        sl_level = round_price(raw_sl, side, min_tick) if raw_sl is not None else None
        tp_level = round_price(raw_tp, side, min_tick) if raw_tp is not None else None

        entry_date = bar_date if bar_date is not None else extract_scalar(current_bar['date'])
        primary_tf = self._cached_primary_tf
        signal_bar_idx = max(0, bar_idx - 1)
        signal_bar_date = extract_scalar(self.full_data[primary_tf][signal_bar_idx]['date'])

        # Calculate position size
        position_size = self.position_sizer.calculate_volume(
            equity=self.current_equity,
            entry_price=bar_open,
            sl_level=sl_level,
            multiplier=multiplier,
            stratOBJ=self.stratOBJ,
            strategy=self.strategy
        )

        # Get SL management config
        sl_mgmt_config = self.stratOBJ.stop_loss_mgmt(self.strategy)

        # Open position
        self.position_manager.open_position(
            side=side,
            entry_bar_idx=bar_idx,
            entry_price=bar_open,
            sl_level=sl_level,
            tp_level=tp_level,
            sl_mgmt_config=sl_mgmt_config,
            position_size=position_size
        )

        # Store ref_price in position for trade record
        pos = self.position_manager.position
        pos.ref_price = ref_price

        if self.verbose:
            print(f"\n[ENTRY] {side.upper()}")
            print(f"  Signal Bar: {bar_idx - 1} | {signal_bar_date}")
            print(f"  Entry Bar:  {bar_idx} | {entry_date}")
            sl_str = f"${sl_level:.2f}" if sl_level is not None else "None"
            tp_str = f"${tp_level:.2f}" if tp_level is not None else "None"
            print(f"  Entry: ${bar_open:.2f} | SL: {sl_str} | TP: {tp_str}")
            print(f"  Position Size: {position_size}")
            if sl_mgmt_config:
                be_cfg = sl_mgmt_config.get('breakeven', {})
                tsl_cfg = sl_mgmt_config.get('trailing', {})
                if be_cfg.get('action') or tsl_cfg.get('action'):
                    print(f"  BE/TSL: BE={be_cfg.get('action', False)} (ratio={be_cfg.get('profitRatio', 0.20)}) | "
                          f"TSL={tsl_cfg.get('action', False)} (ratio={tsl_cfg.get('trailingRatio', 0.80)})")

    def _check_exit(self, bar_idx: int, current_bar, window_data: Optional[Dict[str, pl.DataFrame]],
                    bar_date=None, bar_ohlc=None):
        """Check for exit conditions on current bar."""
        pos = self.position_manager.position
        pos.bars_in_position += 1

        ohlc = bar_ohlc if bar_ohlc is not None else extract_ohlc(current_bar)

        if self.verb_data:
            if bar_date is None:
                bar_date = extract_scalar(current_bar['date'])
            print(f"\n[CHECKING EXIT] Bar {bar_idx} | {bar_date}")
            print(f"  Current Bar OHLC: O={ohlc['open']:.2f} H={ohlc['high']:.2f} L={ohlc['low']:.2f} C={ohlc['close']:.2f}")
            sl_str = f"{pos.sl_level:.2f}" if pos.sl_level is not None else "None"
            tp_str = f"{pos.tp_level:.2f}" if pos.tp_level is not None else "None"
            print(f"  Position: {pos.side} | Entry: {pos.entry_price:.2f} | SL: {sl_str} | TP: {tp_str}")

        exit_price: Optional[float] = None
        exit_reason: Optional[str] = None
        exit_minute_timestamp = None

        # 1) Exit-at-open checks
        exit_schedule_allowed = True
        if self.enforce_trading_hours:
            bar_datetime = bar_date if bar_date is not None else extract_scalar(current_bar['date'])
            exit_schedule_allowed = self.trading_hours.is_exit_allowed(bar_datetime)

        # num_bars exit (Task 1.5: use cached exit_conds)
        if exit_schedule_allowed:
            for cond in self._cached_exit_conds:
                if cond.get('cond_type') == 'num_bars':
                    try:
                        max_bars = int(cond['cond'])
                    except Exception:
                        max_bars = None
                    if max_bars is not None and pos.bars_in_position >= max_bars:
                        exit_price = ohlc['open']
                        exit_reason = ExitReason.NUM_BARS
                        break

        # exit conditions (Task 1.2: reuse exit evaluator)
        if exit_price is None and window_data is not None and exit_schedule_allowed:
            self._exit_evaluator.ind_data = window_data
            _, _, strategies_dict, _ = self._exit_evaluator.process()
            if strategies_dict[self.strategy].get('exit'):
                exit_price = ohlc['open']
                exit_reason = ExitReason.EXIT_CONDITION

        if exit_price is not None:
            self._close_position(bar_idx, current_bar, exit_price, exit_reason)
            return

        # 2) BE/TSL path
        if self._is_sl_mgmt_enabled():
            # Only attempt simulation once (avoid repeated failures)
            if pos.precomputed_exit is None and not getattr(pos, '_sl_mgmt_simulation_failed', False):
                pos.precomputed_exit = self._simulate_position_with_sl_mgmt()
                if pos.precomputed_exit:
                    if self.verbose:
                        print(
                            f"  [BE/TSL] Precomputed exit: Bar {pos.precomputed_exit[0]} | {pos.precomputed_exit[1]} "
                            f"| {pos.precomputed_exit[3]} @ ${pos.precomputed_exit[2]:.2f}"
                        )
                else:
                    # Mark as failed so we don't keep retrying
                    pos._sl_mgmt_simulation_failed = True
                    if self.verbose:
                        print(f"  [BE/TSL] Simulation failed, falling back to standard SL/TP checks")

            if pos.precomputed_exit and bar_idx >= pos.precomputed_exit[0]:
                pe_bar_idx, pe_timestamp, pe_price, pe_reason, pe_final_sl = pos.precomputed_exit
                # Staleness guard: if SL was externally modified since entry, discard
                # Compare initial SL (used by simulation) against current position SL
                if pos.initial_sl_level is not None and pos.sl_level is not None and abs(pos.initial_sl_level - pos.sl_level) > 1e-9:
                    pos.precomputed_exit = None  # Force live evaluation
                else:
                    pos.sl_level = pe_final_sl
                    # Propagate BE/TSL state to position for trade record
                    if pe_reason in ('SL_BE', 'SL_TSL'):
                        pos.be_status = True
                    exit_minute_timestamp = pe_timestamp

                    if self.verb_data:
                        print(f"  [BE/TSL] Triggering precomputed exit: {pe_reason} @ ${pe_price:.2f}")

                    # Use the correct bar data when exit happened on a previous bar
                    # (e.g. minute-level exit within the entry bar itself).
                    # pe_bar_idx is only used for the exit timestamp -- the exit price
                    # (pe_price) was already determined by the exit simulation.
                    if pe_bar_idx < bar_idx:
                        primary_tf = self._cached_primary_tf
                        if pe_bar_idx < len(self.full_data[primary_tf]):
                            exit_bar = self.full_data[primary_tf][pe_bar_idx]
                        else:
                            _logger.warning("Precomputed exit bar %d out of range (len=%d), using current bar",
                                            pe_bar_idx, len(self.full_data[primary_tf]))
                            exit_bar = current_bar
                    else:
                        exit_bar = current_bar

                    self._close_position(pe_bar_idx, exit_bar, pe_price, pe_reason, exit_minute_timestamp)
                    return

            # If simulation succeeded, trust the precomputed exit and skip standard SL/TP
            if pos.precomputed_exit:
                return
            # Otherwise fall through to standard SL/TP checks

        # 3) Standard path: intrabar SL/TP checks
        #    Skip SL check when sl_level is None (no stop loss configured)
        #    Skip TP check when tp_level is None (no take profit configured)
        sl_hit = tp_hit = False
        if pos.side == 'long':
            sl_hit = pos.sl_level is not None and ohlc['low'] <= pos.sl_level
            tp_hit = pos.tp_level is not None and ohlc['high'] >= pos.tp_level
        else:
            sl_hit = pos.sl_level is not None and ohlc['high'] >= pos.sl_level
            tp_hit = pos.tp_level is not None and ohlc['low'] <= pos.tp_level

        if sl_hit and tp_hit:
            exit_price, exit_reason = self._resolve_sl_tp_conflict(bar_idx, current_bar)
        elif sl_hit:
            # Gap-adjusted fill: if bar opens past SL, fill at open
            if (pos.side == 'long' and ohlc['open'] <= pos.sl_level) or \
               (pos.side == 'short' and ohlc['open'] >= pos.sl_level):
                exit_price = ohlc['open']
            else:
                exit_price = pos.sl_level
            exit_reason = ExitReason.SL
        elif tp_hit:
            # Gap-adjusted fill: if bar opens past TP, fill at open
            if (pos.side == 'long' and ohlc['open'] >= pos.tp_level) or \
               (pos.side == 'short' and ohlc['open'] <= pos.tp_level):
                exit_price = ohlc['open']
            else:
                exit_price = pos.tp_level
            exit_reason = ExitReason.TP

        if exit_price:
            self._close_position(bar_idx, current_bar, exit_price, exit_reason)

    def _is_sl_mgmt_enabled(self) -> bool:
        """Check if BE or TSL is enabled for current position."""
        pos = self.position_manager.position
        if not pos or not pos.sl_mgmt_config:
            return False
        config = SLTPConfig.from_strategy_config(pos.sl_mgmt_config)
        return config.is_enabled

    def _simulate_position_with_sl_mgmt(self):
        """Simulate position with BE/TSL management."""
        pos = self.position_manager.position

        simulator = ExitSimulator(
            full_data=self.full_data,
            preprocessor=self.preprocessor,
            stratOBJ=self.stratOBJ,
            strategy=self.strategy,
            symbol=self.symbol,
            timestamp_cache=self.timestamp_cache,
            verbose=self.verbose
        )

        # Create helper functions for the simulator
        def get_window_slice(bar_idx):
            return self._get_precomputed_slice(bar_idx)

        def check_exit_condition(window_data):
            _, _, strategies_dict, _ = STRATEGY_BACKTEST(
                ib=None,
                stratsOBJ=self.stratOBJ,
                strat_id=self.strategy,
                entries=False,
                exits=True,
                all=False,
                logging=False,
                ind_data=window_data
            ).process()
            return strategies_dict[self.strategy].get('exit', False)

        min_tick = self._cached_min_tick

        return simulator.simulate_position_with_sl_mgmt(
            entry_bar_idx=pos.entry_bar_idx,
            entry_price=pos.entry_price,
            position_side=pos.side,
            initial_sl_level=pos.initial_sl_level,
            tp_level=pos.tp_level,
            be_price=pos.be_price,
            sl_mgmt_config=pos.sl_mgmt_config,
            min_tick=min_tick,
            trailing_step=self.trailing_step,
            get_window_slice=get_window_slice,
            check_exit_condition=check_exit_condition
        )

    def _resolve_sl_tp_conflict(self, bar_idx: int, current_bar):
        """Resolve SL/TP conflict using minute data."""
        pos = self.position_manager.position

        simulator = ExitSimulator(
            full_data=self.full_data,
            preprocessor=self.preprocessor,
            stratOBJ=self.stratOBJ,
            strategy=self.strategy,
            symbol=self.symbol,
            timestamp_cache=self.timestamp_cache,
            verbose=self.verbose
        )

        return simulator.resolve_sl_tp_conflict(
            bar_idx=bar_idx,
            current_bar=current_bar,
            position_side=pos.side,
            sl_level=pos.sl_level,
            tp_level=pos.tp_level
        )

    def _close_position(self, bar_idx: int, current_bar, exit_price: float, exit_reason: str,
                        exit_minute_timestamp=None):
        """Close current position and record trade."""
        pos = self.position_manager.position
        multiplier = self._cached_multiplier
        min_tick = self._cached_min_tick or 0.25

        exit_date = extract_scalar(current_bar['date'])
        primary_tf = self._cached_primary_tf
        entry_date = extract_scalar(self.full_data[primary_tf][pos.entry_bar_idx]['date'])
        signal_bar_idx = max(0, pos.entry_bar_idx - 1)
        signal_bar_date = extract_scalar(self.full_data[primary_tf][signal_bar_idx]['date'])

        # Capture ref_price before closing position
        ref_price = getattr(pos, 'ref_price', pos.entry_price)

        trade = self.position_manager.close_position(
            bar_idx=bar_idx,
            exit_price=exit_price,
            exit_reason=exit_reason,
            strategy=self.strategy,
            signal_bar_date=signal_bar_date,
            entry_date=entry_date,
            exit_date=exit_date,
            multiplier=multiplier,
            commission_per_contract=self.comm_per_contract,
            slippage_ticks=self.slippage_ticks,
            min_tick=min_tick,
            exit_minute_timestamp=exit_minute_timestamp
        )

        # Add ref_price to trade record
        trade['ref_price'] = ref_price

        # Update equity if account tracking is enabled
        if self.initial_equity:
            self.current_equity += trade['pnl']
            # Record equity history
            self.equity_history.append({
                'trade_num': len(self.trades),
                'exit_date': exit_date,
                'pnl': trade['pnl'],
                'equity': self.current_equity
            })
            # Add equity info to trade record
            trade['equity_before'] = self.current_equity - trade['pnl']
            trade['equity_after'] = self.current_equity

        if self.verbose:
            print(f"[EXIT] Bar {bar_idx} | {exit_date} | {exit_reason.upper()}")
            print(f"  Exit: ${exit_price:.2f} | Gross PnL: ${trade['gross_pnl']:+.2f}")
            if trade['slippage_cost'] > 0 or trade['commission'] > 0:
                print(f"  Slippage: -${trade['slippage_cost']:.2f} | Commission: -${trade['commission']:.2f} | Net PnL: ${trade['pnl']:+.2f}")
            else:
                print(f"  Net PnL: ${trade['pnl']:+.2f}")
            if trade['be_triggered']:
                final_sl_str = f"${trade['sl_level']:.2f}" if trade['sl_level'] is not None else "None"
                print(f"  BE Triggered: Yes | BE Price: ${trade['be_price']:.2f} | Final SL: {final_sl_str}")
            print(f"  Cumulative PnL: ${trade['cumulative_pnl']:+,.2f}")
            if self.initial_equity:
                print(f"  Equity: ${self.current_equity:+,.2f}")

    def _force_close_position(self, bar_idx: int, current_bar):
        """Force close position at end of backtest."""
        bar_close = float(extract_scalar(current_bar['close']))
        self._close_position(bar_idx, current_bar, bar_close, ExitReason.BACKTEST_END)

    def _find_strategy_filename(self) -> str:
        """Find the strategy filename by ID.

        Searches for strategy file in local Strategies/ folder,
        handling both regular (1001.py) and _mod variants (1001_ADX_30_mod.py).

        Returns:
            Strategy filename (e.g., '1001_ADX_30_mod.py') or None if not found.
        """
        from pathlib import Path

        # Use local Strategies folder (same path as MAIN.py uses for StratOBJ)
        strategies_path = Path(__file__).parent.parent / "Strategies"

        if not strategies_path.exists():
            return None

        # Check exact match first (e.g., 1001.py)
        exact_path = strategies_path / f"{self.strategy}.py"
        if exact_path.exists():
            return exact_path.name

        # Check for files starting with the ID (handles _mod variants)
        for filepath in strategies_path.glob(f"{self.strategy}*.py"):
            return filepath.name

        return None

    def save_results(
        self,
        output_folder: str = None,
        save_all_timeframes: bool = True,
        backtest_name: str = None
    ) -> str:
        """
        Save backtest results to CSV, JSON metrics, and candles.

        Args:
            output_folder: Output folder path (defaults to BACKTEST_LOGS_PATH)
            save_all_timeframes: If True, save candles for all timeframes (for dashboard)
            backtest_name: Optional custom name for the backtest folder

        Returns:
            str: Path to the backtest folder (for visualization)
        """
        if output_folder is None:
            output_folder = BACKTEST_LOGS_PATH

        # Get primary timeframe candles for visualization
        primary_tf = self.stratOBJ.process_freq(self.strategy)
        candles_df = self.full_data.get(primary_tf)

        # Use provided filename or try to find it
        if self.strategy_filename:
            strategy_filename = f"{self.strategy_filename}.py"
        else:
            strategy_filename = self._find_strategy_filename()

        reporter = BacktestReporter(
            strategy=self.strategy,
            symbol=self.symbol,
            start_date=self.start,
            end_date=self.end,
            trades=self.trades,
            stratOBJ=self.stratOBJ,
            verbose=self.verbose,
            position_sizing_mode=self.position_sizing,
            initial_equity=self.initial_equity,
            final_equity=self.current_equity if self.initial_equity else None,
            fixed_volume=self.fixed_volume,
            risk_per_operation=self.risk_per_operation,
            max_volume=self.max_volume,
            candles_df=candles_df,
            primary_timeframe=primary_tf,
            full_data=self.full_data,
            strategy_filename=strategy_filename
        )
        return reporter.save_results(
            output_folder,
            self.slippage_ticks,
            self.comm_per_contract,
            save_all_timeframes=save_all_timeframes,
            backtest_name=backtest_name
        )


# Backwards compatibility: Backtester alias
Backtester = BT_Manager


if __name__ == '__main__':
    # Example usage
    LOCAL_STRATEGIES = str(Path(__file__).parent.parent / 'Strategies')
    stratObj = StratOBJ().upload(strategies_folder=LOCAL_STRATEGIES, connect_ib=False)

    # Example 1: Fixed position sizing (1 contract)
    # backtester = BT_Manager(
    #     strategy=1002,
    #     stratOBJ=stratObj,
    #     start='2015-01-01',
    #     end='2024-11-01',
    #     slippage_ticks=2,
    #     comm_per_contract=0.62,
    #     stop_after=1,
    #     verbose=True,
    #     verb_data=True,
    #     initial_equity=1000000,        # Starting account size
    #     fixed_volume=1,               # Contracts per trade (for 'fixed' mode)
    #     max_volume=10,                # Maximum contracts per trade
    # )

    # backtester.run()
    # backtester.save_results()

    # Example 2: RPO-based position sizing with account tracking
    backtester = BT_Manager(
        strategy=1017,
        stratOBJ=stratObj,
        start='2015-01-01',
        end='2024-01-01',
        slippage_ticks=2,
        comm_per_contract=0.62,
        stop_after=0,
        verbose=False,
        verb_data=False,
        initial_equity=1000000,
        position_sizing='fixed',
        fixed_volume=1, 
        risk_per_operation=0.02,
    )
    results = backtester.run()
    folder = backtester.save_results()

    # Launch dashboard
    # import sys
    # from pathlib import Path
    # PROJECT_ROOT = Path(__file__).parent.parent
    # if str(PROJECT_ROOT) not in sys.path:
    #     sys.path.insert(0, str(PROJECT_ROOT))
    # from dashboard.app import create_app, run_app
    # app = create_app(backtest_folder=folder)
    # run_app(app)

    # Example 3: Half-Kelly position sizing (matches live trading)
    # backtester = BT_Manager(
    #     strategy=1002,
    #     stratOBJ=stratObj,
    #     start='2015-01-01',
    #     end='2024-11-01',
    #     slippage_ticks=2,
    #     comm_per_contract=0.62,
    #     stop_after=1,
    #     verbose=True,
    #     verb_data=True,
    #     initial_equity=1000000,
    #     position_sizing='half_kelly',
    # )
    # backtester.run()
    # backtester.save_results()