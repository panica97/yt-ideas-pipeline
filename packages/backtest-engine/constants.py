"""Centralized constants for the IBKR-BACKTEST project.

All log folder paths are defined here to avoid duplication and ensure consistency.
These are project structure paths, not configurable settings.
"""

from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent

# Log folder paths (all relative to project root)
BACKTEST_LOGS_PATH = PROJECT_ROOT / "logs_backtest"
PORTFOLIO_LOGS_PATH = PROJECT_ROOT / "logs_portfolio"
INTEGRATION_TEST_LOGS_PATH = PROJECT_ROOT / "logs_integration_test"
COMPARISON_LOGS_PATH = PROJECT_ROOT / "logs_comparison"
STRESS_TEST_LOGS_PATH = PROJECT_ROOT / "logs_stress_test"
SYSTEM_LOGS_PATH = PROJECT_ROOT / "logs_system"
