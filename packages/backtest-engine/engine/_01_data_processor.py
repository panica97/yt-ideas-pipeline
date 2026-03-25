import logging
import os
import polars as pl
from pathlib import Path
from typing import Dict, List
from icecream import ic

_logger = logging.getLogger(__name__)


class DataPreprocessor:
    """
    Loads and resamples 1-minute historical data from hist_data folder.
    Converts to multiple timeframes as needed by strategies.
    Returns Polars DataFrames ready for indicator calculation.

    Note: Historical data is in Exchange Time (US Central / CT), NOT Madrid time.
    Multi-hour candles are aligned to 00:00 CT (offset='0h').
    DST-aware aggregation is NOT needed for backtest because the data timestamps
    don't shift with Madrid DST changes.
    """

    # Mapping of timeframe strings to Polars duration strings
    TF_MAP = {
        '1 secs': '1s',
        '5 secs': '5s',
        '10 secs': '10s',
        '15 secs': '15s',
        '30 secs': '30s',
        '1 min': '1m',
        '2 mins': '2m',
        '3 mins': '3m',
        '5 mins': '5m',
        '10 mins': '10m',
        '15 mins': '15m',
        '20 mins': '20m',
        '30 mins': '30m',
        '1 hour': '1h',
        '2 hours': '2h',
        '3 hours': '3h',
        '4 hours': '4h',
        '8 hours': '8h',
        '1 day': '1d',
        '1 week': '1w',
        '1 month': '1mo',
    }

    # Timeframes that require aggregation from 1H data (aligned to market open)
    _AGGREGATE_FROM_HOURLY = {'2 hours', '4 hours', '8 hours', '2h', '4h', '8h'}

    def __init__(self, data_folder: str = 'hist_data'):
        self.data_folder = Path(data_folder)
        self._cache = {}  # Cache for loaded data

    def load_csv(self, symbol: str, use_cache: bool = True) -> pl.DataFrame:
        """
        Load 1-minute CSV data for a given symbol.

        Args:
            symbol: Symbol name (e.g., '@ES', '@NQ')
            use_cache: Whether to use cached data if available

        Returns:
            Polars DataFrame with columns: date, open, high, low, close, volume
        """
        if use_cache and symbol in self._cache:
            return self._cache[symbol].clone()

        # Try different file patterns
        file_patterns = [
            f"{symbol}_1M_edit.txt",
            f"{symbol}_1M.txt",
            f"{symbol}.csv",
        ]

        file_path = None
        for pattern in file_patterns:
            potential_path = self.data_folder / pattern
            if potential_path.exists():
                file_path = potential_path
                break

        if file_path is None:
            raise FileNotFoundError(f"Could not find data file for symbol {symbol} in {self.data_folder}")

        # Load CSV/TXT
        df = pl.read_csv(file_path)

        # Standardize column names (handle case-insensitive)
        column_map = {col.lower(): col for col in df.columns}

        # Check if we have separate Date and Time columns (MT format)
        if 'date' in column_map and 'time' in column_map:
            # Combine Date and Time into datetime
            date_col = column_map['date']
            time_col = column_map['time']

            df = df.with_columns(
                (pl.col(date_col).str.strip_chars() + ' ' + pl.col(time_col).str.strip_chars()).alias('datetime_str')
            )

            # Parse datetime - try common formats
            try:
                # US format: MM/DD/YYYY HH:MM (most common in trading data)
                df = df.with_columns(
                    pl.col('datetime_str').str.to_datetime('%m/%d/%Y %H:%M').alias('date')
                )
            except (pl.exceptions.ComputeError, pl.exceptions.InvalidOperationError):
                try:
                    # European format: DD/MM/YYYY HH:MM
                    df = df.with_columns(
                        pl.col('datetime_str').str.to_datetime('%d/%m/%Y %H:%M').alias('date')
                    )
                except (pl.exceptions.ComputeError, pl.exceptions.InvalidOperationError):
                    try:
                        # ISO format: YYYY-MM-DD HH:MM:SS
                        df = df.with_columns(
                            pl.col('datetime_str').str.to_datetime('%Y-%m-%d %H:%M:%S').alias('date')
                        )
                    except (pl.exceptions.ComputeError, pl.exceptions.InvalidOperationError):
                        # Last resort: let Polars auto-detect format
                        df = df.with_columns(
                            pl.col('datetime_str').str.to_datetime().alias('date')
                        )

            df = df.drop('datetime_str')

        # Map column names to standard OHLCV format
        open_col = column_map.get('open', 'Open')
        high_col = column_map.get('high', 'High')
        low_col = column_map.get('low', 'Low')
        close_col = column_map.get('close', 'Close')

        # Handle volume column (may be 'Vol', 'volume', 'Volume')
        vol_col = None
        for vol_name in ['vol', 'volume']:
            if vol_name in column_map:
                vol_col = column_map[vol_name]
                break

        if vol_col is None:
            # No volume column, create dummy with 0 (neutral default)
            df = df.with_columns(pl.lit(0.0).alias('volume'))
            vol_col = 'volume'

        # Select and rename to standard format
        df = df.select([
            pl.col('date'),
            pl.col(open_col).alias('open').cast(pl.Float64),
            pl.col(high_col).alias('high').cast(pl.Float64),
            pl.col(low_col).alias('low').cast(pl.Float64),
            pl.col(close_col).alias('close').cast(pl.Float64),
            pl.col(vol_col).alias('volume').cast(pl.Float64),
        ])

        # Remove timezone info for consistency
        if df['date'].dtype == pl.Datetime:
            df = df.with_columns(
                pl.col('date').dt.replace_time_zone(None)
            )

        # Sort by date and remove duplicates
        df = df.sort('date').unique(subset=['date'], keep='first')

        # Validate OHLC invariants: high >= max(open,close), low <= min(open,close)
        df = self._validate_ohlc_invariants(df, symbol)

        # Cache the data
        if use_cache:
            self._cache[symbol] = df.clone()

        return df

    @staticmethod
    def _validate_ohlc_invariants(df: pl.DataFrame, symbol: str) -> pl.DataFrame:
        """
        Check OHLC invariants and log warnings for anomalies.
        Does not fail -- just warns so the user is aware of data quality issues.
        """
        anomalies = df.filter(
            (pl.col('high') < pl.max_horizontal('open', 'close')) |
            (pl.col('low') > pl.min_horizontal('open', 'close'))
        )
        if len(anomalies) > 0:
            first_date = anomalies['date'][0]
            _logger.warning(
                "OHLC invariant anomalies in %s: %d bars (first at %s). "
                "high < max(open,close) or low > min(open,close).",
                symbol, len(anomalies), first_date
            )
        return df

    def resample_ohlcv(self, df: pl.DataFrame, timeframe: str) -> pl.DataFrame:
        """
        Resample OHLCV data to a different timeframe.

        For multi-hour timeframes (2h, 4h, 8h), first resamples to 1H then aggregates
        with offset='0h' to align candles to 00:00 CT (exchange time).

        Note: Historical data is in Exchange Time (US Central), so DST-aware
        aggregation is NOT needed. Candle alignment is always:
        00:00, 04:00, 08:00, 12:00, 16:00 (skip), 20:00 CT

        Args:
            df: DataFrame with columns: date, open, high, low, close, volume
            timeframe: Target timeframe (e.g., '1 hour', '4 hours', '1 day')

        Returns:
            Resampled Polars DataFrame
        """
        if timeframe not in self.TF_MAP:
            raise ValueError(f"Unsupported timeframe: {timeframe}. Supported: {list(self.TF_MAP.keys())}")

        polars_interval = self.TF_MAP[timeframe]

        # Check if this timeframe needs aggregation from 1H data
        tf_normalized = timeframe.lower().replace(' ', '')
        needs_hourly_aggregation = any(
            tf.lower().replace(' ', '') == tf_normalized
            for tf in self._AGGREGATE_FROM_HOURLY
        )

        if needs_hourly_aggregation:
            # First resample to 1H
            df_1h = df.group_by_dynamic(
                'date',
                every='1h',
                closed='left',
                label='left'
            ).agg([
                pl.col('open').first().alias('open'),
                pl.col('high').max().alias('high'),
                pl.col('low').min().alias('low'),
                pl.col('close').last().alias('close'),
                pl.col('volume').sum().alias('volume'),
            ]).sort('date').drop_nulls()

            # Aggregate 1H to target timeframe with offset='0h' (aligned to 00:00 CT)
            resampled = df_1h.group_by_dynamic(
                'date',
                every=polars_interval,
                offset='0h',
                closed='left',
                label='left'
            ).agg([
                pl.col('open').first().alias('open'),
                pl.col('high').max().alias('high'),
                pl.col('low').min().alias('low'),
                pl.col('close').last().alias('close'),
                pl.col('volume').sum().alias('volume'),
            ]).sort('date')
        else:
            # Direct resampling for other timeframes
            resampled = df.group_by_dynamic(
                'date',
                every=polars_interval,
                closed='left',
                label='left'
            ).agg([
                pl.col('open').first().alias('open'),
                pl.col('high').max().alias('high'),
                pl.col('low').min().alias('low'),
                pl.col('close').last().alias('close'),
                pl.col('volume').sum().alias('volume'),
            ]).sort('date')

        # Remove rows with null values (incomplete bars at edges)
        resampled = resampled.drop_nulls()

        return resampled

    def load_and_resample(self, symbol: str, timeframes: List[str],
                         start_date: str = None, end_date: str = None) -> Dict[str, pl.DataFrame]:
        """
        Load 1-minute data and resample to multiple timeframes.

        Args:
            symbol: Symbol name (e.g., '@ES', '@NQ')
            timeframes: List of target timeframes (e.g., ['1 hour', '4 hours', '1 day'])
            start_date: Optional start date filter (format: 'YYYY-MM-DD')
            end_date: Optional end date filter (format: 'YYYY-MM-DD')

        Returns:
            Dict mapping timeframe -> DataFrame
        """
        # Load base 1-minute data
        df_1m = self.load_csv(symbol)

        # Apply date filters if provided
        if start_date:
            start_dt = pl.lit(start_date).str.to_date('%Y-%m-%d')
            df_1m = df_1m.filter(pl.col('date').cast(pl.Date) >= start_dt)

        if end_date:
            end_dt = pl.lit(end_date).str.to_date('%Y-%m-%d')
            df_1m = df_1m.filter(pl.col('date').cast(pl.Date) <= end_dt)

        # Resample to each requested timeframe
        result = {}
        for tf in timeframes:
            if tf == '1 min':
                result[tf] = df_1m.clone()
            else:
                result[tf] = self.resample_ohlcv(df_1m, tf)

        return result

    def clear_cache(self):
        """Clear cached data."""
        self._cache = {}


if __name__ == '__main__':
    # Test the preprocessor
    preprocessor = DataPreprocessor()

    # Test loading ES data
    symbol = '@ES'
    timeframes = ['1 min', '5 mins', '1 hour', '4 hours', '1 day']

    try:
        data_dict = preprocessor.load_and_resample(
            symbol=symbol,
            timeframes=timeframes,
            start_date='2024-01-01',
            end_date='2024-12-31'
        )

        print(f"Loaded data for {symbol}")
        for tf, df in data_dict.items():
            print(f"{tf}: {df.shape[0]} bars")
            print(df.head(3))
            print()

    except Exception as e:
        print(f"Error: {e}")
