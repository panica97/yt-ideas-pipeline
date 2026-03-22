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
}
