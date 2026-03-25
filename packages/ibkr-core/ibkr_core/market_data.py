# ibkr_core/market_data.py - extracted from _03_MarketData.py
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple, Optional

import polars as pl
from ._compat import HAS_IB, _require_ib

if HAS_IB:
    from ib_async import IB, util, Contract, ContFuture
else:
    IB = None
    util = None
    Contract = None
    ContFuture = None


from .trading_calendar import get_trading_calendar
from .logger import get_logger


class MarketDataManager:
    # === Map barSize -> seconds ===
    _BARSEC = {
        '1 secs': 1, '5 secs': 5, '10 secs': 10, '15 secs': 15, '30 secs': 30,
        '1 min': 60, '2 mins': 120, '3 mins': 180, '5 mins': 300, '10 mins': 600,
        '15 mins': 900, '20 mins': 1200, '30 mins': 1800,
        '1 hour': 3600, '2 hours': 7200, '3 hours': 10800, '4 hours': 14400, '8 hours': 28800,
        '1 day': 86400, '1 week': 604800, '1 month': 2629800  # ~30.44d
    }

    # === IB step windows (doc examples). Each item: (durationStr, minBarSec, maxBarSec) ===
    _STEP_WINDOWS: List[Tuple[str, int, int]] = [
        ('60 S',     1,    60),        # 1 sec - 1 min
        ('120 S',    1,   120),        # 1 sec - 2 mins
        ('1800 S',   1,  1800),        # 1 sec - 30 mins
        ('3600 S',   5,  3600),        # 5 secs - 1 hr
        ('14400 S', 10, 10800),        # 10 secs - 3 hrs
        ('28800 S', 30, 28800),        # 30 secs - 8 hrs
        ('1 D',     60, 86400),        # 1 min - 1 day
        ('2 D',    120, 86400),        # 2 mins - 1 day
        ('1 W',    180, 604800),       # 3 mins - 1 week
        ('1 M',   1800, 2629800),      # 30 mins - 1 month
        ('1 Y',   86400, 2629800),     # 1 day - 1 month
    ]

    # Timeframes that require aggregation from 1H data (aligned to 00:00 Madrid time)
    _AGGREGATE_FROM_HOURLY = {'2 hours', '4 hours', '8 hours'}

    def __init__(self, ib: IB, contract: Contract, whatToShow: str = 'AUTO', useRTH: bool = False):
        """
        Demanda de datos historicos de mercado.
        Esta clase es llamada por la clase INDICATORS para suministrar los datos de mercado.
        """
        self.ib = ib
        self.contract = contract
        self.whatToShow = whatToShow
        self.useRTH = useRTH
        
        # TradingCalendar for timezone operations
        self._trading_calendar = get_trading_calendar()

