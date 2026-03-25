# ibkr_core/sl_tp.py - extracted from _06_Initial_SL_TP.py
from __future__ import annotations

import importlib
import os
import pandas as pd
from icecream import ic
import polars as pl

from .market_data import MarketDataManager
from .indicators import INDICATORS
from .logger import get_logger

class Initial_SL_TP:
    """
    Esta clase realiza los calculos necesarios para determinar el SL y el TP iniciales de una operación.
    """
    def __init__(self, ib, stratOBJ, signal_dict:dict=None, signals:dict=None, entry_data=None, ref_price=None, SL_market_data=None, TP_market_data=None):
        self.ib = ib
        self.stratOBJ = stratOBJ
        self.signal_dict = signal_dict  # New: single strategy dict
        self.signals = signals  # Legacy: DataFrame support
        self.entry_data = entry_data
        self.ref_price = ref_price
        self.SL_market_data = SL_market_data
        self.TP_market_data = TP_market_data
        self._market_data_cache = {}  # Cache for tick data
        self._indicator_cache = {}    # Cache for indicator calculations

    def _round_to_tick(self, price, strategy_code):
        """Round price to the nearest tick size for the given strategy"""
        min_tick = self.stratOBJ.minTick(strategy_code)
        return round(price / min_tick) * min_tick

###################################################
################ MAIN SYNC FUNCTION ###############
###################################################
    
    def generate(self):
        """
        Generate SL/TP levels for a single strategy signal.
        
        Args:
            Uses self.signal_dict (dict) if provided, otherwise falls back to self.signals (DataFrame)
            
        Returns:
            dict: Signal dict enriched with 'SL_level', 'TP_level', 'close_level'
        """
        # Use dict if provided, otherwise convert DataFrame
        if self.signal_dict is not None:
            signal = self.signal_dict.copy()
            strategy = signal['strat_code']
        else:
            # Legacy DataFrame support
            df = self.signals.copy()
            strategy = df.index[0]
            signal = df.iloc[0].to_dict()
            signal['strat_code'] = strategy
        
        is_long = signal['long']
        
        # Skip if neither long nor short (exit only)
        if not is_long and not signal['short']:
            return signal
        
        contract = self.stratOBJ.contract(strategy)
        stop_loss_params = self.stratOBJ.stop_loss_init(strategy)
        take_profit_params = self.stratOBJ.take_profit_init(strategy)
        
        # Calculate SL and TP
        try:
            if is_long:
                SL_level = self.calculate_initial_SL(SL_params=stop_loss_params, contract=contract, long=True)
                TP_level = self.calculate_initial_TP(TP_params=take_profit_params, contract=contract, long=True)
            else:
                SL_level = self.calculate_initial_SL(SL_params=stop_loss_params, contract=contract, short=True)
                TP_level = self.calculate_initial_TP(TP_params=take_profit_params, contract=contract, short=True)
        except Exception as e:
            print(f"[SL/TP] Calculation failed for {strategy}: {e}")
            get_logger().log_error("STRATEGY", f"SL/TP calculation failed for {strategy}: {e}")
            raise

        # Round and add to dict
        signal['SL_level'] = self._round_to_tick(SL_level, strategy) if SL_level is not None else None
        signal['TP_level'] = self._round_to_tick(TP_level, strategy) if TP_level is not None else None
        signal['close_level'] = self._round_to_tick(self.ref_price, strategy)

        return signal


    def calculate_initial_SL(self, SL_params, contract, long=False, short=False):
        if SL_params['indicator']:
            ind_params = SL_params['indicator_params']
            
            # Extract parameters (new flat structure)
            timeframe = ind_params['tf']
            multiple = ind_params['multiple']
            label = ind_params['col']
            
            # Access entry_data: first by strategy code, then by timeframe
            strategy_code = self.signal_dict['strat_code'] if self.signal_dict else list(self.entry_data.keys())[0]
            
            if self.entry_data and strategy_code in self.entry_data and timeframe in self.entry_data[strategy_code]:
                df = self.entry_data[strategy_code][timeframe]
                
                # Validate column exists
                if label not in df.columns:
                    available_cols = ', '.join(df.columns)
                    raise ValueError(
                        f"Column '{label}' not found in entry_data['{timeframe}']. "
                        f"Available columns: {available_cols}"
                    )
                
                # Get the last row value (most recent)
                indicator_value = df.tail(2).get_column(label)[0]
                
            if long:
                SL_level = self.ref_price - (multiple * indicator_value)
            elif short:
                SL_level = self.ref_price + (multiple * indicator_value)
        
        elif SL_params['pips']:
            pips_params = SL_params['pips_params']
            pip_value = pips_params['pip_value']
            pip_size = pips_params['pip_size']
            
            if long:
                SL_level = self.ref_price - (pip_value * pip_size)
            else:
                SL_level = self.ref_price + (pip_value * pip_size)

        elif SL_params['percent']:
            perc = SL_params['percent_params']
            
            if long:
                SL_level = self.ref_price * (1 - perc)
            else:
                SL_level = self.ref_price * (1 + perc)
        
        if not (SL_params['indicator'] or SL_params['pips'] or SL_params['percent']):
            return None
        return SL_level

    def calculate_initial_TP(self, TP_params, contract, long=False, short=False):
        if TP_params['indicator']:
            ind_params = TP_params['indicator_params']
            
            # Extract parameters (new flat structure)
            timeframe = ind_params['tf']
            multiple = ind_params['multiple']
            label = ind_params['col']
            
            # Access entry_data: first by strategy code, then by timeframe
            strategy_code = self.signal_dict['strat_code'] if self.signal_dict else list(self.entry_data.keys())[0]
            
            # Use pre-calculated data if available
            if self.entry_data and strategy_code in self.entry_data and timeframe in self.entry_data[strategy_code]:
                df = self.entry_data[strategy_code][timeframe]
                
                # Validate column exists
                if label not in df.columns:
                    available_cols = ', '.join(df.columns)
                    raise ValueError(
                        f"Column '{label}' not found in entry_data['{timeframe}']. "
                        f"Available columns: {available_cols}"
                    )
                
                # Get the last row value (most recent)
                indicator_value = df.tail(2).get_column(label)[0]
            
            if long:
                TP_level = self.ref_price + (multiple * indicator_value)
            elif short:
                TP_level = self.ref_price - (multiple * indicator_value)
        
        elif TP_params['pips']:
            pips_params = TP_params['pips_params']
            pip_value = pips_params['pip_value']
            pip_size = pips_params['pip_size']
            
            if long:
                TP_level = self.ref_price + (pip_value * pip_size)
            else:
                TP_level = self.ref_price - (pip_value * pip_size)

        elif TP_params['percent']:
            perc = TP_params['percent_params']
            
            if long:
                TP_level = self.ref_price * (1 + perc)
            else:
                TP_level = self.ref_price * (1 - perc)
        
        if not (TP_params['indicator'] or TP_params['pips'] or TP_params['percent']):
            return None
        return TP_level

