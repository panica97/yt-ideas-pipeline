"""
Portfolio Orchestrator

Coordinates multiple strategies through a synchronized time loop for portfolio-level
backtesting. Ensures all strategies advance through time together with proper
exit-before-entry processing for accurate portfolio state tracking.

Key responsibilities:
- Build unified timeline from all strategy timeframes
- Process ALL exits BEFORE any entries per bar (critical for margin accuracy)
- Track portfolio state (equity, margin) across all strategies
- Coordinate data loading and indicator calculation
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import math

import polars as pl

from ibkr_core import StratOBJ, INDICATORS, Initial_SL_TP

# Add engine directory to path for local imports
ENGINE_PATH = str(Path(__file__).parent)
if ENGINE_PATH not in sys.path:
    sys.path.insert(0, ENGINE_PATH)

# Add project root to path for logger
PROJECT_ROOT = str(Path(__file__).parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from logger import get_logger
_logger = get_logger("engine.portfolio")

from _00_constants import ExitReason
from _01_data_processor import DataPreprocessor
from _02_strategy_manager import STRATEGY_BACKTEST
from _03_price_utils import extract_scalar, extract_ohlc, round_price, timeframe_to_minutes
from _03b_warmup_utils import compute_max_lookback_with_chains, compute_warmup_bars_with_chains
from _04_trading_hours import TradingHoursValidator
from _05_sl_tp_manager import SLTPConfig, SLTPManager
from _06_position_manager import Position, PositionManager
from _09_position_sizer import BacktestPositionSizer
from _11_portfolio_state import PortfolioState, PositionInfo, EquitySnapshot
from _13_margin_calculator import MarginCalculator
from _14_portfolio_metrics import PortfolioMetricsCalculator
from _15_portfolio_reporter import PortfolioReporter


# ============================================================================
# Data Classes for Entry/Exit Results
# ============================================================================

class EntryResult:
    """Result from checking entry conditions for a strategy."""

    def __init__(
        self,
        strategy_id: int,
        symbol: str,
        side: str,
        entry_price: float,
        ref_price: float,
        sl_level: float,
        tp_level: float,
        position_size: int,
        sl_mgmt_config: Optional[Dict],
        bar_idx: int,
        timestamp: datetime
    ):
        self.strategy_id = strategy_id
        self.symbol = symbol
        self.side = side
        self.entry_price = entry_price
        self.ref_price = ref_price
        self.sl_level = sl_level
        self.tp_level = tp_level
        self.position_size = position_size
        self.sl_mgmt_config = sl_mgmt_config
        self.bar_idx = bar_idx
        self.timestamp = timestamp


class ExitResult:
    """Result from checking exit conditions for a strategy."""

    def __init__(
        self,
        strategy_id: int,
        symbol: str,
        exit_price: float,
        exit_reason: str,
        bar_idx: int,
        timestamp: datetime,
        pnl: float,
        exit_minute_timestamp: Optional[datetime] = None
    ):
        self.strategy_id = strategy_id
        self.symbol = symbol
        self.exit_price = exit_price
        self.exit_reason = exit_reason
        self.bar_idx = bar_idx
        self.timestamp = timestamp
        self.pnl = pnl
        self.exit_minute_timestamp = exit_minute_timestamp


# ============================================================================
# StrategyRunner - Per-Strategy Wrapper
# ============================================================================

class StrategyRunner:
    """
    Lightweight wrapper that manages a single strategy within portfolio context.

    Each StrategyRunner:
    - Has its own PositionManager instance
    - Has its own trading hours validator
    - Has its own entry validator
    - Reads from shared PortfolioState (does NOT track its own equity)
    - Stores strategy-specific config (primary_tf, ind_list, etc.)
    """

    def __init__(
        self,
        strategy_id: int,
        stratOBJ: StratOBJ,
        symbol: str,
        portfolio_state: PortfolioState,
        verbose: bool = False,
        slippage_ticks: float = 0.0,
        comm_per_contract: float = 0.0,
        max_volume: Optional[int] = None,
        enforce_trading_hours: bool = False,
        position_sizing: str = 'half_kelly',
        fixed_volume: int = 1,
        risk_per_operation: float = 0.02,
    ):
        """
        Initialize a strategy runner.

        Args:
            strategy_id: Strategy ID
            stratOBJ: StratOBJ instance with strategy definitions
            symbol: Trading symbol (derived from stratOBJ if not provided)
            portfolio_state: Shared portfolio state
            verbose: Print detailed progress
            slippage_ticks: Slippage in ticks per side
            comm_per_contract: Commission per contract per side
            max_volume: Maximum contracts per trade
            enforce_trading_hours: If True, respect strategy trading_hours restrictions
            position_sizing: Sizing mode ('fixed', 'rpo', or 'half_kelly')
            fixed_volume: Number of contracts for fixed mode
            risk_per_operation: Risk percentage for RPO mode (0.02 = 2%)
        """
        self.strategy_id = strategy_id
        self.stratOBJ = stratOBJ
        self.symbol = symbol if symbol else stratOBJ.symbol(strategy_id)
        self.portfolio_state = portfolio_state
        self.verbose = verbose
        self.slippage_ticks = slippage_ticks
        self.comm_per_contract = comm_per_contract
        self.max_volume = max_volume
        self.enforce_trading_hours = enforce_trading_hours

        # Strategy config from stratOBJ
        self.primary_tf = stratOBJ.process_freq(strategy_id)
        self.ind_list = stratOBJ.ind_list(strategy_id)
        self.min_tick = stratOBJ.minTick(strategy_id)
        self.multiplier = stratOBJ.multiplier(strategy_id)

        # Initialize per-strategy managers
        self.position_manager = PositionManager()
        self.trading_hours = TradingHoursValidator(stratOBJ, strategy_id)

        # Position sizer - respects user-provided sizing mode
        self.position_sizer = BacktestPositionSizer(
            mode=position_sizing,
            fixed_volume=fixed_volume,
            risk_per_operation=risk_per_operation,
            max_volume=max_volume,
        )

        # Cached values
        self._effective_max_shift = None
        self._window_size = None
        self._warmup_bars = None

        # Track trades for reporting
        self.trades: List[Dict] = []

    def has_position(self) -> bool:
        """Check if this strategy has an open position."""
        return self.position_manager.is_open

    def get_position_key(self) -> Tuple[int, str]:
        """Get the position key for portfolio state tracking."""
        return (self.strategy_id, self.symbol)

    def compute_warmup_requirements(self) -> Dict:
        """
        Compute warmup bars and window size needed for this strategy.

        Returns:
            Dict with 'window_size', 'warmup_bars', 'max_shift'
        """
        # Compute effective max_shift
        try:
            base_max_shift = int((self.stratOBJ.max_shift(self.strategy_id) or [0])[0] or 0)
        except Exception:
            base_max_shift = 0

        # Check conditions for additional shift requirements
        conds = []
        for getter_name in ('long_conds', 'short_conds', 'exit_conds'):
            try:
                getter = getattr(self.stratOBJ, getter_name, None)
                if getter is None:
                    continue
                clist = getter(self.strategy_id) or []
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
            cond_type = str(c.get('cond_type', '') or '')
            extra = self._cond_extra_bars(cond_type)
            required_tail_len = max(required_tail_len, 1 + max_s + extra)

        required_shift = max(0, required_tail_len - 1)
        max_shift = max(base_max_shift, required_shift)
        self._effective_max_shift = max_shift

        # Compute max lookback from indicators (chain-aware)
        max_lookback = compute_max_lookback_with_chains(
            self.ind_list, self.primary_tf, self._effective_indicator_lookback
        )
        window_size = max_lookback + (1 + max_shift)
        self._window_size = window_size

        # Compute warmup bars (chain-aware)
        warmup_primary = compute_warmup_bars_with_chains(
            self.ind_list, max_shift, self.primary_tf, self._effective_indicator_lookback
        )
        warmup_bars = max(window_size, warmup_primary)
        self._warmup_bars = warmup_bars

        return {
            'window_size': window_size,
            'warmup_bars': warmup_bars,
            'max_shift': max_shift
        }

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

    def check_entry(
        self,
        bar_idx: int,
        current_bar: Any,
        window_data: Dict[str, pl.DataFrame]
    ) -> Optional[EntryResult]:
        """
        Check for entry signals for this strategy.

        Args:
            bar_idx: Current bar index
            current_bar: Current bar data (from primary timeframe)
            window_data: Rolling window data with indicators

        Returns:
            EntryResult if entry should occur, None otherwise
        """
        # Check trading hours
        if self.enforce_trading_hours:
            bar_datetime = extract_scalar(current_bar['date'])
            if not self.trading_hours.is_entry_allowed(bar_datetime):
                return None

        # Check entry conditions
        a, b, strategies_dict, _ = STRATEGY_BACKTEST(
            ib=None,
            stratsOBJ=self.stratOBJ,
            strat_id=self.strategy_id,
            entries=True,
            exits=False,
            all=False,
            logging=False,
            ind_data=window_data
        ).process()

        signal = strategies_dict[self.strategy_id]

        # No signal
        if not signal['long'] and not signal['short']:
            return None

        side = 'long' if signal['long'] else 'short'

        # Get entry price (open of current bar)
        bar_open = float(extract_scalar(current_bar['open']))
        ref_price = bar_open  # In backtest, ref_price = entry bar's open

        # Calculate SL/TP
        signal_dict = {
            'strat_code': self.strategy_id,
            'long': side == 'long',
            'short': side == 'short',
            'exit': False
        }

        sl_tp_calculator = Initial_SL_TP(
            ib=None,
            stratOBJ=self.stratOBJ,
            signal_dict=signal_dict,
            entry_data={self.strategy_id: window_data},
            ref_price=ref_price,
            SL_market_data=None,
            TP_market_data=None
        )

        enriched_signal = sl_tp_calculator.generate()

        # Round SL and TP
        raw_sl = enriched_signal['SL_level']
        raw_tp = enriched_signal['TP_level']
        sl_level = round_price(raw_sl, side, self.min_tick)
        tp_level = round_price(raw_tp, side, self.min_tick)

        # Calculate position size using portfolio equity
        position_size = self.position_sizer.calculate_volume(
            equity=self.portfolio_state.current_equity,
            entry_price=bar_open,
            sl_level=sl_level,
            multiplier=self.multiplier,
            stratOBJ=self.stratOBJ,
            strategy=self.strategy_id
        )

        # Get SL management config
        sl_mgmt_config = self.stratOBJ.stop_loss_mgmt(self.strategy_id)

        entry_timestamp = extract_scalar(current_bar['date'])

        return EntryResult(
            strategy_id=self.strategy_id,
            symbol=self.symbol,
            side=side,
            entry_price=bar_open,
            ref_price=ref_price,
            sl_level=sl_level,
            tp_level=tp_level,
            position_size=position_size,
            sl_mgmt_config=sl_mgmt_config,
            bar_idx=bar_idx,
            timestamp=entry_timestamp
        )

    def check_exit(
        self,
        bar_idx: int,
        current_bar: Any,
        window_data: Optional[Dict[str, pl.DataFrame]],
        primary_df: pl.DataFrame
    ) -> Optional[ExitResult]:
        """
        Check for exit conditions for this strategy.

        Args:
            bar_idx: Current bar index
            current_bar: Current bar data
            window_data: Rolling window data with indicators (may be None)
            primary_df: Full primary timeframe dataframe

        Returns:
            ExitResult if exit should occur, None otherwise
        """
        if not self.has_position():
            return None

        pos = self.position_manager.position
        pos.bars_in_position += 1

        ohlc = extract_ohlc(current_bar)
        exit_price: Optional[float] = None
        exit_reason: Optional[str] = None
        exit_minute_timestamp = None

        # Check trading hours for discretionary exits
        exit_schedule_allowed = True
        if self.enforce_trading_hours:
            bar_datetime = extract_scalar(current_bar['date'])
            exit_schedule_allowed = self.trading_hours.is_exit_allowed(bar_datetime)

        # num_bars exit
        if exit_schedule_allowed:
            exit_conds = self.stratOBJ.exit_conds(self.strategy_id)
            for cond in exit_conds:
                if cond.get('cond_type') == 'num_bars':
                    try:
                        max_bars = int(cond['cond'])
                    except Exception:
                        max_bars = None
                    if max_bars is not None and pos.bars_in_position >= max_bars:
                        exit_price = ohlc['open']
                        exit_reason = ExitReason.NUM_BARS
                        break

        # Exit conditions from strategy
        if exit_price is None and window_data is not None and exit_schedule_allowed:
            _, _, strategies_dict, _ = STRATEGY_BACKTEST(
                ib=None,
                stratsOBJ=self.stratOBJ,
                strat_id=self.strategy_id,
                entries=False,
                exits=True,
                all=False,
                logging=False,
                ind_data=window_data
            ).process()
            if strategies_dict[self.strategy_id].get('exit'):
                exit_price = ohlc['open']
                exit_reason = ExitReason.EXIT_CONDITION

        # Standard SL/TP checks (always active)
        if exit_price is None:
            sl_hit = tp_hit = False
            if pos.side == 'long':
                sl_hit = ohlc['low'] <= pos.sl_level
                tp_hit = ohlc['high'] >= pos.tp_level
            else:
                sl_hit = ohlc['high'] >= pos.sl_level
                tp_hit = ohlc['low'] <= pos.tp_level

            if sl_hit and tp_hit:
                # Conflict - use SL (conservative), gap-adjusted
                if (pos.side == 'long' and ohlc['open'] <= pos.sl_level) or \
                   (pos.side == 'short' and ohlc['open'] >= pos.sl_level):
                    exit_price = ohlc['open']
                else:
                    exit_price = pos.sl_level
                exit_reason = ExitReason.SL
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

        if exit_price is None:
            return None

        # Calculate PnL using slippage-adjusted fill prices
        slippage_per_side = self.slippage_ticks * (self.min_tick or 0.25)
        if pos.side == 'long':
            entry_fill = pos.entry_price + slippage_per_side
            exit_fill = exit_price - slippage_per_side
            gross_pnl = (exit_fill - entry_fill) * pos.position_size * self.multiplier
        else:
            entry_fill = pos.entry_price - slippage_per_side
            exit_fill = exit_price + slippage_per_side
            gross_pnl = (entry_fill - exit_fill) * pos.position_size * self.multiplier

        commission = self.comm_per_contract * pos.position_size * 2
        pnl = gross_pnl - commission

        exit_timestamp = extract_scalar(current_bar['date'])

        return ExitResult(
            strategy_id=self.strategy_id,
            symbol=self.symbol,
            exit_price=exit_price,
            exit_reason=exit_reason,
            bar_idx=bar_idx,
            timestamp=exit_timestamp,
            pnl=pnl,
            exit_minute_timestamp=exit_minute_timestamp
        )

    def open_position(self, entry_result: EntryResult, primary_df: pl.DataFrame) -> None:
        """Open a position based on entry result."""
        self.position_manager.open_position(
            side=entry_result.side,
            entry_bar_idx=entry_result.bar_idx,
            entry_price=entry_result.entry_price,
            sl_level=entry_result.sl_level,
            tp_level=entry_result.tp_level,
            sl_mgmt_config=entry_result.sl_mgmt_config,
            position_size=entry_result.position_size
        )

        # Store ref_price on position
        pos = self.position_manager.position
        pos.ref_price = entry_result.ref_price

        if self.verbose:
            print(f"  [{self.strategy_id}] ENTRY {entry_result.side.upper()} @ ${entry_result.entry_price:.2f} "
                  f"| SL: ${entry_result.sl_level:.2f} | Size: {entry_result.position_size}")

    def close_position(
        self,
        exit_result: ExitResult,
        primary_df: pl.DataFrame,
        entry_equity: Optional[float] = None,
        entry_margin_used: Optional[float] = None,
        entry_open_positions: Optional[int] = None,
        exit_equity: Optional[float] = None,
        exit_margin_used: Optional[float] = None,
        exit_open_positions: Optional[int] = None
    ) -> Dict:
        """
        Close position and record trade.

        Args:
            exit_result: The exit result with price, reason, etc.
            primary_df: Primary timeframe DataFrame
            entry_equity: Portfolio equity at entry time (for enrichment)
            entry_margin_used: Portfolio margin used at entry time
            entry_open_positions: Number of open positions at entry time
            exit_equity: Portfolio equity at exit time
            exit_margin_used: Portfolio margin used at exit time
            exit_open_positions: Number of open positions at exit time

        Returns:
            Trade record dictionary
        """
        pos = self.position_manager.position

        # Get dates for trade record
        entry_date = extract_scalar(primary_df[pos.entry_bar_idx]['date'])
        signal_bar_date = extract_scalar(primary_df[max(0, pos.entry_bar_idx - 1)]['date'])
        exit_date = exit_result.timestamp

        # Capture ref_price
        ref_price = getattr(pos, 'ref_price', pos.entry_price)

        trade = self.position_manager.close_position(
            bar_idx=exit_result.bar_idx,
            exit_price=exit_result.exit_price,
            exit_reason=exit_result.exit_reason,
            strategy=self.strategy_id,
            signal_bar_date=signal_bar_date,
            entry_date=entry_date,
            exit_date=exit_date,
            multiplier=self.multiplier,
            commission_per_contract=self.comm_per_contract,
            slippage_ticks=self.slippage_ticks,
            min_tick=self.min_tick,
            exit_minute_timestamp=exit_result.exit_minute_timestamp
        )

        # Add ref_price to trade
        trade['ref_price'] = ref_price

        # Portfolio state at entry (PORT-04)
        if entry_equity is not None:
            trade['portfolio_state_at_entry'] = {
                'equity': entry_equity,
                'margin_used': entry_margin_used if entry_margin_used is not None else 0.0,
                'open_positions': entry_open_positions if entry_open_positions is not None else 0
            }

        # Portfolio state at exit (PORT-04)
        if exit_equity is not None:
            trade['portfolio_state_at_exit'] = {
                'equity': exit_equity,
                'margin_used': exit_margin_used if exit_margin_used is not None else 0.0,
                'open_positions': exit_open_positions if exit_open_positions is not None else 0
            }

        # Strategy contribution (PORT-03)
        if entry_equity is not None and entry_equity > 0:
            trade['strategy_contribution'] = {
                'pnl': trade['pnl'],
                'pnl_pct_of_equity': (trade['pnl'] / entry_equity) * 100
            }
        else:
            trade['strategy_contribution'] = {
                'pnl': trade['pnl'],
                'pnl_pct_of_equity': 0.0
            }

        self.trades.append(trade)

        if self.verbose:
            print(f"  [{self.strategy_id}] EXIT {exit_result.exit_reason} @ ${exit_result.exit_price:.2f} "
                  f"| PnL: ${trade['pnl']:+,.2f}")

        return trade

    def force_close_position(self, bar_idx: int, current_bar: Any, primary_df: pl.DataFrame) -> Optional[Dict]:
        """Force close position at end of backtest."""
        if not self.has_position():
            return None

        bar_close = float(extract_scalar(current_bar['close']))

        exit_result = ExitResult(
            strategy_id=self.strategy_id,
            symbol=self.symbol,
            exit_price=bar_close,
            exit_reason=ExitReason.BACKTEST_END,
            bar_idx=bar_idx,
            timestamp=extract_scalar(current_bar['date']),
            pnl=0  # Will be calculated in close_position
        )

        return self.close_position(exit_result, primary_df)


# ============================================================================
# PortfolioOrchestrator - Main Coordinator
# ============================================================================

class PortfolioOrchestrator:
    """
    Coordinates multiple strategies through a synchronized time loop.

    Key responsibilities:
    - Build unified timeline from all strategy timeframes
    - Process ALL exits BEFORE any entries per bar (critical!)
    - Track portfolio state (equity, margin) across all strategies
    - Coordinate data loading and indicator calculation
    """

    def __init__(
        self,
        strategies: List[int],
        stratOBJ: StratOBJ,
        start: str,
        end: str,
        initial_equity: float,
        verbose: bool = False,
        slippage_ticks: float = 0.0,
        comm_per_contract: float = 0.0,
        max_volume: Optional[int] = None,
        enforce_trading_hours: bool = False,
        hist_data_path: Optional[str] = None,
        position_sizing: str = 'half_kelly',
        fixed_volume: int = 1,
        risk_per_operation: float = 0.02,
        custom_indicators_dir: Optional[str] = None,
    ):
        """
        Initialize the portfolio orchestrator.

        Args:
            strategies: List of strategy IDs to run
            stratOBJ: StratOBJ instance with strategy definitions
            start: Start date 'YYYY-MM-DD'
            end: End date 'YYYY-MM-DD'
            initial_equity: Starting portfolio equity
            verbose: Print detailed progress
            slippage_ticks: Slippage in ticks per side
            comm_per_contract: Commission per contract per side
            max_volume: Maximum contracts per trade (per strategy)
            enforce_trading_hours: If True, respect strategy trading_hours restrictions
            hist_data_path: Path to historical data folder (default: 'hist_data')
            position_sizing: Sizing mode ('fixed', 'rpo', or 'half_kelly')
            fixed_volume: Number of contracts for fixed mode
            risk_per_operation: Risk percentage for RPO mode (0.02 = 2%)
            custom_indicators_dir: Path to custom indicator modules (None = use default)
        """
        self.strategies = strategies
        self.stratOBJ = stratOBJ
        self.start = start
        self.end = end
        self.initial_equity = initial_equity
        self.verbose = verbose
        self.slippage_ticks = slippage_ticks
        self.comm_per_contract = comm_per_contract
        self.max_volume = max_volume
        self.enforce_trading_hours = enforce_trading_hours
        self._custom_indicators_dir = custom_indicators_dir

        # Initialize margin calculator for per-contract margins
        self.margin_calculator = MarginCalculator()

        # Initialize portfolio state
        self.portfolio_state = PortfolioState(
            initial_equity=initial_equity,
            current_equity=initial_equity
        )

        # Create strategy runners
        self.strategy_runners: Dict[int, StrategyRunner] = {}
        for strat_id in strategies:
            symbol = stratOBJ.symbol(strat_id)
            self.strategy_runners[strat_id] = StrategyRunner(
                strategy_id=strat_id,
                stratOBJ=stratOBJ,
                symbol=symbol,
                portfolio_state=self.portfolio_state,
                verbose=verbose,
                slippage_ticks=slippage_ticks,
                comm_per_contract=comm_per_contract,
                max_volume=max_volume,
                enforce_trading_hours=enforce_trading_hours,
                position_sizing=position_sizing,
                fixed_volume=fixed_volume,
                risk_per_operation=risk_per_operation,
            )

        # Data storage
        self.preprocessor = DataPreprocessor(data_folder=hist_data_path or 'hist_data')
        self.full_data: Dict[str, Dict[str, pl.DataFrame]] = {}  # symbol -> tf -> df
        self.timestamp_cache: Dict[str, Dict[str, Dict]] = {}  # symbol -> tf -> date -> idx

        # Track for reporting
        self.all_trades: List[Dict] = []

    def run(self) -> Dict:
        """
        Execute the portfolio backtest.

        Returns:
            Dict with trades, metrics, portfolio state, etc.
        """
        import time
        start_time = time.time()

        print(f"=== Starting Portfolio Backtest ===")
        print(f"Strategies: {self.strategies}")
        print(f"Period: {self.start} to {self.end}")
        print(f"Initial Equity: ${self.initial_equity:,.2f}")

        # Step 1: Load data for all symbols
        self._load_all_data()

        # Step 2: Compute warmup requirements for each strategy
        warmup_info = {}
        for strat_id, runner in self.strategy_runners.items():
            warmup_info[strat_id] = runner.compute_warmup_requirements()
            if self.verbose:
                print(f"  Strategy {strat_id}: window={warmup_info[strat_id]['window_size']}, "
                      f"warmup={warmup_info[strat_id]['warmup_bars']}")

        # Step 3: Build unified timeline
        unified_timeline, primary_tf = self._build_unified_timeline()
        total_bars = len(unified_timeline)

        # Start loop at the MINIMUM warmup so the fastest strategy can begin
        # trading immediately.  Each strategy has its own warmup gate inside
        # _process_bar() (strat_bar_idx < warmup_info[strat_id]['warmup_bars']),
        # so slower strategies are individually held back until ready.
        min_warmup = min(info['warmup_bars'] for info in warmup_info.values())
        start_bar_idx = min_warmup

        print(f"\nUnified Timeline: {total_bars} bars ({primary_tf})")
        print(f"Per-strategy warmups: {', '.join(f'{sid}={info['warmup_bars']}' for sid, info in warmup_info.items())}")
        print(f"Loop starts at bar {start_bar_idx} (min warmup)")
        print(f"Starting main loop...\n")

        # Step 4: Main backtest loop
        try:
            for bar_idx in range(start_bar_idx, total_bars):
                self._process_bar(bar_idx, unified_timeline, warmup_info)

            # Step 5: Close remaining positions
            self._close_all_positions(total_bars - 1, unified_timeline)
        except Exception:
            _logger.error("Error in portfolio loop at bar %s", bar_idx, exc_info=True)
            raise

        # Step 6: Aggregate results
        self._aggregate_trades()

        # Step 7: Calculate portfolio metrics
        portfolio_metrics = self._calculate_portfolio_metrics()

        elapsed_time = time.time() - start_time

        print(f"\n=== Portfolio Backtest Complete ===")
        print(f"Time Elapsed: {elapsed_time:.2f} seconds")
        print(f"Total Trades: {len(self.all_trades)}")
        print(f"Final Equity: ${self.portfolio_state.current_equity:,.2f}")
        print(f"Total Return: ${self.portfolio_state.current_equity - self.initial_equity:+,.2f} "
              f"({((self.portfolio_state.current_equity / self.initial_equity) - 1) * 100:+.2f}%)")

        # Print strategy contribution breakdown (PORT-03)
        print("\n=== Strategy Contributions ===")
        contributions = self._calculate_strategy_contributions()
        for strat_id, strat_metrics in contributions.items():
            if strat_metrics['trade_count'] > 0:
                print(f"Strategy {strat_id}: "
                      f"PnL ${strat_metrics['total_pnl']:+,.2f} "
                      f"({strat_metrics['contribution_pct']:+.1f}% of total) | "
                      f"Win Rate: {strat_metrics['win_rate']:.1f}%")

        # Print portfolio metrics
        print(f"\n=== Portfolio Metrics ===")
        print(f"Sharpe Ratio: {portfolio_metrics['sharpe_ratio']:.2f}")
        print(f"Max Drawdown: ${portfolio_metrics['max_drawdown']:,.2f} ({portfolio_metrics['max_drawdown_pct']:.1f}%)")
        print(f"Win Rate: {portfolio_metrics['win_rate']:.1f}% ({portfolio_metrics['winning_trades']}W / {portfolio_metrics['losing_trades']}L)")
        if portfolio_metrics['correlation_matrix']:
            print(f"\nStrategy Correlations:")
            for strat_key, correlations in portfolio_metrics['correlation_matrix'].items():
                corr_str = ", ".join(f"{k}: {v:.2f}" for k, v in correlations.items() if k != strat_key)
                if corr_str:
                    print(f"  {strat_key}: {corr_str}")

        return {
            'trades': self.all_trades,
            'initial_equity': self.initial_equity,
            'final_equity': self.portfolio_state.current_equity,
            'equity_curve': self.portfolio_state.equity_curve,
            'strategies': self.strategies,
            'strategy_trades': {
                strat_id: runner.trades
                for strat_id, runner in self.strategy_runners.items()
            },
            'strategy_contributions': contributions,
            'portfolio_metrics': portfolio_metrics
        }

    def _load_all_data(self) -> None:
        """Load data for all symbols required by strategies."""
        # Collect all symbols and their required timeframes
        symbols_tf: Dict[str, set] = {}

        for strat_id, runner in self.strategy_runners.items():
            symbol = runner.symbol
            if symbol not in symbols_tf:
                symbols_tf[symbol] = set()

            # Add all timeframes from ind_list
            for tf in runner.ind_list.keys():
                symbols_tf[symbol].add(tf)

        # Load data for each symbol
        for symbol, timeframes in symbols_tf.items():
            if self.verbose:
                print(f"Loading data for {symbol}: {list(timeframes)}")

            self.full_data[symbol] = self.preprocessor.load_and_resample(
                symbol=symbol,
                timeframes=list(timeframes),
                start_date=self.start,
                end_date=self.end
            )

            # Build timestamp cache for this symbol
            self.timestamp_cache[symbol] = {}
            for tf, df in self.full_data[symbol].items():
                self.timestamp_cache[symbol][tf] = {
                    date: idx for idx, date in enumerate(df['date'].to_list())
                }

    def _build_unified_timeline(self) -> Tuple[List[datetime], str]:
        """
        Build unified timeline using the minimum primary timeframe.

        Returns:
            Tuple of (list of timestamps, primary timeframe string)
        """
        # Find minimum timeframe across all strategies
        min_tf_minutes = float('inf')
        min_tf = None

        for runner in self.strategy_runners.values():
            tf_minutes = timeframe_to_minutes(runner.primary_tf)
            if tf_minutes < min_tf_minutes:
                min_tf_minutes = tf_minutes
                min_tf = runner.primary_tf

        # Merge all symbols' timestamps into a single sorted, deduplicated timeline
        all_timestamps = set()
        for symbol_data in self.full_data.values():
            if min_tf in symbol_data:
                all_timestamps.update(symbol_data[min_tf]['date'].to_list())
        unified_timeline = sorted(all_timestamps)

        return unified_timeline, min_tf

    def _process_bar(
        self,
        bar_idx: int,
        unified_timeline: List[datetime],
        warmup_info: Dict[int, Dict]
    ) -> None:
        """
        Process all strategies for a single bar.

        CRITICAL: Exit-before-entry order!
        1. Process ALL exits first (frees margin, updates equity)
        2. Then process ALL entries (uses updated equity for sizing)
        3. Record portfolio snapshot
        """
        timestamp = unified_timeline[bar_idx]

        if self.verbose and bar_idx % 1000 == 0:
            print(f"Processing bar {bar_idx}/{len(unified_timeline)}: {timestamp}")

        # PHASE 1: ALL EXITS FIRST
        for strat_id, runner in self.strategy_runners.items():
            if not runner.has_position():
                continue

            symbol = runner.symbol
            primary_tf = runner.primary_tf

            # Get data for this strategy
            if symbol not in self.full_data or primary_tf not in self.full_data[symbol]:
                continue

            primary_df = self.full_data[symbol][primary_tf]

            # Find bar index in this strategy's data
            strat_bar_idx = self._find_bar_index(symbol, primary_tf, timestamp)
            if strat_bar_idx is None or strat_bar_idx < warmup_info[strat_id]['warmup_bars']:
                continue

            current_bar = primary_df[strat_bar_idx]

            # Build window data for this strategy
            window_data = self._get_window_slice(
                symbol, strat_bar_idx,
                warmup_info[strat_id]['window_size'],
                runner.ind_list,
                runner._effective_max_shift,
                primary_tf=runner.primary_tf
            )

            # Check exit
            exit_result = runner.check_exit(strat_bar_idx, current_bar, window_data, primary_df)

            if exit_result:
                self._handle_exit(runner, exit_result, primary_df)

        # PHASE 2: ALL ENTRIES AFTER ALL EXITS COMPLETE
        for strat_id, runner in self.strategy_runners.items():
            if runner.has_position():
                continue

            symbol = runner.symbol
            primary_tf = runner.primary_tf

            # Get data
            if symbol not in self.full_data or primary_tf not in self.full_data[symbol]:
                continue

            primary_df = self.full_data[symbol][primary_tf]

            # Find bar index
            strat_bar_idx = self._find_bar_index(symbol, primary_tf, timestamp)
            if strat_bar_idx is None or strat_bar_idx < warmup_info[strat_id]['warmup_bars']:
                continue

            current_bar = primary_df[strat_bar_idx]

            # Build window data
            window_data = self._get_window_slice(
                symbol, strat_bar_idx,
                warmup_info[strat_id]['window_size'],
                runner.ind_list,
                runner._effective_max_shift,
                primary_tf=runner.primary_tf
            )

            if window_data is None:
                continue

            # Check entry
            entry_result = runner.check_entry(strat_bar_idx, current_bar, window_data)

            if entry_result:
                self._handle_entry(runner, entry_result, primary_df)

        # PHASE 3: RECORD PORTFOLIO SNAPSHOT
        # Build current prices dict for mark-to-market unrealized PnL
        current_prices: Dict[str, float] = {}
        for strat_id, runner in self.strategy_runners.items():
            symbol = runner.symbol
            if symbol in current_prices:
                continue
            primary_tf = runner.primary_tf
            if symbol not in self.full_data or primary_tf not in self.full_data[symbol]:
                continue
            strat_bar_idx = self._find_bar_index(symbol, primary_tf, timestamp)
            if strat_bar_idx is not None:
                current_bar = self.full_data[symbol][primary_tf][strat_bar_idx]
                current_prices[symbol] = float(extract_scalar(current_bar['close']))

        self.portfolio_state.snapshot(timestamp, current_prices)

    def _find_bar_index(self, symbol: str, timeframe: str, timestamp: datetime) -> Optional[int]:
        """Find bar index for given timestamp in symbol's data."""
        cache = self.timestamp_cache.get(symbol, {}).get(timeframe, {})

        if timestamp in cache:
            return cache[timestamp]

        # If exact match not found, find nearest bar <= timestamp
        df = self.full_data[symbol][timeframe]
        dates = df['date'].to_list()

        for i in range(len(dates) - 1, -1, -1):
            if dates[i] <= timestamp:
                return i

        return None

    def _get_window_slice(
        self,
        symbol: str,
        bar_idx: int,
        window_size: int,
        ind_list: Dict,
        max_shift: int,
        primary_tf: Optional[str] = None
    ) -> Optional[Dict[str, pl.DataFrame]]:
        """Extract rolling window slice for a strategy."""
        # Use explicit primary_tf; fall back to first ind_list key only as last resort
        if primary_tf is None:
            primary_tf = list(ind_list.keys())[0]

        if symbol not in self.full_data:
            return None

        primary_df = self.full_data[symbol][primary_tf]
        if bar_idx >= len(primary_df):
            return None

        current_timestamp = extract_scalar(primary_df[bar_idx]['date'])

        raw_window_data: Dict[str, pl.DataFrame] = {}
        for tf in ind_list.keys():
            if tf not in self.full_data[symbol]:
                continue
            df = self.full_data[symbol][tf]
            tf_data = df.filter(pl.col('date') <= current_timestamp)
            raw_window_data[tf] = tf_data.tail(window_size)

        # Calculate indicators
        window_data_with_indicators = INDICATORS(
            ib=None,
            contract=None,
            ind_info=ind_list,
            marketData=raw_window_data,
            max_shift=max_shift,
            extended_data=0,
            custom_indicators_dir=self._custom_indicators_dir,
        ).run()

        # Validate
        tail_len = 1 + max_shift
        for tf, df in window_data_with_indicators.items():
            if df.is_empty() or len(df) < tail_len:
                return None

            last_rows = df.tail(tail_len)
            for col in last_rows.columns:
                s = last_rows[col]
                if s.null_count() > 0:
                    return None
                if s.dtype in (pl.Float32, pl.Float64) and s.is_nan().any():
                    return None

        return window_data_with_indicators

    def _handle_entry(self, runner: StrategyRunner, entry_result: EntryResult, primary_df: pl.DataFrame) -> None:
        """
        Handle entry: check initial margin, reserve maintenance margin, open position.
        
        Implements IBKR's dual-margin model:
        - Initial margin: Higher amount checked to ENTER a position
        - Maintenance margin: Lower amount actually RESERVED for holding
        """
        # Calculate both initial and maintenance margin requirements
        margin_req = self.margin_calculator.calculate_margin(
            symbol=runner.symbol,
            position_size=entry_result.position_size,
            entry_price=entry_result.entry_price,
            multiplier=runner.multiplier
        )

        # Try to reserve margin (checks initial, reserves maintenance)
        if not self.portfolio_state.reserve_margin(
            entry_result.strategy_id,
            entry_result.symbol,
            initial_margin=margin_req.initial,
            maintenance_margin=margin_req.maintenance
        ):
            if self.verbose:
                print(f"  [{entry_result.strategy_id}] Entry rejected: Insufficient margin "
                      f"(initial required: ${margin_req.initial:,.2f}, available: ${self.portfolio_state.margin_available:,.2f})")
            return

        # Open position
        runner.open_position(entry_result, primary_df)

        # Add to portfolio state tracking with both margin values
        position_info = PositionInfo(
            strategy_id=entry_result.strategy_id,
            symbol=entry_result.symbol,
            side=entry_result.side,
            entry_price=entry_result.entry_price,
            position_size=entry_result.position_size,
            initial_margin=margin_req.initial,
            maintenance_margin=margin_req.maintenance,
            entry_timestamp=entry_result.timestamp,
            sl_level=entry_result.sl_level,
            multiplier=runner.multiplier
        )

        # Store portfolio state at entry (for trade record enrichment - PORT-04)
        position_info.entry_equity = self.portfolio_state.current_equity
        position_info.entry_margin_used = self.portfolio_state.margin_used
        position_info.entry_open_positions = len(self.portfolio_state.open_positions)

        self.portfolio_state.add_position(position_info)

    def _handle_exit(self, runner: StrategyRunner, exit_result: ExitResult, primary_df: pl.DataFrame) -> None:
        """Handle exit: close position, release margin, update equity."""
        # Get position info for margin release and entry state
        position_info = self.portfolio_state.get_position(
            exit_result.strategy_id,
            exit_result.symbol
        )

        # Get entry state from position_info (stored at entry time - PORT-04)
        entry_equity = getattr(position_info, 'entry_equity', self.initial_equity) if position_info else self.initial_equity
        entry_margin_used = getattr(position_info, 'entry_margin_used', 0.0) if position_info else 0.0
        entry_open_positions = getattr(position_info, 'entry_open_positions', 0) if position_info else 0

        # Current portfolio state (at exit)
        exit_equity = self.portfolio_state.current_equity
        exit_margin_used = self.portfolio_state.margin_used
        exit_open_positions = len(self.portfolio_state.open_positions)

        # Close position and record trade with portfolio state enrichment
        trade = runner.close_position(
            exit_result, primary_df,
            entry_equity=entry_equity,
            entry_margin_used=entry_margin_used,
            entry_open_positions=entry_open_positions,
            exit_equity=exit_equity,
            exit_margin_used=exit_margin_used,
            exit_open_positions=exit_open_positions
        )

        # Update portfolio equity with PnL
        self.portfolio_state.record_trade_pnl(trade['pnl'])

        # Release margin
        if position_info:
            self.portfolio_state.release_margin(
                exit_result.strategy_id,
                exit_result.symbol,
                position_info.margin_required
            )

        # Remove from portfolio tracking
        self.portfolio_state.remove_position(
            exit_result.strategy_id,
            exit_result.symbol
        )

    def _close_all_positions(self, bar_idx: int, unified_timeline: List[datetime]) -> None:
        """Force close all remaining positions at end of backtest."""
        timestamp = unified_timeline[bar_idx]

        for strat_id, runner in self.strategy_runners.items():
            if not runner.has_position():
                continue

            symbol = runner.symbol
            primary_tf = runner.primary_tf

            if symbol not in self.full_data or primary_tf not in self.full_data[symbol]:
                continue

            primary_df = self.full_data[symbol][primary_tf]
            strat_bar_idx = self._find_bar_index(symbol, primary_tf, timestamp)

            if strat_bar_idx is None:
                continue

            current_bar = primary_df[strat_bar_idx]

            # Get position info for margin release and entry state (PORT-04)
            position_info = self.portfolio_state.get_position(strat_id, symbol)

            # Get entry state from position_info
            entry_equity = getattr(position_info, 'entry_equity', self.initial_equity) if position_info else self.initial_equity
            entry_margin_used = getattr(position_info, 'entry_margin_used', 0.0) if position_info else 0.0
            entry_open_positions = getattr(position_info, 'entry_open_positions', 0) if position_info else 0

            # Current portfolio state (at exit)
            exit_equity = self.portfolio_state.current_equity
            exit_margin_used = self.portfolio_state.margin_used
            exit_open_positions = len(self.portfolio_state.open_positions)

            # Create exit result for force close
            bar_close = float(extract_scalar(current_bar['close']))
            exit_result = ExitResult(
                strategy_id=strat_id,
                symbol=symbol,
                exit_price=bar_close,
                exit_reason=ExitReason.BACKTEST_END,
                bar_idx=strat_bar_idx,
                timestamp=extract_scalar(current_bar['date']),
                pnl=0  # Will be calculated in close_position
            )

            # Close position with portfolio state enrichment
            trade = runner.close_position(
                exit_result, primary_df,
                entry_equity=entry_equity,
                entry_margin_used=entry_margin_used,
                entry_open_positions=entry_open_positions,
                exit_equity=exit_equity,
                exit_margin_used=exit_margin_used,
                exit_open_positions=exit_open_positions
            )

            if trade:
                # Update portfolio equity with PnL
                self.portfolio_state.record_trade_pnl(trade['pnl'])

                # Release margin
                if position_info:
                    self.portfolio_state.release_margin(strat_id, symbol, position_info.margin_required)

                self.portfolio_state.remove_position(strat_id, symbol)

    def _aggregate_trades(self) -> None:
        """Aggregate all trades from all strategies."""
        self.all_trades = []
        for strat_id, runner in self.strategy_runners.items():
            for trade in runner.trades:
                trade['strategy_id'] = strat_id
                self.all_trades.append(trade)

        # Sort by exit date
        self.all_trades.sort(key=lambda t: t.get('exit_date', datetime.min))

    def _calculate_strategy_contributions(self) -> Dict[int, Dict]:
        """
        Calculate how each strategy contributed to portfolio performance.

        Returns:
            Dict mapping strategy_id to contribution metrics:
            - total_pnl: Total PnL from this strategy
            - trade_count: Number of trades
            - wins: Number of winning trades
            - losses: Number of losing trades
            - win_rate: Win percentage
            - contribution_pct: Percentage of total portfolio PnL
            - return_on_initial: Return as percentage of initial equity
        """
        by_strategy: Dict[int, Dict] = {}
        total_pnl = sum(t['pnl'] for t in self.all_trades) if self.all_trades else 0

        for strat_id, runner in self.strategy_runners.items():
            trades = runner.trades
            strat_pnl = sum(t['pnl'] for t in trades)
            wins = sum(1 for t in trades if t['pnl'] > 0)
            losses = sum(1 for t in trades if t['pnl'] <= 0)
            trade_count = len(trades)

            by_strategy[strat_id] = {
                'total_pnl': strat_pnl,
                'trade_count': trade_count,
                'wins': wins,
                'losses': losses,
                'win_rate': (wins / trade_count * 100) if trade_count > 0 else 0.0,
                'contribution_pct': (strat_pnl / total_pnl * 100) if total_pnl != 0 else 0.0,
                'return_on_initial': (strat_pnl / self.initial_equity * 100)
            }

        return by_strategy

    def _calculate_portfolio_metrics(self) -> Dict:
        """Calculate portfolio-level performance metrics."""
        calculator = PortfolioMetricsCalculator(
            equity_curve=self.portfolio_state.equity_curve,
            strategy_trades={
                strat_id: runner.trades
                for strat_id, runner in self.strategy_runners.items()
            },
            initial_equity=self.initial_equity,
            start_date=datetime.strptime(self.start, '%Y-%m-%d'),
            end_date=datetime.strptime(self.end, '%Y-%m-%d')
        )
        metrics = calculator.calculate()
        return {
            'sharpe_ratio': metrics.sharpe_ratio,
            'max_drawdown': metrics.max_drawdown,
            'max_drawdown_pct': metrics.max_drawdown_pct,
            'total_pnl': metrics.total_pnl,
            'total_return_pct': metrics.total_return_pct,
            'total_trades': metrics.total_trades,
            'win_rate': metrics.win_rate,
            'winning_trades': metrics.winning_trades,
            'losing_trades': metrics.losing_trades,
            'profit_factor': metrics.profit_factor,
            'correlation_matrix': metrics.correlation_matrix,
            'loss_correlation_matrix': metrics.loss_correlation_matrix,
            'concurrent_loss_days': metrics.concurrent_loss_days,
            'max_concurrent_losses': metrics.max_concurrent_losses
        }

    def save_results(self, output_folder: str = None, backtest_name: str = None) -> str:
        """
        Save portfolio backtest results to disk.

        Args:
            output_folder: Base output folder (defaults to 'logs_portfolio')
            backtest_name: Optional custom name for the backtest folder

        Returns:
            Path to the created backtest folder
        """
        if output_folder is None:
            from pathlib import Path
            output_folder = str(Path(__file__).parent.parent / 'logs_portfolio')

        # Build results dict if not already available (in case called after run())
        results = {
            'trades': self.all_trades,
            'initial_equity': self.initial_equity,
            'final_equity': self.portfolio_state.current_equity,
            'equity_curve': self.portfolio_state.equity_curve,
            'strategies': self.strategies,
            'strategy_trades': {
                strat_id: runner.trades
                for strat_id, runner in self.strategy_runners.items()
            },
            'strategy_contributions': self._calculate_strategy_contributions(),
            'portfolio_metrics': self._calculate_portfolio_metrics()
        }

        reporter = PortfolioReporter(
            results=results,
            stratOBJ=self.stratOBJ,
            start_date=self.start,
            end_date=self.end,
            initial_equity=self.initial_equity,
            strategies=self.strategies,
            slippage_ticks=self.slippage_ticks,
            comm_per_contract=self.comm_per_contract,
            enforce_trading_hours=self.enforce_trading_hours,
            max_volume=self.max_volume,
            full_data=self.full_data,
            verbose=self.verbose
        )

        return reporter.save_results(output_folder, backtest_name=backtest_name)
