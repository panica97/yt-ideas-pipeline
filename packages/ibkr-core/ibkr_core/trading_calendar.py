# ibkr_core/trading_calendar.py - extracted from _00_TradingCalendar.py
"""
_00_TradingCalendar.py - CME Trading Calendar Manager

This module provides comprehensive trading calendar functionality for the IBKR trading
infrastructure, including:
- Market open/closed status detection
- Holiday and early close handling
- DST (Daylight Saving Time) transition awareness
- Weekend detection with proper CME futures session timing
- Dynamic trading hours based on product type and calendar events

Uses pytz with Europe/Madrid timezone for all DST calculations.
Implements singleton pattern for global access across the infrastructure.

The calendar data is loaded from trading_calendar.json which contains:
- Regular trading hours for different product types
- Holiday and early close events by year
- DST transition dates and gap periods
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, date, time, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

import pytz

from .logger import get_logger


# Singleton instance
_calendar_instance: Optional['TradingCalendar'] = None
_calendar_lock = threading.Lock()


def get_trading_calendar() -> 'TradingCalendar':
    """
    Get the singleton TradingCalendar instance.
    
    Thread-safe accessor that creates the instance on first call.
    
    Returns:
        TradingCalendar: The global calendar instance
    """
    global _calendar_instance
    if _calendar_instance is None:
        with _calendar_lock:
            if _calendar_instance is None:
                _calendar_instance = TradingCalendar()
    return _calendar_instance


class TradingCalendar:
    """
    CME Trading Calendar Manager.
    
    Provides methods to determine:
    - Whether markets are currently open for a given symbol
    - Today's close time accounting for holidays and early closes
    - Current DST period (winter/summer/gap)
    - Weekend status with proper session timing
    
    All times are in Europe/Madrid timezone unless otherwise specified.
    """
    
    # Pre-market buffer in minutes (markets considered "open" this many minutes before actual open)
    PRE_MARKET_BUFFER_MINUTES = 2
    
    # Default product type for unknown symbols
    DEFAULT_PRODUCT_TYPE = 'equity_index_futures'
    
    def __init__(self, calendar_path: Optional[str] = None):
        """
        Initialize TradingCalendar.
        
        Args:
            calendar_path: Path to trading_calendar.json. If None, looks in parent directory.
        """
        self._tz = pytz.timezone('Europe/Madrid')
        self._calendar_data: Dict[str, Any] = {}
        self._symbol_to_product: Dict[str, str] = {}
        self._events_cache: Dict[str, Dict[str, Any]] = {}  # {YYYY-MM-DD: event_dict}
        
        # Load calendar data
        self._load_calendar(calendar_path)
        
        # Build symbol -> product type mapping
        self._build_symbol_mapping()
        
        # Build events cache for faster lookup
        self._build_events_cache()
    
    def _load_calendar(self, calendar_path: Optional[str] = None) -> None:
        """
        Load trading calendar JSON file.
        
        Raises:
            FileNotFoundError: If calendar file does not exist
            ValueError: If calendar file contains invalid JSON or missing required data
        """
        if calendar_path is None:
            # Look for trading_calendar.json in the repository root
            # We're in live_trading/, so go up one level
            current_dir = Path(__file__).parent
            calendar_path = current_dir.parent / 'trading_calendar.json'
        
        # Check file exists (raise if not)
        if not Path(calendar_path).exists():
            raise FileNotFoundError(
                f"[TradingCalendar] CRITICAL: Calendar file not found: {calendar_path}\n"
                f"  The trading system cannot operate without the calendar file.\n"
                f"  Please ensure trading_calendar.json is in the repository root."
            )
        
        # Load and parse JSON (raise if invalid)
        try:
            with open(calendar_path, 'r', encoding='utf-8') as f:
                self._calendar_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"[TradingCalendar] CRITICAL: Invalid JSON in calendar file: {e}\n"
                f"  Please fix the JSON syntax in {calendar_path}"
            )
        
        # Validate required sections exist
        required_sections = ['calendar', 'dst_transitions', 'regular_trading_hours', 'years']
        missing = [s for s in required_sections if s not in self._calendar_data]
        if missing:
            raise ValueError(
                f"[TradingCalendar] CRITICAL: Calendar file missing required sections: {missing}\n"
                f"  Please ensure {calendar_path} has all required data."
            )
        
        print(f"[TradingCalendar] Loaded calendar: {self._calendar_data.get('calendar', {}).get('name', 'Unknown')}")
        get_logger().log_info("SYSTEM", f"TradingCalendar loaded: {self._calendar_data.get('calendar', {}).get('name', 'Unknown')}")
    
    def _build_symbol_mapping(self) -> None:
        """
        Build reverse mapping from symbol to product type.
        
        Parses the regular_trading_hours section to map each symbol
        (e.g., 'MNQ', 'MGC') to its product type (e.g., 'equity_index_futures', 'metals_futures').
        """
        regular_hours = self._calendar_data.get('regular_trading_hours', {})
        
        for product_type, product_info in regular_hours.items():
            if product_type == 'description':
                continue
            
            products = product_info.get('products', [])
            for symbol in products:
                self._symbol_to_product[symbol] = product_type
        
        print(f"[TradingCalendar] Mapped {len(self._symbol_to_product)} symbols to product types")
        get_logger().log_info("SYSTEM", f"TradingCalendar mapped {len(self._symbol_to_product)} symbols to product types")
    
    def _build_events_cache(self) -> None:
        """Build a cache of events by date for fast lookup."""
        years_data = self._calendar_data.get('years', {})
        
        for year, year_info in years_data.items():
            events = year_info.get('events', [])
            for event in events:
                event_date = event.get('date')
                if event_date:
                    self._events_cache[event_date] = event
        
        print(f"[TradingCalendar] Cached {len(self._events_cache)} calendar events")
        get_logger().log_info("SYSTEM", f"TradingCalendar cached {len(self._events_cache)} calendar events")
    
    def get_product_type(self, symbol: str) -> str:
        """
        Get the product type for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., 'MNQ', 'MGC', 'ES')
            
        Returns:
            Product type string (e.g., 'equity_index_futures', 'metals_futures')
        """
        return self._symbol_to_product.get(symbol, self.DEFAULT_PRODUCT_TYPE)
    
    def get_current_period(self, check_date: Optional[date] = None) -> str:
        """
        Determine the current DST period.
        
        DST periods affect trading hours as US and Spain transition at different times:
        - 'winter': Both US and Spain in standard time (7-hour difference)
        - 'summer': Both US and Spain in daylight time (7-hour difference)
        - 'dst_gap_spring': US in CDT, Spain still in CET (6-hour difference, markets 1h earlier)
        - 'dst_gap_fall': Spain in CET, US still in CDT (6-hour difference, markets 1h earlier)
        
        Args:
            check_date: Date to check. If None, uses today.
            
        Returns:
            Period string: 'winter', 'summer', 'dst_gap_spring', or 'dst_gap_fall'
        """
        if check_date is None:
            check_date = datetime.now(self._tz).date()
        
        year_str = str(check_date.year)
        dst_transitions = self._calendar_data.get('dst_transitions', {}).get(year_str, {})
        
        if not dst_transitions:
            # No DST data for this year, assume standard (winter)
            return 'winter'
        
        # Check for gap periods first (they have priority)
        gap_periods = dst_transitions.get('gap_periods', [])
        for gap in gap_periods:
            gap_start = datetime.strptime(gap['start'], '%Y-%m-%d').date()
            gap_end = datetime.strptime(gap['end'], '%Y-%m-%d').date()
            
            if gap_start <= check_date <= gap_end:
                # Determine which gap period by type field
                gap_type = gap.get('type', '')
                if gap_type == 'fall':
                    return 'dst_gap_fall'
                else:
                    return 'dst_gap_spring'
        
        # Not in a gap period - determine winter or summer
        # Spain spring forward date marks transition from winter to summer
        spain_spring = dst_transitions.get('spain_spring_forward')
        spain_fall = dst_transitions.get('spain_fall_back')
        
        if spain_spring and spain_fall:
            spring_date = datetime.strptime(spain_spring, '%Y-%m-%d').date()
            fall_date = datetime.strptime(spain_fall, '%Y-%m-%d').date()
            
            if spring_date <= check_date < fall_date:
                return 'summer'
        
        return 'winter'
    
    def is_weekend(self, check_datetime: Optional[datetime] = None) -> bool:
        """
        Check if the given datetime falls on a weekend (market closed).
        
        CME futures markets are closed from Friday 23:00 to Sunday 00:00 Madrid time
        (with variations for DST gap periods).
        
        Note: This checks the CALENDAR weekend, not the session weekend.
        Saturday is always considered weekend.
        Sunday is weekend UNTIL market opens (00:00 standard, varies in DST gaps).
        Friday after close (23:00+) is NOT weekend (just closed session).
        
        Args:
            check_datetime: Datetime to check. If None, uses now.
            
        Returns:
            True if weekend (market definitely closed for extended period)
        """
        if check_datetime is None:
            check_datetime = datetime.now(self._tz)
        elif check_datetime.tzinfo is None:
            check_datetime = self._tz.localize(check_datetime)
        
        weekday = check_datetime.weekday()  # Monday=0, Sunday=6
        
        # Saturday is always weekend
        if weekday == 5:  # Saturday
            return True
        
        # Sunday: depends on DST period
        # CME futures open Sunday 5pm CT (Chicago Time)
        # In Madrid timezone this translates to:
        #   - Winter (CET):      Monday 00:00 Madrid (CT+7, 17+7=24=00:00 next day)
        #   - Summer (CEST):     Monday 00:00 Madrid (CT+7, 17+7=24=00:00 next day)
        #   - DST gap spring:    Sunday 23:00 Madrid (CT+6, 17+6=23:00)
        #   - DST gap fall:      Sunday 23:00 Madrid (CT+6, 17+6=23:00)
        if weekday == 6:  # Sunday
            period = self.get_current_period(check_datetime.date())

            if period == 'dst_gap_spring' or period == 'dst_gap_fall':
                # Spring/Fall gap: markets open Sunday 23:00 Madrid (CT+6)
                # Before 23:00 is weekend, after 23:00 market is open
                return check_datetime.time() < time(23, 0)
            else:
                # Winter and Summer: CME opens Sunday 5pm CT = Monday 00:00 Madrid (CT+7)
                # All of Sunday is weekend (market opens Monday)
                return True
        
        return False
    
    def get_event_for_date(self, check_date: Optional[date] = None) -> Optional[Dict[str, Any]]:
        """
        Get calendar event (holiday/early close) for a specific date.
        
        Args:
            check_date: Date to check. If None, uses today.
            
        Returns:
            Event dict with keys like 'name', 'type', 'trading_status', 'close_time_madrid'
            or None if no event on that date.
        """
        if check_date is None:
            check_date = datetime.now(self._tz).date()
        
        date_str = check_date.strftime('%Y-%m-%d')
        return self._events_cache.get(date_str)
    
    def get_trading_hours(self, symbol: str, check_date: Optional[date] = None) -> Tuple[time, time]:
        """
        Get trading hours for a symbol on a specific date.
        
        Returns the session open and close times accounting for:
        - Product type (equity index, metals, etc.)
        - Current DST period
        - Early close events
        
        Args:
            symbol: Trading symbol
            check_date: Date to check. If None, uses today.
            
        Returns:
            Tuple of (open_time, close_time) as time objects
        """
        if check_date is None:
            check_date = datetime.now(self._tz).date()
        
        product_type = self.get_product_type(symbol)
        period = self.get_current_period(check_date)
        
        # Check for special events (early close, holiday)
        event = self.get_event_for_date(check_date)
        if event:
            trading_status = event.get('trading_status', '')
            
            if trading_status == 'CLOSED':
                # Return None-equivalent times (market closed all day)
                return (time(0, 0), time(0, 0))
            
            elif trading_status == 'EARLY_CLOSE':
                # Use early close time from event
                close_time_str = event.get('close_time_madrid', '23:00')
                # Handle formats like "19:00" or "19:15"
                close_parts = close_time_str.split(':')
                close_time = time(int(close_parts[0]), int(close_parts[1]) if len(close_parts) > 1 else 0)
                
                open_time_str = event.get('regular_open_time_madrid', '00:00')
                open_parts = open_time_str.split(':')
                open_time = time(int(open_parts[0]), int(open_parts[1]) if len(open_parts) > 1 else 0)
                
                return (open_time, close_time)
        
        # Get regular trading hours from calendar
        regular_hours = self._calendar_data.get('regular_trading_hours', {})
        product_info = regular_hours.get(product_type, {})
        schedule = product_info.get('standard_schedule_madrid', {})
        
        # Get hours for current period
        period_schedule = schedule.get(period, schedule.get('winter', {}))
        
        # Handle daily sessions
        daily_sessions = period_schedule.get('daily_sessions', {})
        weekday = check_date.weekday()
        
        if weekday == 4:  # Friday
            session = daily_sessions.get('friday', daily_sessions.get('monday_to_thursday', {}))
        else:
            session = daily_sessions.get('monday_to_thursday', {})
        
        # Parse open/close times
        open_str = session.get('session_open', period_schedule.get('session_open', '00:00'))
        close_str = session.get('session_close', period_schedule.get('session_close', '23:00'))
        
        # Handle "(previous day)" or "(next day)" annotations
        open_str = open_str.split('(')[0].strip()
        close_str = close_str.split('(')[0].strip()
        
        # Parse times
        try:
            open_parts = open_str.split(':')
            open_time = time(int(open_parts[0]), int(open_parts[1]) if len(open_parts) > 1 else 0)
        except (ValueError, IndexError):
            open_time = time(0, 0)
        
        try:
            close_parts = close_str.split(':')
            close_time = time(int(close_parts[0]), int(close_parts[1]) if len(close_parts) > 1 else 0)
        except (ValueError, IndexError):
            close_time = time(23, 0)
        
        return (open_time, close_time)
    
    def get_close_time_today(self, symbol: str) -> datetime:
        """
        Get today's market close time for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            datetime of today's close in Madrid timezone
        """
        today = datetime.now(self._tz).date()
        _, close_time = self.get_trading_hours(symbol, today)
        
        return self._tz.localize(datetime.combine(today, close_time))
    
    def get_next_market_open(self, symbol: str, from_datetime: Optional[datetime] = None) -> datetime:
        """
        Get the next market open time for a symbol.
        
        Useful for determining when queued signals should be executed.
        
        Args:
            symbol: Trading symbol
            from_datetime: Starting datetime. If None, uses now.
            
        Returns:
            datetime of next market open in Madrid timezone
        """
        if from_datetime is None:
            from_datetime = datetime.now(self._tz)
        elif from_datetime.tzinfo is None:
            from_datetime = self._tz.localize(from_datetime)

        check_date = from_datetime.date()

        # Look up to 7 days ahead (covers weekends and most holiday periods)
        for days_ahead in range(8):
            candidate_date = check_date + timedelta(days=days_ahead)

            # Skip Saturday entirely
            if candidate_date.weekday() == 5:  # Saturday
                continue

            # Handle Sunday specially - market opens at specific time
            if candidate_date.weekday() == 6:  # Sunday
                period = self.get_current_period(candidate_date)

                if period == 'dst_gap_spring' or period == 'dst_gap_fall':
                    # Spring/Fall gap: market opens Sunday 23:00 Madrid (CT+6)
                    sunday_open = self._tz.localize(datetime.combine(candidate_date, time(23, 0)))
                    if sunday_open > from_datetime:
                        return sunday_open
                    # If we're past Sunday 23:00, market is open (handled elsewhere)
                    continue
                else:
                    # Winter and Summer: all Sunday is weekend (market opens Monday 00:00)
                    continue

            # Check for holidays
            event = self.get_event_for_date(candidate_date)
            if event and event.get('trading_status') == 'CLOSED':
                continue

            # Get trading hours for this day
            open_time, close_time = self.get_trading_hours(symbol, candidate_date)

            # If market is closed all day (both times are 00:00)
            if open_time == time(0, 0) and close_time == time(0, 0):
                continue

            close_datetime = self._tz.localize(datetime.combine(candidate_date, close_time))

            if open_time > close_time:
                # Overnight session (DST gap): session opened yesterday at open_time,
                # closes today at close_time. Also a new session opens today at open_time.
                if candidate_date == check_date:
                    # Part 1: still in yesterday's session? (before close_time today)
                    if from_datetime.time() < close_time:
                        return from_datetime  # Market is currently open

                    # Part 2: new session starting today at open_time
                    # Skip on Friday — weekly close, no new session starts
                    if candidate_date.weekday() != 4:
                        today_open = self._tz.localize(datetime.combine(candidate_date, open_time))
                        if today_open > from_datetime:
                            return today_open
                        elif from_datetime >= today_open:
                            return from_datetime  # Market is currently open
                    continue
                else:
                    # Future day — the session that covers this day started the previous evening
                    prev_day_open = self._tz.localize(datetime.combine(
                        candidate_date - timedelta(days=1), open_time))
                    if prev_day_open > from_datetime:
                        return prev_day_open
                    continue

            open_datetime = self._tz.localize(datetime.combine(candidate_date, open_time))

            # If this is today and we're past the open, check close
            if candidate_date == check_date:
                if from_datetime >= open_datetime:
                    # Market already open today - return current time or close time
                    if from_datetime < close_datetime:
                        # Market is currently open
                        return from_datetime
                    else:
                        # Market closed today, continue to next day
                        continue

            # Found a valid open time in the future
            if open_datetime > from_datetime:
                return open_datetime

        # Fallback: return tomorrow at 00:00
        tomorrow = check_date + timedelta(days=1)
        return self._tz.localize(datetime.combine(tomorrow, time(0, 0)))
    
    def is_market_open(self, symbol: str, check_datetime: Optional[datetime] = None) -> bool:
        """
        Check if the market is currently open for a symbol.
        
        This is the main method used by BarStreamer and PipelineRunner to determine
        whether to trigger staleness checks or queue signals.
        
        Includes a 2-minute pre-market buffer where market is considered "open"
        to allow order preparation before actual market open.
        
        Args:
            symbol: Trading symbol (e.g., 'MNQ', 'ES', 'MGC')
            check_datetime: Datetime to check. If None, uses now.
            
        Returns:
            True if market is open (or within pre-market buffer), False otherwise
        """
        if check_datetime is None:
            check_datetime = datetime.now(self._tz)
        elif check_datetime.tzinfo is None:
            check_datetime = self._tz.localize(check_datetime)
        
        # Check weekend first (fast path)
        if self.is_weekend(check_datetime):
            return False
        
        check_date = check_datetime.date()
        weekday = check_datetime.weekday()
        
        # SPECIAL CASE: Sunday evening after market opens
        # During DST gap periods (spring/fall), CME futures open Sunday 23:00 Madrid.
        # If we're on Sunday after 23:00 and not weekend (is_weekend returned False),
        # market is definitely open.
        if weekday == 6:  # Sunday
            period = self.get_current_period(check_date)
            if period == 'dst_gap_spring' or period == 'dst_gap_fall':
                # In spring/fall gap, market opens Sunday 23:00
                # If we got here (is_weekend returned False), we're after 23:00
                return True
            # Winter/Summer: all Sunday is weekend, so we shouldn't reach here
        
        # Check for holidays
        event = self.get_event_for_date(check_date)
        if event and event.get('trading_status') == 'CLOSED':
            return False
        
        # Get trading hours
        open_time, close_time = self.get_trading_hours(symbol, check_date)

        # If both are 00:00, market is closed all day
        if open_time == time(0, 0) and close_time == time(0, 0):
            return False

        # Apply pre-market buffer
        buffer = timedelta(minutes=self.PRE_MARKET_BUFFER_MINUTES)

        close_datetime = self._tz.localize(datetime.combine(check_date, close_time))

        if open_time > close_time:
            # Overnight session (DST gap periods): session opened YESTERDAY at open_time,
            # closes TODAY at close_time. A new session also opens TODAY at open_time.
            # e.g. open=23:00(prev day) close=22:00(today) during spring/fall DST gap

            # Part 1: Are we in the tail of yesterday's session? (midnight → close_time)
            if check_datetime.time() < close_time:
                return True

            # Part 2: Are we in the start of today's new session? (open_time → midnight)
            # Skip on Friday — weekly close, no new session starts Friday evening
            today_open = self._tz.localize(datetime.combine(check_date, open_time))
            buffered_today_open = today_open - buffer
            if weekday != 4 and check_datetime >= buffered_today_open:
                return True

            return False

        open_datetime = self._tz.localize(datetime.combine(check_date, open_time))

        # Adjust open time for buffer (market "opens" 2 minutes early for order prep)
        buffered_open = open_datetime - buffer

        # Check if current time is within trading session (with buffer)
        return buffered_open <= check_datetime < close_datetime
    
    def get_roll_window_times(self, check_date: Optional[date] = None) -> Tuple[int, int, int]:
        """
        Calculate the contract rolling window for a specific date.
        
        The roll window is set to 9-4 minutes before market close.
        This accounts for early closes on holidays.
        
        Args:
            check_date: Date to check. If None, uses today.
            
        Returns:
            Tuple of (roll_hour, roll_minute_start, roll_minute_end)
        """
        if check_date is None:
            check_date = datetime.now(self._tz).date()
        
        # Get the close time for today (use a common symbol like MNQ)
        event = self.get_event_for_date(check_date)
        
        if event:
            trading_status = event.get('trading_status', '')
            
            if trading_status == 'CLOSED':
                # Market closed - return None-equivalent (no roll window)
                return (-1, -1, -1)
            
            elif trading_status == 'EARLY_CLOSE':
                # Use early close time
                close_time_str = event.get('close_time_madrid', '23:00')
                close_parts = close_time_str.split(':')
                close_hour = int(close_parts[0])
                close_minute = int(close_parts[1]) if len(close_parts) > 1 else 0
        else:
            # Regular day - get actual close time (accounts for DST gap periods)
            _, actual_close = self.get_trading_hours('MNQ', check_date)
            close_hour = actual_close.hour
            close_minute = actual_close.minute
        
        # Calculate roll window: 9 minutes before close, 5 minute window
        # e.g., 23:00 close → roll at 22:51-22:55
        # e.g., 19:00 close → roll at 18:51-18:55
        close_in_minutes = close_hour * 60 + close_minute
        roll_start_minutes = close_in_minutes - 9
        roll_end_minutes = roll_start_minutes + 5
        
        roll_hour = roll_start_minutes // 60
        roll_minute_start = roll_start_minutes % 60
        roll_minute_end = roll_end_minutes % 60
        
        # Handle hour overflow
        if roll_minute_end < roll_minute_start:
            roll_minute_end = 60  # Will wrap to next hour
        
        return (roll_hour, roll_minute_start, roll_minute_end)
    
    def should_skip_rolling_today(self, check_date: Optional[date] = None) -> bool:
        """
        Check if contract rolling should be skipped today.
        
        Rolling is skipped on:
        - Full closure days (holidays)
        - Weekends
        
        Args:
            check_date: Date to check. If None, uses today.
            
        Returns:
            True if rolling should be skipped, False otherwise
        """
        if check_date is None:
            check_date = datetime.now(self._tz).date()
        
        # Check if it's a weekend
        weekday = check_date.weekday()
        if weekday in (5, 6):  # Saturday or Sunday
            return True
        
        # Check for full closure
        event = self.get_event_for_date(check_date)
        if event and event.get('trading_status') == 'CLOSED':
            return True
        
        return False
    
    def get_timezone(self) -> pytz.timezone:
        """Get the Madrid timezone object."""
        return self._tz
    
    def now(self) -> datetime:
        """Get current time in Madrid timezone."""
        return datetime.now(self._tz)
    
    def today(self) -> date:
        """Get current date in Madrid timezone."""
        return datetime.now(self._tz).date()
    
    def get_market_status(self, symbol: str = 'MNQ') -> dict:
        """
        Get comprehensive market status for display/logging.
        
        Returns dict with:
        - is_open: bool
        - reason: str (why closed, or 'trading')
        - next_open: datetime (if closed)
        - next_close: datetime (if open)
        
        Args:
            symbol: Symbol to check (default MNQ)
            
        Returns:
            Dict with market status information
        """
        now_dt = self.now()
        is_open = self.is_market_open(symbol, now_dt)
        
        result = {
            'is_open': is_open,
            'symbol': symbol,
            'checked_at': now_dt.strftime('%Y-%m-%d %H:%M:%S'),
            'period': self.get_current_period(now_dt.date()),
        }
        
        if is_open:
            result['reason'] = 'trading'
            result['next_close'] = self.get_close_time_today(symbol).strftime('%Y-%m-%d %H:%M')
        else:
            # Determine reason for closure
            if self.is_weekend(now_dt):
                weekday = now_dt.weekday()
                if weekday == 5:
                    result['reason'] = 'weekend_saturday'
                else:
                    result['reason'] = 'weekend_sunday'
            else:
                event = self.get_event_for_date(now_dt.date())
                if event and event.get('trading_status') == 'CLOSED':
                    result['reason'] = f"holiday_{event.get('name', 'unknown')}"
                else:
                    result['reason'] = 'outside_trading_hours'
            
            result['next_open'] = self.get_next_market_open(symbol, now_dt).strftime('%Y-%m-%d %H:%M')
        
        return result
    
    def print_market_status(self, symbol: str = 'MNQ') -> None:
        """
        Print formatted market status to console.
        
        Useful for startup banners and periodic status updates.
        
        Args:
            symbol: Symbol to check (default MNQ)
        """
        status = self.get_market_status(symbol)
        
        if status['is_open']:
            print(f"[TradingCalendar] Market OPEN ({status['symbol']})")
            print(f"[TradingCalendar] Next close: {status['next_close']} Madrid")
        else:
            reason_display = {
                'weekend_saturday': 'Weekend (Saturday)',
                'weekend_sunday': 'Weekend (Sunday - opens tonight)' if status['period'] in ('dst_gap_spring', 'dst_gap_fall') else 'Weekend (Sunday)',
                'outside_trading_hours': 'Outside trading hours',
            }
            reason = reason_display.get(status['reason'], status['reason'])
            
            print(f"[TradingCalendar] Market CLOSED ({status['symbol']})")
            print(f"[TradingCalendar] Reason: {reason}")
            print(f"[TradingCalendar] Next open: {status['next_open']} Madrid")
    
    def is_in_spring_dst_gap(self, check_date: Optional[date] = None) -> bool:
        """
        Check if the given date falls within the spring DST gap period.

        During the ~2 week spring DST gap, the US has already sprung forward
        but Spain has not. This causes markets to open 1 hour earlier in Madrid
        time (23:00 instead of 00:00), which can conflict with the Gateway
        daily restart at 23:45.

        Args:
            check_date: Date to check. If None, uses today.

        Returns:
            True if within the spring DST gap period
        """
        return self.get_current_period(check_date) == 'dst_gap_spring'

    def is_in_server_reset_window(self, check_datetime: Optional[datetime] = None) -> bool:
        """
        Check if we're in IB's daily server reset window: 05:00-07:00 UTC.

        During this window, NA+EU data farms cycle BROKEN/OK rapidly.
        Reconnection attempts during this period cause connection churn
        that can crash the Gateway process.

        DST-proof: converts current Madrid time to UTC for comparison.

        Args:
            check_datetime: Datetime to check. If None, uses now.

        Returns:
            True if within the server reset window (05:00-07:00 UTC)
        """
        if check_datetime is None:
            check_datetime = datetime.now(self._tz)
        elif check_datetime.tzinfo is None:
            check_datetime = self._tz.localize(check_datetime)

        utc_dt = check_datetime.astimezone(pytz.utc)
        return 5 <= utc_dt.hour < 7

    def is_in_client_restart_window(self, check_datetime: Optional[datetime] = None) -> bool:
        """
        Check if we're in the Gateway's daily auto-restart window: 23:45-00:10 ET.

        During this 25-minute window the Gateway process restarts itself.
        TCP probes will fail, which is expected — not a crash.

        Args:
            check_datetime: Datetime to check. If None, uses now.

        Returns:
            True if within the client restart window (23:45-00:10 US/Eastern)
        """
        if check_datetime is None:
            check_datetime = datetime.now(self._tz)
        elif check_datetime.tzinfo is None:
            check_datetime = self._tz.localize(check_datetime)

        et_tz = pytz.timezone('US/Eastern')
        et_dt = check_datetime.astimezone(et_tz)
        et_time = et_dt.time()

        # 23:45 to midnight OR midnight to 00:10
        return et_time >= time(23, 45) or et_time < time(0, 10)

    def is_in_ibc_restart_window(self, check_datetime: Optional[datetime] = None) -> bool:
        """
        Check if we're in the IBC auto-restart window: 23:40-23:55 system timezone.

        IBC's AutoRestartTime is configured in the system timezone (Europe/Madrid).
        The restart fires at 23:45 and Gateway typically needs ~60s to come back.
        We use a 23:40-23:55 window to cover startup and reconnection.

        Args:
            check_datetime: Datetime to check. If None, uses now.

        Returns:
            True if within the IBC restart window (23:40-23:55 Europe/Madrid)
        """
        if check_datetime is None:
            check_datetime = datetime.now(self._tz)
        elif check_datetime.tzinfo is None:
            check_datetime = self._tz.localize(check_datetime)

        madrid_dt = check_datetime.astimezone(self._tz)
        madrid_time = madrid_dt.time()

        return time(23, 40) <= madrid_time <= time(23, 55)

    def is_in_maintenance_window(self, check_datetime: Optional[datetime] = None) -> bool:
        """
        Check if we're in any known IB maintenance window.

        Combines server reset (05:00-07:00 UTC), client restart (23:45-00:10 ET),
        and IBC auto-restart (23:40-23:55 Europe/Madrid).
        Single method for components that don't need to distinguish.

        Args:
            check_datetime: Datetime to check. If None, uses now.

        Returns:
            True if in any maintenance window
        """
        return (self.is_in_server_reset_window(check_datetime) or
                self.is_in_client_restart_window(check_datetime) or
                self.is_in_ibc_restart_window(check_datetime))

    def get_bar_close_time(self, symbol: str, check_date: Optional[date] = None) -> datetime:
        """
        Get the actual bar close time for the last bar of the session,
        accounting for DST offset.

        During DST gap periods, the effective close time shifts by 1 hour.
        This is useful for understanding when the final bar before Gateway
        restart will close.

        Args:
            symbol: Trading symbol
            check_date: Date to check. If None, uses today.

        Returns:
            datetime of the last bar close in Madrid timezone
        """
        if check_date is None:
            check_date = datetime.now(self._tz).date()

        _, close_time_obj = self.get_trading_hours(symbol, check_date)
        return self._tz.localize(datetime.combine(check_date, close_time_obj))

    # Singleton accessor (class method)
    @classmethod
    def get_instance(cls) -> 'TradingCalendar':
        """Get the singleton instance."""
        return get_trading_calendar()


# ======================== TRADING SCHEDULE VALIDATOR ========================

class TradingScheduleValidator:
    """
    Validates if a strategy is allowed to trade at the current time.
    
    Combines two concepts:
    - Market hours (from TradingCalendar) - when the exchange is open
    - Strategy schedule (from trading_hours) - when the strategy is ALLOWED to trade
    
    A strategy can only trade when BOTH conditions are met:
    1. Market is open (TradingCalendar.is_market_open())
    2. Current time is within strategy's trading schedule (if defined)
    
    Trading Schedule Formats:
    -------------------------
    
    1. No restrictions (trade anytime market is open):
       trading_hours = None
    
    2. Simple window (same for entries and exits):
       trading_hours = {'start': '08:00', 'end': '20:00'}
    
    3. Granular control (separate schedules for entries vs exits):
       trading_hours = {
           'mode': 'granular',
           'entries': {'start': '08:00', 'end': '16:00'},
           'exits': None,  # No exit restrictions
       }
    
    4. Entry-only restrictions:
       trading_hours = {
           'mode': 'granular',
           'entries': {'start': '08:00', 'end': '20:00'},
           'exits': None,
       }
    
    5. Exit-only restrictions:
       trading_hours = {
           'mode': 'granular',
           'entries': None,
           'exits': {'start': '00:00', 'end': '22:50'},
       }
    """
    
    def __init__(self, stratOBJ, trading_calendar: Optional['TradingCalendar'] = None):
        """
        Initialize TradingScheduleValidator.
        
        Args:
            stratOBJ: StratOBJ instance for strategy data access
            trading_calendar: TradingCalendar instance (uses singleton if None)
        """
        self._stratOBJ = stratOBJ
        self._calendar = trading_calendar or get_trading_calendar()
    
    def is_entry_allowed(self, strat_code: int, check_datetime: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Check if strategy can OPEN a new position at given time.
        
        Args:
            strat_code: Strategy code
            check_datetime: Time to check (uses now if None)
            
        Returns:
            Tuple of (allowed: bool, reason: str)
            - (True, "ok") if entry is allowed
            - (False, reason) if entry is blocked with explanation
        """
        if check_datetime is None:
            check_datetime = self._calendar.now()
        elif check_datetime.tzinfo is None:
            check_datetime = self._calendar.get_timezone().localize(check_datetime)
        
        # First check: Is market open?
        symbol = self._stratOBJ.symbol(strat_code)
        if not self._calendar.is_market_open(symbol, check_datetime):
            return (False, "market_closed")
        
        # Second check: Is strategy schedule allowing entries?
        entry_schedule = self._stratOBJ.get_entry_schedule(strat_code)
        
        if entry_schedule is None:
            return (True, "ok")  # No restrictions
        
        if not self._is_within_schedule(check_datetime, entry_schedule):
            return (False, f"outside_entry_schedule ({entry_schedule['start']}-{entry_schedule['end']})")
        
        return (True, "ok")
    
    def is_exit_allowed(self, strat_code: int, check_datetime: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Check if strategy can CLOSE a position at given time.
        
        Args:
            strat_code: Strategy code
            check_datetime: Time to check (uses now if None)
            
        Returns:
            Tuple of (allowed: bool, reason: str)
            - (True, "ok") if exit is allowed
            - (False, reason) if exit is blocked with explanation
        """
        if check_datetime is None:
            check_datetime = self._calendar.now()
        elif check_datetime.tzinfo is None:
            check_datetime = self._calendar.get_timezone().localize(check_datetime)
        
        # First check: Is market open?
        symbol = self._stratOBJ.symbol(strat_code)
        if not self._calendar.is_market_open(symbol, check_datetime):
            return (False, "market_closed")
        
        # Second check: Is strategy schedule allowing exits?
        exit_schedule = self._stratOBJ.get_exit_schedule(strat_code)
        
        if exit_schedule is None:
            return (True, "ok")  # No restrictions
        
        if not self._is_within_schedule(check_datetime, exit_schedule):
            return (False, f"outside_exit_schedule ({exit_schedule['start']}-{exit_schedule['end']})")
        
        return (True, "ok")
    
    def _is_within_schedule(self, check_datetime: datetime, schedule: Dict[str, str]) -> bool:
        """
        Check if datetime falls within a schedule window.
        
        Args:
            check_datetime: Datetime to check (timezone-aware)
            schedule: Dict with 'start' and 'end' keys as 'HH:MM' strings
            
        Returns:
            True if within window, False otherwise
        """
        try:
            start_str = schedule.get('start', '00:00')
            end_str = schedule.get('end', '23:59')
            
            start_parts = start_str.split(':')
            end_parts = end_str.split(':')
            
            start_time = time(int(start_parts[0]), int(start_parts[1]) if len(start_parts) > 1 else 0)
            end_time = time(int(end_parts[0]), int(end_parts[1]) if len(end_parts) > 1 else 0)
            
            current_time = check_datetime.time()
            
            # Handle overnight windows (e.g., 22:00 - 06:00)
            if start_time <= end_time:
                return start_time <= current_time <= end_time
            else:
                # Overnight: either after start OR before end
                return current_time >= start_time or current_time <= end_time
                
        except (ValueError, TypeError, AttributeError):
            # If parsing fails, allow trading (fail-safe)
            return True


def get_trading_schedule_validator(stratOBJ, trading_calendar: Optional['TradingCalendar'] = None) -> TradingScheduleValidator:
    """
    Factory function to create TradingScheduleValidator.
    
    Args:
        stratOBJ: StratOBJ instance
        trading_calendar: TradingCalendar instance (optional)
        
    Returns:
        TradingScheduleValidator instance
    """
    return TradingScheduleValidator(stratOBJ, trading_calendar)


# ======================== EXAMPLE USAGE ========================

if __name__ == "__main__":
    # Test the TradingCalendar
    calendar = get_trading_calendar()
    
    print("\n" + "=" * 60)
    print("TRADING CALENDAR TEST")
    print("=" * 60)
    
    # Test symbol mapping
    test_symbols = ['MNQ', 'MES', 'MGC', 'CL', 'ZC', '6E', 'UNKNOWN']
    print("\n1. Symbol → Product Type Mapping:")
    for sym in test_symbols:
        print(f"   {sym} → {calendar.get_product_type(sym)}")
    
    # Test current period
    print(f"\n2. Current DST Period: {calendar.get_current_period()}")
    
    # Test weekend detection
    print(f"\n3. Is Weekend Now: {calendar.is_weekend()}")
    
    # Test event for today
    event = calendar.get_event_for_date()
    print(f"\n4. Event Today: {event.get('name') if event else 'None'}")
    
    # Test trading hours
    for sym in ['MNQ', 'MGC']:
        open_t, close_t = calendar.get_trading_hours(sym)
        print(f"\n5. Trading Hours for {sym}: {open_t.strftime('%H:%M')} - {close_t.strftime('%H:%M')}")
    
    # Test market open
    print(f"\n6. Is Market Open (MNQ): {calendar.is_market_open('MNQ')}")
    
    # Test close time
    close_dt = calendar.get_close_time_today('MNQ')
    print(f"\n7. Today's Close (MNQ): {close_dt.strftime('%Y-%m-%d %H:%M')}")
    
    # Test roll window
    roll_hour, roll_start, roll_end = calendar.get_roll_window_times()
    if roll_hour >= 0:
        print(f"\n8. Roll Window Today: {roll_hour:02d}:{roll_start:02d} - {roll_hour:02d}:{roll_end-1:02d}")
    else:
        print(f"\n8. Roll Window Today: SKIPPED (market closed)")
    
    # Test next market open
    next_open = calendar.get_next_market_open('MNQ')
    print(f"\n9. Next Market Open (MNQ): {next_open.strftime('%Y-%m-%d %H:%M')}")
    
    print("\n" + "=" * 60)
