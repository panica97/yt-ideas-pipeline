export type BacktestMode = 'simple' | 'complete' | 'montecarlo' | 'monkey' | 'stress';

export interface BacktestTradeComplete {
  entry_date: string;
  exit_date: string;
  side: 'long' | 'short';
  entry_fill_price: number;
  exit_fill_price: number;
  pnl: number;
  exit_reason: string;
  bars_held: number;
  cumulative_pnl: number;
}

export interface BacktestMetrics {
  // Engine returns total_pnl, not net_pnl
  total_pnl: number;
  // Engine returns win_rate as percentage (e.g. 43.21), not fraction
  win_rate: number;
  max_drawdown: number;
  sharpe_ratio: number;
  total_trades: number;
  profit_factor: number;
  sortino_ratio: number;
  trade_count: number;
  return_pct?: number;
  max_drawdown_pct?: number;
  initial_equity?: number;
  [key: string]: unknown;
}

/** Baseline (historical backtest) metrics returned alongside MC results */
export interface MCBaselineMetrics {
  total_pnl?: number;
  trade_count?: number;
  avg_trade_pnl?: number;
  sharpe_ratio?: number;
  sortino_ratio?: number;
  profit_factor?: number;
  max_drawdown_pct?: number;
  win_rate_pct?: number;
  return_drawdown_ratio?: number;
  initial_equity?: number;
  final_equity?: number;
  [key: string]: unknown;
}

// Monte Carlo result types — flat structure (no nested statistics wrapper)

/** Percentile distribution for a single metric */
export interface MCDistribution {
  p5: number;
  p10?: number;
  p25: number;
  p50: number;
  p75: number;
  p90?: number;
  p95: number;
  min?: number;
  max?: number;
  median?: number;
  mean?: number;
  std?: number;
}

export interface MCRiskMetrics {
  var_95: number;
  cvar_95: number;
  prob_dd_10?: number;
  prob_dd_20?: number;
  prob_dd_30?: number;
  prob_dd_50?: number;
  prob_negative_return?: number;
}

export interface MCRawMetrics {
  total_pnl?: number[];
  max_drawdown_pct?: number[];
  sharpe_ratio?: number[];
  win_rate?: number[];
  profit_factor?: number[];
  [key: string]: number[] | undefined;
}

export interface MCEquityCurvePercentiles {
  p5?: number[];
  p25?: number[];
  p50?: number[];
  p75?: number[];
  p95?: number[];
}

export interface MCConfidenceIntervals {
  return_95_ci?: [number, number];
  sharpe_95_ci?: [number, number];
  drawdown_95_ci?: [number, number];
}

export interface MCDrawdownCurvePercentiles {
  p5?: number[];
  p25?: number[];
  p50?: number[];
  p75?: number[];
  p95?: number[];
}

export interface MonteCarloMetrics {
  // Simulation info
  n_paths: number;
  n_completed?: number;
  n_failed?: number;
  failure_rate?: number;

  // Per-metric distributions (flat, no statistics wrapper)
  total_pnl?: MCDistribution;
  max_drawdown_pct?: MCDistribution;
  sharpe_ratio?: MCDistribution;
  win_rate?: MCDistribution;
  profit_factor?: MCDistribution;
  total_trades?: MCDistribution;
  avg_trade_pnl?: MCDistribution;
  sortino_ratio?: MCDistribution;
  return_drawdown_ratio?: MCDistribution;

  // Risk
  risk_metrics?: MCRiskMetrics;

  // Raw per-path arrays
  raw_metrics?: MCRawMetrics;

  // Equity curve percentiles (arrays of values, not array of point objects)
  equity_curve_percentiles?: MCEquityCurvePercentiles;

  // Sampled equity curves
  sampled_paths?: number[][];
  historical_close?: number[];
  sampled_close_paths?: number[][];

  // Confidence intervals
  confidence_intervals?: MCConfidenceIntervals;

  // Drawdown curve percentiles
  drawdown_curve_percentiles?: MCDrawdownCurvePercentiles;

  // Baseline (real historical backtest) metrics
  baseline_metrics?: MCBaselineMetrics;

  [key: string]: unknown;
}

export interface BacktestTrade {
  entry_date: string;
  exit_date: string;
  direction: 'long' | 'short';
  entry_price: number;
  exit_price: number;
  pnl: number;
  [key: string]: unknown;
}

export interface BacktestResult {
  id: number;
  metrics: BacktestMetrics;
  trades: BacktestTrade[];
  created_at: string;
}

export interface BacktestJob {
  id: number;
  draft_strat_code: number;
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  mode: BacktestMode;
  n_paths?: number;
  fit_years?: number;
  n_simulations?: number;
  monkey_mode?: string;
  stress_test_name?: string;
  stress_param_overrides?: Record<string, any>;
  stress_single_overrides?: Record<string, any>;
  stress_max_parallel?: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  result: BacktestResult | null;
}

export interface BacktestJobSummary {
  id: number;
  draft_strat_code: number;
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  mode: BacktestMode;
  n_paths?: number;
  fit_years?: number;
  n_simulations?: number;
  monkey_mode?: string;
  stress_test_name?: string;
  stress_param_overrides?: Record<string, any>;
  stress_single_overrides?: Record<string, any>;
  stress_max_parallel?: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface BacktestListResponse {
  total: number;
  jobs: BacktestJobSummary[];
}

export interface CreateBacktestParams {
  draft_strat_code: number;
  symbol: string;
  timeframe?: string;
  start_date: string;
  end_date: string;
  mode?: BacktestMode;
  n_paths?: number;
  fit_years?: number;
  n_simulations?: number;
  monkey_mode?: string;
  stress_test_name?: string;
  stress_param_overrides?: Record<string, any>;
  stress_single_overrides?: Record<string, any>;
  stress_max_parallel?: number;
  debug?: boolean;
}

export interface MonkeyRealStrategyMetrics {
  net_profit: number;
  max_drawdown: number;
  return_dd: number;
  win_rate: number;
  profit_factor: number;
}

export interface MonkeyTestMetrics {
  mode: string;
  n_simulations: number;
  n_trades_requested: number;
  n_trades_actual: number;
  real_strategy: MonkeyRealStrategyMetrics;
  distribution: {
    return_dd: number[];
    net_profit: number[];
    win_rate: number[];
    profit_factor: number[];
  };
  percentile: number;
  p_value: number;
  warnings: string[];
}

export interface StressTestVariation {
  name: string;
  params: Record<string, number>;
  metrics: Record<string, number>;
  status: 'completed' | 'failed';
  test_type: 'multi' | 'single';
  single_param?: string;
}

export interface StressTestRobustness {
  profitable_pct: number;
  positive_sharpe_pct: number;
  low_drawdown_pct: number;
  score: number;
}

export interface StressTestMetrics {
  summary: {
    total_variations: number;
    completed: number;
    failed: number;
    duration_seconds: number;
  };
  robustness: StressTestRobustness;
  variations: StressTestVariation[];
  multi_variations: StressTestVariation[];
  single_variations: Record<string, StressTestVariation[]>;
  config?: {
    strategy_id: number;
    test_type: string;
    param_ranges: Record<string, number[]>;
  };
}
