# ibkr_core/indicators.py - extracted from _04_IndicatorsManager.py
from __future__ import annotations

import importlib.util
import logging
import sys
import talib
import polars as pl
import numpy as np
from typing import Any, Callable, Dict, Optional
from types import ModuleType
from ._compat import HAS_IB, _require_ib

if HAS_IB:
    from ib_async import IB, Contract
else:
    IB = None
    Contract = None

from icecream import ic
from .logger import get_logger
from pathlib import Path


from .market_data import MarketDataManager

_custom_ind_logger = logging.getLogger(__name__ + ".custom")

# Convergence multiplier for infinite-memory indicators (EMA, RSI, MACD, ATR, ADX).
# Applied to TA-Lib's minimum lookback so these indicators receive enough data to
# fully converge. 7x covers even the tightest case (RSI Wilder smoothing) to < 0.2%
# error vs full-history computation. Has no effect on finite-memory indicators
# (SMA, BBANDS, STOCH, etc.) — extra bars are simply ignored.
CONVERGENCE_MULTIPLIER = 7

#https://github.com/TA-Lib/ta-lib-python/tree/master

class INDICATORS(object):
    """
    Devuelve un diccionario de dataframes con los indicadores procesados y agrupados por time frame.
    Si el input es un diccionario de indicadores, se procesará
    La Clase es modular y se le puede agregar cualquier indicador siguiendo la estructura común
    """

    # Retry configuration (unified for sync and async)
    # Safety-net retries for market-data gaps (weekends, holidays).
    # The warmup calculation is accurate for continuous data; retries only
    # cover the rare case where gaps reduce the effective bar count.
    MAX_INDICATOR_RETRIES = 5

    # Default directory for custom indicator modules (alongside this file)
    _DEFAULT_CUSTOM_DIR = Path(__file__).parent / "custom_indicators"

    def __init__(self, ib: IB = None, contract: Contract = None, ind_info=None,
                 marketData: Dict[str, pl.DataFrame] = None, max_shift: int = 0,
                 extended_data: int = 0, custom_indicators_dir: Optional[str] = None):
        self.ib = ib
        self.contract = contract
        self.ind_info = ind_info
        self.marketData = marketData
        self.max_shift = max_shift
        self.extended_data = extended_data

        # Custom indicator registry: name -> callable(prices, ind_args)
        self._custom_registry: Dict[str, Callable] = {}
        self._custom_dir = (
            Path(custom_indicators_dir) if custom_indicators_dir
            else self._DEFAULT_CUSTOM_DIR
        )

        """
        extended_data es una funcionalidad que sirve para pedir y procesar mñás datos de los que serñían estricamente necesarios
        Util por si en el futuro se hacen graficos extensos con los indicadores
        
        marketData: Dict[timeframe, pl.DataFrame] - Preloaded market data for backtesting.
                    If provided, MarketDataManager calls are skipped.
        """

    def get_max_time_period(self, indicators):
        """Return the minimum required warmup (in bars) for this timeframe.

        Detects chained indicators (where one uses another's output as input)
        and sums their warmup requirements so the fetched DataFrame contains
        enough history for all indicators to have valid values on the last
        (1 + max_shift) rows.
        """
        if not indicators:
            return 0

        # Map indCode -> own warmup for each indicator
        own_warmup = {}
        for ind in indicators:
            indicator_name = ind.get('indicator')
            params = ind.get('params', {})
            warmup = self._required_warmup_bars(indicator_name, params)
            ind_code = params.get('indCode', '')
            own_warmup[ind_code] = warmup

        # Compute effective warmup considering chains: if indicator B uses
        # indicator A's output as a price input, B needs A's full warmup
        # plus its own.
        effective = {}
        for ind in indicators:
            params = ind.get('params', {})
            ind_code = params.get('indCode', '')
            warmup = own_warmup[ind_code]

            # Check if any price_* param references a previous indicator's output
            max_dep_warmup = 0
            for key, value in params.items():
                if key.startswith('price_') and isinstance(value, str) and value in effective:
                    max_dep_warmup = max(max_dep_warmup, effective[value])

            effective[ind_code] = max_dep_warmup + warmup

        return max(effective.values()) if effective else 0

    @staticmethod
    def _safe_int(value, default: int | None = 0) -> int | None:
        try:
            if value is None:
                return default
            return int(value)
        except Exception:
            return default

    def _talib_lookback_bars(self, indicator_name: str, params: Dict) -> int | None:
        """Return TA-Lib's lookback bars for the given indicator + params.

        On this project we use TA-Lib via the `talib` Python package. In recent
        versions (e.g. 0.6.x), the `*_Lookback` helper functions are not
        exposed. The most reliable way to obtain lookback is:

        - `from talib import abstract`
        - `f = abstract.Function('<NAME>')`
        - `f.set_parameters(...)`
        - `f.lookback`

        Returns None when the function doesn't exist or parameters cannot be set.
        """
        if not indicator_name:
            return None

        try:
            from talib import abstract

            f = abstract.Function(indicator_name)

            # Map our strategy params to TA-Lib parameter names
            if indicator_name == 'MACD':
                f.set_parameters(
                    fastperiod=self._safe_int(params.get('timePeriod_1'), 0),
                    slowperiod=self._safe_int(params.get('timePeriod_2'), 0),
                    signalperiod=self._safe_int(params.get('signalPeriod'), 0),
                )
                return int(f.lookback)

            if indicator_name == 'STOCH':
                f.set_parameters(
                    fastk_period=self._safe_int(params.get('timePeriod_1'), 0),
                    slowk_period=self._safe_int(params.get('timePeriod_2'), 0),
                    slowk_matype=self._safe_int(params.get('periodType_1'), 0),
                    slowd_period=self._safe_int(params.get('timePeriod_3'), 0),
                    slowd_matype=self._safe_int(params.get('periodType_2'), 0),
                )
                return int(f.lookback)

            if indicator_name == 'BBANDS':
                # Your BBANDS call doesn't pass matype; default to 0.
                f.set_parameters(
                    timeperiod=self._safe_int(params.get('timePeriod_1'), 0),
                    nbdevup=float(params.get('nbdevup')),
                    nbdevdn=float(params.get('nbdevdn')),
                    matype=self._safe_int(params.get('matype', 0), 0),
                )
                return int(f.lookback)

            if indicator_name == 'ULTOSC':
                f.set_parameters(
                    timeperiod1=self._safe_int(params.get('timePeriod_1'), 0),
                    timeperiod2=self._safe_int(params.get('timePeriod_2'), 0),
                    timeperiod3=self._safe_int(params.get('timePeriod_3'), 0),
                )
                return int(f.lookback)

            if 'timePeriod_1' in params:
                f.set_parameters(timeperiod=self._safe_int(params.get('timePeriod_1'), 0))
            # Indicators like TRANGE have no timeperiod
            return int(f.lookback)
        except Exception:
            return None

        return None

    def _required_warmup_bars(self, indicator_name: str, params: Dict) -> int:
        """Minimum warmup bars needed for indicator outputs to be valid.

        - Explicit warmup: if params contains a 'warmup' key, use it directly.
        - TA-Lib indicators: use TA-Lib lookback.
        - Custom indicators: use the minimal warmup implied by the implementation.

        Always returns a non-negative integer.
        """
        # Explicit warmup override (used by custom indicators)
        explicit = (params or {}).get("warmup")
        if explicit is not None:
            return max(0, int(explicit))

        # TA-Lib first — apply convergence multiplier so infinite-memory
        # indicators (EMA, RSI, MACD, ATR, ADX) receive enough data to converge.
        lb = self._talib_lookback_bars(indicator_name, params)
        if lb is not None:
            return max(0, int(lb) * CONVERGENCE_MULTIPLIER)

        # Custom / non-TA-Lib indicators
        tp1 = self._safe_int(params.get('timePeriod_1'), 0)

        if indicator_name in {'PRICE', 'price_formula', 'TRANGE'}:
            return 0

        if indicator_name == 'DATA':
            # DATA doesn't add a column (run_ind skips attaching it) but is used
            # as a manual warmup override in strategy definitions.
            return max(0, tp1)

        if indicator_name in {'PMin', 'PMax', 'BEARS_POWER'}:
            # Uses ATR internally (infinite memory)
            return max(0, (tp1 - 1) * CONVERGENCE_MULTIPLIER)

        if indicator_name == 'KELTNER_CHANNELS':
            # EMA(tp) + ATR — both infinite memory, apply convergence multiplier
            ma_period = self._safe_int(params.get('timePeriod_1'), 0)
            atr_period = self._safe_int(params.get('timePeriod_2'), 0)
            try:
                from talib import abstract
                ema_f = abstract.Function('EMA')
                ema_f.set_parameters(timeperiod=int(ma_period or 0))
                ema_lb = int(ema_f.lookback)
            except Exception:
                ema_lb = max(0, int(ma_period or 0) - 1)
            try:
                from talib import abstract
                atr_f = abstract.Function('ATR')
                atr_f.set_parameters(timeperiod=int(atr_period or 0))
                atr_lb = int(atr_f.lookback)
            except Exception:
                atr_lb = max(0, int(atr_period or 0))
            return max(0, max(ema_lb, atr_lb) * CONVERGENCE_MULTIPLIER)

        if indicator_name == 'ULCER_INDEX':
            # MAX/MIN warmup (tp-1) then SMA warmup (tp-1) on squared moves
            return max(0, 2 * (tp1 - 1))

        if indicator_name == 'ICHIMOKU':
            tenkan = self._safe_int(params.get('timePeriod_1'), 0)
            kijun = self._safe_int(params.get('timePeriod_2'), 0)
            span_b = self._safe_int(params.get('senkou_span_b_period'), 0)
            return max(0, max(tenkan, kijun, span_b) - 1)

        # Fallback: max of any timePeriod_* params (acts as a conservative warmup)
        time_periods = [
            value
            for key, value in (params or {}).items()
            if key.startswith('timePeriod') and isinstance(value, int)
        ]
        return max(0, max(time_periods)) if time_periods else 0

    def _build_processing_order(self):
        """Determine timeframe processing order based on cross-timeframe dependencies.

        Returns a list of timeframes sorted so that dependencies are processed first.
        """
        standard_cols = {'open', 'high', 'low', 'close', 'volume', 'date'}

        # Map indCode -> source timeframe
        ind_code_tf = {}
        for tf, ind_list in self.ind_info.items():
            for ind in ind_list:
                ind_code = ind['params'].get('indCode', '')
                if ind_code:
                    ind_code_tf[ind_code] = tf

        # Build dependency graph: tf -> set of tfs it depends on
        tf_deps = {tf: set() for tf in self.ind_info}
        for tf, ind_list in self.ind_info.items():
            same_tf_codes = {ind['params'].get('indCode', '') for ind in ind_list}
            for ind in ind_list:
                for key, value in ind.get('params', {}).items():
                    if key.startswith('price_') and isinstance(value, str):
                        if value not in standard_cols and value not in same_tf_codes:
                            if value in ind_code_tf and ind_code_tf[value] != tf:
                                tf_deps[tf].add(ind_code_tf[value])

        # Topological sort (DFS) — dependencies processed first
        order = []
        visited = set()

        def visit(tf):
            if tf in visited:
                return
            visited.add(tf)
            for dep in tf_deps.get(tf, set()):
                visit(dep)
            order.append(tf)

        for tf in self.ind_info:
            visit(tf)

        return order

    def _join_cross_tf_columns(self, data, tf, processed):
        """Join indicator columns from already-processed timeframes via asof join.

        Args:
            data: current timeframe's DataFrame
            tf: current timeframe key
            processed: dict of already-processed timeframe DataFrames

        Returns DataFrame with cross-timeframe columns joined.
        """
        standard_cols = {'open', 'high', 'low', 'close', 'volume', 'date'}
        ind_list = self.ind_info[tf]
        same_tf_codes = {ind['params'].get('indCode', '') for ind in ind_list}

        # Collect needed columns grouped by source timeframe
        needed = {}
        for ind in ind_list:
            for key, value in ind.get('params', {}).items():
                if key.startswith('price_') and isinstance(value, str):
                    if value not in standard_cols and value not in same_tf_codes and value not in data.columns:
                        for src_tf, src_data in processed.items():
                            if src_tf != tf and value in src_data.columns:
                                needed.setdefault(src_tf, set()).add(value)
                                break

        for src_tf, cols in needed.items():
            src_data = processed[src_tf]
            src_subset = src_data.select(['date'] + sorted(cols))
            data = data.join_asof(src_subset, on='date', strategy='backward')

        return data

    @staticmethod
    def _tf_to_minutes(tf_str):
        """Convert a timeframe string to approximate minutes per bar."""
        import re
        tf = tf_str.strip().lower()
        m = re.match(r'(\d+)\s*([a-z]+)', tf)
        if not m:
            return 60
        n, unit = int(m.group(1)), m.group(2)
        if unit.startswith('min') or unit == 'm':
            return n
        if unit.startswith('hour') or unit == 'h':
            return n * 60
        if unit.startswith('day') or unit == 'd':
            return n * 1440
        return 60

    def _cross_tf_extra_warmup(self):
        """Extra warmup bars each source timeframe needs for cross-tf consumers.

        When a target timeframe references a source timeframe's indicator,
        the source must fetch enough extra bars so the joined column has
        valid values across the target's full data window.
        """
        standard_cols = {'open', 'high', 'low', 'close', 'volume', 'date'}

        ind_code_tf = {}
        for tf, ind_list in self.ind_info.items():
            for ind in ind_list:
                ind_code = ind['params'].get('indCode', '')
                if ind_code:
                    ind_code_tf[ind_code] = tf

        extra = {}
        tail_len = 1 + int(self.max_shift)

        for tf, ind_list in self.ind_info.items():
            same_tf_codes = {ind['params'].get('indCode', '') for ind in ind_list}
            target_max = self.get_max_time_period(ind_list)

            for ind in ind_list:
                for key, value in ind.get('params', {}).items():
                    if key.startswith('price_') and isinstance(value, str):
                        if value not in standard_cols and value not in same_tf_codes:
                            if value in ind_code_tf and ind_code_tf[value] != tf:
                                src_tf = ind_code_tf[value]
                                src_min = self._tf_to_minutes(src_tf)
                                tgt_min = self._tf_to_minutes(tf)
                                ratio = max(1, tgt_min / src_min)
                                needed = int((target_max + int(self.extended_data) + tail_len) * ratio)
                                extra[src_tf] = max(extra.get(src_tf, 0), needed)

        return extra

    # ------------------------------------------------------------------
    # Custom indicator loading
    # ------------------------------------------------------------------

    def _load_custom_indicators(self) -> None:
        """Scan ind_info for entries with a 'custom' key and load their modules."""
        for tf, ind_list in self.ind_info.items():
            for ind_def in ind_list:
                custom = ind_def.get("custom")
                if not custom:
                    continue
                name = ind_def["indicator"]
                if name in self._custom_registry or hasattr(self, name):
                    continue  # Already loaded or shadows a built-in
                module_path = custom.get("module")
                function_name = custom.get("function", "calculate")
                if not module_path:
                    _custom_ind_logger.warning(
                        "Custom indicator '%s' missing 'module' in definition, skipping.", name)
                    continue
                try:
                    func = self._load_custom_module(name, module_path, function_name)
                    self._custom_registry[name] = func
                    _custom_ind_logger.info("Loaded custom indicator '%s' from %s:%s",
                                            name, module_path, function_name)
                except Exception:
                    _custom_ind_logger.error(
                        "Failed to load custom indicator '%s' from %s",
                        name, module_path, exc_info=True)

    def _load_custom_module(self, name: str, module_path: str,
                            function_name: str) -> Callable:
        """Import a custom indicator module and return the callable."""
        resolved = self._resolve_custom_path(module_path)
        if not resolved.is_file():
            raise FileNotFoundError(f"Custom indicator module not found: {resolved}")

        module_name = f"_custom_ind_{name}"
        spec = importlib.util.spec_from_file_location(module_name, resolved)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for {resolved}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            sys.modules.pop(module_name, None)
            raise ImportError(f"Failed to execute {resolved}: {exc}") from exc

        func = getattr(module, function_name, None)
        if func is None or not callable(func):
            sys.modules.pop(module_name, None)
            raise AttributeError(
                f"Module {resolved} has no callable '{function_name}'")
        return func

    def _resolve_custom_path(self, module_path: str) -> Path:
        """Resolve a module path relative to the custom indicators directory.

        Rejects absolute paths and paths that escape the directory.
        """
        path = Path(module_path)
        if path.is_absolute():
            raise ValueError(
                f"Absolute paths are not allowed for custom indicators: {path}")
        resolved = (self._custom_dir / path).resolve()
        # Path containment check
        try:
            resolved.relative_to(self._custom_dir.resolve())
        except ValueError:
            raise ValueError(
                f"Custom indicator path '{module_path}' resolves outside "
                f"the allowed directory ({self._custom_dir})")
        return resolved

    def call_ind(self, indicator, ind_params, prices):
        """
        Dispatch indicator computation.

        Priority: built-in method -> custom registry -> error.
        """
        if hasattr(self, indicator):
            indicator_method = getattr(self, indicator)
            indicator_method(ind_params, prices)
            return self.ind
        elif indicator in self._custom_registry:
            func = self._custom_registry[indicator]
            self.ind = func(prices, ind_params)
            return self.ind
        else:
            print(f'Indicator {indicator} not implemented.')
            get_logger().log_error("STRATEGY", f"Indicator {indicator} not implemented")

    def run_data(self):
        """
        Funcion to execute indicators if market data is provided
        """
        # Load any custom indicators referenced in ind_info
        if self.ind_info and not self._custom_registry:
            self._load_custom_indicators()

        market = {}
        # Clone each DataFrame to avoid modifying original
        for tf, df in self.marketData.items():
            market[tf] = df.clone()

        processing_order = self._build_processing_order()

        for tf in processing_order:
            ind_list = self.ind_info[tf]
            data = market[tf]

            # Join cross-timeframe indicator columns
            data = self._join_cross_tf_columns(data, tf, market)

            for ind in ind_list:
                indicator = ind['indicator']
                ind_params = ind['params']
                ind_data = self.call_ind(indicator, ind_params, data)

                if type(ind_data) == np.ndarray:
                    data = data.with_columns(pl.Series(ind_params['indCode'], ind_data))
                elif type(ind_data) == dict:
                    for c_name, c_data in ind_data.items():
                        data = data.with_columns(pl.Series(c_name, c_data))
                market[tf] = data

        return market

    def _tail_is_valid(self, data):
        """Return True if the last (1 + max_shift) rows have no NaN / null."""
        tail = data.tail(1 + self.max_shift)
        for col in tail.columns:
            series = tail[col]
            if series.null_count() > 0:
                return False
            if series.dtype in [pl.Float32, pl.Float64] and series.is_nan().any():
                return False
        return True

