"""Monte Carlo simulation engine for trading strategy validation."""

from .generator.garch import GJR_GARCH, GARCH11
from .generator.ohlc_structure import OHLCStructureModel
from .generator.path_generator import SyntheticOHLCGenerator
from .generator.regime import RegimeDetector
from .shuffler.trade_shuffler import TradeShuffler
from .analysis.aggregator import MonteCarloAggregator

__all__ = [
    "GJR_GARCH",
    "GARCH11",  # backward-compatible alias
    "OHLCStructureModel",
    "SyntheticOHLCGenerator",
    "RegimeDetector",
    "TradeShuffler",
    "MonteCarloAggregator",
]