###################################################
############ HOURLY DATA AGGREGATION ##############
###################################################

    def _get_aggregation_offset(self, reference_date=None) -> str:
        """
        Get the Polars offset string for multi-hour candle aggregation based on DST period.
        
        CME markets open at 18:00 ET. Due to DST differences between US and Europe:
        - Normal (winter/summer): 18:00 ET = 00:00 Madrid → offset = '0h'
        - DST gap (spring/fall): 18:00 ET = 23:00 Madrid → offset = '-1h'
        
        This ensures candles align to actual market open:
        - Normal: 00:00, 04:00, 08:00, 12:00, 16:00, 20:00
        - DST gap: 23:00, 03:00, 07:00, 11:00, 15:00, 19:00
        
        Args:
            reference_date: Date to check DST period for. If None, uses today.
            
        Returns:
            Polars offset string ('0h' or '-1h')
        """
        period = self._trading_calendar.get_current_period(reference_date)
        
        if period in ('dst_gap_spring', 'dst_gap_fall'):
            return '-1h'
        return '0h'
    
    def _aggregate_hourly_to_timeframe(self, df_1h: pl.DataFrame, target_timeframe: str, num_bars: int) -> pl.DataFrame:
        """
        Aggregate 1-hour bars into multi-hour candles (2H, 4H, 8H) aligned to market open.
        
        This method builds properly aligned candles by aggregating hourly data using
        Polars group_by_dynamic() with a DST-aware offset. This ensures candles start at:
        - Normal (winter/summer): 00:00, 04:00, 08:00, 12:00, 16:00, 20:00
        - DST gap periods: 23:00, 03:00, 07:00, 11:00, 15:00, 19:00
        
        Note: The last 4H candle before maintenance (20:00 normal, 19:00 DST gap) only
        contains 3 hours due to CME maintenance break. This is correct market behavior.
        
        Args:
            df_1h: Polars DataFrame with 1-hour OHLCV data
            target_timeframe: Target bar size ('2 hours', '4 hours', '8 hours')
            num_bars: Number of target bars to return
            
        Returns:
            DataFrame with aggregated candles aligned to market open
        """
        if df_1h.is_empty():
            return df_1h
        
        # Map target timeframe to Polars interval
        interval_map = {
            '2 hours': '2h',
            '4 hours': '4h',
            '8 hours': '8h',
        }
        
        polars_interval = interval_map.get(target_timeframe)
        if polars_interval is None:
            raise ValueError(f"Unsupported aggregation timeframe: {target_timeframe}")
        
        # Ensure data is sorted by date
        df_1h = df_1h.sort('date')
        
        # Get DST-aware offset for candle alignment
        polars_offset = self._get_aggregation_offset()
        
        # Aggregate using group_by_dynamic with DST-aware offset
        # closed='left' means bar includes its start time
        # label='left' means bar is labeled with its start time
        aggregated = df_1h.group_by_dynamic(
            'date',
            every=polars_interval,
            offset=polars_offset,  # DST-aware: '0h' normal, '-1h' DST gap
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
        aggregated = aggregated.drop_nulls()
        
        # Return last num_bars
        return aggregated.tail(num_bars)

###################################################
##################### HELPERS #####################
###################################################

    def _bar_seconds(self, barSizeSetting: str) -> int:
        if barSizeSetting not in self._BARSEC:
            raise ValueError(f"Unsupported barSizeSetting: {barSizeSetting}")
        return self._BARSEC[barSizeSetting]

    @staticmethod
    def _dur_to_sec(d: str) -> int:
        n, unit = d.split()
        n = int(n)
        if unit == 'S':
            return n
        if unit == 'D':
            return n * 86400
        if unit == 'W':
            return n * 604800
        if unit == 'M':
            return n * 2629800
        # 'Y'
        return n * 31557600  # ~365.25d

    def _smallest_valid_duration(self, bar_sec: int, need_seconds: int) -> str:
        """
        Pick the smallest durationStr that:
          1) allows this bar size per IB step table, and
          2) covers at least 'need_seconds'.
        If none covers it (common for <=30s bars), return the largest allowed
        and let the caller chunk multiple requests.
        """
        candidates = [d for d, lo, hi in self._STEP_WINDOWS if lo <= bar_sec <= hi]
        sized = sorted(((d, self._dur_to_sec(d)) for d in candidates), key=lambda x: x[1])
        for d, secs in sized:
            if secs >= need_seconds:
                return d
        return sized[-1][0]  # no single window large enough
    
    def _largest_valid_duration(self, bar_sec: int) -> str:
        """
        Pick the largest durationStr allowed for this bar size per IB step table.
        Used for bulk data requests to minimize the number of API calls.
        """
        candidates = [d for d, lo, hi in self._STEP_WINDOWS if lo <= bar_sec <= hi]
        sized = sorted(((d, self._dur_to_sec(d)) for d in candidates), key=lambda x: x[1])
        return sized[-1][0]  # largest allowed
    
    def _resolve_wts(self) -> str:
        if self.whatToShow != 'AUTO':
            return self.whatToShow
        sec = (getattr(self.contract, 'secType', '') or '').upper()
        # TRADES where prints exist; MIDPOINT for FX/CMDTY/IND/etc.
        return 'TRADES' if sec in {'FUT','STK','OPT','FOP','WAR'} else 'MIDPOINT'


###################################################
############## PUBLIC SYNC FUNCTIONS ##############
###################################################

    def latestBars_number(self, timeframe: str, num_bars: int, per_req_cap: int = 4000) -> pl.DataFrame:
        """
        Fetch EXACTLY 'num_bars' of 'timeframe' by chunking requests as needed.
        Minimizes overfetch using IB step windows and caps per-request bars to avoid huge payloads.
        Returns a Polars DataFrame.
        
        For multi-hour timeframes (2h, 4h, 8h), fetches 1-hour data from IBKR and
        aggregates into properly aligned candles starting at 00:00 Madrid time.
        """
        # For 2H/4H/8H timeframes, fetch 1H data and aggregate
        if timeframe in self._AGGREGATE_FROM_HOURLY:
            hours_per_bar = self._BARSEC[timeframe] // 3600
            # Calculate how many 1H bars we need (with buffer for aggregation)
            hourly_bars_needed = num_bars * hours_per_bar + hours_per_bar  # +1 bar period buffer
            
            # Fetch 1H bars
            df_1h = self._fetch_bars_chunked('1 hour', hourly_bars_needed, per_req_cap)
            
            # Aggregate to target timeframe
            return self._aggregate_hourly_to_timeframe(df_1h, timeframe, num_bars)
        
        # For other timeframes, fetch directly
        return self._fetch_bars_chunked(timeframe, num_bars, per_req_cap)
    
    def _fetch_bars_chunked(self, timeframe: str, num_bars: int, per_req_cap: int = 4000) -> pl.DataFrame:
        """
        Internal method to fetch bars by chunking requests as needed.
        """
        bar_sec = self._bar_seconds(timeframe)
        
        target_bars = num_bars
        bars: list = []
        dt = ''  # '' = now
        remaining = target_bars
        wts = self._resolve_wts()

        while remaining > 0:
            chunk_bars = min(remaining, per_req_cap)
            chunk_need_secs = chunk_bars * bar_sec
            durationStr = self._smallest_valid_duration(bar_sec, chunk_need_secs)

            
            req = self.ib.reqHistoricalData(
                self.contract,
                endDateTime=dt,
                durationStr=durationStr,
                barSizeSetting=timeframe,
                whatToShow=wts,
                useRTH=self.useRTH,
                formatDate=1  # formatDate operador local time
            )

            # Prepend older bars (req is oldest->newest)
            bars[0:0] = req
            remaining -= len(req)  # para FUT puede haber menos barras disponibles que las pedidas
            dt = req[0].date  # caminar hacia atrás desde la barra más antigua


        pdf = util.df(bars)
        for col in ('average', 'barCount'):
            if col in pdf.columns:
                pdf.drop(columns=[col], inplace=True)

        df = pl.from_pandas(pdf)
        
        # Trim to exact num_bars requested
        df = df.tail(num_bars)

        # Orden de columnas consistente
        desired = [c for c in ['date', 'open', 'high', 'low', 'close', 'volume'] if c in df.columns]
        df = df.select(desired + [c for c in df.columns if c not in desired])

        return df


    def latest_tick(self) -> pl.DataFrame:
        """
        One-shot bid/ask snapshot using IB.reqTickers() (blocking until snapshot arrives).
        Returns a one-row Polars DataFrame with columns: time, bid, ask.
        """

        tks = self.ib.reqTickers(self.contract)

        t = tks[0]
        # Map IB's empty sentinel to NaN (e.g., -1 per IBDefaults)
        empty_price = getattr(getattr(t, "defaults", None), "emptyPrice", None)

        def _val(x):
            return float('nan') if x is None or (empty_price is not None and x == empty_price) else x

        return pl.DataFrame({
            "time": [getattr(t, "time", None)],
            "bid": [_val(getattr(t, "bid", None))],
            "ask": [_val(getattr(t, "ask", None))],
        })

###################################################
############## PUBLIC ASYNC FUNCTIONS #############
###################################################

    async def async_latestBars_number(self, timeframe: str, num_bars: int, per_req_cap: int = 4000) -> pl.DataFrame:
        """
        Async version: EXACTLY 'num_bars' bars by chunking awaitable requests.
        
        For multi-hour timeframes (2h, 4h, 8h), fetches 1-hour data from IBKR and
        aggregates into properly aligned candles starting at 00:00 Madrid time.
        """
        # For 2H/4H/8H timeframes, fetch 1H data and aggregate
        if timeframe in self._AGGREGATE_FROM_HOURLY:
            hours_per_bar = self._BARSEC[timeframe] // 3600
            # Calculate how many 1H bars we need (with buffer for aggregation)
            hourly_bars_needed = num_bars * hours_per_bar + hours_per_bar  # +1 bar period buffer
            
            # Fetch 1H bars
            df_1h = await self._fetch_bars_chunked_async('1 hour', hourly_bars_needed, per_req_cap)
            
            # Aggregate to target timeframe
            return self._aggregate_hourly_to_timeframe(df_1h, timeframe, num_bars)
        
        # For other timeframes, fetch directly
        return await self._fetch_bars_chunked_async(timeframe, num_bars, per_req_cap)
    
    async def _fetch_bars_chunked_async(self, timeframe: str, num_bars: int, per_req_cap: int = 4000) -> pl.DataFrame:
        """
        Internal async method to fetch bars by chunking awaitable requests.
        """
        bar_sec = self._bar_seconds(timeframe)
        
        target_bars = num_bars
        bars: list = []
        dt = ''  # '' = now
        remaining = target_bars
        wts = self._resolve_wts()

        while remaining > 0:
            chunk_bars = min(remaining, per_req_cap)
            chunk_need_secs = chunk_bars * bar_sec
            durationStr = self._smallest_valid_duration(bar_sec, chunk_need_secs)

            req = await self.ib.reqHistoricalDataAsync(
                self.contract,
                endDateTime=dt,
                durationStr=durationStr,
                barSizeSetting=timeframe,
                whatToShow=wts,
                useRTH=self.useRTH,
                formatDate=1
            )
            bars[0:0] = req
            if not req:
                break
            remaining -= len(req)
            dt = req[0].date  # walk back from oldest

        pdf = util.df(bars)
        for col in ('average', 'barCount'):
            if col in pdf.columns:
                pdf.drop(columns=[col], inplace=True)

        df = pl.from_pandas(pdf)
        
        # Trim to exact num_bars requested
        df = df.tail(num_bars)
        
        desired = [c for c in ['date','open','high','low','close','volume'] if c in df.columns]
        return df.select(desired + [c for c in df.columns if c not in desired])

    async def latest_tick_async(self) -> pl.DataFrame:
        """
        Async one-shot bid/ask snapshot.
        """
        tks = await self.ib.reqTickersAsync(self.contract)
        t = tks[0]
        empty_price = getattr(getattr(t, "defaults", None), "emptyPrice", None)

        def _val(x):
            return float('nan') if x is None or (empty_price is not None and x == empty_price) else x

        return pl.DataFrame({
            "time": [getattr(t, "time", None)],
            "bid": [_val(getattr(t, "bid", None))],
            "ask": [_val(getattr(t, "ask", None))],
        })

    async def async_historicalBars_dates(self, timeframe: str, start_date: str, end_date: str, save_csv: bool = False) -> pl.DataFrame:
        """
        Fetch historical bars between start_date and end_date (format: 'yyyy-mm-dd').
        Chunks the time range and makes parallel async requests for faster retrieval.
        Returns a Polars DataFrame with all bars in the date range.
        
        Args:
            timeframe: Bar size (e.g., '1 hour', '1 day')
            start_date: Start date in 'yyyy-mm-dd' format
            end_date: End date in 'yyyy-mm-dd' format
            save_csv: If True, saves data to CSV file named '{symbol}_{start}_{end}.csv'
        
        Note: This method does NOT work with continuous futures (ContFuture).
        Use async_historicalBars_dates_cont() for continuous futures instead.
        """
        import asyncio
        from datetime import datetime, timedelta

        bar_sec = self._bar_seconds(timeframe)
        wts = self._resolve_wts()

        # Parse dates
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        
        if start_dt >= end_dt:
            raise ValueError("start_date must be before end_date")

        # Use the largest valid duration for this bar size to minimize requests
        chunk_duration = self._largest_valid_duration(bar_sec)
        chunk_seconds = self._dur_to_sec(chunk_duration)
        
        # Create chunks working backwards from end_date
        # Each chunk is defined by its endDateTime and durationStr
        chunks = []
        current_end = end_dt
        
        while current_end > start_dt:
            # Calculate where this chunk would start
            chunk_start = current_end - timedelta(seconds=chunk_seconds)
            
            # If chunk would extend before start_date, adjust the duration
            if chunk_start < start_dt:
                # Calculate the actual duration needed
                actual_seconds = int((current_end - start_dt).total_seconds())
                actual_duration = self._smallest_valid_duration(bar_sec, actual_seconds)
                chunks.append((current_end, actual_duration))
                break
            else:
                chunks.append((current_end, chunk_duration))
                current_end = chunk_start
        
        # Reverse to process chronologically (optional, for cleaner logging)
        chunks.reverse()
        
        # Make parallel requests
        async def fetch_chunk(end_dt: datetime, duration: str):
            end_str = end_dt.strftime('%Y%m%d %H:%M:%S')
            req = await self.ib.reqHistoricalDataAsync(
                self.contract,
                endDateTime=end_str,
                durationStr=duration,
                barSizeSetting=timeframe,
                whatToShow=wts,
                useRTH=self.useRTH,
                formatDate=1
            )
            return req
        
        # Execute all requests in parallel
        tasks = [fetch_chunk(end_dt, dur) for end_dt, dur in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results, filtering out errors
        all_bars = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Warning: Chunk {i} failed with error: {result}")
                get_logger().log_warning("MARKET_DATA", f"Chunk {i} failed with error: {result}")
                continue
            if result:
                all_bars.extend(result)
        
        if not all_bars:
            # Return empty DataFrame with correct schema
            return pl.DataFrame({
                'date': [],
                'open': [],
                'high': [],
                'low': [],
                'close': [],
                'volume': []
            })
        
        # Convert to DataFrame
        pdf = util.df(all_bars)
        for col in ('average', 'barCount'):
            if col in pdf.columns:
                pdf.drop(columns=[col], inplace=True)
        
        # Remove duplicates and sort by date
        pdf = pdf.drop_duplicates(subset=['date']).sort_values('date').reset_index(drop=True)
        
        # Convert to Polars
        df = pl.from_pandas(pdf)
        
        # Filter bars to be within the requested date range
        # Convert timezone-aware datetime to date for comparison
        start_str = start_date
        end_str = end_date
        df = df.with_columns(
            pl.col('date').dt.replace_time_zone(None).alias('date')  # Remove timezone
        ).filter(
            (pl.col('date').cast(pl.Date) >= pl.lit(start_str).str.to_date('%Y-%m-%d')) &
            (pl.col('date').cast(pl.Date) <= pl.lit(end_str).str.to_date('%Y-%m-%d'))
        )
        
        # Ensure consistent column order
        desired = [c for c in ['date', 'open', 'high', 'low', 'close', 'volume'] if c in df.columns]
        df = df.select(desired + [c for c in df.columns if c not in desired])
        
        # Save to CSV if requested
        if save_csv:
            symbol = getattr(self.contract, 'symbol', 'unknown')
            filename = f"{symbol}_{start_date}_{end_date}.csv"
            df.write_csv(filename)
            get_logger().log_info("MARKET_DATA", f"Data saved to: {filename}")
        
        return df

    async def async_historicalBars_dates_cont(self, timeframe: str, start_date: str, end_date: str, save_csv: bool = False) -> pl.DataFrame:
        """
        Fetch historical bars between start_date and end_date (format: 'yyyy-mm-dd').
        This method is specifically designed for continuous futures (ContFuture).
        Uses sequential requests walking backwards from current time.
        Returns a Polars DataFrame with all bars in the date range.
        
        Args:
            timeframe: Bar size (e.g., '1 hour', '1 day')
            start_date: Start date in 'yyyy-mm-dd' format
            end_date: End date in 'yyyy-mm-dd' format
            save_csv: If True, saves data to CSV file named '{symbol}_{start}_{end}.csv'
        
        Note: Continuous futures do not allow setting endDateTime, so this method
        walks backwards from "now" using only durationStr.
        """
        from datetime import datetime

        bar_sec = self._bar_seconds(timeframe)
        wts = self._resolve_wts()

        # Parse dates
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        
        if start_dt >= end_dt:
            raise ValueError("start_date must be before end_date")

        # Sequential approach: walk backwards from current time
        chunk_duration = self._largest_valid_duration(bar_sec)
        bars = []
        current_end = ''  # empty string means "now" for continuous futures
        
        while True:
            req = await self.ib.reqHistoricalDataAsync(
                self.contract,
                endDateTime=current_end,
                durationStr=chunk_duration,
                barSizeSetting=timeframe,
                whatToShow=wts,
                useRTH=self.useRTH,
                formatDate=1
            )
            
            if not req:
                break
            
            bars[0:0] = req  # prepend older bars
            
            # Check if we've reached the start date
            oldest_bar_date = req[0].date
            if isinstance(oldest_bar_date, str):
                oldest_dt = datetime.strptime(oldest_bar_date, '%Y%m%d %H:%M:%S')
            else:
                oldest_dt = oldest_bar_date
                # Remove timezone info if present for comparison
                if hasattr(oldest_dt, 'tzinfo') and oldest_dt.tzinfo is not None:
                    oldest_dt = oldest_dt.replace(tzinfo=None)
            
            if oldest_dt <= start_dt:
                break
            
            # Walk backwards from the oldest bar
            # Convert datetime to string format for next request
            oldest_bar = req[0].date
            if isinstance(oldest_bar, str):
                current_end = oldest_bar
            else:
                # Format datetime object to IB's expected format
                current_end = oldest_bar.strftime('%Y%m%d %H:%M:%S')
        
        if not bars:
            # Return empty DataFrame with correct schema
            return pl.DataFrame({
                'date': [],
                'open': [],
                'high': [],
                'low': [],
                'close': [],
                'volume': []
            })
        
        # Convert to DataFrame
        pdf = util.df(bars)
        for col in ('average', 'barCount'):
            if col in pdf.columns:
                pdf.drop(columns=[col], inplace=True)
        
        # Remove duplicates and sort by date
        pdf = pdf.drop_duplicates(subset=['date']).sort_values('date').reset_index(drop=True)
        
        # Convert to Polars
        df = pl.from_pandas(pdf)
        
        # Filter bars to be within the requested date range
        # Convert timezone-aware datetime to date for comparison
        start_str = start_date
        end_str = end_date
        df = df.with_columns(
            pl.col('date').dt.replace_time_zone(None).alias('date')  # Remove timezone
        ).filter(
            (pl.col('date').cast(pl.Date) >= pl.lit(start_str).str.to_date('%Y-%m-%d')) &
            (pl.col('date').cast(pl.Date) <= pl.lit(end_str).str.to_date('%Y-%m-%d'))
        )
        
        # Ensure consistent column order
        desired = [c for c in ['date', 'open', 'high', 'low', 'close', 'volume'] if c in df.columns]
        df = df.select(desired + [c for c in df.columns if c not in desired])
        
        # Save to CSV if requested
        if save_csv:
            symbol = getattr(self.contract, 'symbol', 'unknown')
            filename = f"{symbol}_{start_date}_{end_date}.csv"
            df.write_csv(filename)
            get_logger().log_info("MARKET_DATA", f"Data saved to: {filename}")
        
        return df

if __name__ == '__main__':
    import time
    ib = IB()
    # ib.RequestTimeout = 20 
    ib.connect('127.0.0.1', 7497, clientId=98)
    
    contract = Contract(symbol='MNQ', secType='FUT', exchange='CME', localSymbol='MNQZ5')
    contract = ib.qualifyContracts(contract)[0]
    print(contract)

    data = MarketDataManager(ib=ib,contract=contract).latest_tick()
    print(data)

    # # Test 1: async_historicalBars_dates with MNQ (regular contract)
    # print("=" * 60)
    # print("Testing async_historicalBars_dates with MNQ")
    # print("=" * 60)
    # mnq = Contract(symbol='MNQ', secType='FUT', exchange='CME')
    # start = time.time()
    # data1 = ib.run(MarketDataManager(ib, mnq).async_historicalBars_dates(
    #     '1 hour', '2024-01-01', '2025-10-31', save_csv=True
    # ))
    # end = time.time()
    # print(f"Shape: {data1.shape}")
    # print(f"First 5 rows:\n{data1.head()}")
    # print(f"Last 5 rows:\n{data1.tail()}")
    # print(f"Time taken: {end - start:.2f} seconds")
    
    # # Test 2: async_historicalBars_dates_cont with MNQ (continuous future)
    # print("\n" + "=" * 60)
    # print("Testing async_historicalBars_dates_cont with MNQ")
    # print("=" * 60)
    # contract = ContFuture('MNQ', exchange='CME')
    # start = time.time()
    # data2 = ib.run(MarketDataManager(ib, contract).async_historicalBars_dates_cont(
    
    #     '1 hour', '2024-01-01', '2025-10-31', save_csv=True
    # ))
    # end = time.time()
    # print(f"Shape: {data2.shape}")
    # print(f"First 5 rows:\n{data2.head()}")
    # print(f"Last 5 rows:\n{data2.tail()}")
    # print(f"Time taken: {end - start:.2f} seconds")

    ib.disconnect()
