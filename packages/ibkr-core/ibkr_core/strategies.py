# ibkr_core/strategies.py - extracted from _05_StrategiesManager_3.py
from __future__ import annotations

import os
import shutil
import csv
from ._compat import HAS_DB, HAS_IB, _require_db, _require_ib

if HAS_IB:
    from ib_async import IB
else:
    IB = None

from icecream import ic
import polars as pl
import time
import math
from datetime import datetime, timedelta

from .indicators import INDICATORS
from .logger import get_logger

if HAS_DB:
    from _10_DatabaseManager import TradingDatabaseManager as db
else:
    db = None



class STRATEGIES():
    """
    Esta clase procesa las condicioens de las estrategias
    La clase es modular, se pueden añadir otros tipos de condiciones siguiendo la estructura común
    """
    ### INPUT:
    #           strategies_to_process: lista de las estrategias a procesar
    #           entries / exits: True para solamente procesar entradas (estrategias inectivas) o salidas (estrategias activas), sino se procesa todo
    #           extended_dada: int por si se quiere más datos de los necesarios para procesar los indicadores
    #           direct_import: True para importar los datos de las estrategias a procesar de sus archivos, False para procesar otros datos de strategies_data
    ### OUTPUT:
    #           data_dict: datos (velas, indicadores y condiciones)
    #           summary_dict: señal que se genera con cada condicion
    #           strategies_signals: señal de entrada/salida de cada estrategia procesada

    # Safe comparison operators (replaces eval() for security)
    _OPERATORS = {
        '>': lambda a, b: a > b,
        '<': lambda a, b: a < b,
        '>=': lambda a, b: a >= b,
        '<=': lambda a, b: a <= b,
        '==': lambda a, b: a == b,
        '!=': lambda a, b: a != b,
    }

    def __init__(self, ib, stratsOBJ, strats_to_process: list=[], strategies_folder: str ='Strategies', entries: bool =False, exits: bool =False, all: bool =True,
                 extended_data: int =0, logging: bool =False):

        self.ib = ib
        self.stratsOBJ = stratsOBJ

        self.strats_to_process = strats_to_process
        self.strategies_folder = strategies_folder
        self.entries = entries
        self.exits = exits
        self.all = all

        self.extended_data = extended_data
        self.logging = logging

        # Context used for warning prints (set by process/process_async/STRATEGY_BACKTEST)
        self._current_strategy_id = None


    # Print-throttling across instances (important for backtests where STRATEGY_BACKTEST
    # is instantiated per bar)
    _WARNED_NOT_EVALUABLE = set()


###################################################
############### INTERNAL UTILITIES ################
###################################################

    @staticmethod
    def _is_nan(value) -> bool:
        return isinstance(value, float) and math.isnan(value)

    def _safe_compare(self, left: float, op: str, right: float) -> bool:
        """
        Safe comparison of two float values using an operator string.

        Replaces eval() for security - only allows known comparison operators.

        Args:
            left: Left operand (float)
            op: Operator string ('>', '<', '>=', '<=', '==', '!=')
            right: Right operand (float)

        Returns:
            Boolean result of the comparison

        Raises:
            ValueError: If operator is not in the allowed set
        """
        if op not in self._OPERATORS:
            raise ValueError(f"Invalid operator: {op}")
        return self._OPERATORS[op](left, right)

    def _warn_not_evaluable(self, cond_dict) -> None:
        """Raise a visible flag (once) when a condition cannot be evaluated.

        This is intentionally throttled to avoid spamming prints during backtests.
        """
        try:
            strat_id = self._current_strategy_id
            cond_code = (cond_dict or {}).get('condCode')
            cond_type = (cond_dict or {}).get('cond_type')
            if strat_id is None or cond_code is None:
                return

            key = (int(strat_id), str(cond_code))
            if key in STRATEGIES._WARNED_NOT_EVALUABLE:
                return
            STRATEGIES._WARNED_NOT_EVALUABLE.add(key)

            print(
                f"[WARN] Strategy {int(strat_id)}: condition {cond_code} ({cond_type}) not evaluable "
                f"(missing/NaN/null/out-of-range)."
            )
            get_logger().log_warning("STRATEGY", f"Strategy {int(strat_id)}: condition {cond_code} ({cond_type}) not evaluable (missing/NaN/null/out-of-range)")
        except Exception:
            # Never let warning prints break processing
            return

    def _safe_scalar(self, df: pl.DataFrame, col: str, idx: int):
        """Return a scalar value from df[col][idx] or None.

        Silent and robust:
        - Missing column -> None
        - Out-of-range index -> None
        - Null / NaN -> None
        - 0.0 is valid (NOT treated as missing)
        """
        try:
            if df is None or df.is_empty() or col not in df.columns:
                return None

            height = df.height
            if height <= 0:
                return None

            if idx >= height or idx < -height:
                return None

            value = df[col][idx]
            if value is None or self._is_nan(value):
                return None
            return value
        except Exception:
            return None

    @staticmethod
    def _cond_extra_bars(cond_type: str) -> int:
        """Extra bars required beyond shift for conditions that read prior rows."""
        if cond_type in {
            'cross_ind_relation',
            'cross_num_relation',
            'cross_price_relation',
        }:
            return 1
        if cond_type == 'ind_direction':
            return 2
        return 0

    def _required_tail_len(self, conds_info) -> int:
        """Compute required tail length (bars) so condition evaluation never reads unvalidated rows."""
        if not conds_info:
            return 1

        required = 1
        for c in conds_info:
            try:
                s1 = int(c.get('shift_1', 0) or 0)
            except Exception:
                s1 = 0
            try:
                s2 = int(c.get('shift_2', 0) or 0)
            except Exception:
                s2 = 0

            max_shift = max(s1, s2)
            extra = self._cond_extra_bars(str(c.get('cond_type', '') or ''))
            required = max(required, 1 + max_shift + extra)

        return required

    def _effective_max_shift_for_run(self, base_max_shift: int, *conds_lists) -> int:
        """Compute an effective max_shift that includes cross/direction lookback needs."""
        all_conds = []
        for clist in conds_lists:
            if clist:
                all_conds.extend(clist)
        required_tail_len = self._required_tail_len(all_conds)
        required_shift = max(0, required_tail_len - 1)
        return max(int(base_max_shift or 0), int(required_shift))


