# ibkr_core/_compat.py - Optional dependency guards
#
# Single source of truth for all optional dependency availability flags.
# Consuming modules import what they need:
#   from ._compat import HAS_IB, _require_ib
#   from ._compat import HAS_DB, _require_db
#
# Internal only -- NOT exposed in package __init__.py.

from __future__ import annotations

from typing import TYPE_CHECKING

# ---------------------------------------------------------------------------
# IB guard -- ib_async is optional (only needed for live trading)
# ---------------------------------------------------------------------------
try:
    import ib_async  # noqa: F401
    HAS_IB = True
except ImportError:
    HAS_IB = False

# ---------------------------------------------------------------------------
# Database guard -- DatabaseManager is optional (only needed for live trading)
# ---------------------------------------------------------------------------
try:
    from _10_DatabaseManager import TradingDatabaseManager  # noqa: F401
    HAS_DB = True
except ImportError:
    HAS_DB = False

# ---------------------------------------------------------------------------
# Require helpers -- raise with actionable install instructions
# ---------------------------------------------------------------------------

def _require_ib(feature: str = "live trading") -> None:
    """Raise ImportError with actionable message if ib_async is not installed."""
    if not HAS_IB:
        raise ImportError(
            f"ib_async required for {feature}. "
            f"Install with: pip install ibkr-core[live]"
        )


def _require_db(feature: str = "database operations") -> None:
    """Raise ImportError with actionable message if DatabaseManager is not available."""
    if not HAS_DB:
        raise ImportError(
            f"DatabaseManager required for {feature}. "
            f"Install with: pip install ibkr-core[live]"
        )


# ---------------------------------------------------------------------------
# Conditional type imports -- available at type-check time only
# ---------------------------------------------------------------------------
if TYPE_CHECKING:
    from ib_async import IB, Contract, ContractDetails, ContFuture
