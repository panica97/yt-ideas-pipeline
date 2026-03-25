"""
Portfolio State Management

Provides centralized dataclasses for portfolio-level state tracking during
multi-strategy backtesting. This module serves as the single source of truth
for equity, margin, and position tracking across all strategies.

Key concepts:
- Positions are tracked by (strategy_id, symbol) tuple to avoid netting conflicts
- PortfolioState owns equity and margin; strategies read but never maintain own copies
- Dual-margin model: Initial margin to OPEN, maintenance margin to HOLD
- Margin call detection when equity falls below maintenance requirement
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple


@dataclass
class PositionInfo:
    """
    Lightweight position reference for portfolio tracking.

    Contains only the information needed for portfolio-level management,
    not the full position state (which lives in PositionManager).

    Attributes:
        strategy_id: Strategy that owns this position
        symbol: Trading symbol
        side: 'long' or 'short'
        entry_price: Price at entry
        position_size: Number of contracts
        initial_margin: Initial margin required to open (for reference)
        maintenance_margin: Maintenance margin required to hold (what's reserved)
        entry_timestamp: When position was opened
        sl_level: Stop loss level for open risk calculation
        multiplier: Contract multiplier for open risk calculation
    """
    strategy_id: int
    symbol: str
    side: str  # 'long' or 'short'
    entry_price: float
    position_size: int
    initial_margin: float  # Required to open
    maintenance_margin: float  # Required to hold (what's actually reserved)
    entry_timestamp: datetime

    # Open risk tracking fields
    sl_level: float = 0.0  # Stop loss level for risk calculation
    multiplier: float = 1.0  # Contract multiplier

    # Portfolio state at entry time (for trade record enrichment - PORT-04)
    entry_equity: Optional[float] = None
    entry_margin_used: Optional[float] = None
    entry_open_positions: Optional[int] = None

    # Legacy compatibility: margin_required returns maintenance margin
    @property
    def margin_required(self) -> float:
        """Backwards compatibility: returns maintenance margin."""
        return self.maintenance_margin


@dataclass
class EquitySnapshot:
    """
    Point-in-time portfolio state for equity curve generation.

    Captured at regular intervals (e.g., end of each bar) to build
    the portfolio equity curve for analysis.
    """
    timestamp: datetime
    equity: float
    margin_used: float
    open_position_count: int
    margin_utilization_pct: float = 0.0  # margin used as % of equity
    margin_call: bool = False  # True if equity < maintenance margin
    open_risk: float = 0.0  # Total risk if all positions hit their SL
    unrealized_pnl: float = 0.0  # Mark-to-market unrealized PnL of open positions


@dataclass
class PortfolioState:
    """
    Single source of truth for portfolio-level state.

    Implements IBKR's dual-margin model:
    - Initial margin: Must be available (equity - margin_used) to enter
    - Maintenance margin: What's actually reserved for open positions
    - Margin call: Triggered when current_equity < margin_used

    Attributes:
        initial_equity: Starting portfolio equity
        current_equity: Current portfolio equity (updated after each trade)
        margin_used: Total MAINTENANCE margin reserved for open positions
        open_positions: Dict mapping (strategy_id, symbol) -> PositionInfo
        equity_curve: List of snapshots for equity curve generation
        margin_call_count: Number of times margin call condition was detected
    """
    initial_equity: float
    current_equity: float
    margin_used: float = 0.0  # This is maintenance margin total

    # Track positions by (strategy_id, symbol) to avoid netting conflicts
    # Two strategies can have positions in the same symbol
    open_positions: Dict[Tuple[int, str], PositionInfo] = field(default_factory=dict)
    equity_curve: List[EquitySnapshot] = field(default_factory=list)
    margin_call_count: int = 0

    @property
    def margin_available(self) -> float:
        """Return available margin (equity minus maintenance margin used)."""
        return self.current_equity - self.margin_used

    @property
    def margin_utilization_pct(self) -> float:
        """Current margin utilization as percentage of equity."""
        if self.current_equity <= 0:
            return 0.0
        return (self.margin_used / self.current_equity) * 100

    @property
    def is_margin_call(self) -> bool:
        """
        Check if portfolio is in margin call state.
        
        Margin call occurs when equity falls below maintenance margin requirement.
        In real trading, this would trigger forced liquidation.
        """
        return self.current_equity < self.margin_used

    def check_initial_margin(self, initial_margin_required: float) -> bool:
        """
        Check if there's enough available margin to meet initial margin requirement.
        
        This is used BEFORE entering a position to verify sufficient capital.
        
        Args:
            initial_margin_required: Initial margin needed to open the position
            
        Returns:
            True if initial margin requirement can be met, False otherwise
        """
        return initial_margin_required <= self.margin_available

    def reserve_margin(
        self, 
        strategy_id: int, 
        symbol: str, 
        initial_margin: float,
        maintenance_margin: float
    ) -> bool:
        """
        Reserve margin for a new position.

        Checks if INITIAL margin is available, then reserves MAINTENANCE margin.
        This models IBKR's behavior where you need more capital to enter
        than to hold a position.

        Args:
            strategy_id: Strategy identifier
            symbol: Trading symbol
            initial_margin: Initial margin required to open (checked)
            maintenance_margin: Maintenance margin to reserve (held)

        Returns:
            True if margin was reserved, False if insufficient margin available
        """
        # Check if initial margin requirement can be met
        if not self.check_initial_margin(initial_margin):
            return False
        
        # Reserve maintenance margin (what's actually held)
        self.margin_used += maintenance_margin
        return True

    def release_margin(self, strategy_id: int, symbol: str, amount: float) -> None:
        """
        Release margin when closing a position.

        Args:
            strategy_id: Strategy identifier
            symbol: Trading symbol
            amount: Maintenance margin amount to release
        """
        self.margin_used = max(0.0, self.margin_used - amount)

    def record_trade_pnl(self, pnl: float) -> None:
        """
        Update equity after a trade closes.

        Args:
            pnl: Net PnL from the closed trade (positive or negative)
        """
        self.current_equity += pnl

    def check_margin_call(self) -> bool:
        """
        Check and record if margin call condition exists.

        Returns:
            True if margin call detected, False otherwise
        """
        if self.is_margin_call:
            self.margin_call_count += 1
            return True
        return False

    def calculate_open_risk(self) -> float:
        """
        Calculate total risk if all open positions hit their stop losses.

        Formula:
        - Long:  risk = (entry_price - sl_level) * position_size * multiplier
        - Short: risk = (sl_level - entry_price) * position_size * multiplier

        When no SL is set (sl_level <= 0), estimates risk as full notional value
        (entry_price * position_size * multiplier) as a conservative worst case.

        Returns:
            Total dollar risk across all open positions
        """
        total_risk = 0.0
        for pos in self.open_positions.values():
            if pos.sl_level <= 0:
                # No SL set -- estimate risk as full notional value (conservative)
                risk = pos.entry_price * pos.position_size * pos.multiplier
            elif pos.side == 'long':
                risk = (pos.entry_price - pos.sl_level) * pos.position_size * pos.multiplier
            else:  # short
                risk = (pos.sl_level - pos.entry_price) * pos.position_size * pos.multiplier

            # Only count positive risk (where SL would result in a loss)
            total_risk += max(0, risk)

        return total_risk

    def compute_unrealized_pnl(self, current_prices: Optional[Dict[str, float]] = None) -> float:
        """
        Calculate total unrealized PnL across all open positions.

        Args:
            current_prices: Dict mapping symbol -> current close price.
                           If None, returns 0.0.

        Returns:
            Total unrealized PnL in dollars
        """
        if not current_prices or not self.open_positions:
            return 0.0

        total_unrealized = 0.0
        for (strategy_id, symbol), pos in self.open_positions.items():
            if symbol not in current_prices:
                continue
            current_price = current_prices[symbol]
            if pos.side == 'long':
                unrealized = (current_price - pos.entry_price) * pos.position_size * pos.multiplier
            else:
                unrealized = (pos.entry_price - current_price) * pos.position_size * pos.multiplier
            total_unrealized += unrealized

        return total_unrealized

    def snapshot(self, timestamp: datetime, current_prices: Optional[Dict[str, float]] = None) -> None:
        """
        Record equity snapshot for curve generation.

        Snapshots only record state -- they do NOT increment event counters.
        Margin call counting is handled exclusively by check_margin_call().

        Args:
            timestamp: The timestamp for this snapshot
            current_prices: Dict mapping symbol -> current close price for mark-to-market
        """
        is_margin_call = self.is_margin_call

        unrealized = self.compute_unrealized_pnl(current_prices)

        self.equity_curve.append(EquitySnapshot(
            timestamp=timestamp,
            equity=self.current_equity + unrealized,
            margin_used=self.margin_used,
            open_position_count=len(self.open_positions),
            margin_utilization_pct=self.margin_utilization_pct,
            margin_call=is_margin_call,
            open_risk=self.calculate_open_risk(),
            unrealized_pnl=unrealized
        ))

    def add_position(self, position: PositionInfo) -> None:
        """
        Add position to open_positions tracking.

        Args:
            position: The PositionInfo to add
        """
        key = (position.strategy_id, position.symbol)
        self.open_positions[key] = position

    def remove_position(self, strategy_id: int, symbol: str) -> Optional[PositionInfo]:
        """
        Remove position from tracking.

        Args:
            strategy_id: Strategy identifier
            symbol: Trading symbol

        Returns:
            The removed PositionInfo, or None if no position existed
        """
        key = (strategy_id, symbol)
        return self.open_positions.pop(key, None)

    def has_position(self, strategy_id: int, symbol: str) -> bool:
        """
        Check if a position exists for this strategy/symbol combination.

        Args:
            strategy_id: Strategy identifier
            symbol: Trading symbol

        Returns:
            True if position exists, False otherwise
        """
        return (strategy_id, symbol) in self.open_positions

    def get_position(self, strategy_id: int, symbol: str) -> Optional[PositionInfo]:
        """
        Get position for strategy/symbol if exists.

        Args:
            strategy_id: Strategy identifier
            symbol: Trading symbol

        Returns:
            The PositionInfo if found, None otherwise
        """
        return self.open_positions.get((strategy_id, symbol))