###################################################
############### MAIN SYNC FUNCTION ################
###################################################

    def process(self):

        data_dict = {}
        strategies_dict = {}
        summary_dict = {}

        long_df = pl.DataFrame()
        short_df = pl.DataFrame()
        exit_df = pl.DataFrame()

        if not self.strats_to_process:
            self.strats_to_process = self.stratsOBJ.strat_codes()

        # Loop para procesar cada estrategia
        for strategy in self.strats_to_process:

            # Set context for warning prints
            self._current_strategy_id = strategy

            # Extracción de la información de la estrategia
            contract = self.stratsOBJ.contract(strategy)
            ind_list = self.stratsOBJ.ind_list(strategy)
            max_shift_data = self.stratsOBJ.max_shift(strategy)
            max_shift = max_shift_data[0]

            # Always initialize to avoid referencing undefined variables
            long_conds = []
            short_conds = []
            exit_conds = []

            if self.entries:
                long_conds = self.stratsOBJ.long_conds(strategy)
                short_conds = self.stratsOBJ.short_conds(strategy)

            elif self.exits:
                exit_conds = self.stratsOBJ.exit_conds(strategy)

            elif self.all:
                long_conds = self.stratsOBJ.long_conds(strategy)
                short_conds = self.stratsOBJ.short_conds(strategy)
                exit_conds = self.stratsOBJ.exit_conds(strategy)

            # Some condition types (cross_*, ind_direction) read further back than (1 + max_shift).
            # Compute an effective max_shift so indicators/data include and validate enough tail rows.
            effective_max_shift = self._effective_max_shift_for_run(
                max_shift,
                long_conds,
                short_conds,
                exit_conds,
            )

            # Obtención de los indicadores de la estrategia
            strat_dict = INDICATORS(
                ib=self.ib,
                contract=contract,
                ind_info=ind_list,
                max_shift=effective_max_shift,
                extended_data=self.extended_data,
            ).run()

            # Solo se procesan las condiciones asociados a entradas, salidas o ambos 
            if self.entries:
                long_df  = self.call_conditions(strat_dict, long_conds)
                short_df = self.call_conditions(strat_dict, short_conds)

            elif self.exits:
                exit_df  = self.call_conditions(strat_dict, exit_conds)

            elif self.all:
                long_df  = self.call_conditions(strat_dict, long_conds)
                short_df = self.call_conditions(strat_dict, short_conds)
                exit_df  = self.call_conditions(strat_dict, exit_conds)

            # Porcesamiento de las condiciones para generar una señal de la estrategia
            signal_strat, summary = self.process_conditions(long_df, short_df, exit_df)

            # Se añaden los resultados de las estrategias a los outputs
            data_dict[strategy] = strat_dict
            summary_dict[strategy] = summary
            strategies_dict[strategy] = signal_strat

        # get ref_price
        df = data_dict[next(iter(data_dict))][ next(iter(next(iter(data_dict.values())))) ]
        ref_price = df["open"].tail(1)[0]

        if self.logging:
            self.log_process_outputs(data_dict, summary_dict, strategies_dict)
            
        return data_dict, summary_dict, strategies_dict, ref_price