###################################################
################## SYNC FUNCTIONS #################
###################################################

    def get_data(self, timeFrame, timePeriod):
        """
        Obtención de datos de mercado
        """
        warmup = 0 if timePeriod is None else int(timePeriod)
        tail_len = 1 + int(self.max_shift)
        realPeriod = warmup + int(self.extended_data) + tail_len
        data =  MarketDataManager(self.ib, self.contract).latestBars_number(timeframe=timeFrame, num_bars=realPeriod)
        return data

    def run_ind(self):
        """
        Ejecuta indicadores obteniendo datos de mercado vía API.

        Warmup is pre-computed accurately (chained + cross-tf).  The retry
        loop is a lightweight safety net for market-data gaps only.
        """
        result = {}
        processing_order = self._build_processing_order()
        cross_tf_extra = self._cross_tf_extra_warmup()

        for tf in processing_order:
            ind_list = self.ind_info[tf]
            max_time = self.get_max_time_period(ind_list) + cross_tf_extra.get(tf, 0)

            for attempt in range(self.MAX_INDICATOR_RETRIES):
                data = self.get_data(timeFrame=tf, timePeriod=max_time)

                # Join cross-timeframe indicator columns
                data = self._join_cross_tf_columns(data, tf, result)

                for ind in ind_list:
                    indicator = ind['indicator']
                    ind_params = ind['params']
                    ind_data = self.call_ind(indicator, ind_params, data)

                    if ind_params['indCode'].startswith('DATA'):
                        pass
                    elif isinstance(ind_data, np.ndarray):
                        data = data.with_columns(pl.Series(ind_params['indCode'], ind_data))
                    elif isinstance(ind_data, dict):
                        for c_name, c_data in ind_data.items():
                            data = data.with_columns(pl.Series(c_name, c_data))

                if self._tail_is_valid(data):
                    result[tf] = data
                    break

                max_time += 1
            else:
                print(f"[INDICATORS] Warning: Max retries ({self.MAX_INDICATOR_RETRIES}) "
                      f"exceeded for timeframe '{tf}'. Some NaN may persist.")
                result[tf] = data

        return result

  
    def run(self):
        if self.marketData is None:
            result = self.run_ind()
            return result
        else:
            result = self.run_data()
            return result

