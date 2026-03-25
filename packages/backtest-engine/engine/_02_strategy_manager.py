from icecream import ic
import polars as pl
import time

from ibkr_core import STRATEGIES


class STRATEGY_BACKTEST(STRATEGIES):
    """
    Backtesting version of STRATEGIES class.
    Inherits all condition evaluation methods from parent class.
    Modified to work with preloaded indicator data instead of live market data.

    Key differences from live version:
    - Accepts pre-calculated indicator DataFrames (ind_data)
    - Processes single strategy per instance (strat_id)
    - No database calls for num_bars (handled in Backtester.py)
    """
    ### INPUT:
    #           strat_id: single strategy ID to process
    #           stratsOBJ: StratOBJ instance with strategy definitions
    #           ind_data: Dict[timeframe, pl.DataFrame] with pre-calculated indicators
    #           entries / exits / all: control which conditions to evaluate
    #           logging: enable detailed logging
    ### OUTPUT:
    #           data_dict: datos (velas, indicadores y condiciones)
    #           summary_dict: señal que se genera con cada condicion
    #           strategies_signals: señal de entrada/salida de cada estrategia procesada
    #           ref_price: reference price for the current bar

    def __init__(self, ib=None, stratsOBJ=None, strat_id: int=None, strategies_folder: str='Strategies',
                 entries: bool=False, exits: bool=False, all: bool=True,
                 extended_data: int=0, logging: bool=False, ind_data: dict={}):

        # Call parent constructor (STRATEGIES)
        super().__init__(
            ib=ib,
            stratsOBJ=stratsOBJ,
            strats_to_process=[strat_id] if strat_id else [],
            strategies_folder=strategies_folder,
            entries=entries,
            exits=exits,
            all=all,
            extended_data=extended_data,
            logging=logging
        )

        self.strat_id = strat_id
        self.ind_data = ind_data  # Pre-calculated indicators from Backtester


###################################################
############### MAIN SYNC FUNCTION ################
###################################################

    def process(self):
        """
        Process strategy conditions using pre-calculated indicator data.
        No live data fetching - all indicators must be in self.ind_data.
        """
        data_dict = {}
        strategies_dict = {}
        summary_dict = {}

        long_df = pl.DataFrame()
        short_df = pl.DataFrame()
        exit_df = pl.DataFrame()

        # Set context for warning prints (throttled in parent class)
        self._current_strategy_id = self.strat_id

        # Extracción de la información de la estrategia
        if self.entries:
            long_conds = self.stratsOBJ.long_conds(self.strat_id)
            short_conds = self.stratsOBJ.short_conds(self.strat_id)
            exit_conds = []
        elif self.exits:
            long_conds = []
            short_conds = []
            exit_conds = self.stratsOBJ.exit_conds(self.strat_id)
        elif self.all:
            long_conds = self.stratsOBJ.long_conds(self.strat_id)
            short_conds = self.stratsOBJ.short_conds(self.strat_id)
            exit_conds = self.stratsOBJ.exit_conds(self.strat_id)
        else:
            long_conds = []
            short_conds = []
            exit_conds = []

        # Use pre-calculated indicator data from Backtester
        strat_dict = self.ind_data

        # Process conditions using inherited methods from STRATEGIES
        if self.entries:
            long_df = self.call_conditions(strat_dict, long_conds)
            short_df = self.call_conditions(strat_dict, short_conds)
        elif self.exits:
            exit_df = self.call_conditions(strat_dict, exit_conds)
        elif self.all:
            long_df = self.call_conditions(strat_dict, long_conds)
            short_df = self.call_conditions(strat_dict, short_conds)
            exit_df = self.call_conditions(strat_dict, exit_conds)

        # Procesamiento de las condiciones para generar una señal de la estrategia
        signal_strat, summary = self.process_conditions(long_df, short_df, exit_df)

        # Se añaden los resultados de las estrategias a los outputs
        data_dict[self.strat_id] = strat_dict
        summary_dict[self.strat_id] = summary
        strategies_dict[self.strat_id] = signal_strat

        # get ref_price (current bar open price from primary timeframe)
        primary_tf = self.stratsOBJ.process_freq(self.strat_id)
        strat_data = data_dict[self.strat_id]
        if primary_tf in strat_data:
            df = strat_data[primary_tf]
        else:
            # Fallback to first available timeframe
            df = strat_data[next(iter(strat_data))]
        ref_price = df["open"][-1]

        if self.logging:
            self.log_process_outputs(data_dict, summary_dict, strategies_dict)

        return data_dict, summary_dict, strategies_dict, ref_price


    def num_bars(self, cond_dict, data_dict):
        """Backtest: num_bars exits are handled by the backtester.

        The live implementation queries PostgreSQL for active bars. Backtests
        should be pure/in-memory, so we short-circuit here.
        """
        # Keep shape consistent with other condition methods
        cond_dict['shift_1'] = 0
        cond_dict['shift_2'] = 0
        # Preserve provided strat if present, else use current strat_id
        try:
            cond_dict['strat'] = int(cond_dict.get('strat', self.strat_id))
        except Exception:
            cond_dict['strat'] = self.strat_id
        cond_dict['result'] = False
        return cond_dict


    # Note: All condition evaluation methods (ind_relation, num_relation, price_relation, etc.)
    # are inherited from STRATEGIES parent class.
    # The only modification needed is for num_bars condition, which is handled in Backtester.py
    # since it requires position tracking not available in this class.


if __name__ == '__main__':
    # Test example - would need actual indicator data in practice
    from ibkr_core import StratOBJ

    pl.Config.set_tbl_cols(-1)
    pl.Config.set_tbl_rows(-1)

    obj = StratOBJ().upload()

    # In backtest, ind_data would come from DataPreprocessor + INDICATORS
    # This is just a placeholder for testing structure
    test_ind_data = {}

    start = time.time()

    # Note: No IB connection needed for backtest
    data_dict, summary_dict, strategies_dict, ref_price = STRATEGY_BACKTEST(
        ib=None,
        stratsOBJ=obj,
        strat_id=1003,
        logging=True,
        entries=True,
        ind_data=test_ind_data
    ).process()

    end = time.time()
    print(f"{end - start} seconds")

    ic(data_dict)
    ic(summary_dict)
    ic(strategies_dict)
    ic(ref_price)
