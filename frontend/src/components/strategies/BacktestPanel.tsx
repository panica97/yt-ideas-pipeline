import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { AxiosError } from 'axios';
import { Play, Trash2, ChevronDown, ChevronUp, AlertCircle, Loader2, Info } from 'lucide-react';
import { createBacktest, getBacktestsByDraft, getBacktest, deleteBacktest } from '../../services/backtests';
import type { BacktestJobSummary, BacktestMetrics } from '../../types/backtest';

interface BacktestPanelProps {
  stratCode: number;
  backtestable: boolean;
  defaultSymbol?: string;
}

const TIMEFRAME_OPTIONS = ['1m', '5m', '15m', '30m', '1h', '4h', '1d'];

const STATUS_CONFIG = {
  pending: {
    classes: 'bg-surface-2 text-text-muted border-border',
    dotClass: 'bg-text-muted',
    label: 'Pending',
  },
  running: {
    classes: 'bg-accent/10 text-accent border-accent/20',
    dotClass: 'bg-accent animate-pulse',
    label: 'Running',
  },
  completed: {
    classes: 'bg-accent/10 text-accent border-accent/20',
    dotClass: 'bg-accent',
    label: 'Completed',
  },
  failed: {
    classes: 'bg-danger/10 text-danger border-danger/20',
    dotClass: 'bg-danger',
    label: 'Failed',
  },
} as const;

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

function formatCurrency(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}$${value.toFixed(2)}`;
}

function formatPercent(value: number): string {
  // Engine returns win_rate already as percentage (e.g. 43.21)
  return `${value.toFixed(1)}%`;
}

function StatusBadge({ status }: { status: keyof typeof STATUS_CONFIG }) {
  const cfg = STATUS_CONFIG[status];
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${cfg.classes}`}>
      <span className={`inline-block w-1.5 h-1.5 rounded-full ${cfg.dotClass}`} />
      {cfg.label}
    </span>
  );
}

function MetricCard({ label, value, colorClass }: { label: string; value: string; colorClass?: string }) {
  return (
    <div className="bg-surface-1/50 border border-border rounded-lg p-3">
      <p className="text-xs text-text-muted mb-1">{label}</p>
      <p className={`text-sm font-semibold ${colorClass ?? 'text-text-primary'}`}>{value}</p>
    </div>
  );
}

function MetricsGrid({ metrics }: { metrics: BacktestMetrics }) {
  const pnl = metrics.total_pnl ?? 0;
  const winRate = metrics.win_rate ?? 0;
  const maxDD = metrics.max_drawdown ?? 0;
  const sharpe = metrics.sharpe_ratio ?? 0;
  const trades = metrics.total_trades ?? metrics.trade_count ?? 0;
  const pnlColor = pnl >= 0 ? 'text-accent' : 'text-danger';
  const drawdownColor = 'text-danger';

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
      <MetricCard label="Net PnL" value={formatCurrency(pnl)} colorClass={pnlColor} />
      <MetricCard label="Win Rate" value={formatPercent(winRate)} />
      <MetricCard label="Max Drawdown" value={formatCurrency(maxDD)} colorClass={drawdownColor} />
      <MetricCard label="Sharpe Ratio" value={sharpe.toFixed(2)} />
      <MetricCard label="Total Trades" value={String(trades)} />
    </div>
  );
}