###################################################
############### MAIN ASYNC FUNCTION ###############
###################################################

    async def generate_async(self):
        """
        Generate SL/TP levels for a single strategy signal asynchronously.
        
        Args:
            Uses self.signal_dict (dict) if provided, otherwise falls back to self.signals (DataFrame)
            
        Returns:
            dict: Signal dict enriched with 'SL_level', 'TP_level', 'close_level'
        """
        # Use dict if provided, otherwise convert DataFrame
        if self.signal_dict is not None:
            signal = self.signal_dict.copy()
            strategy = signal['strat_code']
        else:
            # Legacy DataFrame support
            df = self.signals.copy()
            strategy = df.index[0]
            signal = df.iloc[0].to_dict()
            signal['strat_code'] = strategy
        
        is_long = signal['long']
        
        # Skip if neither long nor short (exit only)
        if not is_long and not signal['short']:
            return signal
        
        contract = self.stratOBJ.contract(strategy)
        stop_loss_params = self.stratOBJ.stop_loss_init(strategy)
        take_profit_params = self.stratOBJ.take_profit_init(strategy)
        
        # Calculate SL and TP
        try:
            if is_long:
                SL_level = await self.calculate_initial_SL_async(stop_loss_params, contract, long=True)
                TP_level = await self.calculate_initial_TP_async(take_profit_params, contract, long=True)
            else:
                SL_level = await self.calculate_initial_SL_async(stop_loss_params, contract, short=True)
                TP_level = await self.calculate_initial_TP_async(take_profit_params, contract, short=True)
        except Exception as e:
            print(f"[SL/TP] Async calculation failed for {strategy}: {e}")
            get_logger().log_error("STRATEGY", f"Async SL/TP calculation failed for {strategy}: {e}")
            raise

        # Round and add to dict
        signal['SL_level'] = self._round_to_tick(SL_level, strategy) if SL_level is not None else None
        signal['TP_level'] = self._round_to_tick(TP_level, strategy) if TP_level is not None else None
        signal['close_level'] = self._round_to_tick(self.ref_price, strategy)

        return signal

    async def calculate_initial_SL_async(self, SL_params, contract, *, long=False, short=False):
        if SL_params['indicator']:
            ind_params = SL_params['indicator_params']
            
            # Extract parameters (new flat structure)
            timeframe = ind_params['tf']
            multiple = ind_params['multiple']
            label = ind_params['col']
            
            # Access entry_data: first by strategy code, then by timeframe
            strategy_code = self.signal_dict['strat_code'] if self.signal_dict else list(self.entry_data.keys())[0]
            
            # Use pre-calculated data if available
            if self.entry_data and strategy_code in self.entry_data and timeframe in self.entry_data[strategy_code]:
                df = self.entry_data[strategy_code][timeframe]
                
                # Validate column exists
                if label not in df.columns:
                    available_cols = ', '.join(df.columns)
                    raise ValueError(
                        f"Column '{label}' not found in entry_data['{timeframe}']. "
                        f"Available columns: {available_cols}"
                    )
                
                # Get the last row value (most recent)
                indicator_value = df.tail(2).get_column(label)[0]
            
            if long:
                SL_level = self.ref_price - (multiple * indicator_value)
            elif short:
                SL_level = self.ref_price + (multiple * indicator_value)

        elif SL_params['pips']:
            pips_params = SL_params['pips_params']
            pip_value = pips_params['pip_value']
            pip_size = pips_params['pip_size']
            
            if long:
                SL_level = self.ref_price - (pip_value * pip_size)
            else:
                SL_level = self.ref_price + (pip_value * pip_size)

        elif SL_params['percent']:
            perc = SL_params['percent_params']
            
            if long:
                SL_level = self.ref_price * (1 - perc)
            else:
                SL_level = self.ref_price * (1 + perc)
        
        return SL_level

    async def calculate_initial_TP_async(self, TP_params, contract, *, long=False, short=False):
        if TP_params['indicator']:
            ind_params = TP_params['indicator_params']
            
            # Extract parameters (new flat structure)
            timeframe = ind_params['tf']
            multiple = ind_params['multiple']
            label = ind_params['col']
            
            # Access entry_data: first by strategy code, then by timeframe
            strategy_code = self.signal_dict['strat_code'] if self.signal_dict else list(self.entry_data.keys())[0]
            
            # Use pre-calculated data if available
            if self.entry_data and strategy_code in self.entry_data and timeframe in self.entry_data[strategy_code]:
                df = self.entry_data[strategy_code][timeframe]
                
                # Validate column exists
                if label not in df.columns:
                    available_cols = ', '.join(df.columns)
                    raise ValueError(
                        f"Column '{label}' not found in entry_data['{timeframe}']. "
                        f"Available columns: {available_cols}"
                    )
                
                # Get the last row value (most recent)
                indicator_value = df.tail(2).get_column(label)[0]
            
            if long:
                TP_level = self.ref_price + (multiple * indicator_value)
            elif short:
                TP_level = self.ref_price - (multiple * indicator_value)

        elif TP_params['pips']:
            pips_params = TP_params['pips_params']
            pip_value = pips_params['pip_value']
            pip_size = pips_params['pip_size']
            
            if long:
                TP_level = self.ref_price + (pip_value * pip_size)
            else:
                TP_level = self.ref_price - (pip_value * pip_size)

        elif TP_params['percent']:
            perc = TP_params['percent_params']
            
            if long:
                TP_level = self.ref_price * (1 + perc)
            else:
                TP_level = self.ref_price * (1 - perc)
        
        return TP_level

if __name__=='__main__':

    from .strat_loader import StratOBJ
    from ib_async import IB

    data_dict = {
            1002: {"long": True, "short": False, "exit": False},
            1003: {"long": False, "short": True, "exit": False},
            # 1004: {"long": True, "short": False, "exit": False},
            # 1005: {"long": False, "short": False, "exit": False}
        }
    
    stratOBJ = StratOBJ().upload()

    ib = IB()
    ib.connect('127.0.0.1', 7497, clientId=2)

    signals_df = pd.DataFrame.from_dict(data_dict, orient="index")
    ic(signals_df)

    df = Initial_SL_TP(stratOBJ=stratOBJ, signals=signals_df, ib=ib).generate()
    ic(df)