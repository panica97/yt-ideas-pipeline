export type BacktestMode = 'simple' | 'complete' | 'montecarlo';

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

// Monte Carlo result types
export interface MCPercentileValues {
  p5: number;
  p25: number;
  p50: number;
  p75: number;
  p95: number;
}

export interface MCStatistic {
  mean: number;
  median: number;
  std: number;
  min: number;
  max: number;
  p5: number;
  p25: number;
  p75: number;
  p95: number;
}

export interface MCStatistics {
  total_pnl: MCStatistic;
  max_drawdown_pct: MCStatistic;
  sharpe_ratio: MCStatistic;
  win_rate: MCStatistic;
  profit_factor: MCStatistic;
  raw_metrics?: {
    total_pnl: number[];
    max_drawdown_pct: number[];
    sharpe_ratio: number[];
    win_rate: number[];
    profit_factor: number[];
    [key: string]: number[];
  };
  [key: string]: unknown;
}

export interface MCRiskMetrics {
  prob_negative_return: number;
  prob_dd_20: number;
  prob_dd_30: number;
  prob_dd_50: number;
  var_95: number;
  cvar_95: number;
}

export interface MCComparison {
  return_percentile: number;
  assessment: string;
}

export interface MCEquityCurvePoint {
  step: number;
  p5: number;
  p25: number;
  p50: number;
  p75: number;
  p95: number;
  baseline?: number;
}

export interface MonteCarloMetrics {
  statistics: MCStatistics;
  risk_metrics: MCRiskMetrics;
  comparison: MCComparison;
  equity_curve_percentiles: MCEquityCurvePoint[];
  n_paths: number;
  fit_years: number;
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
  debug?: boolean;
}
