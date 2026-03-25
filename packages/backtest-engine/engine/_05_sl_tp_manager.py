"""
Stop Loss and Take Profit Management

Provides utilities for calculating and updating SL/TP levels including
breakeven (BE) and trailing stop loss (TSL) functionality.
"""

from dataclasses import dataclass
from typing import Optional, Dict

import numpy as np

from _00_constants import ExitReason
from _03_price_utils import round_price


@dataclass
class SLTPConfig:
    """
    Configuration for SL/TP management including BE and TSL settings.

    trailing_step quantization: The profit ratio is snapped to the nearest
    multiple of trailing_step (default 0.05 = 5%) before evaluating the
    trailing formula.  This prevents the TSL from updating on every tiny
    price tick, producing a stair-step SL progression that mirrors the
    discrete update cadence of a live bar-by-bar system.
    """
    # Breakeven settings
    be_enabled: bool = False
    be_profit_ratio: float = 0.20  # Trigger BE when profit ratio reaches this

    # Trailing stop loss settings
    tsl_enabled: bool = False
    tsl_trailing_ratio: float = 0.80  # Exponential decay parameter

    @classmethod
    def from_strategy_config(cls, sl_mgmt_config: Optional[Dict]) -> 'SLTPConfig':
        """
        Create SLTPConfig from strategy's stop_loss_mgmt configuration.

        Args:
            sl_mgmt_config: Dictionary from stratOBJ.stop_loss_mgmt()

        Returns:
            SLTPConfig instance
        """
        if not sl_mgmt_config:
            return cls()

        be_config = sl_mgmt_config.get('breakeven', {})
        trailing_config = sl_mgmt_config.get('trailing', {})

        return cls(
            be_enabled=be_config.get('action', False),
            be_profit_ratio=be_config.get('profitRatio', 0.20),
            tsl_enabled=trailing_config.get('action', False),
            tsl_trailing_ratio=trailing_config.get('trailingRatio', 0.80)
        )

    @property
    def is_enabled(self) -> bool:
        """Check if BE or TSL is enabled."""
        return self.be_enabled or self.tsl_enabled


