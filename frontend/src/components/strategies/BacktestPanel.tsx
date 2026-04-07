import { useState, useMemo, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { AxiosError } from 'axios';
import { Play, Trash2, ChevronDown, ChevronUp, AlertCircle, Loader2, Info, TrendingUp, FileText, Shuffle, Bug, SlidersHorizontal, Layers, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { createBacktest, getBacktestsByDraft, getBacktest, deleteBacktest } from '../../services/backtests';
import type { BacktestJobSummary, BacktestMetrics, BacktestTrade, BacktestMode, PipelineConfig } from '../../types/backtest';
import type { Instrument } from '../../types/instrument';
import BacktestReportDrawer from './BacktestReportDrawer';
import StressParamBuilder from './StressParamBuilder';

interface BacktestPanelProps {
  stratCode: number;
  backtestable: boolean;
  defaultSymbol?: string;
  primaryTimeframe?: string;
  instruments?: Instrument[];
  draftData?: any;
}

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
  const winRate = metrics.win_rate ?? 0;
  const sharpe = metrics.sharpe_ratio ?? 0;
  const trades = metrics.total_trades ?? metrics.trade_count ?? 0;

  // Return / Drawdown ratio card
  const returnPct = typeof metrics.return_pct === 'number' ? metrics.return_pct : undefined;
  const maxDdPct = typeof metrics.max_drawdown_pct === 'number' ? metrics.max_drawdown_pct : undefined;
  let ratioValue: string;
  let ratioColor: string;
  if (returnPct != null && maxDdPct != null && maxDdPct !== 0) {
    const ratio = Math.abs(returnPct) / Math.abs(maxDdPct);
    ratioValue = ratio.toFixed(2);
    ratioColor = ratio > 1 ? 'text-accent' : 'text-danger';
  } else if (metrics.total_pnl != null && metrics.max_drawdown != null && metrics.max_drawdown !== 0) {
    const ratio = Math.abs(metrics.total_pnl / metrics.max_drawdown);
    ratioValue = ratio.toFixed(2);
    ratioColor = ratio > 1 ? 'text-accent' : 'text-danger';
  } else {
    ratioValue = 'N/A';
    ratioColor = 'text-text-muted';
  }

  // Max DD % card
  let ddPctValue: string;
  if (maxDdPct != null) {
    ddPctValue = formatPercent(maxDdPct);
  } else {
    // Fallback: compute from absolute max_drawdown / initial_equity
    const absDd = typeof metrics.max_drawdown === 'number' ? metrics.max_drawdown : undefined;
    const initialEquity = typeof metrics.initial_equity === 'number' ? metrics.initial_equity : undefined;
    if (absDd != null && initialEquity != null && initialEquity !== 0) {
      ddPctValue = formatPercent(Math.abs(absDd) / initialEquity * 100);
    } else {
      ddPctValue = 'N/A';
    }
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
      <MetricCard label="Return / DD" value={ratioValue} colorClass={ratioColor} />
      <MetricCard label="Win Rate" value={formatPercent(winRate)} />
      <MetricCard label="Max DD %" value={ddPctValue} colorClass="text-danger" />
      <MetricCard label="Sharpe Ratio" value={sharpe.toFixed(2)} />
      <MetricCard label="Total Trades" value={String(trades)} />
    </div>
  );
}

function EquityCurveChart({ trades }: { trades: BacktestTrade[] }) {
  const data = useMemo(() => {
    const sorted = [...trades].sort((a, b) => {
      const ta = new Date(a.exit_date).getTime();
      const tb = new Date(b.exit_date).getTime();
      if (isNaN(ta) || isNaN(tb)) return 0; // preserve order on invalid dates
      return ta - tb;
    });
    let cumPnl = 0;
    return sorted.map((t) => {
      cumPnl += t.pnl;
      return { date: t.exit_date, cumPnl: Number(cumPnl.toFixed(2)) };
    });
  }, [trades]);

  return (
    <div className="mt-2 border border-border rounded-lg p-3 bg-surface-1/30">
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: 'var(--color-text-muted)' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 10, fill: 'var(--color-text-muted)' }}
            tickLine={false}
            tickFormatter={(v: number) => formatCurrency(v)}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'var(--color-surface-2)',
              border: '1px solid var(--color-border)',
              borderRadius: '0.375rem',
              fontSize: '0.75rem',
            }}
            labelStyle={{ color: 'var(--color-text-muted)' }}
            formatter={(value) => [formatCurrency(Number(value)), 'Cumulative PnL']}
          />
          <Line
            type="monotone"
            dataKey="cumPnl"
            stroke="var(--color-accent)"
            strokeWidth={1.5}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function JobResultsView({ jobId }: { jobId: number }) {
  const [showTrades, setShowTrades] = useState(false);
  const [showEquityCurve, setShowEquityCurve] = useState(false);

  const { data: job } = useQuery({
    queryKey: ['backtest', jobId],
    queryFn: () => getBacktest(jobId),
  });

  if (!job?.result) {
    return <p className="text-xs text-text-muted italic">Loading results...</p>;
  }

  const { metrics, trades = [] } = job.result;

  return (
    <div className="mt-2 space-y-2">
      <MetricsGrid metrics={metrics as BacktestMetrics} />

      {trades.length > 0 && (
        <div>
          <button
            onClick={() => setShowEquityCurve(!showEquityCurve)}
            className="flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary transition-colors"
          >
            {showEquityCurve ? <ChevronUp size={14} /> : <TrendingUp size={14} />}
            {showEquityCurve ? 'Hide' : 'Show'} Equity Curve
          </button>

          {showEquityCurve && <EquityCurveChart trades={trades} />}
        </div>
      )}

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

function JobItem({ job, onDelete, onViewReport }: { job: BacktestJobSummary; onDelete: (id: number) => void; onViewReport: (id: number) => void }) {
  const [expanded, setExpanded] = useState(false);
  const isCompleteMode = job.mode === 'complete';
  const isMCMode = job.mode === 'montecarlo';
  const isMonkeyMode = job.mode === 'monkey';
  const isStressMode = job.mode === 'stress';

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="group w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-surface-1/30 transition-colors"
      >
        <StatusBadge status={job.status} />
        {isCompleteMode && (
          <span className="text-[10px] bg-accent/10 text-accent border border-accent/20 rounded px-1 py-0.5 font-medium">
            Complete
          </span>
        )}
        {isMCMode && (
          <span className="text-[10px] bg-purple-500/10 text-purple-400 border border-purple-500/20 rounded px-1 py-0.5 font-medium">
            Monte Carlo
          </span>
        )}
        {isMonkeyMode && (
          <span className="text-[10px] bg-orange-500/10 text-orange-400 border border-orange-500/20 rounded px-1 py-0.5 font-medium">
            Monkey Test
          </span>
        )}
        {isStressMode && (
          <span className="text-[10px] bg-rose-500/10 text-rose-400 border border-rose-500/20 rounded px-1 py-0.5 font-medium">
            Stress Test
          </span>
        )}
        <span className="text-xs text-text-secondary flex-1">
          {job.symbol} &middot; {job.timeframe} &middot; {job.start_date} &rarr; {job.end_date}
        </span>
        <span className="text-xs text-text-muted">{formatRelativeTime(job.created_at)}</span>
        {job.status === 'completed' && (isCompleteMode || isMCMode || isMonkeyMode || isStressMode) && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onViewReport(job.id);
            }}
            className="inline-flex items-center gap-1 px-2 py-0.5 text-xs text-accent hover:text-accent/80 transition-colors"
            title="View Report"
          >
            <FileText size={12} />
            Report
          </button>
        )}
        {job.status !== 'running' && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              if (window.confirm('Delete this backtest job?')) {
                onDelete(job.id);
              }
            }}
            className="p-1 text-text-muted hover:text-danger transition-colors opacity-0 group-hover:opacity-100"
            title="Delete"
          >
            <Trash2 size={12} />
          </button>
        )}
        <span className="text-xs text-text-muted">{expanded ? '\u25B2' : '\u25BC'}</span>
      </button>

      {expanded && (
        <div className="px-3 pb-3 bg-surface-1/20">
          {job.status === 'completed' && job.mode !== 'montecarlo' && job.mode !== 'monkey' && job.mode !== 'stress' && (
            <JobResultsView jobId={job.id} />
          )}
          {job.status === 'completed' && job.mode === 'montecarlo' && (
            <p className="mt-2 text-xs text-text-muted italic">Click "Report" to view Monte Carlo results.</p>
          )}
          {job.status === 'completed' && job.mode === 'monkey' && (
            <p className="mt-2 text-xs text-text-muted italic">Click "Report" to view Monkey Test results.</p>
          )}
          {job.status === 'completed' && job.mode === 'stress' && (
            <p className="mt-2 text-xs text-text-muted italic">Click "Report" to view Stress Test results.</p>
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

const PIPELINE_STEP_LABELS: Record<string, string> = {
  complete: 'BT',
  montecarlo: 'MC',
  monkey: 'Monkey',
  stress: 'Stress',
};

function PipelineStepIcon({ status }: { status: string }) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 size={12} className="text-green-400" />;
    case 'running':
      return <Loader2 size={12} className="text-accent animate-spin" />;
    case 'failed':
      return <XCircle size={12} className="text-danger" />;
    default:
      return <Clock size={12} className="text-text-muted" />;
  }
}

function PipelineStatusRow({
  jobs,
  onViewReport,
  onDelete,
}: {
  jobs: BacktestJobSummary[];
  onViewReport: (groupId: string) => void;
  onDelete: (id: number) => void;
}) {
  const firstJob = jobs[0];
  if (!firstJob) return null;

  const statuses = jobs.map((j) => j.status);
  const overallStatus = statuses.some((s) => s === 'failed')
    ? 'failed'
    : statuses.every((s) => s === 'completed')
      ? 'completed'
      : statuses.every((s) => s === 'pending')
        ? 'pending'
        : 'running';

  const isCompleted = overallStatus === 'completed';
  const pipelineGroup = firstJob.pipeline_group!;

  // Sort by mode to get a consistent order: complete -> montecarlo -> monkey -> stress
  const modeOrder = ['complete', 'montecarlo', 'monkey', 'stress'];
  const sortedJobs = [...jobs].sort((a, b) => modeOrder.indexOf(a.mode) - modeOrder.indexOf(b.mode));

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <div className="group flex items-center gap-2 px-3 py-2 hover:bg-surface-1/30 transition-colors">
        <StatusBadge status={overallStatus as keyof typeof STATUS_CONFIG} />
        <span className="text-[10px] bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 rounded px-1 py-0.5 font-medium">
          Pipeline
        </span>
        <span className="flex items-center gap-1.5 text-xs text-text-secondary">
          {sortedJobs.map((j) => (
            <span key={j.id} className="inline-flex items-center gap-0.5">
              <PipelineStepIcon status={j.status} />
              <span className="text-[10px]">{PIPELINE_STEP_LABELS[j.mode] ?? j.mode}</span>
            </span>
          ))}
        </span>
        <span className="text-xs text-text-secondary flex-1">
          {firstJob.symbol} &middot; {firstJob.timeframe} &middot; {firstJob.start_date} &rarr; {firstJob.end_date}
        </span>
        <span className="text-xs text-text-muted">{formatRelativeTime(firstJob.created_at)}</span>
        {isCompleted && (
          <button
            onClick={() => onViewReport(pipelineGroup)}
            className="inline-flex items-center gap-1 px-2 py-0.5 text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
            title="View Pipeline Report"
          >
            <FileText size={12} />
            Report
          </button>
        )}
        {overallStatus !== 'running' && (
          <button
            onClick={() => {
              if (window.confirm('Delete all pipeline jobs?')) {
                jobs.forEach((j) => onDelete(j.id));
              }
            }}
            className="p-1 text-text-muted hover:text-danger transition-colors opacity-0 group-hover:opacity-100"
            title="Delete Pipeline"
          >
            <Trash2 size={12} />
          </button>
        )}
      </div>
    </div>
  );
}

const TIMEFRAME_OPTIONS = [
  { value: '1m', label: '1 min' },
  { value: '5m', label: '5 mins' },
  { value: '15m', label: '15 mins' },
  { value: '30m', label: '30 mins' },
  { value: '1H', label: '1 hour' },
  { value: '2H', label: '2 hours' },
  { value: '3H', label: '3 hours' },
  { value: '4H', label: '4 hours' },
  { value: '8H', label: '8 hours' },
  { value: '1D', label: '1 day' },
  { value: '1W', label: '1 week' },
] as const;

export default function BacktestPanel({ stratCode, backtestable, defaultSymbol, primaryTimeframe, instruments, draftData }: BacktestPanelProps) {
  const [symbol, setSymbol] = useState(defaultSymbol ?? '');
  const [startDate, setStartDate] = useState('');
  const [backtestMode, setBacktestMode] = useState<BacktestMode>('simple');
  const [selectedTimeframe, setSelectedTimeframe] = useState(primaryTimeframe ?? '1D');
  const [endDate, setEndDate] = useState('');
  const [nPaths, setNPaths] = useState(1000);
  const [fitYears, setFitYears] = useState(10);
  const [formError, setFormError] = useState<string | null>(null);
  const [monkeyMode, setMonkeyMode] = useState<string>('A');
  const [nSimulations, setNSimulations] = useState<number>(1000);
  const [stressTestName, setStressTestName] = useState<string>('');
  const [stressParamOverrides, setStressParamOverrides] = useState<Record<string, any>>({});
  const [stressSingleOverrides, setStressSingleOverrides] = useState<Record<string, any>>({});
  const [stressMaxParallel, setStressMaxParallel] = useState<number>(4);
  const [selectedReportJobId, setSelectedReportJobId] = useState<number | null>(null);
  const [selectedPipelineGroupId, setSelectedPipelineGroupId] = useState<string | null>(null);
  const [pipelineMCOpen, setPipelineMCOpen] = useState(true);
  const [pipelineMonkeyOpen, setPipelineMonkeyOpen] = useState(true);
  const [pipelineStressOpen, setPipelineStressOpen] = useState(true);
  const queryClient = useQueryClient();

  // Look up the matched instrument for data range constraints
  const matchedInstrument = useMemo(() => {
    if (!instruments || !symbol.trim()) return undefined;
    return instruments.find((i) => i.symbol.toLowerCase() === symbol.trim().toLowerCase());
  }, [instruments, symbol]);

  const dataMin = matchedInstrument?.data_from?.slice(0, 10) ?? undefined;
  const dataMax = matchedInstrument?.data_to?.slice(0, 10) ?? undefined;

  // Auto-populate / clamp dates when symbol changes and instrument data is available
  useEffect(() => {
    if (!dataMin || !dataMax) return;

    setStartDate((prev) => {
      if (!prev) return dataMin;
      if (prev < dataMin) return dataMin;
      if (prev > dataMax) return dataMax;
      return prev;
    });

    setEndDate((prev) => {
      if (!prev) return dataMax;
      if (prev > dataMax) return dataMax;
      if (prev < dataMin) return dataMin;
      return prev;
    });
  }, [dataMin, dataMax]);

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
    onError: (error: AxiosError<{ detail: string }>) => {
      const detail = error.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : 'Failed to delete backtest';
      setFormError(msg);
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

    if (backtestMode === 'pipeline') {
      const pipelineGroup = crypto.randomUUID();
      const pipelineConfig: PipelineConfig = {
        montecarlo: { n_paths: nPaths, fit_years: fitYears },
        monkey: { n_simulations: nSimulations, monkey_mode: monkeyMode },
        stress: {
          stress_test_name: stressTestName || undefined,
          stress_param_overrides: Object.keys(stressParamOverrides).length > 0 ? stressParamOverrides : undefined,
          stress_single_overrides: Object.keys(stressSingleOverrides).length > 0 ? stressSingleOverrides : undefined,
          stress_max_parallel: stressMaxParallel,
        },
      };
      createMutation.mutate({
        draft_strat_code: stratCode,
        symbol: symbol.trim(),
        timeframe: selectedTimeframe,
        start_date: startDate,
        end_date: endDate,
        mode: 'complete',
        pipeline_group: pipelineGroup,
        pipeline_config: pipelineConfig,
      });
      return;
    }

    createMutation.mutate({
      draft_strat_code: stratCode,
      symbol: symbol.trim(),
      timeframe: (backtestMode === 'complete' || backtestMode === 'montecarlo' || backtestMode === 'monkey' || backtestMode === 'stress') ? selectedTimeframe : (primaryTimeframe ?? '1h'),
      start_date: startDate,
      end_date: endDate,
      mode: backtestMode,
      ...(backtestMode === 'montecarlo' && { n_paths: nPaths, fit_years: fitYears }),
      ...(backtestMode === 'monkey' && { n_simulations: nSimulations, monkey_mode: monkeyMode }),
      ...(backtestMode === 'stress' && {
        stress_test_name: stressTestName || undefined,
        stress_param_overrides: Object.keys(stressParamOverrides).length > 0 ? stressParamOverrides : undefined,
        stress_single_overrides: Object.keys(stressSingleOverrides).length > 0 ? stressSingleOverrides : undefined,
        stress_max_parallel: stressMaxParallel,
      }),
    });
  };

  const jobs = backtestList?.jobs ?? [];

  // Group pipeline jobs vs individual jobs
  const { pipelineGroups, individualJobs } = useMemo(() => {
    const groups = new Map<string, BacktestJobSummary[]>();
    const singles: BacktestJobSummary[] = [];

    for (const job of jobs) {
      if (job.pipeline_group) {
        const existing = groups.get(job.pipeline_group) ?? [];
        existing.push(job);
        groups.set(job.pipeline_group, existing);
      } else {
        singles.push(job);
      }
    }

    return { pipelineGroups: groups, individualJobs: singles };
  }, [jobs]);

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
        {/* Mode selector */}
        <div className="flex gap-2">
          <button
            onClick={() => setBacktestMode('simple')}
            className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded font-medium transition-colors ${
              backtestMode === 'simple'
                ? 'bg-accent text-surface-0'
                : 'bg-surface-2 text-text-muted'
            }`}
          >
            <Play size={12} />
            Simple Backtest
          </button>
          <button
            onClick={() => setBacktestMode('complete')}
            className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded font-medium transition-colors ${
              backtestMode === 'complete'
                ? 'bg-accent text-surface-0'
                : 'bg-surface-2 text-text-muted'
            }`}
          >
            Complete Backtest
          </button>
          <button
            onClick={() => setBacktestMode('montecarlo')}
            className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded font-medium transition-colors ${
              backtestMode === 'montecarlo'
                ? 'bg-purple-600 text-white'
                : 'bg-surface-2 text-text-muted'
            }`}
          >
            <Shuffle size={12} />
            Monte Carlo
          </button>
          <button
            onClick={() => setBacktestMode('monkey')}
            className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded font-medium transition-colors ${
              backtestMode === 'monkey'
                ? 'bg-orange-600 text-white'
                : 'bg-surface-2 text-text-muted'
            }`}
          >
            <Bug size={12} />
            Monkey Test
          </button>
          <button
            onClick={() => setBacktestMode('stress')}
            className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded font-medium transition-colors ${
              backtestMode === 'stress'
                ? 'bg-rose-600 text-white'
                : 'bg-surface-2 text-text-muted'
            }`}
          >
            <SlidersHorizontal size={12} />
            Stress Test
          </button>
          <button
            onClick={() => setBacktestMode('pipeline')}
            className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded font-medium transition-colors ${
              backtestMode === 'pipeline'
                ? 'bg-gradient-to-r from-cyan-600 to-teal-600 text-white'
                : 'bg-surface-2 text-text-muted'
            }`}
          >
            <Layers size={12} />
            Pipeline
          </button>
        </div>

        <div className="grid grid-cols-3 gap-2">
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
            <label className="block text-xs text-text-muted mb-1">Start Date</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              min={dataMin}
              max={dataMax}
              className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
            />
          </div>
          <div>
            <label className="block text-xs text-text-muted mb-1">End Date</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              min={dataMin}
              max={dataMax}
              className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
            />
          </div>
        </div>

        {(backtestMode === 'complete' || backtestMode === 'montecarlo' || backtestMode === 'monkey' || backtestMode === 'stress' || backtestMode === 'pipeline') && (
          <div>
            <label className="block text-xs text-text-muted mb-1">Timeframe</label>
            <select
              value={selectedTimeframe}
              onChange={(e) => setSelectedTimeframe(e.target.value)}
              className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
            >
              {TIMEFRAME_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label} ({opt.value})
                </option>
              ))}
            </select>
          </div>
        )}

        {backtestMode === 'montecarlo' && (
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-text-muted mb-1">Number of Paths</label>
              <input
                type="number"
                value={nPaths}
                onChange={(e) => setNPaths(Math.max(1, parseInt(e.target.value) || 1))}
                min={1}
                max={10000}
                className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
            <div>
              <label className="block text-xs text-text-muted mb-1">Fit Years</label>
              <input
                type="number"
                value={fitYears}
                onChange={(e) => setFitYears(Math.max(1, parseInt(e.target.value) || 1))}
                min={1}
                max={50}
                className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
          </div>
        )}

        {backtestMode === 'monkey' && (
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-text-muted mb-1">Monkey Mode</label>
              <select
                value={monkeyMode}
                onChange={(e) => setMonkeyMode(e.target.value)}
                className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
              >
                <option value="A">A: Empirical Distribution</option>
                <option value="B">B: Always Max Bars</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-text-muted mb-1">Simulations</label>
              <select
                value={nSimulations}
                onChange={(e) => setNSimulations(parseInt(e.target.value))}
                className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
              >
                <option value={1000}>1,000</option>
                <option value={2500}>2,500</option>
                <option value={5000}>5,000</option>
              </select>
            </div>
          </div>
        )}

        {backtestMode === 'stress' && (
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs text-text-muted mb-1">Test Name</label>
                <input
                  type="text"
                  value={stressTestName}
                  onChange={(e) => setStressTestName(e.target.value)}
                  className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
                  placeholder="e.g. rsi_period_sweep"
                />
              </div>
              <div>
                <label className="block text-xs text-text-muted mb-1">Max Parallel</label>
                <select
                  value={stressMaxParallel}
                  onChange={(e) => setStressMaxParallel(parseInt(e.target.value))}
                  className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
                >
                  <option value={1}>1</option>
                  <option value={2}>2</option>
                  <option value={4}>4</option>
                </select>
              </div>
            </div>
            <StressParamBuilder
              draftData={draftData}
              onParamOverridesChange={setStressParamOverrides}
              onSingleOverridesChange={setStressSingleOverrides}
            />
          </div>
        )}

        {backtestMode === 'pipeline' && (
          <div className="space-y-2">
            {/* Monte Carlo section */}
            <div className="border border-border rounded-lg overflow-hidden">
              <button
                type="button"
                onClick={() => setPipelineMCOpen(!pipelineMCOpen)}
                className="w-full flex items-center justify-between px-3 py-2 bg-surface-2/50 hover:bg-surface-2 transition-colors"
              >
                <span className="text-xs font-semibold text-purple-400 flex items-center gap-1.5">
                  <Shuffle size={12} />
                  Monte Carlo
                </span>
                <ChevronDown size={14} className={`text-text-muted transition-transform ${pipelineMCOpen ? 'rotate-180' : ''}`} />
              </button>
              {pipelineMCOpen && (
                <div className="px-3 py-2">
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-xs text-text-muted mb-1">Number of Paths</label>
                      <input
                        type="number"
                        value={nPaths}
                        onChange={(e) => setNPaths(Math.max(1, parseInt(e.target.value) || 1))}
                        min={1}
                        max={10000}
                        className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-text-muted mb-1">Fit Years</label>
                      <input
                        type="number"
                        value={fitYears}
                        onChange={(e) => setFitYears(Math.max(1, parseInt(e.target.value) || 1))}
                        min={1}
                        max={50}
                        className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Monkey Test section */}
            <div className="border border-border rounded-lg overflow-hidden">
              <button
                type="button"
                onClick={() => setPipelineMonkeyOpen(!pipelineMonkeyOpen)}
                className="w-full flex items-center justify-between px-3 py-2 bg-surface-2/50 hover:bg-surface-2 transition-colors"
              >
                <span className="text-xs font-semibold text-orange-400 flex items-center gap-1.5">
                  <Bug size={12} />
                  Monkey Test
                </span>
                <ChevronDown size={14} className={`text-text-muted transition-transform ${pipelineMonkeyOpen ? 'rotate-180' : ''}`} />
              </button>
              {pipelineMonkeyOpen && (
                <div className="px-3 py-2">
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-xs text-text-muted mb-1">Monkey Mode</label>
                      <select
                        value={monkeyMode}
                        onChange={(e) => setMonkeyMode(e.target.value)}
                        className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
                      >
                        <option value="A">A: Empirical Distribution</option>
                        <option value="B">B: Always Max Bars</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-text-muted mb-1">Simulations</label>
                      <select
                        value={nSimulations}
                        onChange={(e) => setNSimulations(parseInt(e.target.value))}
                        className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
                      >
                        <option value={1000}>1,000</option>
                        <option value={2500}>2,500</option>
                        <option value={5000}>5,000</option>
                      </select>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Stress Test section */}
            <div className="border border-border rounded-lg overflow-hidden">
              <button
                type="button"
                onClick={() => setPipelineStressOpen(!pipelineStressOpen)}
                className="w-full flex items-center justify-between px-3 py-2 bg-surface-2/50 hover:bg-surface-2 transition-colors"
              >
                <span className="text-xs font-semibold text-rose-400 flex items-center gap-1.5">
                  <SlidersHorizontal size={12} />
                  Stress Test
                </span>
                <ChevronDown size={14} className={`text-text-muted transition-transform ${pipelineStressOpen ? 'rotate-180' : ''}`} />
              </button>
              {pipelineStressOpen && (
                <div className="px-3 py-2 space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-xs text-text-muted mb-1">Test Name</label>
                      <input
                        type="text"
                        value={stressTestName}
                        onChange={(e) => setStressTestName(e.target.value)}
                        className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
                        placeholder="e.g. rsi_period_sweep"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-text-muted mb-1">Max Parallel</label>
                      <select
                        value={stressMaxParallel}
                        onChange={(e) => setStressMaxParallel(parseInt(e.target.value))}
                        className="w-full text-xs bg-surface-2 text-text-primary border border-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
                      >
                        <option value={1}>1</option>
                        <option value={2}>2</option>
                        <option value={4}>4</option>
                      </select>
                    </div>
                  </div>
                  <StressParamBuilder
                    draftData={draftData}
                    onParamOverridesChange={setStressParamOverrides}
                    onSingleOverridesChange={setStressSingleOverrides}
                  />
                </div>
              )}
            </div>
          </div>
        )}

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
                {backtestMode === 'pipeline' ? 'Run Pipeline' : backtestMode === 'montecarlo' ? 'Run Monte Carlo' : backtestMode === 'monkey' ? 'Run Monkey Test' : backtestMode === 'stress' ? 'Run Stress Test' : 'Run Backtest'}
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
            {/* Pipeline groups */}
            {Array.from(pipelineGroups.entries()).map(([groupId, groupJobs]) => (
              <PipelineStatusRow
                key={groupId}
                jobs={groupJobs}
                onViewReport={(gId) => setSelectedPipelineGroupId(gId)}
                onDelete={(id) => deleteMutation.mutate(id)}
              />
            ))}
            {/* Individual (non-pipeline) jobs */}
            {individualJobs.map((job) => (
              <JobItem
                key={job.id}
                job={job}
                onDelete={(id) => deleteMutation.mutate(id)}
                onViewReport={(id) => setSelectedReportJobId(id)}
              />
            ))}
          </div>
        )}
      </div>

      {selectedReportJobId !== null && (
        <BacktestReportDrawer
          jobId={selectedReportJobId}
          open={selectedReportJobId !== null}
          onClose={() => setSelectedReportJobId(null)}
        />
      )}

      {selectedPipelineGroupId !== null && (
        <BacktestReportDrawer
          jobId={0}
          pipelineGroupId={selectedPipelineGroupId}
          open={selectedPipelineGroupId !== null}
          onClose={() => setSelectedPipelineGroupId(null)}
        />
      )}
    </div>
  );
}