###################################################
############### MAIN ASYNC FUNCTION ###############
###################################################

    async def process_async(self):
        data_dict = {}
        strategies_dict = {}
        summary_dict = {}

        long_df = pl.DataFrame()
        short_df = pl.DataFrame()
        exit_df = pl.DataFrame()

        if not self.strats_to_process:
            self.strats_to_process = self.stratsOBJ.strat_codes()

        for strategy in self.strats_to_process:
            self._current_strategy_id = strategy
            contract = self.stratsOBJ.contract(strategy)
            ind_list = self.stratsOBJ.ind_list(strategy)
            max_shift_data = self.stratsOBJ.max_shift(strategy)
            max_shift = max_shift_data[0]

            long_conds = []
            short_conds = []
            exit_conds = []

            if self.entries:
                long_conds  = self.stratsOBJ.long_conds(strategy)
                short_conds = self.stratsOBJ.short_conds(strategy)
            elif self.exits:
                exit_conds  = self.stratsOBJ.exit_conds(strategy)
            else:
                long_conds  = self.stratsOBJ.long_conds(strategy)
                short_conds = self.stratsOBJ.short_conds(strategy)
                exit_conds  = self.stratsOBJ.exit_conds(strategy)

            effective_max_shift = self._effective_max_shift_for_run(
                max_shift,
                long_conds,
                short_conds,
                exit_conds,
            )

            # async indicators/data fetch
            strat_dict = await INDICATORS(
                ib=self.ib,
                contract=contract,
                ind_info=ind_list,
                max_shift=effective_max_shift,
                extended_data=self.extended_data,
            ).run_async()

            if self.entries:
                long_df  = self.call_conditions(strat_dict, long_conds)
                short_df = self.call_conditions(strat_dict, short_conds)
            elif self.exits:
                exit_df  = self.call_conditions(strat_dict, exit_conds)
            else:
                long_df  = self.call_conditions(strat_dict, long_conds)
                short_df = self.call_conditions(strat_dict, short_conds)
                exit_df  = self.call_conditions(strat_dict, exit_conds)

            signal_strat, summary = self.process_conditions(long_df, short_df, exit_df)
            data_dict[strategy] = strat_dict
            summary_dict[strategy] = summary
            strategies_dict[strategy] = signal_strat

        # get ref_price
        df = data_dict[next(iter(data_dict))][ next(iter(next(iter(data_dict.values())))) ]
        ref_price = df["open"].tail(1)[0]

        if self.logging:
            self.log_process_outputs(data_dict, summary_dict, strategies_dict)

        return data_dict, summary_dict, strategies_dict, ref_price