###################################################
################# ASYNC FUNCTIONS #################
###################################################

    async def get_data_async(self, timeFrame, timePeriod):
        warmup = 0 if timePeriod is None else int(timePeriod)
        tail_len = 1 + int(self.max_shift)
        realPeriod = warmup + tail_len + int(self.extended_data)
        return await MarketDataManager(self.ib, self.contract).async_latestBars_number(
            timeframe=timeFrame, num_bars=realPeriod
        )

    async def run_ind_async(self):
        """
        Async version of run_ind(): awaits data fetches.

        Warmup is pre-computed accurately (chained + cross-tf).  The retry
        loop is a lightweight safety net for market-data gaps only.
        """
        result = {}
        processing_order = self._build_processing_order()
        cross_tf_extra = self._cross_tf_extra_warmup()

        for tf in processing_order:
            ind_list = self.ind_info[tf]
            max_time = self.get_max_time_period(ind_list) + cross_tf_extra.get(tf, 0)

            for attempt in range(self.MAX_INDICATOR_RETRIES):
                data = await self.get_data_async(timeFrame=tf, timePeriod=max_time)

                # Join cross-timeframe indicator columns
                data = self._join_cross_tf_columns(data, tf, result)

                for ind in ind_list:
                    indicator = ind['indicator']
                    ind_params = ind['params']
                    ind_data = self.call_ind(indicator, ind_params, data)

                    if ind_params['indCode'].startswith('DATA'):
                        pass
                    elif isinstance(ind_data, np.ndarray):
                        data = data.with_columns(pl.Series(ind_params['indCode'], ind_data))
                    elif isinstance(ind_data, dict):
                        for c_name, c_data in ind_data.items():
                            data = data.with_columns(pl.Series(c_name, c_data))

                if self._tail_is_valid(data):
                    result[tf] = data
                    break

                max_time += 1
            else:
                print(f"[INDICATORS] Warning: Max retries ({self.MAX_INDICATOR_RETRIES}) "
                      f"exceeded for timeframe '{tf}'. Some NaN may persist.")
                result[tf] = data
        return result

    async def run_async(self):
        return await self.run_ind_async()