class SLTPManager:
    """
    Manages stop loss and take profit calculations including BE and TSL.
    """

    def __init__(
        self,
        entry_price: float,
        tp_level: Optional[float],
        sl_level: Optional[float],
        side: str,
        min_tick: Optional[float],
        config: SLTPConfig,
        trailing_step: float = 0.05
    ):
        """
        Args:
            entry_price: Position entry price
            tp_level: Take profit level
            sl_level: Initial stop loss level
            side: 'long' or 'short'
            min_tick: Minimum tick size for rounding
            config: SLTPConfig with BE/TSL settings
            trailing_step: Step size for profit ratio quantization (default 0.05 = 5%)
        """
        self.entry_price = entry_price
        self.tp_level = tp_level
        self.sl_level = sl_level
        self.initial_sl_level = sl_level
        self.be_price = entry_price
        self.side = side
        self.min_tick = min_tick
        self.config = config
        self.trailing_step = trailing_step

        # State tracking
        self.be_triggered = False
        self.tsl_activated = False

    def calculate_profit_ratio(self, current_price: float) -> float:
        """
        Calculate current profit ratio relative to TP distance.

        For LONG:  (current - entry) / (tp - entry)
        For SHORT: (entry - current) / (entry - tp)

        Args:
            current_price: Current market price

        Returns:
            Profit ratio (can be negative if in loss).
            Returns 0.0 when TP distance is zero or tp_level is None (no TP configured).
        """
        if self.tp_level is None:
            return 0.0
        if self.side == 'long':
            denominator = self.tp_level - self.entry_price
            if denominator == 0:
                return 0.0
            return (current_price - self.entry_price) / denominator
        else:  # short
            denominator = self.entry_price - self.tp_level
            if denominator == 0:
                return 0.0
            return (self.entry_price - current_price) / denominator

    def calculate_trailing_sl(self, current_price: float) -> float:
        """
        Calculate new trailing stop loss price using exponential formula.

        Formula: x = (1 - exp(-R * (r - be_ratio))) / (1 - exp(-R * (1 - be_ratio)))
        New SL = entry + (current - entry) * x

        Args:
            current_price: Current market price

        Returns:
            New trailing stop loss price
        """
        profit_ratio = self.calculate_profit_ratio(current_price)
        if profit_ratio == 0.0 and (self.tp_level is None or self.tp_level == self.entry_price):
            return self.sl_level

        # Quantize profit ratio to trailing step
        ratio_adj = np.floor(profit_ratio / self.trailing_step) * self.trailing_step

        # Calculate trailing multiplier using exponential formula
        # x = (1 - exp(-R * (r - be_ratio))) / (1 - exp(-R * (1 - be_ratio)))
        be_ratio = self.config.be_profit_ratio
        trailing_ratio = self.config.tsl_trailing_ratio

        # Handle edge case: trailing_ratio near zero causes 0/0 (NaN)
        # Fall back to linear interpolation when ratio is very small
        if trailing_ratio < 1e-6:
            # Linear fallback: x = (ratio_adj - be_ratio) / (1 - be_ratio)
            if (1 - be_ratio) <= 0:
                return self.sl_level
            x = (ratio_adj - be_ratio) / (1 - be_ratio)
        else:
            numerator = 1 - np.exp(-trailing_ratio * (ratio_adj - be_ratio))
            denominator = 1 - np.exp(-trailing_ratio * (1 - be_ratio))

            if abs(denominator) < 1e-10:  # Avoid division by very small numbers
                return self.sl_level

            x = numerator / denominator

        x = max(0.0, min(1.0, x))  # Clamp to [0, 1]

        # Calculate new SL: entry + (current - entry) * x
        new_sl = self.entry_price + (current_price - self.entry_price) * x

        # Round to minTick precision
        new_sl = round_price(new_sl, self.side, self.min_tick)

        return new_sl

    def update_sl_management(self, current_price: float, verbose: bool = False) -> bool:
        """
        Check and update breakeven/trailing stop loss.

        Args:
            current_price: Current market price
            verbose: If True, print debug messages

        Returns:
            True if SL was modified, False otherwise
        """
        sl_modified = False

        profit_ratio = self.calculate_profit_ratio(current_price)
        if profit_ratio == 0.0 and (self.tp_level is None or self.tp_level == self.entry_price):
            return False

        # 1. Check breakeven trigger
        if self.config.be_enabled and not self.be_triggered:
            if profit_ratio >= self.config.be_profit_ratio:
                self.sl_level = self.be_price
                self.be_triggered = True
                sl_modified = True
                if verbose:
                    print(f"  [BE TRIGGERED] Profit ratio {profit_ratio:.2%} >= {self.config.be_profit_ratio:.2%}, "
                          f"SL moved to BE: ${self.be_price:.2f}")

        # 2. Check trailing stop update (only after BE triggered)
        if self.config.tsl_enabled and self.be_triggered:
            new_sl = self.calculate_trailing_sl(current_price)

            # Check if new SL is better than current
            is_better = False
            if self.side == 'long':
                is_better = new_sl > self.sl_level
            else:  # short
                is_better = new_sl < self.sl_level

            if is_better:
                old_sl = self.sl_level
                self.sl_level = new_sl
                self.tsl_activated = True
                sl_modified = True
                if verbose:
                    print(f"  [TSL UPDATE] SL moved from ${old_sl:.2f} to ${new_sl:.2f} "
                          f"(profit ratio: {profit_ratio:.2%})")

        return sl_modified

    def check_sl_hit(self, bar_low: float, bar_high: float) -> bool:
        """
        Check if SL was hit during the bar.

        Args:
            bar_low: Bar's low price
            bar_high: Bar's high price

        Returns:
            True if SL was hit.  Returns False when sl_level is None (no SL configured).
        """
        if self.sl_level is None:
            return False
        if self.side == 'long':
            return bar_low <= self.sl_level
        else:  # short
            return bar_high >= self.sl_level

    def check_tp_hit(self, bar_low: float, bar_high: float) -> bool:
        """
        Check if TP was hit during the bar.

        Args:
            bar_low: Bar's low price
            bar_high: Bar's high price

        Returns:
            True if TP was hit.  Returns False when tp_level is None (no TP configured).
        """
        if self.tp_level is None:
            return False
        if self.side == 'long':
            return bar_high >= self.tp_level
        else:  # short
            return bar_low <= self.tp_level

    def get_exit_reason(self, is_sl_exit: bool) -> str:
        """
        Get the appropriate exit reason based on current state.

        Args:
            is_sl_exit: True if exiting via SL, False for TP

        Returns:
            Exit reason string (ExitReason.SL, SL_BE, SL_TSL, or TP)
        """
        if is_sl_exit:
            if self.tsl_activated:
                return ExitReason.SL_TSL
            elif self.be_triggered:
                return ExitReason.SL_BE
            else:
                return ExitReason.SL
        else:
            return ExitReason.TP

    def reset_for_simulation(self) -> None:
        """Reset state for simulation (used in _simulate_position_with_sl_mgmt)."""
        self.sl_level = self.initial_sl_level
        self.be_triggered = False
        self.tsl_activated = False
