"""Monte Carlo simulation configuration constants."""


class MonteCarloConfig:
    """Central configuration for all Monte Carlo simulation parameters."""

    # --- GJR-GARCH ---
    GARCH_MAX_ITER = 500
    GARCH_MAX_PERSISTENCE = 0.9999
    GARCH_INITIAL_PARAMS = {
        'omega': 0.1,
        'alpha': 0.1,
        'beta': 0.8,
        'nu': 10.0,
        'gamma': 0.1,   # leverage / asymmetry
        'lam': -0.1,    # skewness (slight left-skew prior for equities)
    }
    GARCH_N_RESTARTS = 5
    GARCH_NU_LOWER_BOUND = 4.01          # minimum df (>4 ensures finite 4th moment)
    GARCH_VARIANCE_TARGETING = True      # pin long_run_var = sample_var during MLE
    GARCH_KURTOSIS_CALIBRATION = True    # post-fit nu adjustment to match kurtosis
    GARCH_KURTOSIS_TARGET_RATIO = (0.5, 2.0)  # acceptable kurtosis ratio range (wide to avoid over-calibrating)
    GARCH_KURTOSIS_TEST_PATHS = 100     # paths per candidate nu during calibration
    GARCH_KURTOSIS_SEEDS = [42, 123, 999]  # multiple seeds for stable kurtosis estimate
    KURTOSIS_POST_FIT_REFINEMENT = False # disabled: was fighting variance targeting; trust per-GARCH calibration
    KURTOSIS_POST_FIT_PATHS = 50        # paths for post-fit kurtosis measurement

    # --- Jump Diffusion ---
    JUMP_THRESHOLD = 3.0   # std devs beyond which residuals are classified as jumps

    # --- Regime Switching ---
    MIN_REGIME_OBSERVATIONS = 500  # minimum data points to attempt regime detection
    REGIME_VOL_SCALE = 1.5         # stressed regime vol scaling factor (for simulation)
    MIN_REGIME_PERSISTENCE = 0.70  # minimum P(stay) for normal regime
    MIN_REGIME_PERSISTENCE_STRESSED = 0.50  # lower bar for stressed (transient by nature)
    REGIME_TRANSITION_BLEND = 0.5  # blend rate toward new regime's LRV on transitions
    MIN_REGIME_DURATION_HOURS = 48 # minimum regime segment duration (~2 trading days)
    REGIME_PERSISTENCE_PRIOR = 2.5 # Dirichlet pseudo-count favoring persistence in EM (reduced from 5.0)
    REGIME_PERSISTENCE_ADAPTIVE = True   # scale threshold by timeframe
    MAX_REGIME_STATES = 3                # max HMM states to test during auto-selection
    AUTO_SELECT_REGIME_STATES = True     # use BIC to pick optimal state count
    MIN_BARS_FOR_3_STATES = 5000         # minimum bars to consider 3-state HMM

    # --- Path Generation ---
    DEFAULT_N_PATHS = 1000
    MAX_N_PATHS = 10_000
    DEFAULT_BATCH_SIZE = 500
    DEFAULT_N_PERIODS = 252

    # --- Simulation Window ---
    DEFAULT_SIM_BARS = 252       # default simulation length (~1 year daily)
    DEFAULT_FIT_YEARS = 10       # years of history for model fitting (0 = all)

    # --- Workers ---
    DEFAULT_N_WORKERS = None  # None means cpu_count - 1
    SUBPROCESS_TIMEOUT = 7200  # 2 hours

    # --- Intraday Vol Seasonality ---
    SEASONAL_VOL_ENABLED = True          # fit periodic vol multiplier for sub-daily TF
    SEASONAL_MIN_BARS_PER_DAY = 4        # minimum bars/day to activate (4h = 6 bars)

    # --- OHLC Structure ---
    OHLC_REGIME_CONDITIONAL = True       # fit separate OHLC params per regime

    # --- Validation ---
    MIN_HISTORICAL_CANDLES = 250
    OHLC_TOLERANCE = 1e-6
    KS_TEST_THRESHOLD = 0.05
    KS_PRACTICAL_THRESHOLD = 0.10       # max KS statistic for "practically similar"
    VOL_CLUSTERING_MAE_THRESHOLD = 0.10  # GARCH(1,1) structural limit ~0.08-0.12
    VALIDATION_TEST_PATHS = 100  # paths for model fit quality check (0 = skip)

    # --- AR(1) Mean Dynamics ---
    GARCH_AR1_ENABLED = True             # fit AR(1) if returns show autocorrelation
    GARCH_AR1_LJUNGBOX_ALPHA = 0.05      # significance level for Ljung-Box test

    # --- Trade Shuffling ---
    DEFAULT_SHUFFLE_PATHS = 10_000
    DEFAULT_BLOCK_SIZE = 5

    # --- Failure Thresholds ---
    MAX_FAILURE_RATE = 0.20
    MIN_SUCCESSFUL_PATHS_RATIO = 0.50

    # --- Synthetic Data ---
    DEFAULT_SYNTHETIC_VOLUME = 10_000

    # --- Storage ---
    SAVE_INDIVIDUAL_TRADES = False
    SAVE_EQUITY_CURVES = True
    SAVE_PATH_METRICS = True
    RESULTS_FORMAT = 'parquet'
