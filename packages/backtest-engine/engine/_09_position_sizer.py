"""
Backtest Position Sizer

Calculates position sizes for backtesting based on account equity and risk parameters.
Supports three sizing modes: fixed, RPO (Risk Per Operation), and Half-Kelly.

For Half-Kelly mode, this module uses the same formula as the live trading
_16_PositionSizer.py module.
"""

import logging
from math import floor
from typing import Any, Optional

_logger = logging.getLogger(__name__)


class BacktestPositionSizer:
    """
    Position sizer for backtesting that calculates contract volume based on
    account equity and risk parameters.

    Modes:
    - 'fixed': Always use fixed_volume contracts
    - 'rpo': Risk a fixed percentage of equity per trade
    - 'half_kelly': Use Half-Kelly formula with max_rpo cap (matches live trading)

    Safety Features:
    - Prevents extreme position sizes from tiny SL distances (gap handling)
    - Reference volume comparison to detect anomalies
    - Safety cap multiplier to limit size explosion
    """

    def __init__(
        self,
        mode: str = 'fixed',
        fixed_volume: int = 1,
        risk_per_operation: float = 0.02,
        max_volume: Optional[int] = None,
        safety_cap_multiplier: float = 10.0
    ):
        """
        Initialize the position sizer.

        Args:
            mode: Position sizing mode ('fixed', 'rpo', or 'half_kelly')
            fixed_volume: Number of contracts for fixed mode
            risk_per_operation: Risk percentage for RPO mode (0.02 = 2%)
            max_volume: Maximum contracts per trade (None = no limit)
            safety_cap_multiplier: Maximum multiple of reference volume allowed (default: 10x)
                                   This catches edge cases where SL distance is abnormally small.
        """
        self.mode = mode.lower().strip()
        self.fixed_volume = max(1, fixed_volume)
        self.risk_per_operation = risk_per_operation
        self.max_volume = max_volume
        self.safety_cap_multiplier = safety_cap_multiplier

        # Statistics for tracking safety cap activations
        self.safety_cap_activations = 0
        self.total_calculations = 0

        # Validate mode
        if self.mode not in ('fixed', 'rpo', 'half_kelly'):
            print(f"Warning: Unknown position sizing mode '{mode}', using 'fixed'")
            self.mode = 'fixed'

    def calculate_volume(
        self,
        equity: float,
        entry_price: float,
        sl_level: Optional[float],
        multiplier: float,
        stratOBJ: Any = None,
        strategy: int = None
    ) -> int:
        """
        Calculate position volume based on current equity and trade parameters.

        Includes safety cap to prevent extreme position sizes from tiny SL distances.

        Args:
            equity: Current account equity
            entry_price: Entry price for the trade
            sl_level: Stop loss price level
            multiplier: Contract multiplier (point value)
            stratOBJ: Strategy object (required for 'half_kelly' mode)
            strategy: Strategy ID (required for 'half_kelly' mode)

        Returns:
            Number of contracts (integer, always rounded DOWN for conservative sizing)
        """
        self.total_calculations += 1

        # Fixed mode: always return fixed_volume
        if self.mode == 'fixed':
            return self._apply_limits(self.fixed_volume)

        # Validate inputs for dynamic modes
        if equity <= 0:
            return self._apply_limits(1)

        # Calculate risk per contract
        # When no SL is configured, fall back to fixed volume
        if sl_level is None:
            _logger.info("No SL configured, returning minimum volume for position sizing")
            return self._apply_limits(self.fixed_volume if self.mode == 'fixed' else 1)
        sl_distance = abs(entry_price - sl_level)
        if sl_distance <= 0:
            _logger.warning("SL distance is 0 (entry=%.2f, sl=%.2f), returning minimum volume", entry_price, sl_level)
            return self._apply_limits(1)

        risk_per_contract = sl_distance * multiplier
        if risk_per_contract <= 0:
            return self._apply_limits(1)

        # RPO mode: risk X% of equity per trade
        if self.mode == 'rpo':
            volume = self._calculate_rpo_volume(equity, risk_per_contract)

        # Half-Kelly mode: use strategy's half_kelly and max_rpo
        elif self.mode == 'half_kelly':
            volume = self._calculate_half_kelly_volume(
                equity, risk_per_contract, stratOBJ, strategy
            )

        else:
            volume = self.fixed_volume

        # Safety cap: prevent extreme position sizes from tiny SL distances
        # Calculate "reference" volume using 1% of entry price as reference SL
        reference_sl_distance = entry_price * 0.01  # 1% of price
        reference_risk_per_contract = reference_sl_distance * multiplier
        if reference_risk_per_contract > 0:
            reference_volume = self._calculate_rpo_volume(equity, reference_risk_per_contract)
            max_safe_volume = max(1, int(reference_volume * self.safety_cap_multiplier))

            if volume > max_safe_volume and max_safe_volume > 0:
                self.safety_cap_activations += 1
                # Cap at reference * multiplier
                volume = max_safe_volume

        return self._apply_limits(volume)

    def _apply_limits(self, volume: int) -> int:
        """Apply min (1) and max volume constraints.

        Always enforces a floor of 1 contract so that callers never receive
        a zero-volume result, which would be meaningless in a backtest.
        """
        volume = max(1, volume)
        if self.max_volume is not None:
            volume = min(volume, self.max_volume)
        return volume

    def _calculate_rpo_volume(self, equity: float, risk_per_contract: float) -> int:
        """
        Calculate volume using Risk Per Operation method.

        Formula: volume = floor((equity * rpo) / risk_per_contract)
        """
        allowed_risk = equity * self.risk_per_operation
        # Use floor() for conservative (round down) sizing
        return floor(allowed_risk / risk_per_contract)

    def _calculate_half_kelly_volume(
        self,
        equity: float,
        risk_per_contract: float,
        stratOBJ: Any,
        strategy: int
    ) -> int:
        """
        Calculate volume using Half-Kelly formula with max_rpo constraint.

        This mirrors the live trading _16_PositionSizer.py logic:
            kelly_risk = equity * half_kelly
            max_risk = equity * (max_rpo / 100)
            volume = floor(min(kelly_risk, max_risk) / risk_per_contract)

        Falls back to RPO mode if strategy config is unavailable.
        """
        # Fall back to RPO if strategy config not available
        if stratOBJ is None or strategy is None:
            return self._calculate_rpo_volume(equity, risk_per_contract)

        # Get control_params for half_kelly
        try:
            control_params = stratOBJ.control_params(strategy)
        except Exception:
            control_params = None

        if control_params is None:
            return self._calculate_rpo_volume(equity, risk_per_contract)

        metrics = control_params.get('metrics', {})
        half_kelly = metrics.get('half_kelly')

        if half_kelly is None or half_kelly <= 0:
            # Fall back to RPO if no valid half_kelly
            return self._calculate_rpo_volume(equity, risk_per_contract)

        # Get order_params for max_rpo
        try:
            order_params = stratOBJ.order_params(strategy)
        except Exception:
            order_params = None

        max_rpo = None
        if order_params:
            max_rpo = order_params.get('max_rpo')

        # Calculate kelly-based risk
        kelly_risk = equity * half_kelly

        # Apply max_rpo constraint if available
        if max_rpo and max_rpo > 0:
            max_risk = equity * (max_rpo / 100.0)
            allowed_risk = min(kelly_risk, max_risk)
        else:
            allowed_risk = kelly_risk

        # Use floor() for conservative (round down) sizing
        return floor(allowed_risk / risk_per_contract)

    def get_safety_statistics(self) -> dict:
        """
        Get statistics about safety cap activations.

        Returns:
            Dict with safety cap statistics
        """
        return {
            'total_calculations': self.total_calculations,
            'safety_cap_activations': self.safety_cap_activations,
            'activation_rate': (
                self.safety_cap_activations / self.total_calculations
                if self.total_calculations > 0 else 0
            )
        }

    def reset_statistics(self) -> None:
        """Reset safety statistics."""
        self.safety_cap_activations = 0
        self.total_calculations = 0