###################################################
################ PROCESS FUNCTIONS ################
###################################################

    def call_conditions(self, data_dict, conds_info):
        """
        Función para llamar a los métodos de las condiciones de la estrategia.
        Soporta cond_result con o sin 'expression', 'past_expression' y 'current_expression'.
        """

        if not conds_info:
            return pl.DataFrame()
        
        SCHEMA = {
            "condCode": pl.Utf8,
            "cond_type": pl.Utf8,
            "cond": pl.Utf8,
            # Exit logic extensions (backward compatible):
            # - group: AND within a group, OR across groups
            # - mode: 'force' exits immediately if True
            "group": pl.Int64,
            "mode": pl.Utf8,
            "expression": pl.Utf8,
            "past_expression": pl.Utf8,
            "current_expression": pl.Utf8,
            "shift_1": pl.Int64,
            "shift_2": pl.Int64,
            "result": pl.Boolean,
        }
        expected_columns = list(SCHEMA.keys())

        conditions = pl.DataFrame(schema=SCHEMA)

        for cond_dict in conds_info:
            ctype = cond_dict.get("cond_type")
            if hasattr(self, ctype):
                cond_method = getattr(self, ctype)
                try:
                    cond_result = cond_method(cond_dict, data_dict)
                except Exception as e:
                    group_val = cond_dict.get("group")
                    try:
                        group_val = int(group_val) if group_val is not None else None
                    except Exception:
                        group_val = None

                    row = {
                        "condCode": cond_dict.get("condCode"),
                        "cond_type": ctype,
                        "cond": cond_dict.get("cond"),
                        "group": group_val,
                        "mode": str(cond_dict.get("mode")) if cond_dict.get("mode") is not None else "normal",
                        "expression": None,
                        "past_expression": None,
                        "current_expression": None,
                        "shift_1": cond_dict.get("shift_1"),
                        "shift_2": cond_dict.get("shift_2"),
                        "result": False, 
                    }
                    cond_df = pl.from_dicts([row], schema=SCHEMA)
                    conditions = pl.concat([conditions, cond_df])
                    continue

                # Ensure optional exit-logic keys exist even if the condition method didn't touch them
                if "group" not in cond_result:
                    cond_result["group"] = cond_dict.get("group")
                if "mode" not in cond_result:
                    cond_result["mode"] = cond_dict.get("mode", "normal")

                row = {col: cond_result.get(col, None) for col in expected_columns}


                if row["shift_1"] is not None:
                    row["shift_1"] = int(row["shift_1"])
                if row["shift_2"] is not None:
                    row["shift_2"] = int(row["shift_2"])
                if row["result"] is not None:
                    row["result"] = bool(row["result"])

                if row["group"] is not None:
                    row["group"] = int(row["group"])
                if row["mode"] is not None:
                    row["mode"] = str(row["mode"])
                else:
                    row["mode"] = "normal"

                cond_df = pl.from_dicts([row], schema=SCHEMA)
                conditions = pl.concat([conditions, cond_df])
            else:
                print(f'Condition {cond_dict} not implemented.')
                get_logger().log_error("STRATEGY", f"Condition {cond_dict} not implemented")

        return conditions

    def process_conditions(self, long_conds, short_conds, exit_conds):
        """
        Función que comprueba si las condiciones de la estrategia han generado una señal
        """
        conds_list = [long_conds, short_conds, exit_conds]
        non_empty_conds = [df for df in conds_list if not df.is_empty()]
        summary = pl.concat(non_empty_conds) if non_empty_conds else pl.DataFrame()

        signal_dict = {'long': False, 'short': False, 'exit': False}

        signal_dict['long'] = not long_conds.is_empty() and long_conds["result"].all()
        signal_dict['short'] = not short_conds.is_empty() and short_conds["result"].all()

        # Exit logic:
        # - If any exit condition has mode == 'force' and is True -> exit
        # - Else: AND within a group, OR across groups
        # - Conditions without 'group' are treated as singleton groups (legacy OR behavior)
        if exit_conds.is_empty():
            signal_dict['exit'] = False
        else:
            df = exit_conds
            if "mode" not in df.columns:
                df = df.with_columns(pl.lit("normal").alias("mode"))
            if "group" not in df.columns:
                df = df.with_columns(pl.lit(None).cast(pl.Int64).alias("group"))

            force_triggered = (
                df.filter((pl.col("mode") == "force") & (pl.col("result") == True)).height > 0
            )

            if force_triggered:
                signal_dict['exit'] = True
            else:
                df = df.with_columns(
                    pl.when(pl.col("group").is_null())
                    .then(pl.col("condCode"))
                    .otherwise(pl.col("group").cast(pl.Utf8))
                    .alias("group_id")
                )

                group_eval = df.group_by("group_id").agg(
                    pl.col("result").all().alias("group_true")
                )

                signal_dict['exit'] = bool(group_eval["group_true"].any()) if group_eval.height > 0 else False

        return signal_dict, summary


