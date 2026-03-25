"""
Position Management

Provides dataclasses and utilities for tracking position state and trade records
during backtesting.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Position:
    """
    Represents an open trading position.

    Tracks all state needed for position management including entry details,
    SL/TP levels, and BE/TSL state.
    """
    side: str  # 'long' or 'short'
    entry_bar_idx: int
    entry_price: float
    sl_level: Optional[float]
    tp_level: Optional[float]
    initial_sl_level: Optional[float]
    be_price: float
    position_size: int = 1
    bars_in_position: int = 0

    # BE/TSL state
    be_status: bool = False  # Whether breakeven has been triggered
    sl_mgmt_config: Optional[Dict] = None  # stop_loss_mgmt config from strategy
    precomputed_exit: Optional[tuple] = None  # Pre-computed exit info when BE/TSL enabled


@dataclass
class Trade:
    """
    Represents a completed trade record.

    Contains all information about a closed trade including entry/exit details,
    PnL calculations, and metadata.
    """
    strategy: int
    signal_bar: int
    signal_date: Any
    entry_bar: int
    exit_bar: int
    entry_date: Any
    exit_date: Any
    exit_minute_timestamp: Optional[Any]  # Exact minute timestamp for BE/TSL exits
    side: str
    entry_price: float
    exit_price: float
    initial_sl_level: Optional[float]  # Original SL before BE/TSL
    sl_level: Optional[float]  # Final SL (may have been modified by BE/TSL)
    tp_level: Optional[float]
    be_triggered: bool  # Whether breakeven was triggered
    be_price: float  # The breakeven price if triggered
    position_size: int
    multiplier: float
    gross_pnl: float
    slippage_cost: float
    commission: float
    pnl: float  # Net PnL after slippage and commission
    bars_held: int
    exit_reason: str
    cumulative_pnl: float


class PositionManager:
    """
    Manages position lifecycle: opening, tracking, and closing positions.

    Handles the mechanics of position state management independent of
    the strategy evaluation logic.
    """

    def __init__(self):
        self.position: Optional[Position] = None
        self.trades: List[Dict] = []
        self.total_pnl: float = 0.0

    @property
    def is_open(self) -> bool:
        """Check if a position is currently open."""
        return self.position is not None

    def open_position(
        self,
        side: str,
        entry_bar_idx: int,
        entry_price: float,
        sl_level: Optional[float],
        tp_level: Optional[float],
        sl_mgmt_config: Optional[Dict] = None,
        position_size: int = 1
    ) -> Position:
        """
        Open a new position.

        Args:
            side: 'long' or 'short'
            entry_bar_idx: Bar index at entry
            entry_price: Entry price
            sl_level: Stop loss level
            tp_level: Take profit level
            sl_mgmt_config: Stop loss management configuration (BE/TSL)
            position_size: Position size (default 1)

        Returns:
            The opened Position
        """
        self.position = Position(
            side=side,
            entry_bar_idx=entry_bar_idx,
            entry_price=entry_price,
            sl_level=sl_level,
            tp_level=tp_level,
            initial_sl_level=sl_level,
            be_price=entry_price,  # BE price is the entry price
            position_size=position_size,
            bars_in_position=0,
            be_status=False,
            sl_mgmt_config=sl_mgmt_config,
            precomputed_exit=None
        )
        return self.position

    def close_position(
        self,
        bar_idx: int,
        exit_price: float,
        exit_reason: str,
        strategy: int,
        signal_bar_date: Any,
        entry_date: Any,
        exit_date: Any,
        multiplier: float,
        commission_per_contract: float = 0.0,
        slippage_ticks: float = 0.0,
        min_tick: float = 0.25,
        exit_minute_timestamp: Optional[Any] = None
    ) -> Dict:
        """
        Close the current position and record the trade.

        Args:
            bar_idx: Exit bar index
            exit_price: Exit price
            exit_reason: Reason for exit ('SL', 'TP', 'num_bars', etc.)
            strategy: Strategy ID
            signal_bar_date: Date of the signal bar
            entry_date: Entry date
            exit_date: Exit date
            multiplier: Contract multiplier
            commission_per_contract: Commission per contract per side
            slippage_ticks: Slippage in ticks per side
            min_tick: Minimum tick size
            exit_minute_timestamp: Exact minute timestamp for BE/TSL exits

        Returns:
            Trade record dictionary
        """
        if self.position is None:
            raise ValueError("No position to close")

        pos = self.position

        # Calculate slippage-adjusted fill prices
        # Slippage always worsens the fill: entry is worse, exit is worse
        slippage_per_side = slippage_ticks * min_tick
        if pos.side == 'long':
            entry_fill_price = pos.entry_price + slippage_per_side  # buy higher
            exit_fill_price = exit_price - slippage_per_side        # sell lower
        else:  # short
            entry_fill_price = pos.entry_price - slippage_per_side  # sell lower
            exit_fill_price = exit_price + slippage_per_side        # buy higher

        # Calculate commission (per contract, both sides)
        total_commission = commission_per_contract * pos.position_size * 2

        # Gross PnL from fill prices (slippage is embedded in the fills)
        if pos.side == 'long':
            gross_pnl = (exit_fill_price - entry_fill_price) * pos.position_size * multiplier
        else:  # short
            gross_pnl = (entry_fill_price - exit_fill_price) * pos.position_size * multiplier

        # Slippage cost in dollars (kept for backward compatibility / reporting)
        slippage_cost = slippage_per_side * 2 * pos.position_size * multiplier

        # Net PnL = Gross PnL - Commission (slippage already in fill prices)
        pnl = gross_pnl - total_commission

        # Update cumulative PnL
        self.total_pnl += pnl

        # Record trade
        # Signal bar is the bar before entry (where conditions were evaluated).
        # max(0, ...) handles the edge case of entry at bar 0 where there is no
        # prior bar -- in that scenario signal_bar and entry_bar coincide at 0.
        trade = {
            'strategy': strategy,
            'signal_bar': max(0, pos.entry_bar_idx - 1),
            'signal_date': signal_bar_date,
            'entry_bar': pos.entry_bar_idx,
            'exit_bar': bar_idx,
            'entry_date': entry_date,
            'exit_date': exit_date,
            'exit_minute_timestamp': exit_minute_timestamp,
            'side': pos.side,
            'entry_price': pos.entry_price,
            'exit_price': exit_price,
            'entry_fill_price': entry_fill_price,
            'exit_fill_price': exit_fill_price,
            'initial_sl_level': pos.initial_sl_level,
            'sl_level': pos.sl_level,
            'tp_level': pos.tp_level,
            'be_triggered': pos.be_status,
            'be_price': pos.be_price,
            'position_size': pos.position_size,
            'multiplier': multiplier,
            'gross_pnl': gross_pnl,
            'slippage_cost': slippage_cost,
            'commission': total_commission,
            'pnl': pnl,
            'bars_held': pos.bars_in_position,
            'exit_reason': exit_reason,
            'cumulative_pnl': self.total_pnl
        }

        self.trades.append(trade)

        # Reset position
        self.position = None

        return trade

    def increment_bars_held(self) -> None:
        """Increment the bars held counter for the current position."""
        if self.position is not None:
            self.position.bars_in_position += 1

    def update_sl_level(self, new_sl: float) -> None:
        """Update the SL level for the current position."""
        if self.position is not None:
            self.position.sl_level = new_sl

    def set_be_triggered(self, be_price: float) -> None:
        """Mark breakeven as triggered and set the BE price."""
        if self.position is not None:
            self.position.be_status = True
            self.position.sl_level = be_price

    def set_precomputed_exit(self, exit_info: tuple) -> None:
        """Set precomputed exit information for BE/TSL simulation."""
        if self.position is not None:
            self.position.precomputed_exit = exit_info
