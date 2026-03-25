# ibkr_core/strat_loader.py - extracted from _00_StratLoader.py
from __future__ import annotations

import json
import os
import importlib.util
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from datetime import datetime

from ._compat import HAS_IB, _require_ib

if HAS_IB:
    from ib_async import IB, Contract, ContractDetails, util
else:
    IB = None
    Contract = None
    ContractDetails = None
    util = None

from .trading_calendar import get_trading_calendar
from .logger import get_logger

# JSON Schema validation (optional -- graceful fallback if not installed)
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

# Load schema once at module level
_SCHEMA_PATH = Path(__file__).parent / 'schema.json'
_SCHEMA = None


def _get_schema():
    global _SCHEMA
    if _SCHEMA is None and _SCHEMA_PATH.exists():
        with open(_SCHEMA_PATH, 'r') as f:
            _SCHEMA = json.load(f)
    return _SCHEMA


@dataclass
class StrategyData:
    """Container for all the attributes found in a strategy .py file."""
    data: Dict[str, Any] = field(default_factory=dict)


class StratOBJ:
    """Load, manage & call strategies information. Prepares IB contracts on upload()."""

    def __init__(self, host: str = "127.0.0.1", port: int = 7497, client_id: int = 1):
        self.host = host
        self.port = port
        self.client_id = client_id
        self._strategies: Dict[int, StrategyData] = {}
        self._ib: Optional[IB] = None
        self._last_rolled_contracts: Dict[int, Tuple[Contract, Contract]] = {}  # Cache for skip_refresh mode

        # Thread-safe access for hot-reload
        # Uses RLock to allow nested locking within same thread
        self._lock = threading.RLock()

    # -----------------------------
    # Pickle support (for multiprocessing)
    # -----------------------------
    def __getstate__(self):
        """Drop non-serializable RLock for pickling (multiprocessing workers)."""
        state = self.__dict__.copy()
        state.pop('_lock', None)
        state.pop('_ib', None)  # IB connection is not serializable
        return state

    def __setstate__(self, state):
        """Restore RLock after unpickling."""
        self.__dict__.update(state)
        self._lock = threading.RLock()
        self._ib = None

    # -----------------------------
    # Strategy file loading helpers
    # -----------------------------
    def _load_strategy_file(self, file_path: Path) -> dict:
        """Load a strategy file. Supports .json (preferred) and .py (legacy fallback)."""
        if file_path.suffix == '.json':
            with open(file_path, 'r') as f:
                data = json.load(f)
            # Remove JSON-only keys not needed at runtime
            data.pop("$schema", None)
            return data
        elif file_path.suffix == '.py':
            spec = importlib.util.spec_from_file_location(file_path.stem, str(file_path))
            if not spec or not spec.loader:
                raise ValueError(f"Cannot load strategy file: {file_path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            data = {}
            for attr_name in dir(module):
                if attr_name.startswith("__"):
                    continue
                val = getattr(module, attr_name)
                if callable(val):
                    continue
                data[attr_name] = val
            return data
        else:
            raise ValueError(f"Unsupported strategy file format: {file_path.suffix}")

    def _validate_strategy_json(self, data: dict, file_path: Path) -> bool:
        """Validate strategy data against JSON schema. Returns True if valid."""
        schema = _get_schema()
        if not schema or not HAS_JSONSCHEMA:
            return True  # Skip validation if schema or jsonschema unavailable
        try:
            jsonschema.validate(instance=data, schema=schema)
            return True
        except jsonschema.ValidationError as e:
            get_logger().log_warning("StratLoader",
                f"Schema validation failed for {file_path.name}: {e.message}")
            return False

    # -----------------------------
    # Load strategies + connect IB + prepare contracts
    # -----------------------------
    def upload(self, strategies_folder: str = "Strategies", connect_ib: bool = True, mode: str = 'all'):
        """
        Import strategy files and optionally connect to IB to prebuild contracts.

        Args:
            strategies_folder: Path to folder containing strategy files
            connect_ib: If True, connect to IBKR to resolve contracts (required for live trading).
                       If False, skip IB connection (suitable for backtesting on historical data).
            mode: 'live' = only load active+tested+prod strategies.
                  'all'  = load every strategy regardless of flags (for backtest platform).

        Raises:
            FileNotFoundError: If strategies folder does not exist
            ValueError: If no active strategies are found
        """
        self._strategies.clear()

        # 0) Check strategies folder exists
        if not os.path.exists(strategies_folder):
            raise FileNotFoundError(
                f"[StratLoader] CRITICAL: Strategies folder not found: {strategies_folder}\n"
                f"  The trading system requires at least one strategy to operate."
            )

        # 1) Discover strategy files -- prefer .json, fall back to .py
        folder = Path(strategies_folder)
        json_files = {f.stem: f for f in sorted(folder.glob('*.json')) if f.stem.isdigit()}
        py_files = {f.stem: f for f in sorted(folder.glob('*.py')) if f.stem.isdigit()}

        # Merge: .json wins when both exist for same strategy code
        all_strategy_names = sorted(set(json_files.keys()) | set(py_files.keys()))

        loaded_files = []
        for name in all_strategy_names:
            json_path = json_files.get(name)
            py_path = py_files.get(name)

            # Try .json first
            if json_path:
                try:
                    data_dict = self._load_strategy_file(json_path)
                    # Validate .json against schema
                    if not self._validate_strategy_json(data_dict, json_path):
                        # Schema validation failed -- fall back to .py with warning
                        if py_path:
                            get_logger().log_warning("StratLoader",
                                f"Falling back to {py_path.name} after {json_path.name} validation failure")
                            data_dict = self._load_strategy_file(py_path)
                            loaded_files.append(py_path.name)
                        else:
                            get_logger().log_warning("StratLoader",
                                f"Skipping {json_path.name} -- validation failed and no .py fallback")
                            continue
                    else:
                        loaded_files.append(json_path.name)
                except Exception as e:
                    # .json load failed -- fall back to .py
                    if py_path:
                        get_logger().log_warning("StratLoader",
                            f"Failed to load {json_path.name}: {e}, falling back to {py_path.name}")
                        try:
                            data_dict = self._load_strategy_file(py_path)
                            loaded_files.append(py_path.name)
                        except Exception as e2:
                            get_logger().log_error("StratLoader",
                                f"Failed to load both {json_path.name} and {py_path.name}: {e2}")
                            continue
                    else:
                        get_logger().log_error("StratLoader",
                            f"Failed to load {json_path.name}: {e} (no .py fallback)")
                        continue
            elif py_path:
                # Only .py exists
                try:
                    data_dict = self._load_strategy_file(py_path)
                    loaded_files.append(py_path.name)
                except Exception as e:
                    get_logger().log_error("StratLoader", f"Failed to load {py_path.name}: {e}")
                    continue
            else:
                continue

            code = data_dict.get('strat_code')
            if mode == 'live':
                if not (data_dict.get('active', True) and data_dict.get('tested', False) and data_dict.get('prod', False)):
                    continue
            if code is not None:
                self._strategies[code] = StrategyData(data=data_dict)

        # 1.5) Validate at least one strategy was loaded
        if not self._strategies:
            if mode == 'live':
                raise ValueError(
                    f"[StratLoader] CRITICAL: No qualified strategies found in {strategies_folder}\n"
                    f"  Found {len(loaded_files)} strategy file(s), but none pass active+tested+prod filter.\n"
                    f"  Ensure at least one strategy has active=True, tested=True, prod=True."
                )
            else:
                raise ValueError(
                    f"[StratLoader] CRITICAL: No strategies found in {strategies_folder}\n"
                    f"  Found {len(loaded_files)} strategy file(s), but none could be loaded."
                )

        print(f"[StratLoader] Loaded {len(self._strategies)} strategy(ies) (mode={mode}): {sorted(self._strategies.keys())}")
        get_logger().log_info("STRATEGY", f"Loaded {len(self._strategies)} strategy(ies) (mode={mode}): {sorted(self._strategies.keys())}")

        # 2) Skip IB connection if not needed (e.g., backtesting mode)
        if not connect_ib:
            print(f"[StratLoader] Skipping IB connection (connect_ib=False)")
            get_logger().log_info("STRATEGY", "Skipping IB connection (connect_ib=False)")
            return self

        # 3) Connect to IB (standard settings as requested)
        _require_ib("live IB connection")
        self._ib = IB()
        self._ib.connect(self.host, self.port, clientId=self.client_id) # , timeout=20)

        # 4) Prepare contracts
        for code, sdata in self._strategies.items():
            symbol = sdata.data.get("symbol")
            secType = sdata.data.get("secType")
            exchange = sdata.data.get("exchange")
            rolling_day = sdata.data.get("rolling_days", None)

            if not symbol or not secType or not exchange:
                sdata.data["ib_contract_error"] = "Missing symbol/secType/exchange"
                continue

            try:
                contract = self._create_contract(symbol, secType, exchange, rolling_day)
                if contract:
                    sdata.data["ib_contract"] = contract
                    if contract:
                        sdata.data["conId"] = getattr(contract, "conId", None)
                        sdata.data["localSymbol"] = getattr(contract, "localSymbol", None)
                        sdata.data["tradingClass"] = getattr(contract, "tradingClass", None)
                else:
                    # Contract resolution returned None -- no matching contract found
                    sdata.data["ib_contract_error"] = "No matching contract found"
                    print(f"[StratLoader] CRITICAL: Strategy {code} ({symbol}) -- "
                          f"contract resolution returned None. Strategy will NOT be loaded.")
                    get_logger().log_error("StratLoader",
                        f"CRITICAL: Strategy {code} ({symbol}) -- "
                        f"contract resolution failed, removing from registry")
            except Exception as e:
                sdata.data["ib_contract_error"] = str(e)
                print(f"[StratLoader] CRITICAL: Strategy {code} ({symbol}) -- "
                      f"contract resolution exception: {e}. Strategy will NOT be loaded.")
                get_logger().log_error("StratLoader",
                    f"CRITICAL: Strategy {code} ({symbol}) -- "
                    f"contract exception: {e}, removing from registry")

        # Remove strategies that failed contract resolution (LOAD-02)
        failed_codes = [
            code for code, sdata in self._strategies.items()
            if "ib_contract_error" in sdata.data
        ]
        for code in failed_codes:
            del self._strategies[code]
        if failed_codes:
            print(f"[StratLoader] Removed {len(failed_codes)} strategy(ies) "
                  f"with failed contract resolution: {failed_codes}")
            get_logger().log_error("STRATEGY", f"Removed {len(failed_codes)} strategy(ies) with failed contract resolution: {failed_codes}")

        self._ib.disconnect()

        return self

    # -----------------------------
    # Internal helpers
    # -----------------------------
    def _get_strategy_data(self, code: int) -> Dict[str, Any]:
        if code not in self._strategies:
            raise ValueError("Strategy code not found. Did you run upload()?")
        return self._strategies[code].data

    def _create_contract(self, symbol: str, secType: str, exchange: str, rolling_day: int | None = None):
        """
        Return canonical IB Contract. For FUT, roll to 2nd expiry if days_to_front < rolling_day.
        Uses realExpirationDate (YYYYMMDD).
        """
        _require_ib("contract creation")
        cds: list[ContractDetails] = self._ib.reqContractDetails(
            Contract(symbol=symbol, exchange=exchange, secType=secType)
            )

        if not cds:
            return None

        if secType != 'FUT' or rolling_day is None:
            return cds[0].contract

        cds_sorted = sorted(
            cds,
            key=lambda cd: datetime.strptime(cd.realExpirationDate, "%Y%m%d").date()
        )
        front = cds_sorted[0]
        nxt = cds_sorted[1] if len(cds_sorted) > 1 else None
        if not nxt:
            return front.contract

        try:
            today = get_trading_calendar().today()
        except Exception:
            today = datetime.now().date()  # Fallback if calendar unavailable
        days_to_front = (datetime.strptime(front.realExpirationDate, "%Y%m%d").date() - today).days
        return nxt.contract if days_to_front < rolling_day else front.contract

    # -----------------------------
    # Public API
    # -----------------------------
    def strat_codes(self) -> list[int]:
        return sorted(self._strategies.keys())

    def STF_dict(self) -> Dict[str, Dict[str, list]]:
        """{'EURUSD': {'1h': [1001, 1002], '5m': [1004]}, 'SP500': {'1m': [1003]}}"""
        result: Dict[str, Dict[str, list]] = {}
        for code, sdata in self._strategies.items():
            symbol = sdata.data.get("symbol")
            timeframe = sdata.data.get("process_freq")
            if symbol and timeframe:
                result.setdefault(symbol, {}).setdefault(timeframe, []).append(code)
        for sym in result:
            for tf in result[sym]:
                result[sym][tf].sort()
        return result

    def contract_map(self) -> Dict[str, Contract]:
        """{1001: Contract(),
            1002: Contract()}"""
        result: Dict[str, Contract] = {}
        for code, sdata in self._strategies.items():
            result[code] = sdata.data.get("ib_contract")
        return result

    def trading_hours_map(self) -> Dict[str, Dict[str, str]]:
        """
        Returns trading hours for each unique symbol.

        Returns:
            Dict mapping {symbol: {'start': 'HH:MM', 'end': 'HH:MM'}}

        Example:
            {'MNQ': {'start': '00:00', 'end': '23:00'},
             'MGC': {'start': '08:00', 'end': '17:00'}}
        """
        result: Dict[str, Dict[str, str]] = {}
        for code, sdata in self._strategies.items():
            symbol = sdata.data.get("symbol")
            trading_hours = sdata.data.get("trading_hours")
            if symbol and trading_hours and symbol not in result:
                result[symbol] = trading_hours
        return result

    # -----------------------------
    # Contract Rolling
    # -----------------------------
    def refresh_contracts(self) -> Dict[int, Tuple[Contract, Contract]]:
        """
        Refresh contracts for all strategies, detecting which need rolling.

        This method:
        1. Reconnects to IB
        2. Re-evaluates _create_contract() for each strategy
        3. Compares old vs new conId to detect changes
        4. Updates _strategies dict in-place with new contracts

        Returns:
            Dict mapping {strategy_id: (old_contract, new_contract)} for strategies
            where the contract changed. Empty dict if no contracts rolled.
        """
        _require_ib("contract refresh")
        rolled_contracts: Dict[int, Tuple[Contract, Contract]] = {}

        # Connect to IB
        self._ib = IB()
        try:
            self._ib.connect(self.host, self.port, clientId=self.client_id)
        except Exception as e:
            print(f"[StratOBJ] Failed to connect for contract refresh: {e}")
            return rolled_contracts

        try:
            # Check each strategy for contract changes
            for code, sdata in self._strategies.items():
                symbol = sdata.data.get("symbol")
                secType = sdata.data.get("secType")
                exchange = sdata.data.get("exchange")
                rolling_day = sdata.data.get("rolling_days", None)

                if not symbol or not secType or not exchange:
                    continue

                # Skip non-futures or strategies without rolling_days
                if secType != 'FUT' or rolling_day is None:
                    continue

                # Get current contract
                old_contract = sdata.data.get("ib_contract")
                old_con_id = sdata.data.get("conId")

                try:
                    # Get fresh contract based on current date
                    new_contract = self._create_contract(symbol, secType, exchange, rolling_day)

                    if new_contract:
                        new_con_id = getattr(new_contract, "conId", None)

                        # Compare conIds to detect rolling
                        if old_con_id and new_con_id and old_con_id != new_con_id:
                            # Contract rolled!
                            rolled_contracts[code] = (old_contract, new_contract)

                            # Update strategy data in-place
                            sdata.data["ib_contract"] = new_contract
                            sdata.data["conId"] = new_con_id
                            sdata.data["localSymbol"] = getattr(new_contract, "localSymbol", None)
                            sdata.data["tradingClass"] = getattr(new_contract, "tradingClass", None)

                            old_local = getattr(old_contract, 'localSymbol', 'UNKNOWN') if old_contract else 'UNKNOWN'
                            new_local = getattr(new_contract, 'localSymbol', 'UNKNOWN')
                            print(f"[StratOBJ] Strategy {code} contract rolled: {old_local} -> {new_local}")

                except Exception as e:
                    print(f"[StratOBJ] Error refreshing contract for strategy {code}: {e}")
                    sdata.data["ib_contract_refresh_error"] = str(e)

        finally:
            self._ib.disconnect()

        return rolled_contracts

    async def refresh_contracts_async(self, existing_ib: Optional[IB] = None) -> Dict[int, Tuple[Contract, Contract]]:
        """
        Async version of refresh_contracts() - properly handles event loops.

        This method:
        1. Clears ib_async's cached event loop to avoid conflicts
        2. Connects asynchronously (non-blocking)
        3. Re-evaluates _create_contract_async() for each strategy
        4. Compares old vs new conId to detect changes
        5. Updates _strategies dict in-place with new contracts

        Args:
            existing_ib: Optional existing IB connection to reuse.
                        If provided, skips connection/disconnection.

        Returns:
            Dict mapping {strategy_id: (old_contract, new_contract)} for strategies
            where the contract changed. Empty dict if no contracts rolled.
        """
        _require_ib("async contract refresh")
        rolled_contracts: Dict[int, Tuple[Contract, Contract]] = {}
        own_connection = existing_ib is None

        if own_connection:
            # CRITICAL: Clear cached event loop before creating new IB instance
            # This prevents event loop conflicts when called from different async contexts
            util.getLoop.cache_clear()

            self._ib = IB()
            try:
                await self._ib.connectAsync(self.host, self.port, clientId=self.client_id)
            except Exception as e:
                print(f"[StratOBJ] Failed to connect async for contract refresh: {e}")
                return rolled_contracts
        else:
            self._ib = existing_ib

        try:
            # Check each strategy for contract changes
            for code, sdata in self._strategies.items():
                symbol = sdata.data.get("symbol")
                secType = sdata.data.get("secType")
                exchange = sdata.data.get("exchange")
                rolling_day = sdata.data.get("rolling_days", None)

                if not symbol or not secType or not exchange:
                    continue

                # Skip non-futures or strategies without rolling_days
                if secType != 'FUT' or rolling_day is None:
                    continue

                # Get current contract
                old_contract = sdata.data.get("ib_contract")
                old_con_id = sdata.data.get("conId")

                try:
                    # Get fresh contract based on current date (async version)
                    new_contract = await self._create_contract_async(symbol, secType, exchange, rolling_day)

                    if new_contract:
                        new_con_id = getattr(new_contract, "conId", None)

                        # Compare conIds to detect rolling
                        if old_con_id and new_con_id and old_con_id != new_con_id:
                            # Contract rolled!
                            rolled_contracts[code] = (old_contract, new_contract)

                            # Update strategy data in-place
                            sdata.data["ib_contract"] = new_contract
                            sdata.data["conId"] = new_con_id
                            sdata.data["localSymbol"] = getattr(new_contract, "localSymbol", None)
                            sdata.data["tradingClass"] = getattr(new_contract, "tradingClass", None)

                            old_local = getattr(old_contract, 'localSymbol', 'UNKNOWN') if old_contract else 'UNKNOWN'
                            new_local = getattr(new_contract, 'localSymbol', 'UNKNOWN')
                            print(f"[StratOBJ] Strategy {code} contract rolled: {old_local} -> {new_local}")

                except Exception as e:
                    print(f"[StratOBJ] Error refreshing contract async for strategy {code}: {e}")
                    sdata.data["ib_contract_refresh_error"] = str(e)

        finally:
            if own_connection:
                self._ib.disconnect()

        # Cache the rolled contracts for skip_refresh mode
        self._last_rolled_contracts = rolled_contracts
        return rolled_contracts

    def get_last_rolled_contracts(self) -> Dict[int, Tuple[Contract, Contract]]:
        """
        Get the contracts that were rolled in the last refresh_contracts_async() call.

        Used by ContractRoller when skip_refresh=True to avoid refreshing twice.

        Returns:
            Dict mapping {strategy_id: (old_contract, new_contract)} from last refresh
        """
        return self._last_rolled_contracts

    async def _create_contract_async(self, symbol: str, secType: str, exchange: str, rolling_day: int | None = None):
        """
        Async version of _create_contract().
        Return canonical IB Contract. For FUT, roll to 2nd expiry if days_to_front < rolling_day.
        Uses realExpirationDate (YYYYMMDD).
        """
        _require_ib("async contract creation")
        cds: list[ContractDetails] = await self._ib.reqContractDetailsAsync(
            Contract(symbol=symbol, exchange=exchange, secType=secType)
        )

        if not cds:
            return None

        if secType != 'FUT' or rolling_day is None:
            return cds[0].contract

        cds_sorted = sorted(
            cds,
            key=lambda cd: datetime.strptime(cd.realExpirationDate, "%Y%m%d").date()
        )
        front = cds_sorted[0]
        nxt = cds_sorted[1] if len(cds_sorted) > 1 else None
        if not nxt:
            return front.contract

        try:
            today = get_trading_calendar().today()
        except Exception:
            today = datetime.now().date()  # Fallback if calendar unavailable
        days_to_front = (datetime.strptime(front.realExpirationDate, "%Y%m%d").date() - today).days
        return nxt.contract if days_to_front < rolling_day else front.contract

    def get_entry_schedule(self, code: int) -> Optional[Dict[str, str]]:
        """
        Get entry trading schedule for a strategy.

        Returns the time window during which the strategy can OPEN new positions.

        Returns:
            Dict with 'start' and 'end' keys (HH:MM format), or None if no restrictions.

        Examples:
            - None -> No restrictions (trade anytime market is open)
            - {'start': '08:00', 'end': '16:00'} -> Only enter 08:00-16:00
        """
        trading_hours = self._get_strategy_data(code).get("trading_hours")

        if trading_hours is None:
            return None  # No restrictions

        # New granular format with mode='granular'
        if isinstance(trading_hours, dict) and trading_hours.get('mode') == 'granular':
            entries = trading_hours.get('entries')
            return entries  # Can be None or {'start': ..., 'end': ...}

        # Legacy format - same schedule applies to both entries and exits
        if isinstance(trading_hours, dict) and 'start' in trading_hours and 'end' in trading_hours:
            return trading_hours

        return None

    def get_exit_schedule(self, code: int) -> Optional[Dict[str, str]]:
        """
        Get exit trading schedule for a strategy.

        Returns the time window during which the strategy can CLOSE positions.

        Returns:
            Dict with 'start' and 'end' keys (HH:MM format), or None if no restrictions.

        Examples:
            - None -> No restrictions (exit anytime market is open)
            - {'start': '00:00', 'end': '22:50'} -> Only exit before 22:50
        """
        trading_hours = self._get_strategy_data(code).get("trading_hours")

        if trading_hours is None:
            return None  # No restrictions

        # New granular format with mode='granular'
        if isinstance(trading_hours, dict) and trading_hours.get('mode') == 'granular':
            exits = trading_hours.get('exits')
            return exits  # Can be None or {'start': ..., 'end': ...}

        # Legacy format - same schedule applies to both entries and exits
        if isinstance(trading_hours, dict) and 'start' in trading_hours and 'end' in trading_hours:
            return trading_hours

        return None

    # -----------------------------
    # Hot-Reload Support
    # -----------------------------
    def reload_strategy(self, code: int, file_path: str) -> bool:
        """
        Re-import a modified strategy file and update in-place.

        Thread-safe: Uses RLock for atomic dict update (<1ms hold time).
        Non-blocking for readers: They see either old or new value, both valid.

        Args:
            code: Strategy code (e.g., 1001)
            file_path: Path to the strategy file (.json or .py)

        Returns:
            True if reload succeeded, False otherwise
        """
        try:
            # Load file (outside lock - can take time)
            data_dict = self._load_strategy_file(Path(file_path))

            # Check if active
            if not data_dict.get("active", True):
                # Mark as inactive but keep in system
                with self._lock:
                    if code in self._strategies:
                        self._strategies[code].data["active"] = False
                return True

            # Preserve existing contract info if symbol didn't change
            with self._lock:
                if code in self._strategies:
                    old_data = self._strategies[code].data
                    if (data_dict.get("symbol") == old_data.get("symbol") and
                        data_dict.get("secType") == old_data.get("secType") and
                        data_dict.get("exchange") == old_data.get("exchange")):
                        # Preserve contract data
                        data_dict["ib_contract"] = old_data.get("ib_contract")
                        data_dict["conId"] = old_data.get("conId")
                        data_dict["localSymbol"] = old_data.get("localSymbol")
                        data_dict["tradingClass"] = old_data.get("tradingClass")

                # Atomic update
                self._strategies[code] = StrategyData(data=data_dict)

            print(f"[StratLoader] Strategy {code} reloaded")
            get_logger().log_info("STRATEGY", f"Strategy {code} reloaded")
            return True

        except Exception as e:
            print(f"[StratLoader] Failed to reload strategy {code}: {e}")
            get_logger().log_error("STRATEGY", f"Failed to reload strategy {code}: {e}")
            return False

    def add_strategy(self, code: int, file_path: str, resolve_contract: bool = False) -> bool:
        """
        Import a new strategy file and add to the system.

        Thread-safe: Uses RLock for atomic dict update.

        Args:
            code: Strategy code (e.g., 9999)
            file_path: Path to the strategy file (.json or .py)
            resolve_contract: If True, connect to IB to resolve contract

        Returns:
            True if add succeeded, False otherwise
        """
        try:
            # Load the file
            data_dict = self._load_strategy_file(Path(file_path))

            # Check if active
            if not data_dict.get("active", True):
                print(f"[StratLoader] Strategy {code} is not active, skipping add")
                return True

            # Resolve contract if requested
            if resolve_contract:
                contract = self._refresh_single_contract(data_dict)
                if contract:
                    data_dict["ib_contract"] = contract
                    data_dict["conId"] = getattr(contract, "conId", None)
                    data_dict["localSymbol"] = getattr(contract, "localSymbol", None)
                    data_dict["tradingClass"] = getattr(contract, "tradingClass", None)

            # Atomic add
            with self._lock:
                self._strategies[code] = StrategyData(data=data_dict)

            print(f"[StratLoader] Strategy {code} added")
            get_logger().log_info("STRATEGY", f"Strategy {code} added")
            return True

        except Exception as e:
            print(f"[StratLoader] Failed to add strategy {code}: {e}")
            get_logger().log_error("STRATEGY", f"Failed to add strategy {code}: {e}")
            return False

    def deactivate_strategy(self, code: int, preserve_for_position: bool = True) -> bool:
        """
        Mark a strategy as inactive (preserves positions).

        This is safer than removal when the strategy might have open positions.
        The strategy remains in the system but won't process new signals.

        Args:
            code: Strategy code
            preserve_for_position: If True, keep strategy data for position tracking

        Returns:
            True if deactivation succeeded, False otherwise
        """
        with self._lock:
            if code not in self._strategies:
                return False

            if preserve_for_position:
                # Mark inactive but keep in system
                self._strategies[code].data["active"] = False
                self._strategies[code].data["_deactivated_by_hot_reload"] = True
            else:
                # Remove completely
                del self._strategies[code]

        print(f"[StratLoader] Strategy {code} deactivated (preserve={preserve_for_position})")
        get_logger().log_info("STRATEGY", f"Strategy {code} deactivated (preserve={preserve_for_position})")
        return True

    def _refresh_single_contract(self, data_dict: Dict[str, Any]) -> Optional[Contract]:
        """
        Resolve IB contract for a single strategy's data.

        Creates a temporary IB connection to resolve the contract.
        For async contexts, use _refresh_single_contract_async instead.

        Args:
            data_dict: Strategy data dictionary with symbol, secType, exchange

        Returns:
            Resolved Contract or None
        """
        symbol = data_dict.get("symbol")
        sec_type = data_dict.get("secType")
        exchange = data_dict.get("exchange")
        rolling_day = data_dict.get("rolling_days")

        if not symbol or not sec_type or not exchange:
            return None

        _require_ib("single contract refresh")

        # Create temporary connection
        ib = IB()
        try:
            ib.connect(self.host, self.port, clientId=98)  # Temp client
            return self._create_contract(symbol, sec_type, exchange, rolling_day)
        except Exception as e:
            print(f"[StratLoader] Contract resolution failed: {e}")
            return None
        finally:
            try:
                ib.disconnect()
            except:
                pass

    async def _refresh_single_contract_async(
        self, data_dict: Dict[str, Any], existing_ib: Optional[IB] = None
    ) -> Optional[Contract]:
        """
        Async version of _refresh_single_contract.

        Args:
            data_dict: Strategy data dictionary
            existing_ib: Optional existing IB connection to reuse

        Returns:
            Resolved Contract or None
        """
        symbol = data_dict.get("symbol")
        sec_type = data_dict.get("secType")
        exchange = data_dict.get("exchange")
        rolling_day = data_dict.get("rolling_days")

        if not symbol or not sec_type or not exchange:
            return None

        _require_ib("async single contract refresh")
        own_connection = existing_ib is None

        if own_connection:
            util.getLoop.cache_clear()
            ib = IB()
            try:
                await ib.connectAsync(self.host, self.port, clientId=98)
            except Exception as e:
                print(f"[StratLoader] Async contract resolution failed: {e}")
                return None
        else:
            ib = existing_ib

        try:
            return await self._create_contract_async(symbol, sec_type, exchange, rolling_day)
        except Exception as e:
            print(f"[StratLoader] Contract resolution error: {e}")
            return None
        finally:
            if own_connection:
                try:
                    ib.disconnect()
                except:
                    pass

    def get_active_strategies(self) -> Dict[int, StrategyData]:
        """
        Get all active strategies (thread-safe snapshot).

        Returns:
            Dict of active strategies {code: StrategyData}
        """
        with self._lock:
            return {
                code: sdata for code, sdata in self._strategies.items()
                if sdata.data.get("active", True)
            }

    def is_strategy_active(self, code: int) -> bool:
        """Check if a strategy is active (thread-safe)."""
        with self._lock:
            if code not in self._strategies:
                return False
            return self._strategies[code].data.get("active", True)


###################################################
############### ATTRIBUTES FUNCTIONS ##############
###################################################

    def get_all_data(self, code: int) -> Dict[str, Any]:
        return self._get_strategy_data(code)

    def strat_name(self, code: int) -> Any:
        return self._get_strategy_data(code).get("strat_name")

    def rolling_days(self, code: int) -> Any:
        return self._get_strategy_data(code).get("rolling_days")

    def symbol(self, code: int) -> Any:
        return self._get_strategy_data(code).get("symbol")

    def exchange(self, code: int) -> Any:
        return self._get_strategy_data(code).get("exchange")

    def asset_type(self, code: int) -> Any:
        return self._get_strategy_data(code).get("secType")

    def multiplier(self, code: int) -> Any:
        return self._get_strategy_data(code).get("multiplier")

    def minTick(self, code: int) -> Any:
        return self._get_strategy_data(code).get("minTick")

    def contract(self, code: int):
        return self._get_strategy_data(code).get("ib_contract")

    def strategy_type(self, code: int) -> Any:
        return self._get_strategy_data(code).get("strategy_type")

    def process_freq(self, code: int) -> Any:
        return self._get_strategy_data(code).get("process_freq")

    def trading_hours(self, code: int) -> Any:
        return self._get_strategy_data(code).get("trading_hours")

    def has_trading_restrictions(self, code: int) -> bool:
        return self.get_entry_schedule(code) is not None or self.get_exit_schedule(code) is not None

    def UTC_tz(self, code: int) -> Any:
        return self._get_strategy_data(code).get("UTC_tz")

    def ind_list(self, code: int) -> Any:
        return self._get_strategy_data(code).get("ind_list")

    def long_conds(self, code: int) -> Any:
        return self._get_strategy_data(code).get("long_conds")

    def short_conds(self, code: int) -> Any:
        return self._get_strategy_data(code).get("short_conds")

    def exit_conds(self, code: int) -> Any:
        return self._get_strategy_data(code).get("exit_conds")

    def max_shift(self, code: int) -> Any:
        return self._get_strategy_data(code).get("max_shift")

    def stop_loss_init(self, code: int) -> Any:
        return self._get_strategy_data(code).get("stop_loss_init")

    def stop_loss_mgmt(self, code: int) -> Any:
        return self._get_strategy_data(code).get("stop_loss_mgmt")

    def take_profit_init(self, code: int) -> Any:
        return self._get_strategy_data(code).get("take_profit_init")

    def control_params(self, code: int) -> Any:
        return self._get_strategy_data(code).get("control_params")

    def order_params(self, code: int) -> Any:
        return self._get_strategy_data(code).get("order_params")

    def max_timePeriod(self, code: int) -> Any:
        return self._get_strategy_data(code).get("max_timePeriod")


if __name__ == '__main__':
    # client_id is optional; defaults to 1
    stratOBJ = StratOBJ().upload()

    print(type(stratOBJ))
    print(stratOBJ.strat_codes())

    stream_dict = stratOBJ.STF_dict()
    print(stream_dict)

    contract_map = stratOBJ.trading_hours_map()
    print(contract_map)

    print(stratOBJ.minTick(1002))
    # print(stratOBJ.ind_list(1002))
    # print(stratOBJ.strat_name(1002))
    print(stratOBJ.contract(1002))
    # print(stratOBJ.contract(1003))
    print(stratOBJ.minTick(1002))