###################################################
################ CONDITION TYPES ##################
###################################################
        
    """
    Métodos para los tipos de condiciones (o relaciones) de las estrategias
    """
    def num_bars(self, cond_dict, data_dict):
        """
        Condición de salida de posición por número de barras activas
        """
        result = False
        strat = None
        if cond_dict['condCode'].split('_')[0] == 'exit':
            exit_bars = int(cond_dict['cond'])
            strat_val = cond_dict.get('strat')
            if strat_val is None:
                # Fallback to current strategy context if 'strat' not provided
                strat = self._current_strategy_id
            else:
                strat = int(strat_val)

            dbm = db.get_instance()
            if dbm.is_active(strat):
                active_bars = dbm.get_active_bars_from_strategy(strategy_id=strat)
                if not active_bars == None:
                    if active_bars >= exit_bars:
                        result = True

        cond_dict['shift_1'] = 0
        cond_dict['shift_2'] = 0
        if strat is not None:
            cond_dict['strat'] = strat
        cond_dict['result'] = result

        return cond_dict
    
    def ind_relation(self, cond_dict, data_dict):
        """
        Condición de entrada o salida por el valor de dos indicadores 
        """
        result = False
        ind_1_value = None
        ind_2_value = None

        ind_1, operator, ind_2 = cond_dict['cond'].split()
        shift_1 = -int(cond_dict.get('shift_1', 0) or 0) - 1
        shift_2 = -int(cond_dict.get('shift_2', 0) or 0) - 1

        for _, df in data_dict.items():
            if ind_1_value is None:
                ind_1_value = self._safe_scalar(df, ind_1, shift_1)
            if ind_2_value is None:
                ind_2_value = self._safe_scalar(df, ind_2, shift_2)
            if ind_1_value is not None and ind_2_value is not None:
                break

        if ind_1_value is None or ind_2_value is None:
            self._warn_not_evaluable(cond_dict)
            cond_dict['expression'] = None
            cond_dict['result'] = False
            return cond_dict

        try:
            expression = f"{ind_1_value} {operator} {ind_2_value}"
            cond_dict['expression'] = expression
            result = self._safe_compare(float(ind_1_value), operator, float(ind_2_value))
        except Exception:
            cond_dict['expression'] = None
            result = False

        cond_dict['result'] = result
        return cond_dict

    def num_relation(self, cond_dict, data_dict):
        """
        Condición de entrada o salida por la relación de un indicador con un threshold
        """
        result = False
        ind_1_value = None

        ind_1, operator, threshold = cond_dict['cond'].split()
        shift_1 = -int(cond_dict.get('shift_1', 0) or 0) - 1
        cond_dict['shift_2'] = 0

        for _, df in data_dict.items():
            if ind_1_value is None:
                ind_1_value = self._safe_scalar(df, ind_1, shift_1)
            if ind_1_value is not None:
                break

        if ind_1_value is None:
            self._warn_not_evaluable(cond_dict)
            cond_dict['expression'] = None
            cond_dict['result'] = False
            return cond_dict

        try:
            threshold_val = float(threshold)
            expression = f"{ind_1_value} {operator} float({threshold})"
            cond_dict['expression'] = expression
            result = self._safe_compare(float(ind_1_value), operator, threshold_val)
        except Exception:
            cond_dict['expression'] = None
            result = False

        cond_dict['result'] = result
        return cond_dict

    def price_relation(self, cond_dict, data_dict):
        """
        Condición de entrada o salida por la relación de un indicador con un precio
        """
        result = False
        ind_1_value = None
        price_1_value = None

        ind_1, operator, price = cond_dict['cond'].split()
        price_tf = price.split("_")[-1]
        price_type = price.split("_")[0]
        shift_1 = -int(cond_dict.get('shift_1', 0) or 0) - 1
        shift_2 = -int(cond_dict.get('shift_2', 0) or 0) - 1

        for tf, df in data_dict.items():
            if ind_1_value is None:
                ind_1_value = self._safe_scalar(df, ind_1, shift_1)

            if tf == price_tf:
                price_1_value = self._safe_scalar(df, price_type, shift_2)

        if ind_1_value is None or price_1_value is None:
            self._warn_not_evaluable(cond_dict)
            cond_dict['expression'] = None
            cond_dict['result'] = False
            return cond_dict

        try:
            expression = f"{ind_1_value} {operator} {price_1_value}"
            cond_dict['expression'] = expression
            result = self._safe_compare(float(ind_1_value), operator, float(price_1_value))
        except Exception:
            cond_dict['expression'] = None
            result = False

        cond_dict['result'] = result

        return cond_dict

    def p2p_relation(self, cond_dict, data_dict):
        """
        Condición de entrada o salida por la relación de un precio con otro precio
        """
        result = False
        price_1_value = None
        price_2_value = None

        price_1, operator, price_2 = cond_dict['cond'].split()
        price_tf_1 = price_1.split("_")[-1]
        price_type_1 = price_1.split("_")[0]
        price_tf_2 = price_2.split("_")[-1]
        price_type_2 = price_2.split("_")[0]
        shift_1 = -int(cond_dict.get('shift_1', 0) or 0) - 1
        shift_2 = -int(cond_dict.get('shift_2', 0) or 0) - 1

        for tf, df in data_dict.items():
            if tf == price_tf_1:
                 price_1_value = self._safe_scalar(df, price_type_1, shift_1)

        for tf, df in data_dict.items():
            if tf == price_tf_2:
                price_2_value = self._safe_scalar(df, price_type_2, shift_2)

        if price_1_value is None or price_2_value is None:
            self._warn_not_evaluable(cond_dict)
            cond_dict['expression'] = None
            cond_dict['result'] = False
            return cond_dict

        try:
            expression = f"{price_1_value} {operator} {price_2_value}"
            cond_dict['expression'] = expression
            result = self._safe_compare(float(price_1_value), operator, float(price_2_value))
        except Exception:
            cond_dict['expression'] = None
            result = False

        cond_dict['result'] = result

        return cond_dict

    def cross_ind_relation(self, cond_dict, data_dict):
        """
        Condición de entrada o salida por el cruce del valor de dos indicadores 
        """
        result = False
        ind_1_past_value = None
        ind_1_current_value = None
        ind_2_past_value = None
        ind_2_current_value = None

        condition = cond_dict['cond'].split()
        ind_1, operator, ind_2 = condition
        shift_1 = -int(cond_dict.get('shift_1', 0) or 0) - 1
        shift_2 = -int(cond_dict.get('shift_2', 0) or 0) - 1

        for _, df in data_dict.items():
            if ind_1_past_value is None:
                ind_1_past_value = self._safe_scalar(df, ind_1, shift_1 - 1)
            if ind_1_current_value is None:
                ind_1_current_value = self._safe_scalar(df, ind_1, shift_1)
            if ind_2_past_value is None:
                ind_2_past_value = self._safe_scalar(df, ind_2, shift_2 - 1)
            if ind_2_current_value is None:
                ind_2_current_value = self._safe_scalar(df, ind_2, shift_2)

            if (
                ind_1_past_value is not None
                and ind_1_current_value is not None
                and ind_2_past_value is not None
                and ind_2_current_value is not None
            ):
                break

        if (
            ind_1_past_value is None
            or ind_1_current_value is None
            or ind_2_past_value is None
            or ind_2_current_value is None
        ):
            self._warn_not_evaluable(cond_dict)
            cond_dict['past_expression'] = None
            cond_dict['current_expression'] = None
            cond_dict['result'] = False
            return cond_dict

        if operator == 'above':
            cond_dict['past_expression'] = f"{ind_1_past_value} > {ind_2_past_value}"
            cond_dict['current_expression'] = f"{ind_1_current_value} > {ind_2_current_value}"
            past_ok = ind_1_past_value > ind_2_past_value
            curr_ok = ind_1_current_value > ind_2_current_value
            result = (past_ok is False) and (curr_ok is True)
        elif operator == 'bellow':
            cond_dict['past_expression'] = f"{ind_1_past_value} < {ind_2_past_value}"
            cond_dict['current_expression'] = f"{ind_1_current_value} < {ind_2_current_value}"
            past_ok = ind_1_past_value < ind_2_past_value
            curr_ok = ind_1_current_value < ind_2_current_value
            result = (past_ok is False) and (curr_ok is True)
        else:
            cond_dict['past_expression'] = None
            cond_dict['current_expression'] = None
            result = False

       
        cond_dict['result'] = result

        return cond_dict

    def ind_direction(self, cond_dict, data_dict):
        """
        Condición de entrada o salida por el cambio de dirección de un indicador (upwards o downwards)
        Requiere 3 valores consecutivos para detectar el cambio de dirección:
        - value[t-2] vs value[t-1] = dirección anterior
        - value[t-1] vs value[t] = dirección actual
        """
        result = False
        ind_1_prev_value = None    # t-2
        ind_1_past_value = None    # t-1
        ind_1_current_value = None # t

        condition = cond_dict['cond'].split()
        ind_1, operator = condition
        shift_1 = -int(cond_dict.get('shift_1', 0) or 0) - 1
        cond_dict['shift_2'] = 0

        for _, df in data_dict.items():
            if ind_1_prev_value is None:
                ind_1_prev_value = self._safe_scalar(df, ind_1, shift_1 - 2)
            if ind_1_past_value is None:
                ind_1_past_value = self._safe_scalar(df, ind_1, shift_1 - 1)
            if ind_1_current_value is None:
                ind_1_current_value = self._safe_scalar(df, ind_1, shift_1)
            if (
                ind_1_prev_value is not None
                and ind_1_past_value is not None
                and ind_1_current_value is not None
            ):
                break

        if ind_1_prev_value is None or ind_1_past_value is None or ind_1_current_value is None:
            self._warn_not_evaluable(cond_dict)
            cond_dict['past_expression'] = None
            cond_dict['current_expression'] = None
            cond_dict['result'] = False
            return cond_dict

        if operator == 'upwards':
            cond_dict['past_expression'] = f"{ind_1_prev_value} > {ind_1_past_value}"
            cond_dict['current_expression'] = f"{ind_1_past_value} < {ind_1_current_value}"
            prev_going_down = ind_1_prev_value > ind_1_past_value
            now_going_up = ind_1_past_value < ind_1_current_value
            result = bool(prev_going_down and now_going_up)
        elif operator == 'downwards':
            cond_dict['past_expression'] = f"{ind_1_prev_value} < {ind_1_past_value}"
            cond_dict['current_expression'] = f"{ind_1_past_value} > {ind_1_current_value}"
            prev_going_up = ind_1_prev_value < ind_1_past_value
            now_going_down = ind_1_past_value > ind_1_current_value
            result = bool(prev_going_up and now_going_down)
        else:
            cond_dict['past_expression'] = None
            cond_dict['current_expression'] = None
            result = False

        cond_dict['result'] = result

        return cond_dict

    def cross_num_relation(self, cond_dict, data_dict):
        """
        Condición de entrada o salida por el cruce del valor de un indicador con un threshold
        """
        result = False
        ind_1_past_value = None
        ind_1_current_value = None

        condition = cond_dict['cond'].split()
        ind_1, operator, threshold = condition
        shift_1 = -int(cond_dict.get('shift_1', 0) or 0) - 1
        cond_dict['shift_2'] = 0

        for _, df in data_dict.items():
            if ind_1_past_value is None:
                ind_1_past_value = self._safe_scalar(df, ind_1, shift_1 - 1)
            if ind_1_current_value is None:
                ind_1_current_value = self._safe_scalar(df, ind_1, shift_1)
            if ind_1_past_value is not None and ind_1_current_value is not None:
                break

        if ind_1_past_value is None or ind_1_current_value is None:
            self._warn_not_evaluable(cond_dict)
            cond_dict['past_expression'] = None
            cond_dict['current_expression'] = None
            cond_dict['result'] = False
            return cond_dict

        try:
            thresh_val = float(threshold)
        except Exception:
            thresh_val = None

        if thresh_val is None:
            cond_dict['past_expression'] = None
            cond_dict['current_expression'] = None
            result = False
        elif operator == 'above':
            cond_dict['past_expression'] = f"{ind_1_past_value} > float({threshold})"
            cond_dict['current_expression'] = f"{ind_1_current_value} > float({threshold})"
            past_ok = ind_1_past_value > thresh_val
            curr_ok = ind_1_current_value > thresh_val
            result = (past_ok is False) and (curr_ok is True)
        elif operator == 'bellow':
            cond_dict['past_expression'] = f"{ind_1_past_value} < float({threshold})"
            cond_dict['current_expression'] = f"{ind_1_current_value} < float({threshold})"
            past_ok = ind_1_past_value < thresh_val
            curr_ok = ind_1_current_value < thresh_val
            result = (past_ok is False) and (curr_ok is True)
        else:
            cond_dict['past_expression'] = None
            cond_dict['current_expression'] = None
            result = False

        cond_dict['result'] = result

        return cond_dict

    def cross_price_relation(self, cond_dict, data_dict):
        """
        Condición de entrada o salida por el cruce del valor de un indicador con un precio
        """
        result = False
        ind_1_past_value = None
        ind_1_current_value = None
        price_1_past_value = None
        price_1_current_value = None
    
        ind_1, operator, price = cond_dict['cond'].split()
        price_tf = price.split("_")[-1]
        price_type = price.split("_")[0]
        shift_1 = -int(cond_dict.get('shift_1', 0) or 0) - 1
        shift_2 = -int(cond_dict.get('shift_2', 0) or 0) - 1

        for tf, df in data_dict.items():
            if ind_1_past_value is None:
                ind_1_past_value = self._safe_scalar(df, ind_1, shift_1 - 1)
            if ind_1_current_value is None:
                ind_1_current_value = self._safe_scalar(df, ind_1, shift_1)

            if tf == price_tf:
                if price_1_past_value is None:
                    price_1_past_value = self._safe_scalar(df, price_type, shift_2 - 1)
                if price_1_current_value is None:
                    price_1_current_value = self._safe_scalar(df, price_type, shift_2)

        if (
            ind_1_past_value is None
            or ind_1_current_value is None
            or price_1_past_value is None
            or price_1_current_value is None
        ):
            self._warn_not_evaluable(cond_dict)
            cond_dict['past_expression'] = None
            cond_dict['current_expression'] = None
            cond_dict['result'] = False
            return cond_dict

        if operator == 'above':
            cond_dict['past_expression'] = f"{ind_1_past_value} > {price_1_past_value}"
            cond_dict['current_expression'] = f"{ind_1_current_value} > {price_1_current_value}"
            past_ok = ind_1_past_value > price_1_past_value
            curr_ok = ind_1_current_value > price_1_current_value
            result = (past_ok is False) and (curr_ok is True)
        elif operator == 'bellow':
            cond_dict['past_expression'] = f"{ind_1_past_value} < {price_1_past_value}"
            cond_dict['current_expression'] = f"{ind_1_current_value} < {price_1_current_value}"
            past_ok = ind_1_past_value < price_1_past_value
            curr_ok = ind_1_current_value < price_1_current_value
            result = (past_ok is False) and (curr_ok is True)
        else:
            cond_dict['past_expression'] = None
            cond_dict['current_expression'] = None
            result = False

        cond_dict['result'] = result

        return cond_dict