###################################################
################ TALIB INDICATORS #################
###################################################

    def DATA(self,ind_args, prices):
        args = ['timePeriod_1']
        args_list = list(ind_args.keys())

        if not args == args_list[:-1]:
            print('WRONG ARGS for DATA')

        timePeriod_1 = ind_args['timePeriod_1']
        self.ind = np.zeros(timePeriod_1)

    def PRICE(self,ind_args, prices):
        # real = RSI(close, timeperiod=14)
        args = ['price_1', 'timePeriod_1']
        args_list = list(ind_args.keys())

        if not args == args_list[:-1]:
            print('WRONG ARGS for PRICE')

        price_1 = prices[ind_args['price_1']].to_numpy()
        self.ind = price_1

    def RSI(self,ind_args, prices):
        # real = RSI(close, timeperiod=14)
        args = ['price_1', 'timePeriod_1']
        args_list = list(ind_args.keys())

        if not args == args_list[:-1]:
            print('WRONG ARGS for RSI')

        price_1 = prices[ind_args['price_1']].to_numpy()
        timePeriod_1 = ind_args['timePeriod_1']
        self.ind = talib.RSI(price_1, timeperiod=timePeriod_1)

    def SMA(self,ind_args, prices):
        # real = SMA(close, timeperiod=30)
        args = ['price_1', 'timePeriod_1']
        args_list = list(ind_args.keys())

        if not args == args_list[:-1]:
            print('WRONG ARGS for SMA')

        price_1 = prices[ind_args['price_1']].to_numpy()
        timePeriod_1 = ind_args['timePeriod_1']
        self.ind = talib.SMA(price_1, timeperiod=timePeriod_1)

    def WILLR(self,ind_args, prices):
        # real = WILLR(high, low, close, timeperiod=14)
        args = ['price_1','price_2','price_3','timePeriod_1']
        args_list = list(ind_args.keys())

        if not args == args_list[:-1]:
            print('WRONG ARGS for WILLR')

        price_1 = prices[ind_args['price_1']].to_numpy()
        price_2 = prices[ind_args['price_2']].to_numpy()
        price_3 = prices[ind_args['price_3']].to_numpy()
        timePeriod_1 = ind_args['timePeriod_1']
        self.ind = talib.WILLR(price_1, price_2, price_3, timeperiod=timePeriod_1)

    def MACD(self,ind_args, prices):
        # macd, macdsignal, macdhist = MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
        args = ['price_1','timePeriod_1','timePeriod_2','signalPeriod']
        args_list = list(ind_args.keys())

        if not args == args_list[:-1]:
            print('WRONG ARGS for MACD')

        if ind_args['indCode'].startswith('MULT'):
            added_code = ind_args['indCode'].split('_')[-1]

        price_1 = prices[ind_args['price_1']].to_numpy()
        fastperiod = ind_args['timePeriod_1']
        slowperiod = ind_args['timePeriod_2']
        signalperiod = ind_args['signalPeriod']
        macd, macdsignal, macdhist = talib.MACD(price_1, fastperiod, slowperiod, signalperiod)
        self.ind = {f'macd_{added_code}':macd, f'macdsignal_{added_code}':macdsignal, f'macdhist_{added_code}':macdhist}

    def STOCH(self,ind_args, prices):
        # slowk, slowd = STOCH(high, low, close, fastk_period=5, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
        args = ['price_1','price_2','price_3','timePeriod_1','timePeriod_2','periodType_1','timePeriod_3','periodType_2']
        args_list = list(ind_args.keys())

        if not args == args_list[:-1]:
            print('WRONG ARGS for STOCH')

        if ind_args['indCode'].startswith('MULT'):
            added_code = ind_args['indCode'].split('_')[-1]

        price_1 = prices[ind_args['price_1']].to_numpy()
        price_2 = prices[ind_args['price_2']].to_numpy()
        price_3 = prices[ind_args['price_3']].to_numpy()
        fastk_period = ind_args['timePeriod_1']
        slowk_period = ind_args['timePeriod_2']
        slowk_matype = ind_args['periodType_1']
        slowd_period = ind_args['timePeriod_3']
        slowd_matype = ind_args['periodType_2']
        slowk, slowd = talib.STOCH(price_1, price_2, price_3, fastk_period, slowk_period, slowk_matype, slowd_period, slowd_matype)
        self.ind = {f'stoch_slowk_{added_code}':slowk, f'stoch_slowd_{added_code}':slowd}

    def BBANDS(self,ind_args, prices):
        # upperband, middleband, lowerband = BBANDS(close, timeperiod=5, nbdevup=2, nbdevdn=2, matype=0)
        args = ['price_1','timePeriod_1','nbdevup','nbdevdn']
        args_list = list(ind_args.keys())

        if not args == args_list[:-1]:
            print('WRONG ARGS for BBANDS')

        if ind_args['indCode'].startswith('MULT'):
            added_code = ind_args['indCode'].split('_')[-1]

        price_1 = prices[ind_args['price_1']].to_numpy()
        timePeriod_1 = ind_args['timePeriod_1']
        nbdevup = ind_args['nbdevup']
        nbdevdn = ind_args['nbdevdn']
        upperband, middleband, lowerband = talib.BBANDS(price_1, timePeriod_1, nbdevup, nbdevdn)
        self.ind = {f'BBAND_upperband_{added_code}':upperband, f'BBAND_middleband_{added_code}':middleband, f'BBAND_lowerband_{added_code}':lowerband}
    

    def ATR(self,ind_args, prices):
        # real = ATR(high, low, close, timeperiod=14)
        args = ['price_1','price_2','price_3','timePeriod_1']
        args_list = list(ind_args.keys())

        if not args == args_list[:-1]:
            print('WRONG ARGS for ATR')

        price_1 = prices[ind_args['price_1']].to_numpy()
        price_2 = prices[ind_args['price_2']].to_numpy()
        price_3 = prices[ind_args['price_3']].to_numpy()
        timePeriod_1 = ind_args['timePeriod_1']
        self.ind = talib.ATR(price_1, price_2, price_3, timeperiod=timePeriod_1)

    def NATR(self,ind_args, prices):
        # real = NATR(high, low, close, timeperiod=14)
        args = ['price_1','price_2','price_3','timePeriod_1']
        args_list = list(ind_args.keys())

        if not args == args_list[:-1]:
            print('WRONG ARGS for NATR')

        price_1 = prices[ind_args['price_1']].to_numpy()
        price_2 = prices[ind_args['price_2']].to_numpy()
        price_3 = prices[ind_args['price_3']].to_numpy()
        timePeriod_1 = ind_args['timePeriod_1']
        self.ind = talib.NATR(price_1, price_2, price_3, timeperiod=timePeriod_1)

    def TRANGE(self,ind_args, prices):
        # real = NATR(high, low, close)
        args = ['price_1','price_2','price_3']
        args_list = list(ind_args.keys())

        if not args == args_list[:-1]:
            print('WRONG ARGS for TRANGE')

        price_1 = prices[ind_args['price_1']].to_numpy()
        price_2 = prices[ind_args['price_2']].to_numpy()
        price_3 = prices[ind_args['price_3']].to_numpy()
        self.ind = talib.TRANGE(price_1, price_2, price_3)

    def ADX(self,ind_args, prices):
        # real = ADX(high, low, close, timeperiod=14)
        args = ['price_1','price_2','price_3','timePeriod_1']
        args_list = list(ind_args.keys())

        if not args == args_list[:-1]:
            print('WRONG ARGS for ADX')

        price_1 = prices[ind_args['price_1']].to_numpy()
        price_2 = prices[ind_args['price_2']].to_numpy()
        price_3 = prices[ind_args['price_3']].to_numpy()
        timePeriod_1 = ind_args['timePeriod_1']
        self.ind = talib.ADX(price_1, price_2, price_3, timePeriod_1)

    def PLUS_DI(self,ind_args, prices):
        # real = PLUS_DI(high, low, close, timeperiod=14)
        args = ['price_1','price_2','price_3','timePeriod_1']
        args_list = list(ind_args.keys())

        if not args == args_list[:-1]:
            print('WRONG ARGS for PLUS_DI')

        price_1 = prices[ind_args['price_1']].to_numpy()
        price_2 = prices[ind_args['price_2']].to_numpy()
        price_3 = prices[ind_args['price_3']].to_numpy()
        timePeriod_1 = ind_args['timePeriod_1']
        self.ind = talib.PLUS_DI(price_1, price_2, price_3, timeperiod=timePeriod_1)


    def ULTOSC(self,ind_args, prices):
        # real = ULTOSC(high, low, close, timeperiod1=7, timeperiod2=14, timeperiod3=28)
        args = ['price_1','price_2','price_3','timePeriod_1','timePeriod_2','timePeriod_3']
        args_list = list(ind_args.keys())

        if not args == args_list[:-1]:
            print('WRONG ARGS for ULTOSC')

        price_1 = prices[ind_args['price_1']].to_numpy()
        price_2 = prices[ind_args['price_2']].to_numpy()
        price_3 = prices[ind_args['price_3']].to_numpy()
        timePeriod_1 = ind_args['timePeriod_1']
        timePeriod_2 = ind_args['timePeriod_2']
        timePeriod_3 = ind_args['timePeriod_3']
        self.ind = talib.ULTOSC(price_1, price_2, price_3, timeperiod1=timePeriod_1, timeperiod2=timePeriod_2, timeperiod3=timePeriod_3)

    def MINUS_DI(self, ind_args, prices):
        # ['price_1','price_2','price_3','timePeriod_1']
        args = ['price_1', 'price_2', 'price_3', 'timePeriod_1']
        args_list = list(ind_args.keys())
        if not args == args_list[:-1]:

            print('WRONG ARGS for MINUS_DI')

        high       = prices[ind_args['price_1']].to_numpy()
        low        = prices[ind_args['price_2']].to_numpy()
        close      = prices[ind_args['price_3']].to_numpy()
        timePeriod = ind_args['timePeriod_1']

        self.ind = talib.MINUS_DI(high, low, close, timeperiod=timePeriod)

    def CCI(self, ind_args, prices):
        # ['price_1','price_2','price_3','timePeriod_1']
        args = ['price_1', 'price_2', 'price_3', 'timePeriod_1']
        args_list = list(ind_args.keys())

        if not args == args_list[:-1]:
            print('WRONG ARGS for CCI')

        high        = prices[ind_args['price_1']].to_numpy()
        low         = prices[ind_args['price_2']].to_numpy()
        close       = prices[ind_args['price_3']].to_numpy()
        timePeriod  = ind_args['timePeriod_1']

        self.ind = talib.CCI(high, low, close, timeperiod=timePeriod)

