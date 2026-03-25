"""
Backtest Engine Constants

Centralized string constants for exit reasons and other shared values.
Using a plain class (not enum.Enum) to preserve backward compatibility
with JSON serialization and string comparisons.
"""


class ExitReason:
    """Exit reason constants for position closures."""
    SL = 'SL'
    SL_BE = 'SL_BE'
    SL_TSL = 'SL_TSL'
    TP = 'TP'
    NUM_BARS = 'num_bars'
    EXIT_CONDITION = 'exit_condition'
    BACKTEST_END = 'backtest_end'
    MARGIN_CALL = 'margin_call'
