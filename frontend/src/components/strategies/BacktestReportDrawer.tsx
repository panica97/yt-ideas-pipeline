import { useState, useEffect, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { X, ArrowUpDown, Shuffle, TrendingDown, DollarSign, Percent, ShieldAlert, BarChart3, Table, Activity, Target } from 'lucide-react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
  AreaChart, Area, BarChart, Bar, Cell, ReferenceLine,
  ScatterChart, Scatter,
} from 'recharts';
import { getBacktest } from '../../services/backtests';
import type { BacktestTradeComplete, BacktestMetrics, MonteCarloMetrics, MCDistribution } from '../../types/backtest';

interface BacktestReportDrawerProps {
  jobId: number;
  open: boolean;
  onClose: () => void;
}

type SortField = 'entry_date' | 'exit_date' | 'side' | 'entry_fill_price' | 'exit_fill_price' | 'pnl' | 'cumulative_pnl' | 'exit_reason' | 'bars_held';
type SortDir = 'asc' | 'desc';

function formatCurrency(value: number | string | null | undefined): string {
  if (value == null) return 'N/A';
  const n = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(n)) return 'N/A';
  const sign = n >= 0 ? '+' : '';
  return `${sign}$${n.toFixed(2)}`;
}

function formatPercent(value: number | string | null | undefined): string {
  if (value == null) return 'N/A';
  const n = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(n)) return 'N/A';
  return `${n.toFixed(1)}%`;
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
      <MetricCard label="Sharpe" value={sharpe != null ? Number(sharpe).toFixed(2) : 'N/A'} colorClass={sharpe != null && Number(sharpe) > 0 ? 'text-accent' : 'text-danger'} />
      <MetricCard label="Total Trades" value={String(trades_count)} />
      <MetricCard label="Profit Factor" value={profitFactor != null ? Number(profitFactor).toFixed(2) : 'N/A'} colorClass={profitFactor != null && Number(profitFactor) > 1 ? 'text-accent' : 'text-danger'} />
      <MetricCard label="Sortino" value={sortino != null ? Number(sortino).toFixed(2) : 'N/A'} colorClass={sortino != null && Number(sortino) > 0 ? 'text-accent' : 'text-danger'} />
      <MetricCard label="Avg Win / Loss" value={derived.avgWinLoss != null ? Number(derived.avgWinLoss).toFixed(2) : 'N/A'} colorClass={derived.avgWinLoss != null && Number(derived.avgWinLoss) > 1 ? 'text-accent' : 'text-danger'} />
      <MetricCard label="Max Consec. Losses" value={String(derived.maxConsecutiveLosses)} colorClass={derived.maxConsecutiveLosses > 5 ? 'text-danger' : 'text-text-primary'} />
      <MetricCard label="Avg Duration" value={derived.avgTradeDuration != null ? `${Number(derived.avgTradeDuration).toFixed(1)} bars` : 'N/A'} />
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
      cumPnl: Number((t.cumulative_pnl ?? 0).toFixed(2)),
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
  const lineColor = finalPnl >= 0 ? '#10b981' : '#ef4444';

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
                <td className="px-2 py-1.5 text-right text-text-secondary">{(trade.entry_fill_price ?? 0).toFixed(2)}</td>
                <td className="px-2 py-1.5 text-right text-text-secondary">{(trade.exit_fill_price ?? 0).toFixed(2)}</td>
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

// ─── Monte Carlo Report Components ───────────────────────────────────

// Shared tooltip style
const mcTooltipStyle = {
  backgroundColor: 'var(--color-surface-2)',
  border: '1px solid var(--color-border)',
  borderRadius: '0.375rem',
  fontSize: '0.75rem',
};

interface FanChartPoint {
  step: number;
  p5: number;
  p25: number;
  p50: number;
  p75: number;
  p95: number;
  [key: string]: number;
}

/** Compute histogram bins from a raw array of numbers */
interface HistogramBin {
  binStart: number;
  binEnd: number;
  label: string;
  count: number;
}

