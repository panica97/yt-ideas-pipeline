"""
Exit Simulation

Provides minute-level simulation for precise exit timing, especially for
positions with BE/TSL management enabled.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Tuple

import numpy as np
import polars as pl

from _00_constants import ExitReason
from _03_price_utils import extract_scalar, extract_ohlc, timeframe_to_minutes, round_price
from _05_sl_tp_manager import SLTPConfig

_logger = logging.getLogger(__name__)


class ExitSimulator:
    """
    Simulates position exits with minute-level granularity.

    Handles:
    - Baseline exit finding (without BE/TSL)
    - Minute data loading for precise simulation
    - BE/TSL state updates during simulation
    - SL/TP conflict resolution
    """

    def __init__(
        self,
        full_data: Dict[str, pl.DataFrame],
        preprocessor: Any,
        stratOBJ: Any,
        strategy: int,
        symbol: str,
        timestamp_cache: Dict[str, Dict],
        verbose: bool = False
    ):
        """
        Args:
            full_data: Dict of DataFrames by timeframe
            preprocessor: DataPreprocessor instance for loading minute data
            stratOBJ: StratOBJ instance
            strategy: Strategy ID
            symbol: Symbol being traded
            timestamp_cache: Timestamp-to-index cache
            verbose: Enable verbose output
        """
        self.full_data = full_data
        self.preprocessor = preprocessor
        self.stratOBJ = stratOBJ
        self.strategy = strategy
        self.symbol = symbol
        self.timestamp_cache = timestamp_cache
        self.verbose = verbose

    def find_baseline_exit(
        self,
        entry_bar_idx: int,
        position_side: str,
        initial_sl_level: float,
        tp_level: float,
        get_window_slice: Callable,
        check_exit_condition: Callable
    ) -> Tuple[int, datetime, float, str]:
        """
        Find the baseline exit (without BE/TSL) by iterating through primary bars.

        This determines the maximum date range needed for minute data loading.

        Args:
            entry_bar_idx: Bar index where position was entered
            position_side: 'long' or 'short'
            initial_sl_level: Initial SL level (before any BE/TSL)
            tp_level: Take profit level
            get_window_slice: Function to get window data for a bar
            check_exit_condition: Function to check exit conditions

        Returns:
            Tuple of (exit_bar_idx, exit_timestamp, exit_price, exit_reason)
        """
        primary_tf = self.stratOBJ.process_freq(self.strategy)
        primary_df = self.full_data[primary_tf]
        total_bars = len(primary_df)

        sl_level = initial_sl_level
        # bars_in_pos tracks how many bars we've been in position
        # Entry bar is bar 0, first bar after entry is bar 1, etc.
        # We start checking from the bar AFTER entry (matching main backtester behavior)
        bars_in_pos = 0

        for bar_idx in range(entry_bar_idx + 1, total_bars):
            current_bar = primary_df[bar_idx]
            bars_in_pos += 1

            # Extract OHLC
            ohlc = extract_ohlc(current_bar)
            bar_date = extract_scalar(current_bar['date'])

            exit_price = None
            exit_reason = None

            # Check SL/TP hits (gap-adjusted: fill at open if bar opens past level)
            # Skip SL/TP checks when level is None (not configured)
            if position_side == 'long':
                if sl_level is not None and ohlc['low'] <= sl_level:
                    exit_price = ohlc['open'] if ohlc['open'] <= sl_level else sl_level
                    exit_reason = ExitReason.SL
                elif tp_level is not None and ohlc['high'] >= tp_level:
                    exit_price = ohlc['open'] if ohlc['open'] >= tp_level else tp_level
                    exit_reason = ExitReason.TP
            else:  # short
                if sl_level is not None and ohlc['high'] >= sl_level:
                    exit_price = ohlc['open'] if ohlc['open'] >= sl_level else sl_level
                    exit_reason = ExitReason.SL
                elif tp_level is not None and ohlc['low'] <= tp_level:
                    exit_price = ohlc['open'] if ohlc['open'] <= tp_level else tp_level
                    exit_reason = ExitReason.TP

            # Check num_bars exit
            if not exit_price:
                exit_conds = self.stratOBJ.exit_conds(self.strategy)
                for cond in exit_conds:
                    if cond.get('cond_type') == 'num_bars':
                        max_bars = int(cond['cond'])
                        if bars_in_pos >= max_bars:
                            exit_price = ohlc['open']
                            exit_reason = ExitReason.NUM_BARS
                            break

            # Check exit conditions (requires window data)
            if not exit_price and bar_idx > entry_bar_idx:
                window_data = get_window_slice(bar_idx)
                if window_data is not None and check_exit_condition(window_data):
                    exit_price = ohlc['open']
                    exit_reason = ExitReason.EXIT_CONDITION

            if exit_price:
                return (bar_idx, bar_date, exit_price, exit_reason)

        # If we reach end of data, force close at last bar
        last_bar = primary_df[total_bars - 1]
        last_date = extract_scalar(last_bar['date'])
        last_close = float(extract_scalar(last_bar['close']))
        return (total_bars - 1, last_date, last_close, ExitReason.BACKTEST_END)

    def load_minute_data_for_range(
        self,
        start_timestamp: datetime,
        end_timestamp: datetime
    ) -> Optional[pl.DataFrame]:
        """
        Load 1-minute data for a specific timestamp range.

        Args:
            start_timestamp: Start of range (inclusive)
            end_timestamp: End of range (inclusive)

        Returns:
            DataFrame with 1-minute bars, or None if unavailable
        """
        try:
            # Convert timestamps to date strings for loading
            start_date = start_timestamp.strftime('%Y-%m-%d') if hasattr(start_timestamp, 'strftime') else str(start_timestamp)[:10]
            end_date = end_timestamp.strftime('%Y-%m-%d') if hasattr(end_timestamp, 'strftime') else str(end_timestamp)[:10]

            # Load 1-minute data using preprocessor
            minute_data = self.preprocessor.load_and_resample(
                symbol=self.symbol,
                timeframes=['1 min'],
                start_date=start_date,
                end_date=end_date
            )

            if '1 min' not in minute_data or minute_data['1 min'].is_empty():
                if self.verbose:
                    print(f"  [WARNING] No 1-minute data available for {self.symbol} from {start_date} to {end_date}")
                return None

            # Truncate to minute precision before filtering to avoid sub-minute
            # timestamp mismatches between primary-bar boundaries and minute data.
            df = minute_data['1 min']
            df = df.with_columns(pl.col('date').dt.truncate('1m'))
            start_trunc = start_timestamp.replace(second=0, microsecond=0) if hasattr(start_timestamp, 'replace') else start_timestamp
            end_trunc = end_timestamp.replace(second=0, microsecond=0) if hasattr(end_timestamp, 'replace') else end_timestamp
            df = df.filter(
                (pl.col('date') >= start_trunc) &
                (pl.col('date') <= end_trunc)
            )

            if df.is_empty():
                if self.verbose:
                    print(f"  [WARNING] No 1-minute data in range {start_timestamp} to {end_timestamp}")
                return None

            return df

        except Exception as e:
            if self.verbose:
                print(f"  [WARNING] Failed to load 1-minute data: {e}")
            return None

    def simulate_position_with_sl_mgmt(
        self,
        entry_bar_idx: int,
        entry_price: float,
        position_side: str,
        initial_sl_level: float,
        tp_level: float,
        be_price: float,
        sl_mgmt_config: Dict,
        min_tick: Optional[float],
        trailing_step: float,
        get_window_slice: Callable,
        check_exit_condition: Callable
    ) -> Tuple[int, datetime, float, str, float]:
        """
        Simulate the entire position with BE/TSL management.

        This method:
        1. Finds baseline exit to determine date range
        2. Loads minute data for that range
        3. Simulates BE/TSL management on minute bars
        4. Returns the actual exit with granular exit reason

        Args:
            entry_bar_idx: Bar index where position was entered
            entry_price: Entry price
            position_side: 'long' or 'short'
            initial_sl_level: Initial SL level
            tp_level: Take profit level
            be_price: Breakeven price
            sl_mgmt_config: Stop loss management config
            min_tick: Minimum tick size
            trailing_step: Trailing step size
            get_window_slice: Function to get window data
            check_exit_condition: Function to check exit conditions

        Returns:
            Tuple of (exit_bar_idx, exit_minute_timestamp, exit_price, exit_reason, final_sl_level)
        """
        primary_tf = self.stratOBJ.process_freq(self.strategy)
        primary_df = self.full_data[primary_tf]

        # Get entry timestamp
        entry_bar = primary_df[entry_bar_idx]
        entry_timestamp = extract_scalar(entry_bar['date'])

        # Find baseline exit to determine date range
        baseline_exit_bar, baseline_exit_timestamp, baseline_exit_price, baseline_exit_reason = \
            self.find_baseline_exit(
                entry_bar_idx, position_side, initial_sl_level, tp_level,
                get_window_slice, check_exit_condition
            )

        # DIAGNOSTIC: Log initial state
        if self.verbose:
            print(f"  [SL_MGMT] === DIAGNOSTIC START ===")
            print(f"  [SL_MGMT] Entry: ${entry_price:.2f} | Side: {position_side}")
            sl_str = f"${initial_sl_level:.2f}" if initial_sl_level is not None else "None"
            tp_str = f"${tp_level:.2f}" if tp_level is not None else "None"
            print(f"  [SL_MGMT] Initial SL: {sl_str} | TP: {tp_str} | BE Price: ${be_price:.2f}")
            print(f"  [SL_MGMT] Baseline exit: Bar {baseline_exit_bar} | {baseline_exit_timestamp} | {baseline_exit_reason} @ ${baseline_exit_price:.2f}")

        # Reset SL to initial level for simulation
        sim_sl_level = initial_sl_level
        sim_be_status = False
        sim_tsl_activated = False

        # Extract config
        config = SLTPConfig.from_strategy_config(sl_mgmt_config)

        # Load minute data for the position's timespan
        minute_df = self.load_minute_data_for_range(entry_timestamp, baseline_exit_timestamp)

        if minute_df is not None and not minute_df.is_empty():
            # Simulate on minute bars
            if self.verbose:
                print(f"  [SL_MGMT] Simulating on {len(minute_df)} minute bars")

            result = self._simulate_on_minute_bars(
                minute_df, entry_price, position_side, tp_level, be_price,
                sim_sl_level, sim_be_status, sim_tsl_activated, config,
                min_tick, trailing_step, baseline_exit_bar, baseline_exit_timestamp,
                baseline_exit_price, baseline_exit_reason
            )
            return result
        else:
            # Fallback: simulate on primary bars
            if self.verbose:
                print(f"  [SL_MGMT] Fallback: simulating on primary bars (no minute data)")

            result = self._simulate_on_primary_bars(
                entry_bar_idx, entry_price, position_side, tp_level, be_price,
                sim_sl_level, sim_be_status, sim_tsl_activated, config,
                min_tick, trailing_step, baseline_exit_bar, baseline_exit_timestamp,
                baseline_exit_price, baseline_exit_reason
            )
            return result

    def _simulate_on_minute_bars(
        self,
        minute_df: pl.DataFrame,
        entry_price: float,
        position_side: str,
        tp_level: float,
        be_price: float,
        sim_sl_level: float,
        sim_be_status: bool,
        sim_tsl_activated: bool,
        config: SLTPConfig,
        min_tick: Optional[float],
        trailing_step: float,
        baseline_exit_bar: int,
        baseline_exit_timestamp: datetime,
        baseline_exit_price: float,
        baseline_exit_reason: str
    ) -> Tuple[int, datetime, float, str, float]:
        """Simulate position on minute bars."""

        for i in range(len(minute_df)):
            minute_bar = minute_df[i]

            bar_open = float(extract_scalar(minute_bar['open']))
            bar_high = float(extract_scalar(minute_bar['high']))
            bar_low = float(extract_scalar(minute_bar['low']))
            bar_date = extract_scalar(minute_bar['date'])

            # STEP 1: Check SL/TP exits FIRST using CURRENT SL level
            # Gap-adjusted: fill at open if bar opens past level
            exit_price = None
            exit_reason = None

            if position_side == 'long':
                if sim_sl_level is not None and bar_low <= sim_sl_level:
                    exit_price = bar_open if bar_open <= sim_sl_level else sim_sl_level
                    exit_reason = self._get_sl_exit_reason(sim_be_status, sim_tsl_activated)
                    if self.verbose:
                        print(f"  [SL_MGMT] EXIT @ {bar_date} | bar_low=${bar_low:.2f} <= sim_sl=${sim_sl_level:.2f} | reason={exit_reason}")
                elif tp_level is not None and bar_high >= tp_level:
                    exit_price = bar_open if bar_open >= tp_level else tp_level
                    exit_reason = ExitReason.TP
                    if self.verbose:
                        print(f"  [SL_MGMT] EXIT @ {bar_date} | bar_high=${bar_high:.2f} >= tp=${tp_level:.2f} | reason=TP")
            else:  # short
                if sim_sl_level is not None and bar_high >= sim_sl_level:
                    exit_price = bar_open if bar_open >= sim_sl_level else sim_sl_level
                    exit_reason = self._get_sl_exit_reason(sim_be_status, sim_tsl_activated)
                    if self.verbose:
                        print(f"  [SL_MGMT] EXIT @ {bar_date} | bar_high=${bar_high:.2f} >= sim_sl=${sim_sl_level:.2f} | reason={exit_reason}")
                elif tp_level is not None and bar_low <= tp_level:
                    exit_price = bar_open if bar_open <= tp_level else tp_level
                    exit_reason = ExitReason.TP
                    if self.verbose:
                        print(f"  [SL_MGMT] EXIT @ {bar_date} | bar_low=${bar_low:.2f} <= tp=${tp_level:.2f} | reason=TP")

            # If exit triggered, return immediately
            if exit_price:
                exit_bar_idx = self._find_primary_bar_for_timestamp(bar_date)
                if self.verbose:
                    print(f"  [SL_MGMT] RETURN FROM MINUTE SIM: exit_bar={exit_bar_idx} | exit_reason={exit_reason} | exit_price=${exit_price:.2f}")
                    print(f"  [SL_MGMT]   final sim_be_status={sim_be_status} | sim_tsl_activated={sim_tsl_activated}")
                    print(f"  [SL_MGMT] === DIAGNOSTIC END ===")
                return (exit_bar_idx, bar_date, exit_price, exit_reason, sim_sl_level)

            # STEP 2: No exit occurred - update BE/TSL state for next bar
            favorable_price = bar_high if position_side == 'long' else bar_low
            sim_sl_level, sim_be_status, sim_tsl_activated = self._update_be_tsl_state(
                favorable_price, entry_price, tp_level, be_price,
                sim_sl_level, sim_be_status, sim_tsl_activated,
                config, min_tick, trailing_step, position_side, bar_date
            )

        # If we finished minute bars without exit, use baseline exit
        if baseline_exit_reason == ExitReason.SL:
            baseline_exit_reason = self._get_sl_exit_reason(sim_be_status, sim_tsl_activated)

        if self.verbose:
            print(f"  [SL_MGMT] RETURN FROM BASELINE (minute sim finished without exit)")
            print(f"  [SL_MGMT]   baseline_exit_reason={baseline_exit_reason} | baseline_exit_price=${baseline_exit_price:.2f}")
            print(f"  [SL_MGMT]   final sim_be_status={sim_be_status} | sim_tsl_activated={sim_tsl_activated}")
            print(f"  [SL_MGMT] === DIAGNOSTIC END ===")

        return (baseline_exit_bar, baseline_exit_timestamp, baseline_exit_price, baseline_exit_reason, sim_sl_level)

    def _simulate_on_primary_bars(
        self,
        entry_bar_idx: int,
        entry_price: float,
        position_side: str,
        tp_level: float,
        be_price: float,
        sim_sl_level: float,
        sim_be_status: bool,
        sim_tsl_activated: bool,
        config: SLTPConfig,
        min_tick: Optional[float],
        trailing_step: float,
        baseline_exit_bar: int,
        baseline_exit_timestamp: datetime,
        baseline_exit_price: float,
        baseline_exit_reason: str
    ) -> Tuple[int, datetime, float, str, float]:
        """Fallback: simulate on primary bars when minute data unavailable."""
        primary_tf = self.stratOBJ.process_freq(self.strategy)
        primary_df = self.full_data[primary_tf]
        total_bars = len(primary_df)

        # Start from bar after entry to match main backtester behavior
        bars_in_pos = 0

        for bar_idx in range(entry_bar_idx + 1, min(baseline_exit_bar + 1, total_bars)):
            current_bar = primary_df[bar_idx]
            bars_in_pos += 1

            ohlc = extract_ohlc(current_bar)
            bar_date = extract_scalar(current_bar['date'])

            # STEP 1: Check SL/TP exits FIRST using CURRENT SL level
            # Gap-adjusted: fill at open if bar opens past level
            exit_price = None
            exit_reason = None

            if position_side == 'long':
                if sim_sl_level is not None and ohlc['low'] <= sim_sl_level:
                    exit_price = ohlc['open'] if ohlc['open'] <= sim_sl_level else sim_sl_level
                    exit_reason = self._get_sl_exit_reason(sim_be_status, sim_tsl_activated)
                    if self.verbose:
                        print(f"  [SL_MGMT] FALLBACK EXIT @ bar {bar_idx} | bar_low=${ohlc['low']:.2f} <= sim_sl=${sim_sl_level:.2f} | reason={exit_reason}")
                elif tp_level is not None and ohlc['high'] >= tp_level:
                    exit_price = ohlc['open'] if ohlc['open'] >= tp_level else tp_level
                    exit_reason = ExitReason.TP
            else:  # short
                if sim_sl_level is not None and ohlc['high'] >= sim_sl_level:
                    exit_price = ohlc['open'] if ohlc['open'] >= sim_sl_level else sim_sl_level
                    exit_reason = self._get_sl_exit_reason(sim_be_status, sim_tsl_activated)
                    if self.verbose:
                        print(f"  [SL_MGMT] FALLBACK EXIT @ bar {bar_idx} | bar_high=${ohlc['high']:.2f} >= sim_sl=${sim_sl_level:.2f} | reason={exit_reason}")
                elif tp_level is not None and ohlc['low'] <= tp_level:
                    exit_price = ohlc['open'] if ohlc['open'] <= tp_level else tp_level
                    exit_reason = ExitReason.TP

            # Check num_bars exit (exit-at-open)
            if not exit_price:
                exit_conds = self.stratOBJ.exit_conds(self.strategy)
                for cond in exit_conds:
                    if cond.get('cond_type') == 'num_bars':
                        max_bars = int(cond['cond'])
                        if bars_in_pos >= max_bars:
                            exit_price = ohlc['open']
                            exit_reason = ExitReason.NUM_BARS
                            break

            if exit_price:
                if self.verbose:
                    print(f"  [SL_MGMT] RETURN FROM FALLBACK: exit_bar={bar_idx} | exit_reason={exit_reason} | exit_price=${exit_price:.2f}")
                    print(f"  [SL_MGMT] === DIAGNOSTIC END ===")
                return (bar_idx, bar_date, exit_price, exit_reason, sim_sl_level)

            # STEP 2: No exit - update BE/TSL state for next bar
            favorable_price = ohlc['high'] if position_side == 'long' else ohlc['low']
            sim_sl_level, sim_be_status, sim_tsl_activated = self._update_be_tsl_state(
                favorable_price, entry_price, tp_level, be_price,
                sim_sl_level, sim_be_status, sim_tsl_activated,
                config, min_tick, trailing_step, position_side, bar_date,
                is_fallback=True, bar_idx=bar_idx
            )

        # Use baseline exit
        if baseline_exit_reason == ExitReason.SL:
            baseline_exit_reason = self._get_sl_exit_reason(sim_be_status, sim_tsl_activated)

        if self.verbose:
            print(f"  [SL_MGMT] RETURN FROM FALLBACK BASELINE: exit_reason={baseline_exit_reason} | exit_price=${baseline_exit_price:.2f}")
            print(f"  [SL_MGMT]   sim_be_status={sim_be_status} | sim_tsl_activated={sim_tsl_activated}")
            print(f"  [SL_MGMT] === DIAGNOSTIC END ===")

        return (baseline_exit_bar, baseline_exit_timestamp, baseline_exit_price, baseline_exit_reason, sim_sl_level)

    def _update_be_tsl_state(
        self,
        favorable_price: float,
        entry_price: float,
        tp_level: float,
        be_price: float,
        sim_sl_level: float,
        sim_be_status: bool,
        sim_tsl_activated: bool,
        config: SLTPConfig,
        min_tick: Optional[float],
        trailing_step: float,
        position_side: str,
        bar_date: Any,
        is_fallback: bool = False,
        bar_idx: Optional[int] = None
    ) -> Tuple[float, bool, bool]:
        """Update BE/TSL state based on favorable price."""
        profit_ratio = self._calculate_profit_ratio(favorable_price, entry_price, tp_level, position_side)

        if profit_ratio is not None:
            # Check BE trigger
            if config.be_enabled and not sim_be_status:
                if profit_ratio >= config.be_profit_ratio:
                    old_sl = sim_sl_level
                    sim_sl_level = be_price
                    sim_be_status = True
                    if self.verbose:
                        prefix = f"bar {bar_idx}" if is_fallback else str(bar_date)
                        print(f"  [SL_MGMT] {'FALLBACK ' if is_fallback else ''}BE TRIGGERED @ {prefix} | ratio={profit_ratio:.2%} >= {config.be_profit_ratio:.2%} | SL: ${old_sl:.2f} -> ${sim_sl_level:.2f}")

            # Check TSL update (only after BE triggered)
            if config.tsl_enabled and sim_be_status:
                ratio_adj = np.floor(profit_ratio / trailing_step) * trailing_step

                # Handle edge case: trailing_ratio near zero causes 0/0 (NaN)
                tsl_ratio = config.tsl_trailing_ratio
                be_ratio = config.be_profit_ratio

                if tsl_ratio < 1e-6:
                    # Linear fallback: x = (ratio_adj - be_ratio) / (1 - be_ratio)
                    if (1 - be_ratio) > 0:
                        x = max(0.0, min(1.0, (ratio_adj - be_ratio) / (1 - be_ratio)))
                    else:
                        x = None
                else:
                    numerator = 1 - np.exp(-tsl_ratio * (ratio_adj - be_ratio))
                    denominator = 1 - np.exp(-tsl_ratio * (1 - be_ratio))
                    if abs(denominator) >= 1e-10:
                        x = max(0.0, min(1.0, numerator / denominator))
                    else:
                        x = None

                if x is not None:
                    new_sl = entry_price + (favorable_price - entry_price) * x
                    new_sl = round_price(new_sl, position_side, min_tick)

                    is_better = (position_side == 'long' and new_sl > sim_sl_level) or \
                               (position_side == 'short' and new_sl < sim_sl_level)

                    if is_better:
                        old_sl = sim_sl_level
                        sim_sl_level = new_sl
                        sim_tsl_activated = True
                        if self.verbose:
                            prefix = f"bar {bar_idx}" if is_fallback else str(bar_date)
                            print(f"  [SL_MGMT] {'FALLBACK ' if is_fallback else ''}TSL UPDATE @ {prefix} | ratio={profit_ratio:.2%} | SL: ${old_sl:.2f} -> ${sim_sl_level:.2f}")

        return sim_sl_level, sim_be_status, sim_tsl_activated

    def _calculate_profit_ratio(
        self,
        current_price: float,
        entry_price: float,
        tp_level: float,
        position_side: str
    ) -> Optional[float]:
        """Calculate profit ratio relative to TP distance.  Returns None when tp_level is None."""
        if tp_level is None:
            return None
        if position_side == 'long':
            denominator = tp_level - entry_price
            if denominator == 0:
                return None
            return (current_price - entry_price) / denominator
        else:  # short
            denominator = entry_price - tp_level
            if denominator == 0:
                return None
            return (entry_price - current_price) / denominator

    def _get_sl_exit_reason(self, be_status: bool, tsl_activated: bool) -> str:
        """Get appropriate SL exit reason based on state."""
        if tsl_activated:
            return ExitReason.SL_TSL
        elif be_status:
            return ExitReason.SL_BE
        else:
            return ExitReason.SL

    def _find_primary_bar_for_timestamp(self, timestamp: datetime) -> int:
        """Find the primary bar index that contains the given timestamp."""
        primary_tf = self.stratOBJ.process_freq(self.strategy)
        primary_df = self.full_data[primary_tf]

        # Find the bar where timestamp falls within
        filtered = primary_df.filter(pl.col('date') <= timestamp)

        if filtered.is_empty():
            _logger.warning("_find_primary_bar_for_timestamp: no bars at or before %s, returning 0", timestamp)
            return 0

        # Return the index of the last bar before or at this timestamp
        last_date = filtered['date'][-1]
        if last_date in self.timestamp_cache.get(primary_tf, {}):
            return self.timestamp_cache[primary_tf][last_date]

        # Fallback: linear search
        for i in range(len(primary_df) - 1, -1, -1):
            bar_date = extract_scalar(primary_df[i]['date'])
            if bar_date <= timestamp:
                return i

        _logger.warning("_find_primary_bar_for_timestamp: linear search failed for %s, returning 0", timestamp)
        return 0

    def resolve_sl_tp_conflict(
        self,
        bar_idx: int,
        current_bar: Any,
        position_side: str,
        sl_level: float,
        tp_level: float
    ) -> Tuple[float, str]:
        """
        Resolve SL/TP conflict when both could trigger on the same bar.

        Loads 1-minute data to determine which level was actually hit first.

        Args:
            bar_idx: Current bar index
            current_bar: Current bar data
            position_side: 'long' or 'short'
            sl_level: Current SL level
            tp_level: Take profit level

        Returns:
            Tuple of (exit_price, exit_reason)
        """
        primary_tf = self.stratOBJ.process_freq(self.strategy)

        # Get bar timestamps
        bar_timestamp = extract_scalar(current_bar['date'])

        # For end timestamp, get the next bar's timestamp or add timeframe duration
        primary_df = self.full_data[primary_tf]
        if bar_idx + 1 < len(primary_df):
            next_bar = primary_df[bar_idx + 1]
            end_timestamp = extract_scalar(next_bar['date'])
        else:
            # Last bar - estimate end based on timeframe
            minutes = timeframe_to_minutes(primary_tf)
            end_timestamp = bar_timestamp + timedelta(minutes=minutes)

        # Load minute data for this bar
        minute_df = self.load_minute_data_for_range(bar_timestamp, end_timestamp)

        if minute_df is None or minute_df.is_empty():
            # Fallback: SL priority (conservative)
            if self.verbose:
                print(f"  [SL/TP CONFLICT] No minute data available, defaulting to SL")
            return (sl_level, ExitReason.SL)

        if self.verbose:
            print(f"  [SL/TP CONFLICT] Resolving with {len(minute_df)} minute bars")

        # Walk through minute bars to find which was hit first
        # Gap-adjusted: fill at open if bar opens past level
        for i in range(len(minute_df)):
            minute_bar = minute_df[i]
            m_open = float(extract_scalar(minute_bar['open']))
            m_high = float(extract_scalar(minute_bar['high']))
            m_low = float(extract_scalar(minute_bar['low']))

            if position_side == 'long':
                # Check SL first (low touches SL)
                if sl_level is not None and m_low <= sl_level:
                    fill = m_open if m_open <= sl_level else sl_level
                    if self.verbose:
                        print(f"  [SL/TP CONFLICT] SL hit first at minute bar {i}")
                    return (fill, ExitReason.SL)
                # Check TP (high touches TP)
                if tp_level is not None and m_high >= tp_level:
                    fill = m_open if m_open >= tp_level else tp_level
                    if self.verbose:
                        print(f"  [SL/TP CONFLICT] TP hit first at minute bar {i}")
                    return (fill, ExitReason.TP)
            else:  # short
                # Check SL first (high touches SL)
                if sl_level is not None and m_high >= sl_level:
                    fill = m_open if m_open >= sl_level else sl_level
                    if self.verbose:
                        print(f"  [SL/TP CONFLICT] SL hit first at minute bar {i}")
                    return (fill, ExitReason.SL)
                # Check TP (low touches TP)
                if tp_level is not None and m_low <= tp_level:
                    fill = m_open if m_open <= tp_level else tp_level
                    if self.verbose:
                        print(f"  [SL/TP CONFLICT] TP hit first at minute bar {i}")
                    return (fill, ExitReason.TP)

        # If we get here without hitting either (shouldn't happen), default to SL
        if self.verbose:
            print(f"  [SL/TP CONFLICT] No clear hit found in minute data, defaulting to SL")
        return (sl_level, ExitReason.SL)