function JobResultsView({ jobId }: { jobId: number }) {
  const [showTrades, setShowTrades] = useState(false);

  const { data: job } = useQuery({
    queryKey: ['backtest', jobId],
    queryFn: () => getBacktest(jobId),
  });

  if (!job?.result) {
    return <p className="text-xs text-text-muted italic">Loading results...</p>;
  }

  const { metrics, trades } = job.result;

  return (
    <div className="mt-2 space-y-2">
      <MetricsGrid metrics={metrics as BacktestMetrics} />

      {trades.length > 0 && (
        <div>
          <button
            onClick={() => setShowTrades(!showTrades)}
            className="flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary transition-colors"
          >
            {showTrades ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            {showTrades ? 'Hide' : 'Show'} Trades ({trades.length})
          </button>

          {showTrades && (
            <div className="mt-1 max-h-60 overflow-y-auto border border-border rounded">
              <table className="w-full text-xs">
                <thead className="bg-surface-2/50 sticky top-0">
                  <tr>
                    <th className="text-left px-2 py-1 text-text-muted font-medium">Entry</th>
                    <th className="text-left px-2 py-1 text-text-muted font-medium">Exit</th>
                    <th className="text-left px-2 py-1 text-text-muted font-medium">Dir</th>
                    <th className="text-right px-2 py-1 text-text-muted font-medium">Entry $</th>
                    <th className="text-right px-2 py-1 text-text-muted font-medium">Exit $</th>
                    <th className="text-right px-2 py-1 text-text-muted font-medium">PnL</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((trade, i) => (
                    <tr key={i} className="border-t border-border/50 hover:bg-surface-1/30">
                      <td className="px-2 py-1 text-text-secondary">{trade.entry_date}</td>
                      <td className="px-2 py-1 text-text-secondary">{trade.exit_date}</td>
                      <td className="px-2 py-1">
                        <span className={`text-xs font-medium ${trade.direction === 'long' ? 'text-accent' : 'text-danger'}`}>
                          {trade.direction === 'long' ? 'Long' : 'Short'}
                        </span>
                      </td>
                      <td className="px-2 py-1 text-right text-text-secondary">{trade.entry_price.toFixed(2)}</td>
                      <td className="px-2 py-1 text-right text-text-secondary">{trade.exit_price.toFixed(2)}</td>
                      <td className={`px-2 py-1 text-right font-medium ${trade.pnl >= 0 ? 'text-accent' : 'text-danger'}`}>
                        {formatCurrency(trade.pnl)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function JobItem({ job, onDelete }: { job: BacktestJobSummary; onDelete: (id: number) => void }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-surface-1/30 transition-colors"
      >
        <StatusBadge status={job.status} />
        <span className="text-xs text-text-secondary flex-1">
          {job.symbol} &middot; {job.timeframe} &middot; {job.start_date} &rarr; {job.end_date}
        </span>
        <span className="text-xs text-text-muted">{formatRelativeTime(job.created_at)}</span>
        {job.status === 'pending' && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete(job.id);
            }}
            className="p-1 text-text-muted hover:text-danger transition-colors"
            title="Cancel"
          >
            <Trash2 size={12} />
          </button>
        )}
        <span className="text-xs text-text-muted">{expanded ? '\u25B2' : '\u25BC'}</span>
      </button>

      {expanded && (
        <div className="px-3 pb-3 bg-surface-1/20">
          {job.status === 'completed' && (
            <JobResultsView jobId={job.id} />
          )}
          {job.status === 'failed' && job.error_message && (
            <div className="mt-2 flex items-start gap-2 bg-danger/10 border border-danger/20 rounded p-2">
              <AlertCircle size={14} className="text-danger mt-0.5 shrink-0" />
              <p className="text-xs text-danger break-all">{job.error_message}</p>
            </div>
          )}
          {job.status === 'running' && (
            <div className="mt-2 flex items-center gap-2 text-xs text-accent">
              <Loader2 size={14} className="animate-spin" />
              Running backtest...
            </div>
          )}
          {job.status === 'pending' && (
            <p className="mt-2 text-xs text-text-muted italic">Waiting to be picked up by worker...</p>
          )}
        </div>
      )}
    </div>
  );
}

export default function BacktestPanel({ stratCode, backtestable, defaultSymbol }: BacktestPanelProps) {
  const [symbol, setSymbol] = useState(defaultSymbol ?? '');
  const [timeframe, setTimeframe] = useState('1h');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: backtestList } = useQuery({
    queryKey: ['backtests', stratCode],
    queryFn: () => getBacktestsByDraft(stratCode),
    refetchInterval: (query) => {
      const jobs = query.state.data?.jobs;
      if (!jobs) return false;
      const hasActive = jobs.some((j) => j.status === 'pending' || j.status === 'running');
      return hasActive ? 3000 : false;
    },
  });

  const createMutation = useMutation({
    mutationFn: createBacktest,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backtests', stratCode] });
      setFormError(null);
    },
    onError: (error: AxiosError<{ detail: string }>) => {
      const detail = error.response?.data?.detail;
      if (typeof detail === 'string') {
        setFormError(detail);
      } else {
        setFormError('Failed to connect to server');
      }
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteBacktest,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backtests', stratCode] });
    },
  });

  const handleSubmit = () => {
    setFormError(null);

    if (!symbol.trim()) {
      setFormError('Symbol is required');
      return;
    }
    if (!startDate || !endDate) {
      setFormError('Start date and end date are required');
      return;
    }
    if (startDate >= endDate) {
      setFormError('Start date must be before end date');
      return;
    }

    createMutation.mutate({
      draft_strat_code: stratCode,
      symbol: symbol.trim(),
      timeframe,
      start_date: startDate,
      end_date: endDate,
    });
  };

  const jobs = backtestList?.jobs ?? [];

  // Disabled state
  if (!backtestable) {
    return (
      <div className="flex items-start gap-2 bg-surface-2/50 border border-border rounded-lg p-3">
        <Info size={14} className="text-text-muted mt-0.5 shrink-0" />
        <p className="text-xs text-text-muted">
          Strategy must be validated and all TODOs resolved before backtesting.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Trigger form */}
      <div className="space-y-2">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <div>
            <label className="block text-xs text-text-muted mb-1">Symbol</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
              placeholder="e.g. MNQ"
            />
          </div>
          <div>
            <label className="block text-xs text-text-muted mb-1">Timeframe</label>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
            >
              {TIMEFRAME_OPTIONS.map((tf) => (
                <option key={tf} value={tf}>{tf}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-text-muted mb-1">Start Date</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
            />
          </div>
          <div>
            <label className="block text-xs text-text-muted mb-1">End Date</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
            />
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleSubmit}
            disabled={createMutation.isPending}
            className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 bg-accent text-surface-0 rounded hover:bg-accent/90 transition-colors disabled:opacity-50"
          >
            {createMutation.isPending ? (
              <>
                <Loader2 size={12} className="animate-spin" />
                Running...
              </>
            ) : (
              <>
                <Play size={12} />
                Run Backtest
              </>
            )}
          </button>
        </div>

        {formError && (
          <div className="flex items-start gap-2 bg-danger/10 border border-danger/20 rounded p-2">
            <AlertCircle size={14} className="text-danger mt-0.5 shrink-0" />
            <p className="text-xs text-danger">{formError}</p>
          </div>
        )}
      </div>

      {/* Job history */}
      <div className="space-y-2">
        <h5 className="text-xs font-semibold text-text-muted uppercase">History</h5>
        {jobs.length === 0 ? (
          <p className="text-xs text-text-muted italic">
            No backtests yet. Configure parameters above and run your first backtest.
          </p>
        ) : (
          <div className="space-y-1.5">
            {jobs.map((job) => (
              <JobItem key={job.id} job={job} onDelete={(id) => deleteMutation.mutate(id)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