###################################################
################# OWN INDICATORS ##################
###################################################

    def price_formula(self,ind_args, prices):
        args = ['formula', 'timePeriod_1']
        args_list = list(ind_args.keys())
        if not args == args_list[:-1]:
            print('WRONG ARGS for price_formula')

        open = prices['open'].to_numpy()
        high = prices['high'].to_numpy()
        low = prices['low'].to_numpy()
        close = prices['close'].to_numpy()
        result = eval(ind_args['formula'])

        if np.any(result == 0.0):
            self.ind = np.where(result == 0.0, 0.001, result)
        else:
            self.ind = result

    def PMin(self, ind_args, prices):
        if list(ind_args.keys())[:-1] != ['price_1', 'timePeriod_1']:
            print('WRONG ARGS for PMin')

        price_1 = prices[ind_args['price_1']].to_numpy()
        timePeriod_1 = ind_args['timePeriod_1']
        n = len(price_1)

        result = np.full(n, np.nan)
        if n >= timePeriod_1:
            shape = (n - timePeriod_1 + 1, timePeriod_1)
            strides = (price_1.strides[0], price_1.strides[0])
            rolling_view = np.lib.stride_tricks.as_strided(price_1, shape=shape, strides=strides)
            rolling_min = np.min(rolling_view, axis=1)
            result[timePeriod_1 - 1:] = rolling_min

        self.ind = result

    def PMax(self, ind_args, prices):
        if list(ind_args.keys())[:-1] != ['price_1', 'timePeriod_1']:
            print('WRONG ARGS for PMax')

        price_1 = prices[ind_args['price_1']].to_numpy()
        timePeriod_1 = ind_args['timePeriod_1']
        n = len(price_1)

        result = np.full(n, np.nan)
        if n >= timePeriod_1:
            shape = (n - timePeriod_1 + 1, timePeriod_1)
            strides = (price_1.strides[0], price_1.strides[0])
            rolling_view = np.lib.stride_tricks.as_strided(price_1, shape=shape, strides=strides)
            rolling_min = np.max(rolling_view, axis=1)
            result[timePeriod_1 - 1:] = rolling_min

        self.ind = result


    def ICHIMOKU(self, ind_args, prices):
        price_1 = prices[ind_args['price_1']].to_numpy()
        price_2 = prices[ind_args['price_2']].to_numpy()
        price_3 = prices[ind_args['price_3']].to_numpy()
        tenkan_period = ind_args['timePeriod_1']
        kijun_period = ind_args['timePeriod_2']
        senkou_span_b_period = ind_args['senkou_span_b_period']
        senkou_span_a_shift = ind_args['senkou_span_a_shift']
        senkou_span_b_shift = ind_args['senkou_span_b_shift']
        chikou_span_shift = ind_args['chikou_span_shift']

        if ind_args['indCode'].startswith('MULT'):
            added_code = ind_args['indCode'].split('_')[-1]

        # Tenkan-sen (Conversion Line)
        tenkan_sen = (talib.MAX(price_1, timeperiod=tenkan_period) + talib.MIN(price_2, timeperiod=tenkan_period)) / 2
        tenkan_sen = pl.Series(tenkan_sen) 

        # Kijun-sen (Base Line)
        kijun_sen = (talib.MAX(price_1, timeperiod=kijun_period) + talib.MIN(price_2, timeperiod=kijun_period)) / 2
        kijun_sen = pl.Series(kijun_sen) 

        # Senkou Span A (Leading Span A)
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(senkou_span_a_shift)

        # Senkou Span B (Leading Span B)
        senkou_span_b = ((talib.MAX(price_1, timeperiod=senkou_span_b_period) + talib.MIN(price_2, timeperiod=senkou_span_b_period)) / 2)
        senkou_span_b = pl.Series(senkou_span_b).shift(senkou_span_b_shift)

        # Chikou Span (Lagging Span)
        chikou_span = pl.Series(price_3).shift(-chikou_span_shift)
        chikou_span.ffill(inplace=True)
        
        self.ind = {f'tenkan_sen_{added_code}':tenkan_sen, f'kijun_sen_{added_code}':kijun_sen, f'senkou_span_a_{added_code}':senkou_span_a,
                     f'senkou_span_b_{added_code}':senkou_span_b, f'chikou_span_{added_code}':chikou_span}

    def KELTNER_CHANNELS(self, ind_args, prices):
        high = prices[ind_args['price_1']].to_numpy()
        low = prices[ind_args['price_2']].to_numpy()
        close = prices[ind_args['price_3']].to_numpy()

        ma_period   = ind_args['timePeriod_1']      # EMA length
        atr_period  = ind_args['timePeriod_2']      # ATR length
        multiplier  = ind_args['multiplier']        # band width

        if ind_args['indCode'].startswith('MULT'):
            added_code = ind_args['indCode'].split('_')[-1]


        tp = (high + low + close) / 3

        # Middle line: EMA of typical price
        middle_band = talib.EMA(tp, timeperiod=ma_period)

        # ATR for band calculation
        atr = talib.ATR(high, low, close, timeperiod=atr_period)

        # Upper / Lower bands
        upper_band = middle_band + multiplier * atr
        lower_band = middle_band - multiplier * atr

        # wrap into Polars Series
        middle_band = pl.Series(middle_band)
        upper_band  = pl.Series(upper_band)
        lower_band  = pl.Series(lower_band)

        # store results
        self.ind = {
            f'KC_middle_band_{added_code}': middle_band,
            f'KC_upper_band_{added_code}' : upper_band,
            f'KC_lower_band_{added_code}' : lower_band
            }


    def ULCER_INDEX(self, ind_args, prices):
        # ['price_1','timePeriod_1','risk']
        args     = ['price_1', 'timePeriod_1', 'risk']
        args_list = list(ind_args.keys())
        if not args == args_list[:-1]:
            print('WRONG ARGS for ULCER_INDEX')

        price_1      = prices[ind_args['price_1']].to_numpy()
        timePeriod_1 = ind_args['timePeriod_1']
        risk         = ind_args['risk']   # 'UP' or 'DOWN'

        # drawdown (DOWN) or run-up (UP)
        if risk == 'DOWN':
            rolling_extreme = talib.MAX(price_1, timeperiod=timePeriod_1)
        elif risk == 'UP':
            rolling_extreme = talib.MIN(price_1, timeperiod=timePeriod_1)
        else:
            print(f"Invalid risk parameter: {risk}")
            self.ind = np.full(len(price_1), np.nan)
            return

        # Safe division: avoid divide-by-zero warnings
        # When rolling_extreme is 0, set pct_move to 0 (no meaningful percentage change)
        # Use np.divide with where/out to prevent numpy from evaluating the division at invalid positions
        pct_move = np.zeros_like(price_1)
        mask = rolling_extreme != 0
        np.divide(price_1 - rolling_extreme, rolling_extreme, out=pct_move, where=mask)
        pct_move *= 100.0

        sq_moves = pct_move ** 2
        avg_sq   = talib.SMA(sq_moves, timeperiod=timePeriod_1)
        ulcer    = np.sqrt(avg_sq)

        self.ind = ulcer


    def BEARS_POWER(self, ind_args, prices):
        # ['price_1','timePeriod_1']
        args      = ['price_1', 'timePeriod_1']
        args_list = list(ind_args.keys())
        if not args == args_list[:-1]:
            print('WRONG ARGS for BEARS_POWER')

        low         = prices[ind_args['price_1']].to_numpy()
        timePeriod  = ind_args['timePeriod_1']

        close = prices['close'].to_numpy()
        ema_close = talib.EMA(close, timeperiod=timePeriod)

        bears = low - ema_close # BearsPower = low - EMA(close)

        self.ind = bears

    def SUPERTREND(self, ind_args, prices):
        """
        SuperTrend indicator - trend-following based on ATR
        params: price_1 (high), price_2 (low), price_3 (close),
                timePeriod_1 (ATR period), multiplier
        """
        args = ['price_1', 'price_2', 'price_3', 'timePeriod_1', 'multiplier']
        args_list = list(ind_args.keys())
        if not args == args_list[:-1]:
            print('WRONG ARGS for SUPERTREND')

        high = prices[ind_args['price_1']].to_numpy()
        low = prices[ind_args['price_2']].to_numpy()
        close = prices[ind_args['price_3']].to_numpy()
        atr_period = ind_args['timePeriod_1']
        multiplier = ind_args['multiplier']

        # Calculate ATR
        atr = talib.ATR(high, low, close, timeperiod=atr_period)

        # Basic bands (HL2 +/- multiplier * ATR)
        hl2 = (high + low) / 2
        basic_upper = hl2 + multiplier * atr
        basic_lower = hl2 - multiplier * atr

        n = len(close)
        supertrend = np.full(n, np.nan)
        direction = np.zeros(n)  # 1 = uptrend, -1 = downtrend

        final_upper = np.copy(basic_upper)
        final_lower = np.copy(basic_lower)

        # Find first valid index (where ATR is not NaN)
        first_valid = atr_period
        for i in range(n):
            if not np.isnan(atr[i]):
                first_valid = i
                break

        # Initialize first valid values
        if first_valid < n:
            # Initial direction: uptrend if close is above hl2, else downtrend
            direction[first_valid] = 1 if close[first_valid] > hl2[first_valid] else -1
            supertrend[first_valid] = final_lower[first_valid] if direction[first_valid] == 1 else final_upper[first_valid]

        for i in range(first_valid + 1, n):
            # Skip if ATR is NaN
            if np.isnan(atr[i]) or np.isnan(atr[i-1]):
                continue

            # Final upper band
            if basic_upper[i] < final_upper[i-1] or close[i-1] > final_upper[i-1]:
                final_upper[i] = basic_upper[i]
            else:
                final_upper[i] = final_upper[i-1]

            # Final lower band
            if basic_lower[i] > final_lower[i-1] or close[i-1] < final_lower[i-1]:
                final_lower[i] = basic_lower[i]
            else:
                final_lower[i] = final_lower[i-1]

            # SuperTrend direction
            if direction[i-1] == 1:  # was uptrend
                if close[i] < final_lower[i]:
                    direction[i] = -1
                    supertrend[i] = final_upper[i]
                else:
                    direction[i] = 1
                    supertrend[i] = final_lower[i]
            else:  # was downtrend
                if close[i] > final_upper[i]:
                    direction[i] = 1
                    supertrend[i] = final_lower[i]
                else:
                    direction[i] = -1
                    supertrend[i] = final_upper[i]

        self.ind = supertrend

    def SRPERCENTRANK(self, ind_args, prices):
        """
        Support/Resistance Percent Rank - ranks current price vs recent range
        params: price_1 (close), timePeriod_1 (lookback)
        Returns value 0-100 representing where price sits in recent range
        """
        args = ['price_1', 'timePeriod_1']
        args_list = list(ind_args.keys())
        if not args == args_list[:-1]:
            print('WRONG ARGS for SRPERCENTRANK')

        close = prices[ind_args['price_1']].to_numpy()
        high = prices['high'].to_numpy()
        low = prices['low'].to_numpy()
        lookback = ind_args['timePeriod_1']

        n = len(close)
        result = np.full(n, np.nan)

        for i in range(lookback, n):
            window_high = np.max(high[i-lookback:i])
            window_low = np.min(low[i-lookback:i])
            range_size = window_high - window_low

            if range_size > 0:
                result[i] = ((close[i] - window_low) / range_size) * 100
            else:
                result[i] = 50.0

        self.ind = result