###################################################
################ LOGGING OUTPUTS ##################
###################################################

    @staticmethod
    def _append_parquet(path: str, df: pl.DataFrame):
        """Read existing parquet, concat new rows, write back with zstd compression."""
        try:
            if os.path.exists(path):
                existing = pl.read_parquet(path)
                df = pl.concat([existing, df], how="diagonal_relaxed")
            df.write_parquet(path, compression="zstd")
        except Exception as e:
            import sys
            print(f"[STRATEGY LOG] Failed to write {path}: {e}", file=sys.stderr)

    @staticmethod
    def cleanup_old_strategy_logs(base_folder: str = "logs/logs_strategies", retention_days: int = 90):
        """Delete day-folders older than retention_days."""
        cutoff = datetime.now() - timedelta(days=retention_days)
        if not os.path.exists(base_folder):
            return
        for day_dir in os.listdir(base_folder):
            try:
                dir_date = datetime.strptime(day_dir, "%Y-%m-%d")
                if dir_date < cutoff:
                    shutil.rmtree(os.path.join(base_folder, day_dir))
            except (ValueError, OSError):
                pass

    def log_process_outputs(self, data_dict, summary_dict, strategies_dict):
        base_folder = "logs/logs_strategies"
        today_str = datetime.now().strftime("%Y-%m-%d")
        calc_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Determine calculation type
        if self.entries:
            calc_type = "ENTRY"
        elif self.exits:
            calc_type = "EXIT"
        else:
            calc_type = "ALL"

        day_folder = os.path.join(base_folder, today_str)
        os.makedirs(day_folder, exist_ok=True)

        # Summary CSV path (one per day)
        summary_csv = os.path.join(day_folder, "summary.csv")
        write_header = not os.path.exists(summary_csv)

        try:
            for strat_id, strat_data in data_dict.items():
                strat_folder = os.path.join(day_folder, str(strat_id))
                os.makedirs(strat_folder, exist_ok=True)

                # 1) Timeframe data → data_{safe_tf}.parquet
                for tf, df in strat_data.items():
                    if not isinstance(df, pl.DataFrame) or df.is_empty():
                        continue
                    safe_tf = tf.replace(" ", "_")
                    df_tagged = df.with_columns([
                        pl.lit(calc_timestamp).alias("_calc_timestamp"),
                        pl.lit(calc_type).alias("_calc_type"),
                    ])
                    path = os.path.join(strat_folder, f"data_{safe_tf}.parquet")
                    self._append_parquet(path, df_tagged)

                # 2) Conditions → conditions.parquet
                if strat_id in summary_dict:
                    summary_df = summary_dict[strat_id]
                    if isinstance(summary_df, pl.DataFrame) and not summary_df.is_empty():
                        cond_df = summary_df.with_columns([
                            pl.lit(calc_timestamp).alias("_calc_timestamp"),
                            pl.lit(calc_type).alias("_calc_type"),
                        ])
                        cond_path = os.path.join(strat_folder, "conditions.parquet")
                        self._append_parquet(cond_path, cond_df)

                # 3) Signals → signals.parquet
                if strat_id in strategies_dict:
                    signal = strategies_dict[strat_id]
                    sig_df = pl.DataFrame({
                        "_calc_timestamp": [calc_timestamp],
                        "_calc_type": [calc_type],
                        "long": [signal.get("long", False)],
                        "short": [signal.get("short", False)],
                        "exit": [signal.get("exit", False)],
                    })
                    sig_path = os.path.join(strat_folder, "signals.parquet")
                    self._append_parquet(sig_path, sig_df)

                # 4) Daily summary CSV
                if strat_id in strategies_dict:
                    signal = strategies_dict[strat_id]
                    with open(summary_csv, "a", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        if write_header:
                            writer.writerow(["timestamp", "strategy", "calc_type", "long", "short", "exit"])
                            write_header = False
                        writer.writerow([
                            calc_timestamp,
                            strat_id,
                            calc_type,
                            signal.get("long", False),
                            signal.get("short", False),
                            signal.get("exit", False),
                        ])

        except Exception as e:
            import sys
            print(f"[STRATEGY LOG] Error writing logs: {e}", file=sys.stderr)

if __name__ == '__main__':

    from .strat_loader import StratOBJ


    pl.Config.set_tbl_cols(-1)
    pl.Config.set_tbl_rows(-1)

    ib = IB()
    ib.connect('127.0.0.1', 7497, clientId=5)

    obj = StratOBJ().upload()

    start = time.time()

    data_dict, summary_dict, strategies_dict, ref_price = STRATEGIES(ib=ib, stratsOBJ=obj, strats_to_process=[1001], logging=True, all=True).process()

    end = time.time()
    print(f"{end - start} seconds")


    ic(data_dict)
    ic(summary_dict)
    ic(strategies_dict)
    ic(ref_price)








