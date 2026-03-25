"""
Margin Calculator Module

Provides per-contract IBKR margin requirements for futures contracts.
Implements realistic dual-margin tracking:
- Initial Margin: Required to OPEN a position (higher threshold)
- Maintenance Margin: Required to HOLD a position (lower threshold)

Key concepts:
- Initial margin checked when entering a trade
- Maintenance margin reserved/tracked for open positions
- Margin call triggered if equity falls below maintenance requirement
- Fallback to percentage-based calculation for unknown symbols
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple, NamedTuple
import json

_logger = logging.getLogger(__name__)


class MarginRequirement(NamedTuple):
    """
    Margin requirements for a position.
    
    Attributes:
        initial: Initial margin required to OPEN the position
        maintenance: Maintenance margin required to HOLD the position
    """
    initial: float
    maintenance: float


@dataclass(frozen=True)
class ContractSpecs:
    """
    Specifications for a futures contract including margin requirements.

    Margin values are overnight margins from IBKR.
    Using overnight (not intraday) ensures adequate capital for
    positions held through session boundaries.

    Attributes:
        symbol: Trading symbol (e.g., 'MNQ', 'ES')
        multiplier: Contract point value multiplier
        min_tick: Minimum price increment
        initial_margin: Initial margin per contract (required to open)
        maintenance_margin: Maintenance margin per contract (required to hold)
    """
    symbol: str
    multiplier: float
    min_tick: float
    initial_margin: float
    maintenance_margin: float

    @property
    def margin_per_contract(self) -> MarginRequirement:
        """Return both margin requirements per contract."""
        return MarginRequirement(
            initial=self.initial_margin,
            maintenance=self.maintenance_margin
        )


class MarginCalculator:
    """
    Calculates margin requirements using per-contract specifications.

    Implements IBKR's dual-margin model:
    - Initial margin: Must be available to enter a position
    - Maintenance margin: What's actually held/reserved for open positions
    
    Falls back to percentage-based calculation if contract not found.

    Attributes:
        specs: Dict mapping symbol to ContractSpecs
        fallback_initial_rate: Rate for initial margin on unknown symbols
        fallback_maintenance_rate: Rate for maintenance margin on unknown symbols
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize margin calculator with contract specifications.

        Args:
            config_path: Path to margin_data.json. If None, uses default location.
        """
        self.specs: Dict[str, ContractSpecs] = {}
        self.fallback_initial_rate: float = 0.115  # ~15% higher than maintenance
        self.fallback_maintenance_rate: float = 0.10
        self._load_config(config_path)

    def _load_config(self, config_path: Optional[Path]) -> None:
        """
        Load contract specifications from JSON config.

        Args:
            config_path: Path to config file, or None for default location
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'data' / 'margin_data.json'
        elif isinstance(config_path, str):
            config_path = Path(config_path)

        if not config_path.exists():
            # Use empty specs, will fall back to rate-based calculation
            return

        with open(config_path) as f:
            data = json.load(f)

        for symbol, info in data.get('contracts', {}).items():
            # Support both old format (overnight_margin) and new format (initial/maintenance)
            if 'initial_margin' in info:
                initial = info['initial_margin']
                maintenance = info['maintenance_margin']
            else:
                # Legacy format: use overnight_margin for both (maintenance)
                # and estimate initial as 15% higher
                maintenance = info.get('overnight_margin', 0)
                initial = maintenance * 1.15
            
            self.specs[symbol] = ContractSpecs(
                symbol=symbol,
                multiplier=info['multiplier'],
                min_tick=info['min_tick'],
                initial_margin=initial,
                maintenance_margin=maintenance
            )

        fallback = data.get('fallback', {})
        self.fallback_initial_rate = fallback.get('initial_margin_rate', 0.115)
        self.fallback_maintenance_rate = fallback.get('maintenance_margin_rate', 0.10)

    def get_margin_per_contract(self, symbol: str) -> Optional[MarginRequirement]:
        """
        Get margin requirements for one contract of the given symbol.

        Args:
            symbol: Trading symbol (e.g., 'MNQ', 'ES')

        Returns:
            MarginRequirement with initial and maintenance, or None if not found
        """
        if symbol in self.specs:
            return self.specs[symbol].margin_per_contract
        return None

    def calculate_margin(
        self,
        symbol: str,
        position_size: int,
        entry_price: float,
        multiplier: float
    ) -> MarginRequirement:
        """
        Calculate total margin requirements for a position.

        For known symbols, uses IBKR per-contract margins.
        For unknown symbols, falls back to percentage of notional value.

        Args:
            symbol: Trading symbol (e.g., 'MNQ', 'ES')
            position_size: Number of contracts
            entry_price: Entry price (used for fallback calculation)
            multiplier: Contract multiplier (used for fallback)

        Returns:
            MarginRequirement with initial and maintenance margins
        """
        per_contract = self.get_margin_per_contract(symbol)

        if per_contract is not None:
            # Use IBKR margin requirements
            return MarginRequirement(
                initial=position_size * per_contract.initial,
                maintenance=position_size * per_contract.maintenance
            )
        else:
            # Fallback: percentage of notional value (symbol not in margin_data.json)
            _logger.warning("No margin specs for symbol '%s', using percentage-based fallback "
                            "(initial=%.1f%%, maintenance=%.1f%%)", symbol,
                            self.fallback_initial_rate * 100, self.fallback_maintenance_rate * 100)
            notional_value = entry_price * position_size * multiplier
            return MarginRequirement(
                initial=notional_value * self.fallback_initial_rate,
                maintenance=notional_value * self.fallback_maintenance_rate
            )

    def get_initial_margin(
        self,
        symbol: str,
        position_size: int,
        entry_price: float,
        multiplier: float
    ) -> float:
        """
        Convenience method to get just the initial margin.
        
        Args:
            symbol: Trading symbol
            position_size: Number of contracts
            entry_price: Entry price
            multiplier: Contract multiplier
            
        Returns:
            Initial margin required to open the position
        """
        return self.calculate_margin(symbol, position_size, entry_price, multiplier).initial

    def get_maintenance_margin(
        self,
        symbol: str,
        position_size: int,
        entry_price: float,
        multiplier: float
    ) -> float:
        """
        Convenience method to get just the maintenance margin.
        
        Args:
            symbol: Trading symbol
            position_size: Number of contracts
            entry_price: Entry price
            multiplier: Contract multiplier
            
        Returns:
            Maintenance margin required to hold the position
        """
        return self.calculate_margin(symbol, position_size, entry_price, multiplier).maintenance