ind_list_7 = {'1D': [
                    {'indicator': 'RSI', 'params': {'price_1': 'close', 'timePeriod_1': 10, 'indCode': 'RSI_10'}},
                    {'indicator': 'MACD', 'params': {'price_1': 'close', 'timePeriod_1':3, 'timePeriod_2':10, 'signalPeriod':9, 'indCode': 'MULT_1D'}},
                    ], 
              '1h': [
                    {'indicator': 'RSI', 'params': {'price_1': 'close', 'timePeriod_1': 14, 'indCode': 'RSI_14'}},
                    {'indicator': 'SMA', 'params': {'price_1': 'close', 'timePeriod_1': 5, 'indCode': 'SMA_20'}},
                    ]
            }

ind_list_8 = {'1D': [
                    {'indicator': 'SMA', 'params': {'price_1': 'close', 'timePeriod_1': 200, 'indCode': 'SMA_200'}},
                    {'indicator': 'SMA', 'params': {'price_1': 'close', 'timePeriod_1': 30, 'indCode': 'SMA_30'}},
                    {'indicator': 'SMA', 'params': {'price_1': 'close', 'timePeriod_1': 2, 'indCode': 'SMA_2'}},
                    {'indicator': 'RSI', 'params': {'price_1': 'close', 'timePeriod_1': 2, 'indCode': 'RSI_2'}},
                    {'indicator': 'RSI', 'params': {'price_1': 'close', 'timePeriod_1': 14, 'indCode': 'RSI_14'}},
                    ], 
              '1h': [
                    {'indicator': 'WILLR', 'params': {'price_1': 'high', 'price_2': 'low', 'price_3': 'close', 'timePeriod_1': 14, 'indCode': 'WILLR'}},
                    {'indicator': 'ATR', 'params': {'price_1': 'high', 'price_2': 'low', 'price_3': 'close', 'timePeriod_1': 14, 'indCode': 'ATR'}},
                    {'indicator': 'NATR', 'params': {'price_1': 'high', 'price_2': 'low', 'price_3': 'close', 'timePeriod_1': 14, 'indCode': 'NATR'}},
                    {'indicator': 'TRANGE', 'params': {'price_1': 'high', 'price_2': 'low', 'price_3': 'close', 'indCode': 'TRANGE'}},
                    {'indicator': 'BBANDS', 'params': {'price_1': 'close', 'timePeriod_1': 5, 'nbdevup': 2,'nbdevdn': 2, 'indCode': 'MULT_1h'}}
                    ]
            }

