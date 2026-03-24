import { useState, useEffect, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { X, ArrowUpDown } from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { getBacktest } from '../../services/backtests';
import type { BacktestTradeComplete, BacktestMetrics } from '../../types/backtest';

interface BacktestReportDrawerProps {
  jobId: number;
  open: boolean;
  onClose: () => void;
}

type SortField = 'entry_date' | 'exit_date' | 'side' | 'entry_fill_price' | 'exit_fill_price' | 'pnl' | 'cumulative_pnl' | 'exit_reason' | 'bars_held';
type SortDir = 'asc' | 'desc';

function formatCurrency(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}$${value.toFixed(2)}`;
}

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

function computeDerivedMetrics(trades: BacktestTradeComplete[]) {
  if (trades.length === 0) {
    return { avgWinLoss: null, maxConsecutiveLosses: 0, avgTradeDuration: null };
  }

  // Avg Win / Loss ratio
  const wins = trades.filter((t) => t.pnl > 0);
  const losses = trades.filter((t) => t.pnl < 0);
  const avgWin = wins.length > 0 ? wins.reduce((s, t) => s + t.pnl, 0) / wins.length : 0;
  const avgLoss = losses.length > 0 ? losses.reduce((s, t) => s + t.pnl, 0) / losses.length : 0;
  const avgWinLoss = avgLoss !== 0 ? Math.abs(avgWin / avgLoss) : null;

  // Max consecutive losses
  let maxConsec = 0;
  let current = 0;
  for (const t of trades) {
    if (t.pnl < 0) {
      current++;
      if (current > maxConsec) maxConsec = current;
    } else {
      current = 0;
    }
  }

  // Avg trade duration
  const avgDuration = trades.reduce((s, t) => s + t.bars_held, 0) / trades.length;

  return { avgWinLoss, maxConsecutiveLosses: maxConsec, avgTradeDuration: avgDuration };
}

function MetricCard({ label, value, colorClass }: { label: string; value: string; colorClass?: string }) {
  return (
    <div className="bg-surface-1/50 border border-border rounded-lg p-3">
      <p className="text-xs text-text-muted mb-1">{label}</p>
      <p className={`text-sm font-semibold ${colorClass ?? 'text-text-primary'}`}>{value}</p>
    </div>
  );
}

function ExtendedMetricsGrid({ metrics, trades }: { metrics: BacktestMetrics; trades: BacktestTradeComplete[] }) {
  const derived = useMemo(() => computeDerivedMetrics(trades), [trades]);

  // Return / DD
  const returnPct = metrics.return_pct as number | undefined;
  const maxDdPct = metrics.max_drawdown_pct as number | undefined;
  let ratioValue: string;
  let ratioColor: string;
  if (returnPct != null && maxDdPct != null && maxDdPct !== 0) {
    const ratio = returnPct / maxDdPct;
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

  // Max DD %
  let ddPctValue: string;
  if (maxDdPct != null) {
    ddPctValue = formatPercent(maxDdPct);
  } else {
    const absDd = metrics.max_drawdown as number | undefined;
    const initialEquity = metrics.initial_equity as number | undefined;
    if (absDd != null && initialEquity != null && initialEquity !== 0) {
      ddPctValue = formatPercent(Math.abs(absDd) / initialEquity * 100);
    } else {
      ddPctValue = 'N/A';
    }
  }

  const winRate = metrics.win_rate ?? 0;
  const sharpe = metrics.sharpe_ratio;
  const trades_count = metrics.total_trades ?? metrics.trade_count ?? 0;
  const profitFactor = metrics.profit_factor;
  const sortino = metrics.sortino_ratio;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
      <MetricCard label="Return / DD" value={ratioValue} colorClass={ratioColor} />
      <MetricCard label="Win Rate" value={formatPercent(winRate)} colorClass={winRate >= 50 ? 'text-accent' : 'text-danger'} />
      <MetricCard label="Max DD %" value={ddPctValue} colorClass="text-danger" />
      <MetricCard label="Sharpe" value={sharpe != null ? sharpe.toFixed(2) : 'N/A'} colorClass={sharpe != null && sharpe > 0 ? 'text-accent' : 'text-danger'} />
      <MetricCard label="Total Trades" value={String(trades_count)} />
      <MetricCard label="Profit Factor" value={profitFactor != null ? profitFactor.toFixed(2) : 'N/A'} colorClass={profitFactor != null && profitFactor > 1 ? 'text-accent' : 'text-danger'} />
      <MetricCard label="Sortino" value={sortino != null ? sortino.toFixed(2) : 'N/A'} colorClass={sortino != null && sortino > 0 ? 'text-accent' : 'text-danger'} />
      <MetricCard label="Avg Win / Loss" value={derived.avgWinLoss != null ? derived.avgWinLoss.toFixed(2) : 'N/A'} colorClass={derived.avgWinLoss != null && derived.avgWinLoss > 1 ? 'text-accent' : 'text-danger'} />
      <MetricCard label="Max Consec. Losses" value={String(derived.maxConsecutiveLosses)} colorClass={derived.maxConsecutiveLosses > 5 ? 'text-danger' : 'text-text-primary'} />
      <MetricCard label="Avg Duration" value={derived.avgTradeDuration != null ? `${derived.avgTradeDuration.toFixed(1)} bars` : 'N/A'} />
    </div>
  );
}

function ReportEquityCurve({ trades }: { trades: BacktestTradeComplete[] }) {
  const data = useMemo(() => {
    const sorted = [...trades].sort(
      (a, b) => new Date(a.exit_date).getTime() - new Date(b.exit_date).getTime(),
    );
    return sorted.map((t) => ({
      date: t.exit_date,
      cumPnl: Number(t.cumulative_pnl.toFixed(2)),
    }));
  }, [trades]);

  if (data.length === 0) {
    return (
      <div className="border border-border rounded-lg p-6 bg-surface-1/30 text-center">
        <p className="text-sm text-text-muted">No trades to display</p>
      </div>
    );
  }

  const finalPnl = data[data.length - 1].cumPnl;
  const lineColor = finalPnl >= 0 ? 'var(--color-accent)' : 'var(--color-danger)';

  return (
    <div className="border border-border rounded-lg p-4 bg-surface-1/30">
      <h3 className="text-sm font-semibold text-text-primary mb-3">Equity Curve</h3>
      <ResponsiveContainer width="100%" height={300}>
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
            stroke={lineColor}
            strokeWidth={1.5}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function TradesTable({ trades }: { trades: BacktestTradeComplete[] }) {
  const [sortField, setSortField] = useState<SortField>('entry_date');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const sorted = useMemo(() => {
    const arr = [...trades];
    arr.sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];
      let cmp = 0;
      if (typeof aVal === 'string' && typeof bVal === 'string') {
        cmp = aVal.localeCompare(bVal);
      } else {
        cmp = (aVal as number) - (bVal as number);
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return arr;
  }, [trades, sortField, sortDir]);

  if (trades.length === 0) {
    return (
      <div className="border border-border rounded-lg p-6 bg-surface-1/30 text-center">
        <p className="text-sm text-text-muted">No trades recorded</p>
      </div>
    );
  }

  const SortHeader = ({ field, label, align }: { field: SortField; label: string; align?: string }) => (
    <th
      className={`${align === 'right' ? 'text-right' : 'text-left'} px-2 py-2 text-text-muted font-medium cursor-pointer hover:text-text-secondary transition-colors select-none`}
      onClick={() => toggleSort(field)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {sortField === field && (
          <ArrowUpDown size={10} className="text-accent" />
        )}
      </span>
    </th>
  );

  return (
    <div className="border border-border rounded-lg bg-surface-1/30">
      <h3 className="text-sm font-semibold text-text-primary p-4 pb-2">Trades ({trades.length})</h3>
      <div className="max-h-96 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="bg-surface-2/50 sticky top-0">
            <tr>
              <th className="text-left px-2 py-2 text-text-muted font-medium">#</th>
              <SortHeader field="entry_date" label="Entry Date" />
              <SortHeader field="exit_date" label="Exit Date" />
              <SortHeader field="side" label="Direction" />
              <SortHeader field="entry_fill_price" label="Entry $" align="right" />
              <SortHeader field="exit_fill_price" label="Exit $" align="right" />
              <SortHeader field="pnl" label="PnL" align="right" />
              <SortHeader field="cumulative_pnl" label="Cum. PnL" align="right" />
              <SortHeader field="exit_reason" label="Exit Reason" />
              <SortHeader field="bars_held" label="Bars" align="right" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((trade, i) => (
              <tr key={i} className="border-t border-border/50 hover:bg-surface-1/30">
                <td className="px-2 py-1.5 text-text-muted">{i + 1}</td>
                <td className="px-2 py-1.5 text-text-secondary">{trade.entry_date}</td>
                <td className="px-2 py-1.5 text-text-secondary">{trade.exit_date}</td>
                <td className="px-2 py-1.5">
                  <span className={`font-medium ${trade.side === 'long' ? 'text-accent' : 'text-danger'}`}>
                    {trade.side === 'long' ? 'Long' : 'Short'}
                  </span>
                </td>
                <td className="px-2 py-1.5 text-right text-text-secondary">{trade.entry_fill_price.toFixed(2)}</td>
                <td className="px-2 py-1.5 text-right text-text-secondary">{trade.exit_fill_price.toFixed(2)}</td>
                <td className={`px-2 py-1.5 text-right font-medium ${trade.pnl >= 0 ? 'text-accent' : 'text-danger'}`}>
                  {formatCurrency(trade.pnl)}
                </td>
                <td className={`px-2 py-1.5 text-right font-medium ${trade.cumulative_pnl >= 0 ? 'text-accent' : 'text-danger'}`}>
                  {formatCurrency(trade.cumulative_pnl)}
                </td>
                <td className="px-2 py-1.5 text-text-secondary">{trade.exit_reason}</td>
                <td className="px-2 py-1.5 text-right text-text-secondary">{trade.bars_held}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function BacktestReportDrawer({ jobId, open, onClose }: BacktestReportDrawerProps) {
  const { data: job } = useQuery({
    queryKey: ['backtest', jobId],
    queryFn: () => getBacktest(jobId),
    enabled: open,
  });

  // Lock body scroll when open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  // Close on Escape
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (open) {
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open, handleKeyDown]);

  if (!open) return null;

  const metrics = job?.result?.metrics as BacktestMetrics | undefined;
  const trades = (job?.result?.trades ?? []) as unknown as BacktestTradeComplete[];

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 transition-opacity"
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div className="relative w-4/5 max-w-[1400px] h-full bg-surface-0 border-l border-border shadow-2xl overflow-y-auto animate-slide-in-right">
        {/* Header */}
        <div className="sticky top-0 z-10 bg-surface-0 border-b border-border px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-text-primary">
              Backtest Report
              {job && (
                <span className="ml-2 text-sm font-normal text-text-muted">
                  #{job.id}
                </span>
              )}
            </h2>
            {job && (
              <p className="text-xs text-text-muted mt-1">
                {job.symbol} &middot; {job.timeframe} &middot; {job.start_date} &rarr; {job.end_date}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 text-text-muted hover:text-text-primary transition-colors rounded hover:bg-surface-2"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-6">
          {!job?.result ? (
            <p className="text-sm text-text-muted italic">Loading report data...</p>
          ) : (
            <>
              {/* Metrics */}
              {metrics && (
                <div>
                  <h3 className="text-sm font-semibold text-text-primary mb-3">Metrics</h3>
                  <ExtendedMetricsGrid metrics={metrics} trades={trades} />
                </div>
              )}

              {/* Equity Curve */}
              <ReportEquityCurve trades={trades} />

              {/* Trades Table */}
              <TradesTable trades={trades} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