function buildHistogramBins(values: number[], nBins: number = 20, labelPrefix: string = ''): HistogramBin[] {
  if (!values || values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return [{ binStart: min, binEnd: max, label: `${labelPrefix}${Number(min).toFixed(1)}`, count: values.length }];

  const binWidth = (max - min) / nBins;
  const result: HistogramBin[] = [];
  for (let i = 0; i < nBins; i++) {
    const binStart = min + i * binWidth;
    const binEnd = i === nBins - 1 ? max + 0.01 : min + (i + 1) * binWidth;
    const count = values.filter(v => v >= binStart && v < binEnd).length;
    result.push({
      binStart,
      binEnd,
      label: `${labelPrefix}${Number(binStart).toFixed(1)}`,
      count,
    });
  }
  return result;
}

/** Percentile rank: what % of distribution is <= value. Higher-is-better or lower-is-better handled by caller. */
function percentileRank(values: number[] | undefined, actual: number): number | null {
  if (!values || values.length === 0) return null;
  const count = values.filter(v => v <= actual).length;
  return (count / values.length) * 100;
}

// ── 1. Key Stats Cards ──────────────────────────────────────────────

function MCSummaryCards({ mc }: { mc: MonteCarloMetrics }) {
  const medianPnl = Number(mc.total_pnl?.median ?? mc.total_pnl?.p50 ?? 0);
  const medianDD = Number(mc.max_drawdown_pct?.median ?? mc.max_drawdown_pct?.p50 ?? 0);
  const probLoss = Number(mc.risk_metrics?.prob_negative_return ?? 0);
  const var95 = Number(mc.risk_metrics?.var_95 ?? 0);

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <div className="bg-surface-1/50 border border-border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-2">
          <DollarSign size={14} className="text-text-muted" />
          <p className="text-xs text-text-muted">Median PnL</p>
        </div>
        <p className={`text-lg font-bold ${medianPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {medianPnl >= 0 ? '+' : ''}${medianPnl.toFixed(2)}
        </p>
      </div>
      <div className="bg-surface-1/50 border border-border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-2">
          <TrendingDown size={14} className="text-text-muted" />
          <p className="text-xs text-text-muted">Median Max DD</p>
        </div>
        <p className="text-lg font-bold text-red-400">
          {medianDD.toFixed(1)}%
        </p>
      </div>
      <div className="bg-surface-1/50 border border-border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-2">
          <Percent size={14} className="text-text-muted" />
          <p className="text-xs text-text-muted">Probability of Loss</p>
        </div>
        <p className={`text-lg font-bold ${probLoss > 0.5 ? 'text-red-400' : probLoss > 0.3 ? 'text-amber-400' : 'text-green-400'}`}>
          {(probLoss * 100).toFixed(1)}%
        </p>
      </div>
      <div className="bg-surface-1/50 border border-border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-2">
          <ShieldAlert size={14} className="text-text-muted" />
          <p className="text-xs text-text-muted">VaR 95%</p>
        </div>
        <p className="text-lg font-bold text-red-400">
          ${var95.toFixed(2)}
        </p>
      </div>
    </div>
  );
}

function MCSimulationSummary({ mc }: { mc: MonteCarloMetrics }) {
  const nPaths = mc.n_paths ?? 0;
  const nCompleted = mc.n_completed ?? nPaths;
  const failureRate = Number(mc.failure_rate ?? 0);

  const colorClass = failureRate > 0.1 ? 'text-amber-400' : 'text-green-400';
  const bgClass = failureRate > 0.1 ? 'border-amber-500/30 bg-amber-500/5' : 'border-green-500/30 bg-green-500/5';

  return (
    <div className={`border rounded-lg p-4 ${bgClass}`}>
      <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
        <Shuffle size={14} />
        Simulation Summary
      </h3>
      <div className="grid grid-cols-3 gap-4">
        <div>
          <p className="text-xs text-text-muted mb-1">Paths Requested</p>
          <p className="text-lg font-bold text-text-primary">{nPaths}</p>
        </div>
        <div>
          <p className="text-xs text-text-muted mb-1">Paths Completed</p>
          <p className={`text-lg font-bold ${colorClass}`}>{nCompleted}</p>
        </div>
        <div>
          <p className="text-xs text-text-muted mb-1">Failure Rate</p>
          <p className={`text-lg font-bold ${colorClass}`}>{(failureRate * 100).toFixed(1)}%</p>
        </div>
      </div>
    </div>
  );
}

// ── 2. Strategy Scorecard Table ─────────────────────────────────────

function MCScorecard({ mc }: { mc: MonteCarloMetrics }) {
  const rows = useMemo(() => {
    const defs: {
      label: string;
      distKey: keyof MonteCarloMetrics;
      rawKey: string;
      fmt: (v: number) => string;
      higherIsBetter: boolean;
    }[] = [
      { label: 'Total PnL', distKey: 'total_pnl', rawKey: 'total_pnl', fmt: (v) => `$${Number(v).toFixed(2)}`, higherIsBetter: true },
      { label: 'Max DD %', distKey: 'max_drawdown_pct', rawKey: 'max_drawdown_pct', fmt: (v) => `${Number(v).toFixed(1)}%`, higherIsBetter: false },
      { label: 'Sharpe', distKey: 'sharpe_ratio', rawKey: 'sharpe_ratio', fmt: (v) => Number(v).toFixed(2), higherIsBetter: true },
      { label: 'Win Rate', distKey: 'win_rate', rawKey: 'win_rate', fmt: (v) => `${Number(v).toFixed(1)}%`, higherIsBetter: true },
      { label: 'Profit Factor', distKey: 'profit_factor', rawKey: 'profit_factor', fmt: (v) => Number(v).toFixed(2), higherIsBetter: true },
      { label: 'Avg Trade PnL', distKey: 'avg_trade_pnl', rawKey: 'avg_trade_pnl', fmt: (v) => `$${Number(v).toFixed(2)}`, higherIsBetter: true },
    ];

    return defs.map((d) => {
      const dist = mc[d.distKey] as MCDistribution | undefined;
      const rawArr = mc.raw_metrics?.[d.rawKey];
      // Use median as "actual" if no separate baseline
      const actual = dist?.median ?? dist?.p50;
      const rank = rawArr && actual != null ? percentileRank(rawArr, actual) : null;

      return {
        label: d.label,
        dist,
        actual: actual != null ? d.fmt(actual) : 'N/A',
        rank,
        higherIsBetter: d.higherIsBetter,
        fmt: d.fmt,
      };
    });
  }, [mc]);

  function rankColor(rank: number | null, higherIsBetter: boolean): string {
    if (rank == null) return 'text-text-secondary';
    // For higher-is-better, high rank is good. For lower-is-better, low rank is good.
    const effective = higherIsBetter ? rank : 100 - rank;
    if (effective >= 60) return 'text-green-400';
    if (effective >= 40) return 'text-amber-400';
    return 'text-red-400';
  }

  return (
    <div className="border border-border rounded-lg bg-surface-1/30">
      <h3 className="text-sm font-semibold text-text-primary p-4 pb-2 flex items-center gap-2">
        <Table size={14} />
        Strategy Scorecard
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-surface-2/50">
            <tr>
              <th className="text-left px-3 py-2 text-text-muted font-medium">Metric</th>
              <th className="text-right px-3 py-2 text-text-muted font-medium">Actual</th>
              <th className="text-right px-3 py-2 text-text-muted font-medium">Rank</th>
              <th className="text-right px-3 py-2 text-text-muted font-medium">P5</th>
              <th className="text-right px-3 py-2 text-text-muted font-medium">P25</th>
              <th className="text-right px-3 py-2 text-text-muted font-medium">P50</th>
              <th className="text-right px-3 py-2 text-text-muted font-medium">P75</th>
              <th className="text-right px-3 py-2 text-text-muted font-medium">P95</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              if (!row.dist) return null;
              return (
                <tr key={row.label} className="border-t border-border/50">
                  <td className="px-3 py-2 text-text-secondary font-medium">{row.label}</td>
                  <td className={`px-3 py-2 text-right font-semibold ${rankColor(row.rank, row.higherIsBetter)}`}>
                    {row.actual}
                  </td>
                  <td className={`px-3 py-2 text-right font-semibold ${rankColor(row.rank, row.higherIsBetter)}`}>
                    {row.rank != null ? `P${Number(row.rank).toFixed(0)}` : '—'}
                  </td>
                  <td className="px-3 py-2 text-right text-text-secondary">{row.fmt(Number(row.dist.p5))}</td>
                  <td className="px-3 py-2 text-right text-text-secondary">{row.fmt(Number(row.dist.p25))}</td>
                  <td className="px-3 py-2 text-right text-text-primary font-semibold">{row.fmt(Number(row.dist.p50 ?? row.dist.median))}</td>
                  <td className="px-3 py-2 text-right text-text-secondary">{row.fmt(Number(row.dist.p75))}</td>
                  <td className="px-3 py-2 text-right text-text-secondary">{row.fmt(Number(row.dist.p95))}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── 3. Distribution Histograms (2x2 grid) ──────────────────────────

function MCDistributionHistogram({
  title,
  values,
  color,
  labelPrefix,
  medianValue,
}: {
  title: string;
  values: number[] | undefined;
  color: string;
  labelPrefix?: string;
  medianValue?: number;
}) {
  const bins = useMemo(() => buildHistogramBins(values ?? [], 20, labelPrefix ?? ''), [values, labelPrefix]);

  if (bins.length === 0) {
    return (
      <div className="border border-border rounded-lg p-6 bg-surface-1/30 text-center">
        <p className="text-sm text-text-muted">No data for {title}</p>
      </div>
    );
  }

  return (
    <div className="border border-border rounded-lg p-4 bg-surface-1/30">
      <h3 className="text-sm font-semibold text-text-primary mb-3">{title}</h3>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={bins} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 9, fill: '#9ca3af' }}
            tickLine={false}
            interval={Math.max(0, Math.floor(bins.length / 5) - 1)}
          />
          <YAxis
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            tickLine={false}
          />
          <Tooltip
            contentStyle={mcTooltipStyle}
            formatter={(value) => [`${value} paths`, 'Count']}
            labelFormatter={(label) => `${title}: ${label}`}
          />
          <Bar dataKey="count" radius={[2, 2, 0, 0]}>
            {bins.map((_, i) => (
              <Cell key={i} fill={color} fillOpacity={0.7} />
            ))}
          </Bar>
          {medianValue != null && (
            <ReferenceLine
              x={bins.reduce((closest, b) =>
                Math.abs(b.binStart - medianValue) < Math.abs(closest.binStart - medianValue) ? b : closest
              , bins[0]).label}
              stroke="#f59e0b"
              strokeWidth={2}
              strokeDasharray="5 3"
              label={{ value: 'Median', position: 'top', fill: '#f59e0b', fontSize: 10 }}
            />
          )}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function MCDistributionsGrid({ mc }: { mc: MonteCarloMetrics }) {
  const medianPnl = Number(mc.total_pnl?.median ?? mc.total_pnl?.p50 ?? undefined);
  const medianDD = Number(mc.max_drawdown_pct?.median ?? mc.max_drawdown_pct?.p50 ?? undefined);
  const medianSharpe = Number(mc.sharpe_ratio?.median ?? mc.sharpe_ratio?.p50 ?? undefined);
  const medianAvgPnl = Number(mc.avg_trade_pnl?.median ?? mc.avg_trade_pnl?.p50 ?? undefined);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <MCDistributionHistogram
        title="PnL Distribution"
        values={mc.raw_metrics?.total_pnl}
        color="#10b981"
        labelPrefix="$"
        medianValue={isNaN(medianPnl) ? undefined : medianPnl}
      />
      <MCDistributionHistogram
        title="Max Drawdown Distribution"
        values={mc.raw_metrics?.max_drawdown_pct}
        color="#ef4444"
        medianValue={isNaN(medianDD) ? undefined : medianDD}
      />
      <MCDistributionHistogram
        title="Sharpe Ratio Distribution"
        values={mc.raw_metrics?.sharpe_ratio}
        color="#6366f1"
        medianValue={isNaN(medianSharpe) ? undefined : medianSharpe}
      />
      <MCDistributionHistogram
        title="Avg PnL/Trade Distribution"
        values={mc.raw_metrics?.avg_trade_pnl}
        color="#14b8a6"
        labelPrefix="$"
        medianValue={isNaN(medianAvgPnl) ? undefined : medianAvgPnl}
      />
    </div>
  );
}

// ── 4. Win Rate vs Profit Factor Scatter ────────────────────────────

function MCScatterWinRateVsPF({ mc }: { mc: MonteCarloMetrics }) {
  const data = useMemo(() => {
    const wr = mc.raw_metrics?.win_rate;
    const pf = mc.raw_metrics?.profit_factor;
    if (!wr || !pf) return [];
    const len = Math.min(wr.length, pf.length);
    return Array.from({ length: len }, (_, i) => ({
      winRate: Number(wr[i]),
      profitFactor: Number(pf[i]),
    }));
  }, [mc.raw_metrics]);

  if (data.length === 0) {
    return (
      <div className="border border-border rounded-lg p-6 bg-surface-1/30 text-center">
        <p className="text-sm text-text-muted">No scatter data available</p>
      </div>
    );
  }

  return (
    <div className="border border-border rounded-lg p-4 bg-surface-1/30">
      <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
        <Target size={14} />
        Win Rate vs Profit Factor
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart margin={{ top: 10, right: 10, left: 10, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            type="number"
            dataKey="winRate"
            name="Win Rate"
            unit="%"
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            tickLine={false}
            label={{ value: 'Win Rate %', position: 'insideBottom', offset: -5, fontSize: 10, fill: '#9ca3af' }}
          />
          <YAxis
            type="number"
            dataKey="profitFactor"
            name="Profit Factor"
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            tickLine={false}
            label={{ value: 'Profit Factor', angle: -90, position: 'insideLeft', fontSize: 10, fill: '#9ca3af' }}
          />
          <Tooltip
            contentStyle={mcTooltipStyle}
            formatter={(value, name) => {
              if (name === 'Win Rate') return [`${Number(value).toFixed(1)}%`, name];
              return [Number(value).toFixed(2), String(name)];
            }}
          />
          <ReferenceLine x={50} stroke="#f59e0b" strokeDasharray="5 3" strokeOpacity={0.6} />
          <ReferenceLine y={1} stroke="#f59e0b" strokeDasharray="5 3" strokeOpacity={0.6} />
          <Scatter data={data} fill="#3b82f6" fillOpacity={0.5} r={3} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── 5. Equity Fan Chart (enhanced with sampled paths) ───────────────

function MCFanChart({ mc }: { mc: MonteCarloMetrics }) {
  const { fanData, sampledPaths } = useMemo(() => {
    const ecp = mc.equity_curve_percentiles;
    if (!ecp?.p50 || ecp.p50.length === 0) return { fanData: [] as FanChartPoint[], sampledPaths: [] as number[][] };

    const len = ecp.p50.length;
    const fd: FanChartPoint[] = Array.from({ length: len }, (_, i) => ({
      step: i,
      p5: Number(ecp.p5?.[i] ?? ecp.p50![i]),
      p25: Number(ecp.p25?.[i] ?? ecp.p50![i]),
      p50: Number(ecp.p50![i]),
      p75: Number(ecp.p75?.[i] ?? ecp.p50![i]),
      p95: Number(ecp.p95?.[i] ?? ecp.p50![i]),
    }));

    // Add sampled paths (max 20) as columns on each data point
    const sp = mc.sampled_paths ?? [];
    const limitedPaths = sp.slice(0, 20);
    limitedPaths.forEach((path, pi) => {
      fd.forEach((point, si) => {
        point[`s${pi}`] = Number(path?.[si] ?? 0);
      });
    });

    return { fanData: fd, sampledPaths: limitedPaths };
  }, [mc.equity_curve_percentiles, mc.sampled_paths]);

  if (fanData.length === 0) {
    return (
      <div className="border border-border rounded-lg p-6 bg-surface-1/30 text-center">
        <p className="text-sm text-text-muted">No equity curve data available</p>
      </div>
    );
  }

  return (
    <div className="border border-border rounded-lg p-4 bg-surface-1/30">
      <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
        <TrendingDown size={14} />
        Equity Curve Fan Chart
      </h3>
      <ResponsiveContainer width="100%" height={350}>
        <AreaChart data={fanData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="step"
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            tickLine={false}
            label={{ value: 'Step', position: 'insideBottom', offset: -2, fontSize: 10, fill: '#9ca3af' }}
          />
          <YAxis
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            tickLine={false}
            tickFormatter={(v: number) => `$${Number(v ?? 0).toFixed(0)}`}
          />
          <Tooltip
            contentStyle={mcTooltipStyle}
            labelStyle={{ color: '#9ca3af' }}
            formatter={(value, name) => {
              const labels: Record<string, string> = {
                p5: 'P5', p25: 'P25', p50: 'P50 (Median)', p75: 'P75', p95: 'P95',
              };
              if (String(name).startsWith('s')) return null;
              return [`$${Number(value).toFixed(2)}`, labels[String(name)] ?? String(name)];
            }}
          />
          {/* Sampled paths as very light background lines */}
          {sampledPaths.map((_, pi) => (
            <Line
              key={`s${pi}`}
              type="monotone"
              dataKey={`s${pi}`}
              stroke="#3b82f6"
              strokeWidth={0.5}
              strokeOpacity={0.12}
              dot={false}
              activeDot={false}
              legendType="none"
            />
          ))}
          {/* P5-P95 band */}
          <Area type="monotone" dataKey="p95" stackId="band" stroke="none" fill="#3b82f6" fillOpacity={0.08} />
          <Area type="monotone" dataKey="p5" stackId="band2" stroke="none" fill="transparent" fillOpacity={0} />
          {/* P25-P75 band */}
          <Area type="monotone" dataKey="p75" stroke="none" fill="#3b82f6" fillOpacity={0.15} />
          <Area type="monotone" dataKey="p25" stroke="none" fill="#3b82f6" fillOpacity={0.08} />
          {/* P50 median line */}
          <Line type="monotone" dataKey="p50" stroke="#3b82f6" strokeWidth={2} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
      <div className="flex items-center gap-4 mt-2 text-xs text-text-muted justify-center">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded" style={{ backgroundColor: '#3b82f6', opacity: 0.08 }} /> P5-P95
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded" style={{ backgroundColor: '#3b82f6', opacity: 0.3 }} /> P25-P75
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-2 rounded" style={{ backgroundColor: '#3b82f6' }} /> Median
        </span>
        {sampledPaths.length > 0 && (
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-0.5 rounded" style={{ backgroundColor: '#3b82f6', opacity: 0.3 }} /> Sampled Paths
          </span>
        )}
      </div>
    </div>
  );
}

// ── 6. Drawdown Cone ────────────────────────────────────────────────

function MCDrawdownCone({ mc }: { mc: MonteCarloMetrics }) {
  const data = useMemo(() => {
    const dcp = mc.drawdown_curve_percentiles;
    if (!dcp?.p50 || dcp.p50.length === 0) return [];
    const len = dcp.p50.length;
    return Array.from({ length: len }, (_, i) => ({
      step: i,
      p5: Number(dcp.p5?.[i] ?? dcp.p50![i]),
      p25: Number(dcp.p25?.[i] ?? dcp.p50![i]),
      p50: Number(dcp.p50![i]),
      p75: Number(dcp.p75?.[i] ?? dcp.p50![i]),
      p95: Number(dcp.p95?.[i] ?? dcp.p50![i]),
    }));
  }, [mc.drawdown_curve_percentiles]);

  if (data.length === 0) return null;

  return (
    <div className="border border-border rounded-lg p-4 bg-surface-1/30">
      <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
        <TrendingDown size={14} />
        Drawdown Cone
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="step"
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            tickLine={false}
            label={{ value: 'Step', position: 'insideBottom', offset: -2, fontSize: 10, fill: '#9ca3af' }}
          />
          <YAxis
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            tickLine={false}
            tickFormatter={(v: number) => `${Number(v ?? 0).toFixed(0)}%`}
            reversed
          />
          <Tooltip
            contentStyle={mcTooltipStyle}
            labelStyle={{ color: '#9ca3af' }}
            formatter={(value, name) => {
              const labels: Record<string, string> = {
                p5: 'P5', p25: 'P25', p50: 'P50 (Median)', p75: 'P75', p95: 'P95',
              };
              return [`${Number(value).toFixed(2)}%`, labels[String(name)] ?? String(name)];
            }}
          />
          {/* P5-P95 band */}
          <Area type="monotone" dataKey="p95" stackId="ddband" stroke="none" fill="#ef4444" fillOpacity={0.08} />
          <Area type="monotone" dataKey="p5" stackId="ddband2" stroke="none" fill="transparent" fillOpacity={0} />
          {/* P25-P75 band */}
          <Area type="monotone" dataKey="p75" stroke="none" fill="#ef4444" fillOpacity={0.15} />
          <Area type="monotone" dataKey="p25" stroke="none" fill="#ef4444" fillOpacity={0.08} />
          {/* P50 median line */}
          <Line type="monotone" dataKey="p50" stroke="#ef4444" strokeWidth={2} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
      <div className="flex items-center gap-4 mt-2 text-xs text-text-muted justify-center">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded" style={{ backgroundColor: '#ef4444', opacity: 0.08 }} /> P5-P95
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded" style={{ backgroundColor: '#ef4444', opacity: 0.3 }} /> P25-P75
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-2 rounded" style={{ backgroundColor: '#ef4444' }} /> Median DD
        </span>
      </div>
    </div>
  );
}

// ── 7. Price Paths Chart ────────────────────────────────────────────

function MCPricePaths({ mc }: { mc: MonteCarloMetrics }) {
  const data = useMemo(() => {
    const historical = mc.historical_close;
    const sampledPaths = mc.sampled_close_paths;
    if (!historical || historical.length === 0) return [];

    const maxLen = Math.max(
      historical.length,
      ...(sampledPaths ?? []).map(p => p?.length ?? 0),
    );

    const limited = (sampledPaths ?? []).slice(0, 30);

    return Array.from({ length: maxLen }, (_, i) => {
      const point: Record<string, number | null> = { step: i };
      point.historical = i < historical.length ? Number(historical[i]) : null;
      limited.forEach((path, pi) => {
        point[`p${pi}`] = path?.[i] != null ? Number(path[i]) : null;
      });
      return point;
    });
  }, [mc.historical_close, mc.sampled_close_paths]);

  if (data.length === 0) return null;

  const pathCount = Math.min((mc.sampled_close_paths ?? []).length, 30);

  return (
    <div className="border border-border rounded-lg p-4 bg-surface-1/30">
      <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
        <Activity size={14} />
        Synthetic Price Paths
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="step"
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            tickLine={false}
            tickFormatter={(v: number) => `$${Number(v ?? 0).toFixed(0)}`}
          />
          <Tooltip
            contentStyle={mcTooltipStyle}
            labelStyle={{ color: '#9ca3af' }}
            formatter={(value, name) => {
              if (name === 'historical') return [`$${Number(value).toFixed(2)}`, 'Historical'];
              return null;
            }}
          />
          {/* Sampled price paths */}
          {Array.from({ length: pathCount }, (_, pi) => (
            <Line
              key={`p${pi}`}
              type="monotone"
              dataKey={`p${pi}`}
              stroke="#3b82f6"
              strokeWidth={0.8}
              strokeOpacity={0.25}
              dot={false}
              activeDot={false}
              connectNulls={false}
              legendType="none"
            />
          ))}
          {/* Historical close (bold red) */}
          <Line
            type="monotone"
            dataKey="historical"
            stroke="#ef4444"
            strokeWidth={2.5}
            dot={false}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <div className="flex items-center gap-4 mt-2 text-xs text-text-muted justify-center">
        <span className="flex items-center gap-1">
          <span className="inline-block w-4 h-0.5 rounded" style={{ backgroundColor: '#ef4444' }} /> Historical
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-4 h-0.5 rounded" style={{ backgroundColor: '#3b82f6', opacity: 0.4 }} /> Synthetic ({pathCount})
        </span>
      </div>
    </div>
  );
}

// ── 8. Risk Metrics Table (unchanged) ───────────────────────────────

function MCRiskTable({ mc }: { mc: MonteCarloMetrics }) {
  const rm = mc.risk_metrics;
  if (!rm) return null;

  const probNeg = Number(rm.prob_negative_return ?? 0);
  const probDd10 = Number(rm.prob_dd_10 ?? 0);
  const probDd20 = Number(rm.prob_dd_20 ?? 0);
  const probDd30 = Number(rm.prob_dd_30 ?? 0);
  const probDd50 = Number(rm.prob_dd_50 ?? 0);
  const var95 = Number(rm.var_95 ?? 0);
  const cvar95 = Number(rm.cvar_95 ?? 0);

  const rows = [
    { label: 'Probability of negative return', value: `${(probNeg * 100).toFixed(1)}%`, color: probNeg > 0.5 ? 'text-red-400' : 'text-green-400' },
    ...(rm.prob_dd_10 != null ? [{ label: 'Probability of >10% drawdown', value: `${(probDd10 * 100).toFixed(1)}%`, color: probDd10 > 0.5 ? 'text-red-400' : probDd10 > 0.3 ? 'text-amber-400' : 'text-green-400' }] : []),
    ...(rm.prob_dd_20 != null ? [{ label: 'Probability of >20% drawdown', value: `${(probDd20 * 100).toFixed(1)}%`, color: probDd20 > 0.5 ? 'text-red-400' : probDd20 > 0.3 ? 'text-amber-400' : 'text-green-400' }] : []),
    ...(rm.prob_dd_30 != null ? [{ label: 'Probability of >30% drawdown', value: `${(probDd30 * 100).toFixed(1)}%`, color: probDd30 > 0.3 ? 'text-red-400' : probDd30 > 0.15 ? 'text-amber-400' : 'text-green-400' }] : []),
    ...(rm.prob_dd_50 != null ? [{ label: 'Probability of >50% drawdown', value: `${(probDd50 * 100).toFixed(1)}%`, color: probDd50 > 0.1 ? 'text-red-400' : 'text-green-400' }] : []),
    { label: 'VaR 95%', value: `$${var95.toFixed(2)}`, color: 'text-red-400' },
    { label: 'CVaR 95%', value: `$${cvar95.toFixed(2)}`, color: 'text-red-400' },
  ];

  return (
    <div className="border border-border rounded-lg bg-surface-1/30">
      <h3 className="text-sm font-semibold text-text-primary p-4 pb-2 flex items-center gap-2">
        <ShieldAlert size={14} />
        Risk Metrics
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-surface-2/50">
            <tr>
              <th className="text-left px-3 py-2 text-text-muted font-medium">Metric</th>
              <th className="text-right px-3 py-2 text-text-muted font-medium">Value</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className="border-t border-border/50">
                <td className="px-3 py-2 text-text-secondary">{row.label}</td>
                <td className={`px-3 py-2 text-right font-semibold ${row.color}`}>{row.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── 9. Confidence Intervals ─────────────────────────────────────────

function MCConfidenceIntervals({ mc }: { mc: MonteCarloMetrics }) {
  const ci = mc.confidence_intervals;
  if (!ci) return null;

  const rows: { label: string; value: string }[] = [];
  if (ci.return_95_ci) {
    rows.push({
      label: 'Return 95% CI',
      value: `$${Number(ci.return_95_ci[0]).toFixed(2)} to $${Number(ci.return_95_ci[1]).toFixed(2)}`,
    });
  }
  if (ci.sharpe_95_ci) {
    rows.push({
      label: 'Sharpe 95% CI',
      value: `${Number(ci.sharpe_95_ci[0]).toFixed(2)} to ${Number(ci.sharpe_95_ci[1]).toFixed(2)}`,
    });
  }
  if (ci.drawdown_95_ci) {
    rows.push({
      label: 'Max DD 95% CI',
      value: `${Number(ci.drawdown_95_ci[0]).toFixed(1)}% to ${Number(ci.drawdown_95_ci[1]).toFixed(1)}%`,
    });
  }

  if (rows.length === 0) return null;

  return (
    <div className="border border-border rounded-lg bg-surface-1/30">
      <h3 className="text-sm font-semibold text-text-primary p-4 pb-2 flex items-center gap-2">
        <BarChart3 size={14} />
        Confidence Intervals
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-surface-2/50">
            <tr>
              <th className="text-left px-3 py-2 text-text-muted font-medium">Metric</th>
              <th className="text-right px-3 py-2 text-text-muted font-medium">95% CI</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className="border-t border-border/50">
                <td className="px-3 py-2 text-text-secondary">{row.label}</td>
                <td className="px-3 py-2 text-right text-text-primary font-semibold">{row.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Main Monte Carlo Report ─────────────────────────────────────────

function MonteCarloReport({ mc }: { mc: MonteCarloMetrics }) {
  return (
    <div className="space-y-6">
      {/* Simulation summary */}
      <MCSimulationSummary mc={mc} />

      {/* 1. Key Stats Cards */}
      <MCSummaryCards mc={mc} />

      {/* 2. Strategy Scorecard */}
      <MCScorecard mc={mc} />

      {/* 3. Distribution Histograms (2x2) */}
      <MCDistributionsGrid mc={mc} />

      {/* 4. Win Rate vs Profit Factor Scatter */}
      <MCScatterWinRateVsPF mc={mc} />

      {/* 5. Equity Fan Chart */}
      <MCFanChart mc={mc} />

      {/* 6. Drawdown Cone */}
      <MCDrawdownCone mc={mc} />

      {/* 7. Price Paths */}
      <MCPricePaths mc={mc} />

      {/* 8. Risk table */}
      <MCRiskTable mc={mc} />

      {/* 9. Confidence Intervals */}
      <MCConfidenceIntervals mc={mc} />
    </div>
  );
}

// ─── Main Drawer ─────────────────────────────────────────────────────

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

  const isMC = job?.mode === 'montecarlo';
  const metrics = job?.result?.metrics as BacktestMetrics | undefined;
  const mcMetrics = isMC ? (job?.result?.metrics as unknown as MonteCarloMetrics | undefined) : undefined;
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
              {isMC ? 'Monte Carlo Report' : 'Backtest Report'}
              {job && (
                <span className="ml-2 text-sm font-normal text-text-muted">
                  #{job.id}
                </span>
              )}
            </h2>
            {job && (
              <p className="text-xs text-text-muted mt-1">
                {job.symbol} &middot; {job.timeframe} &middot; {job.start_date} &rarr; {job.end_date}
                {isMC && job.n_paths && (
                  <span> &middot; {job.n_paths} paths</span>
                )}
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
          ) : isMC && mcMetrics ? (
            <MonteCarloReport mc={mcMetrics} />
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