ind_list_9 = {'5m': [
                    {'indicator': 'RSI', 'params': {'price_1': 'close', 'timePeriod_1': 10, 'indCode': 'RSI_10_5m'}},
                    {'indicator': 'RSI', 'params': {'price_1': 'close', 'timePeriod_1': 9, 'indCode': 'RSI_9_5m'}},
                    {'indicator': 'MACD', 'params': {'price_1': 'close', 'timePeriod_1':3, 'timePeriod_2':10, 'signalPeriod':9, 'indCode': 'MULT_5m'}},
                    {'indicator': 'SMA', 'params': {'price_1': 'close', 'timePeriod_1': 10, 'indCode': 'SMA_30_5m'}},
                    {'indicator': 'ATR', 'params': {'price_1': 'high', 'price_2': 'low', 'price_3': 'close', 'timePeriod_1': 14, 'indCode': 'ATR_14_5m'}},
                    {'indicator': 'STOCH', 'params': {'price_1': 'high','price_2': 'low','price_3': 'close','timePeriod_1':5,'timePeriod_2':3,'periodType_1':0,'timePeriod_3':3,'periodType_2':0, 'indCode': 'MULT_5m'}},
                    ],
            }

ind_list_10 = {'1 hour': [
                          {'indicator': 'RSI', 'params': {'price_1': 'close', 'timePeriod_1': 14, 'indCode': 'RSI_14_1h'}},
                          {'indicator': 'RSI_SQ', 'params': {'price_1': 'close', 'timePeriod_1': 14, 'indCode': 'RSI_SQ_14_1h'}},
                          ]}

ind_list_17 = {'1 hour': [
                          {'indicator': 'ATR', 'params': {'price_1': 'high', 'price_2': 'low', 'price_3': 'close', 'timePeriod_1': 14, 'indCode': 'ATR_14_1h'}},
                          {'indicator': 'ATR_SQ', 'params': {'price_1': 'high', 'price_2': 'low', 'price_3': 'close', 'timePeriod_1': 14, 'indCode': 'ATR_SQ_14_1h'}},
                          ]}

ind_list_11 = {'1 hour':[{'indicator': 'ATR', 'params': {'price_1': 'high', 'price_2': 'low', 'price_3': 'close', 'timePeriod_1': 20, 'indCode': 'ATR_20_1h'}}]}

ind_list_12 = {'1 hour':[{'indicator': 'price_min_return', 'params': {'price_1': 'close', 'timePeriod_1': 7, 'indCode': 'min_7_1h'}},
                     {'indicator': 'price_max_return', 'params': {'price_1': 'close', 'timePeriod_1': 7, 'indCode': 'max_7_1h'}},
                     {'indicator': 'PLUS_DI', 'params': {'price_1': 'high', 'price_2': 'low', 'price_3': 'close', 'timePeriod_1': 84, 'indCode': 'PLUS_DI_84_1h'}},
                     {'indicator': 'price_formula', 'params': {'formula': '(close-low)/(high-low)', 'indCode': 'formula_1h'}},
                     {'indicator': 'KELTNER_CHANNELS', 'params': {'price_1': 'high', 'price_2': 'low', 'price_3': 'close', 'timePeriod_1': 37, 'timePeriod_2': 37, 'multiplier': 2.5,'indCode': 'MULT_1h'}},
                     {'indicator': 'ULCER_INDEX', 'params': {'price_1': 'close', 'timePeriod_1': 7, 'risk':'DOWN', 'indCode': 'ULCER_D_7_1h'}},
                     {'indicator': 'ULCER_INDEX', 'params': {'price_1': 'close', 'timePeriod_1': 7, 'risk':'UP', 'indCode': 'ULCER_U_7_1h'}},
                     ]}

ind_list_13 = {'4h':[{'indicator': 'ULCER_INDEX', 'params': {'price_1': 'close', 'timePeriod_1': 169, 'risk':'DOWN', 'indCode': 'ULCER_D_7_1h'}},
                     {'indicator': 'ULCER_INDEX', 'params': {'price_1': 'close', 'timePeriod_1': 169, 'risk':'UP', 'indCode': 'ULCER_U_7_1h'}},
                     ]}


ind_list_14 = {'1 hour':[{'indicator': 'SMA', 'params': {'price_1': 'high', 'timePeriod_1': 100, 'indCode': 'SMA_1h'}},
                         {'indicator': 'SMA', 'params': {'price_1': 'SMA_1h', 'timePeriod_1': 20, 'indCode': 'SMA_SMA_20_1h'}}
                         ],
               '4 hours':[{'indicator': 'SMA', 'params': {'price_1': 'high', 'timePeriod_1': 30, 'indCode': 'SMA_4h'}}],
               '2 hours':[{'indicator': 'SMA', 'params': {'price_1': 'high', 'timePeriod_1': 60, 'indCode': 'SMA_2h'}}],
               '8 hours':[{'indicator': 'SMA', 'params': {'price_1': 'high', 'timePeriod_1': 30, 'indCode': 'SMA_8h'}}]}

ind_list_15 = {'1 hour':[{'indicator': 'MACD', 'params': {'price_1': 'close', 'timePeriod_1':3, 'timePeriod_2':10, 'signalPeriod':9, 'indCode': 'MULT_5m'}}]}

ind_list_16 = {'1 day':[{'indicator': 'PRICE', 'params': {'price_1': 'low', 'timePeriod_1': 10, 'indCode': 'Low_1d'}}],
               '1 hour':[{'indicator': 'ADX', 'params': {'price_1': 'high', 'price_2': 'low', 'price_3': 'close', 'timePeriod_1': 20, 'indCode': 'ADX_20_1h'}}]}

ind_list_17 = { '4 hours': [{'indicator': 'KELTNER_CHANNELS', 'params': {'price_1': 'high', 'price_2': 'low', 'price_3': 'close', 'timePeriod_1': 37, 'timePeriod_2': 37, 'multiplier': 2.5,'indCode': 'MULT_4h'}},
                            {'indicator': 'ATR', 'params': {'price_1': 'high', 'price_2': 'low', 'price_3': 'close', 'timePeriod_1': 20, 'indCode': 'ATR_20_4h'}}], 
                '1 day':   [{'indicator': 'price_formula', 'params': {'formula': '(close-low)/(high-low)', 'timePeriod_1': 1, 'indCode': 'formula_1D'}},], 
                }


ind_list_18 = {'1 hour':[{'indicator': 'SMA', 'params': {'price_1': 'high', 'timePeriod_1': 100, 'indCode': 'SMA_1h'}},
                         {'indicator': 'SMA', 'params': {'price_1': 'SMA_1h', 'timePeriod_1': 20, 'indCode': 'SMA_SMA_20_1h'}}
                         ]}

ind_list_19 = {'1 min': [{'indicator': 'RSI', 'params': {'price_1': 'close', 'timePeriod_1': 30, 'indCode': 'RSI_30_1m'}},
                      {'indicator': 'SMA', 'params': {'price_1': 'RSI_30_1m', 'timePeriod_1': 7, 'indCode': 'SMA_7_1m'}},
                       ],
            }

# Test both: same-timeframe chaining + cross-timeframe chaining
ind_list_20 = {
    # 1) Source: compute SMA on 1-hour high prices
    '1 hour': [{'indicator': 'SMA', 'params': {'price_1': 'high', 'timePeriod_1': 50, 'indCode': 'SMA_50_1h'}},
               # Same-TF chain: SMA of the SMA
               {'indicator': 'SMA', 'params': {'price_1': 'SMA_50_1h', 'timePeriod_1': 20, 'indCode': 'SMA_SMA_20_1h'}}],
    # 2) Cross-TF chain: use the 1-hour SMA as input on 4-hour bars
    '4 hours': [{'indicator': 'SMA', 'params': {'price_1': 'SMA_50_1h', 'timePeriod_1': 10, 'indCode': 'SMA_XTF_4h'}}],
}

if __name__ == "__main__":

    pl.Config.set_tbl_cols(-1)
    pl.Config.set_tbl_rows(-1)

    inds = ind_list_20

    ib = IB()
    ib.connect('127.0.0.1', 7497, clientId=1)

    contract = Contract(
        secType='FUT', conId=750150193, symbol='MNQ',
        lastTradeDateOrContractMonth='20260320', multiplier='2',
        exchange='CME', currency='USD', localSymbol='MNQH6', tradingClass='MNQ'
    )

    ind_dict = INDICATORS(ib=ib, contract=contract, ind_info=inds, max_shift=1, extended_data=0).run()
    print(ind_dict)











