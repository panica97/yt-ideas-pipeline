import { useState, useEffect, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { X, ArrowUpDown, Shuffle, TrendingDown, TrendingUp, Percent, ShieldAlert, BarChart3, Table } from 'lucide-react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
  BarChart, Bar, Cell, ReferenceLine,
} from 'recharts';
import { getBacktest, getPipelineStatus } from '../../services/backtests';
import type { BacktestTradeComplete, BacktestMetrics, MonteCarloMetrics, MCDistribution, MCBaselineMetrics, MonkeyTestMetrics, StressTestMetrics, StressTestRobustness, StressTestVariation, BacktestJob } from '../../types/backtest';
import MonkeyTestReport from './MonkeyTestReport';
import StressTestReport from './StressTestReport';

interface BacktestReportDrawerProps {
  jobId: number;
  pipelineGroupId?: string;
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

  // Return / DD — normalize with Math.abs to handle sign conventions
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

/** Compute histogram bins from a raw array of numbers */
interface HistogramBin {
  binStart: number;
  binEnd: number;
  label: string;
  count: number;
}

function buildHistogramBins(values: number[], nBins: number = 20, labelPrefix: string = ''): HistogramBin[] {
  if (!values || values.length === 0) return [];

  // Loop-based min/max to avoid stack overflow on large arrays (M-02 fix)
  let min = values[0];
  let max = values[0];
  for (let i = 1; i < values.length; i++) {
    if (values[i] < min) min = values[i];
    if (values[i] > max) max = values[i];
  }
  if (min === max) return [{ binStart: min, binEnd: max, label: `${labelPrefix}${Number(min).toFixed(1)}`, count: values.length }];

  const binWidth = (max - min) / nBins;

  // Single-pass bucket assignment instead of O(n*bins) filter (M-01 fix)
  const counts = new Array<number>(nBins).fill(0);
  for (const v of values) {
    let idx = Math.floor((v - min) / binWidth);
    if (idx >= nBins) idx = nBins - 1; // clamp max value into last bin
    counts[idx]++;
  }

  const result: HistogramBin[] = [];
  for (let i = 0; i < nBins; i++) {
    const binStart = min + i * binWidth;
    const binEnd = i === nBins - 1 ? max + 0.01 : min + (i + 1) * binWidth;
    result.push({
      binStart,
      binEnd,
      label: `${labelPrefix}${Number(binStart).toFixed(1)}`,
      count: counts[i],
    });
  }
  return result;
}

/** Percentile rank: what % of distribution is <= value. Higher-is-better or lower-is-better handled by caller. */
function percentileRank(sortedValues: number[] | undefined, actual: number): number | null {
  if (!sortedValues || sortedValues.length === 0) return null;
  // Binary search for count of values <= actual (assumes pre-sorted input)
  let lo = 0;
  let hi = sortedValues.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (sortedValues[mid] <= actual) lo = mid + 1;
    else hi = mid;
  }
  return (lo / sortedValues.length) * 100;
}

// ── 1. Key Stats Cards ──────────────────────────────────────────────

function MCSummaryCards({ mc }: { mc: MonteCarloMetrics }) {
  const { dist: retDDDist } = computeReturnDDFromRaw(mc);
  const medianRetDD = Number(retDDDist?.median ?? retDDDist?.p50 ?? 0);
  const medianDD = Number(mc.max_drawdown_pct?.median ?? mc.max_drawdown_pct?.p50 ?? 0);
  const probLoss = Number(mc.risk_metrics?.prob_negative_return ?? 0);
  const var95 = Number(mc.risk_metrics?.var_95 ?? 0);

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <div className="bg-surface-1/50 border border-border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-2">
          <TrendingUp size={14} className="text-text-muted" />
          <p className="text-xs text-text-muted">Median Ret/DD</p>
        </div>
        <p className={`text-lg font-bold ${medianRetDD >= 1 ? 'text-green-400' : 'text-red-400'}`}>
          {medianRetDD.toFixed(2)}
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

/** Get Return/DD ratio distribution — prefer backend-aggregated data (dollar/dollar),
 *  fall back to computing from raw arrays (also dollar/dollar via return_drawdown_ratio). */
function computeReturnDDFromRaw(mc: MonteCarloMetrics): { dist: MCDistribution | undefined; rawArr: number[] | undefined } {
  // 1. Prefer aggregated distribution + raw array from backend
  const aggDist = mc.return_drawdown_ratio as MCDistribution | undefined;
  const rawRetDD = mc.raw_metrics?.return_drawdown_ratio;

  if (aggDist) {
    return { dist: aggDist, rawArr: rawRetDD };
  }

  // 2. Fallback: use raw return_drawdown_ratio array if available (build dist client-side)
  if (rawRetDD && rawRetDD.length > 0) {
    const sorted = [...rawRetDD].sort((a, b) => a - b);
    const pct = (p: number) => {
      const idx = Math.max(0, Math.ceil((p / 100) * sorted.length) - 1);
      return sorted[idx];
    };
    const mean = rawRetDD.reduce((s, v) => s + v, 0) / rawRetDD.length;
    const std = Math.sqrt(rawRetDD.reduce((s, v) => s + (v - mean) ** 2, 0) / rawRetDD.length);
    return {
      dist: { p5: pct(5), p25: pct(25), p50: pct(50), p75: pct(75), p95: pct(95), mean, std, median: pct(50), min: sorted[0], max: sorted[sorted.length - 1] },
      rawArr: rawRetDD,
    };
  }

  // 3. No data available — don't compute from mismatched units
  return { dist: undefined, rawArr: undefined };
}

/** Sort a numeric array for use with percentileRank (binary search). Returns a new sorted copy. */
function sortedCopy(arr: number[] | undefined): number[] | undefined {
  if (!arr || arr.length === 0) return arr;
  return [...arr].sort((a, b) => a - b);
}

function MCScorecard({ mc }: { mc: MonteCarloMetrics }) {
  const { retDDDist, retDDRaw } = useMemo(() => {
    const { dist, rawArr } = computeReturnDDFromRaw(mc);
    return { retDDDist: dist, retDDRaw: rawArr };
  }, [mc]);

  const baseline = mc.baseline_metrics as MCBaselineMetrics | undefined;

  // Pre-sort raw arrays once for efficient percentileRank calls (M-03 fix)
  const sortedRetDD = useMemo(() => sortedCopy(retDDRaw), [retDDRaw]);
  const sortedMaxDD = useMemo(() => sortedCopy(mc.raw_metrics?.max_drawdown_pct), [mc.raw_metrics?.max_drawdown_pct]);
  const sortedSharpe = useMemo(() => sortedCopy(mc.raw_metrics?.sharpe_ratio), [mc.raw_metrics?.sharpe_ratio]);

  const rows = useMemo(() => {
    const defs: {
      label: string;
      dist: MCDistribution | undefined;
      sortedArr: number[] | undefined;
      fmt: (v: number) => string;
      higherIsBetter: boolean;
      baselineKey: keyof MCBaselineMetrics;
    }[] = [
      {
        label: 'Return / DD',
        dist: retDDDist,
        sortedArr: sortedRetDD,
        fmt: (v) => Number(v).toFixed(2),
        higherIsBetter: true,
        baselineKey: 'return_drawdown_ratio',
      },
      {
        label: 'Max DD %',
        dist: mc.max_drawdown_pct as MCDistribution | undefined,
        sortedArr: sortedMaxDD,
        fmt: (v) => `${Number(v).toFixed(1)}%`,
        higherIsBetter: false,
        baselineKey: 'max_drawdown_pct',
      },
      {
        label: 'Sharpe',
        dist: mc.sharpe_ratio as MCDistribution | undefined,
        sortedArr: sortedSharpe,
        fmt: (v) => Number(v).toFixed(2),
        higherIsBetter: true,
        baselineKey: 'sharpe_ratio',
      },
    ];

    return defs.map((d) => {
      // Prefer real baseline metric; fall back to MC median for old jobs
      const baselineVal = baseline?.[d.baselineKey];
      const actual = (baselineVal != null ? Number(baselineVal) : null) ?? d.dist?.median ?? d.dist?.p50;
      const rank = d.sortedArr && actual != null ? percentileRank(d.sortedArr, actual) : null;

      // Z-Score = (actual - mean) / std
      const mean = d.dist?.mean;
      const std = d.dist?.std;
      let zScore: number | null = null;
      if (actual != null && mean != null && std != null && std > 0) {
        zScore = (actual - mean) / std;
      }

      return {
        label: d.label,
        dist: d.dist,
        actual: actual != null ? d.fmt(actual) : 'N/A',
        rank,
        zScore,
        higherIsBetter: d.higherIsBetter,
        fmt: d.fmt,
      };
    });
  }, [mc, baseline, retDDDist, sortedRetDD, sortedMaxDD, sortedSharpe]);

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
              <th className="text-right px-3 py-2 text-text-muted font-medium">Z-Score</th>
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
              const zColor = row.zScore != null
                ? (Math.abs(row.zScore) > 1 ? 'text-red-400' : 'text-green-400')
                : 'text-text-muted';
              return (
                <tr key={row.label} className="border-t border-border/50">
                  <td className="px-3 py-2 text-text-secondary font-medium">{row.label}</td>
                  <td className="px-3 py-2 text-right font-semibold text-text-primary">
                    {row.actual}
                  </td>
                  <td className={`px-3 py-2 text-right font-semibold ${zColor}`}>
                    {row.zScore != null ? Math.abs(row.zScore).toFixed(2) : '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-semibold text-text-primary">
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
  dist,
  actualValue,
}: {
  title: string;
  values: number[] | undefined;
  color: string;
  labelPrefix?: string;
  dist?: MCDistribution;
  actualValue?: number;
}) {
  const bins = useMemo(() => buildHistogramBins(values ?? [], 20, labelPrefix ?? ''), [values, labelPrefix]);

  // Helper: find the closest bin label for a given numeric value
  const closestBinLabel = useCallback((val: number) => {
    if (bins.length === 0) return undefined;
    return bins.reduce((closest, b) =>
      Math.abs(b.binStart - val) < Math.abs(closest.binStart - val) ? b : closest
    , bins[0]).label;
  }, [bins]);

  if (bins.length === 0) {
    return (
      <div className="border border-border rounded-lg p-6 bg-surface-1/30 text-center">
        <p className="text-sm text-text-muted">No data for {title}</p>
      </div>
    );
  }

  const p5Val = dist?.p5;
  const p50Val = dist?.p50 ?? dist?.median;
  const p95Val = dist?.p95;

  return (
    <div className="border border-border rounded-lg p-4 bg-surface-1/30">
      <h3 className="text-sm font-semibold text-text-primary mb-3">{title}</h3>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={bins} margin={{ top: 15, right: 10, left: 10, bottom: 5 }}>
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
          {/* P5 line - red dashed */}
          {p5Val != null && closestBinLabel(p5Val) && (
            <ReferenceLine
              x={closestBinLabel(p5Val)}
              stroke="#ef4444"
              strokeWidth={1.5}
              strokeDasharray="5 3"
              label={{ value: 'P5', position: 'top', fill: '#ef4444', fontSize: 9 }}
            />
          )}
          {/* P50 line - amber dashed */}
          {p50Val != null && closestBinLabel(p50Val) && (
            <ReferenceLine
              x={closestBinLabel(p50Val)}
              stroke="#f59e0b"
              strokeWidth={1.5}
              strokeDasharray="5 3"
              label={{ value: 'P50', position: 'top', fill: '#f59e0b', fontSize: 9 }}
            />
          )}
          {/* P95 line - green dashed */}
          {p95Val != null && closestBinLabel(p95Val) && (
            <ReferenceLine
              x={closestBinLabel(p95Val)}
              stroke="#10b981"
              strokeWidth={1.5}
              strokeDasharray="5 3"
              label={{ value: 'P95', position: 'top', fill: '#10b981', fontSize: 9 }}
            />
          )}
          {/* Actual line - solid blue */}
          {actualValue != null && closestBinLabel(actualValue) && (
            <ReferenceLine
              x={closestBinLabel(actualValue)}
              stroke="#3b82f6"
              strokeWidth={2}
              label={{ value: 'Actual', position: 'top', fill: '#3b82f6', fontSize: 9 }}
            />
          )}
        </BarChart>
      </ResponsiveContainer>
      {/* Legend */}
      <div className="flex items-center gap-3 mt-2 text-xs text-text-muted justify-center flex-wrap">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-0.5 rounded" style={{ backgroundColor: '#ef4444', borderTop: '1px dashed #ef4444' }} /> P5
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-0.5 rounded" style={{ backgroundColor: '#f59e0b', borderTop: '1px dashed #f59e0b' }} /> P50
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-0.5 rounded" style={{ backgroundColor: '#10b981', borderTop: '1px dashed #10b981' }} /> P95
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-0.5 rounded" style={{ backgroundColor: '#3b82f6' }} /> Actual
        </span>
      </div>
    </div>
  );
}

function MCDistributionsGrid({ mc }: { mc: MonteCarloMetrics }) {
  // Compute Return/DD ratio raw array for histogram
  const { retDDRaw, retDDDist } = useMemo(() => {
    const { dist, rawArr } = computeReturnDDFromRaw(mc);
    return { retDDRaw: rawArr, retDDDist: dist };
  }, [mc]);

  const baseline = mc.baseline_metrics;
  // Prefer real baseline; fall back to MC median for old jobs
  const retDDActual = (baseline?.return_drawdown_ratio != null ? Number(baseline.return_drawdown_ratio) : null)
    ?? retDDDist?.median ?? retDDDist?.p50;
  const ddDist = mc.max_drawdown_pct as MCDistribution | undefined;
  const ddActual = (baseline?.max_drawdown_pct != null ? Number(baseline.max_drawdown_pct) : null)
    ?? ddDist?.median ?? ddDist?.p50;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <MCDistributionHistogram
        title="Return / DD Distribution"
        values={retDDRaw}
        color="#10b981"
        dist={retDDDist}
        actualValue={retDDActual != null ? Number(retDDActual) : undefined}
      />
      <MCDistributionHistogram
        title="Max Drawdown Distribution"
        values={mc.raw_metrics?.max_drawdown_pct}
        color="#ef4444"
        dist={ddDist}
        actualValue={ddActual != null ? Number(ddActual) : undefined}
      />
    </div>
  );
}

// ── 4. Risk Metrics Table ────────────────────────────────────────────

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

      {/* 3. Distribution Histograms (Return/DD + Max DD) */}
      <MCDistributionsGrid mc={mc} />

      {/* 4. Risk table */}
      <MCRiskTable mc={mc} />

      {/* 5. Confidence Intervals */}
      <MCConfidenceIntervals mc={mc} />
    </div>
  );
}

// ─── Stress metrics normalizer ──────────────────────────────────────
// The backend runner returns a flat structure (robustness, all_results,
// multi_grid, single_sweeps, etc.) while StressTestReport expects
// a StressTestMetrics shape (summary, variations, multi_variations,
// single_variations, config).  This function bridges the two.

function normalizeStressMetrics(raw: Record<string, unknown>): StressTestMetrics {
  // Map variation status: backend uses "ok"/"error", frontend uses "completed"/"failed"
  function mapVariation(v: Record<string, unknown>, testType: 'multi' | 'single', singleParam?: string): StressTestVariation {
    return {
      name: (v.name as string) ?? '',
      params: (v.params as Record<string, number>) ?? {},
      metrics: (v.metrics as Record<string, number>) ?? {},
      status: v.status === 'ok' ? 'completed' : 'failed',
      test_type: testType,
      single_param: singleParam,
    };
  }

  // all_results contains every variation (both multi-grid and single-sweep)
  const allResults = (raw.all_results as Record<string, unknown>[]) ?? [];
  const variations: StressTestVariation[] = allResults.map(v => {
    const sweepParam = v._sweep_param as string | undefined;
    return mapVariation(v, sweepParam ? 'single' : 'multi', sweepParam);
  });

  // multi_grid.results
  const multiGrid = (raw.multi_grid as Record<string, unknown>) ?? {};
  const multiResults = (multiGrid.results as Record<string, unknown>[]) ?? [];
  const multi_variations: StressTestVariation[] = multiResults.map(v => mapVariation(v, 'multi'));

  // single_sweeps: { param_name: { results: [...] } }
  const singleSweeps = (raw.single_sweeps as Record<string, Record<string, unknown>>) ?? {};
  const single_variations: Record<string, StressTestVariation[]> = {};
  for (const [paramName, sweep] of Object.entries(singleSweeps)) {
    const results = (sweep.results as Record<string, unknown>[]) ?? [];
    single_variations[paramName] = results.map(v => mapVariation(v, 'single', paramName));
  }

  // Build summary from top-level fields
  const summary = {
    total_variations: (raw.total_variations as number) ?? 0,
    completed: (raw.successful_variations as number) ?? 0,
    failed: (raw.failed_variations as number) ?? 0,
    duration_seconds: (raw.duration_seconds as number) ?? 0,
  };

  // Robustness (already matches the expected shape)
  const robustness = (raw.robustness as StressTestRobustness) ?? {
    profitable_pct: 0,
    positive_sharpe_pct: 0,
    low_drawdown_pct: 0,
    score: 0,
  };

  // Config
  const config = {
    strategy_id: (raw.strategy_id as number) ?? 0,
    test_type: (raw.test_type as string) ?? 'multi_param',
    param_ranges: (raw.param_ranges as Record<string, number[]>) ?? {},
    base_params: undefined as Record<string, number> | undefined,
  };

  return {
    summary,
    robustness,
    variations,
    multi_variations,
    single_variations,
    config,
  };
}

// ─── Pipeline Section Component ─────────────────────────────────────

function PipelineSectionReport({ job }: { job: BacktestJob }) {
  const rawMetrics = job.result?.metrics as unknown;
  const isObj = rawMetrics != null && typeof rawMetrics === 'object';
  const metrics = rawMetrics as BacktestMetrics | undefined;
  const trades = (job.result?.trades ?? []) as unknown as BacktestTradeComplete[];

  if (job.status === 'failed') {
    return (
      <div className="flex items-start gap-2 bg-danger/10 border border-danger/20 rounded p-3">
        <X size={14} className="text-danger mt-0.5 shrink-0" />
        <p className="text-xs text-danger">{job.error_message ?? 'Job failed'}</p>
      </div>
    );
  }

  if (job.status !== 'completed' || !job.result) {
    return (
      <p className="text-xs text-text-muted italic">
        {job.status === 'running' ? 'Running...' : 'Pending...'}
      </p>
    );
  }

  if (job.mode === 'montecarlo') {
    const mcMetrics = (isObj && 'raw_metrics' in (rawMetrics as object))
      ? (rawMetrics as unknown as MonteCarloMetrics) : undefined;
    if (mcMetrics) return <MonteCarloReport mc={mcMetrics} />;
  }

  if (job.mode === 'monkey') {
    const monkeyMetrics = (isObj && 'strategy_results' in (rawMetrics as object))
      ? (rawMetrics as unknown as MonkeyTestMetrics) : undefined;
    if (monkeyMetrics) return <MonkeyTestReport monkey={monkeyMetrics} />;
  }

  if (job.mode === 'stress') {
    // Detect raw stress data: backend returns 'robustness' at top level (not 'summary')
    const hasStressData = isObj && ('robustness' in (rawMetrics as object) || 'summary' in (rawMetrics as object));
    if (hasStressData) {
      // If already normalized (has 'summary'), use as-is; otherwise normalize from raw backend format
      const stressMetrics = 'summary' in (rawMetrics as object)
        ? (rawMetrics as unknown as StressTestMetrics)
        : normalizeStressMetrics(rawMetrics as Record<string, unknown>);
      return <StressTestReport stress={stressMetrics} />;
    }
  }

  // Default: backtest (complete mode)
  return (
    <>
      {metrics && <ExtendedMetricsGrid metrics={metrics} trades={trades} />}
      <ReportEquityCurve trades={trades} />
      <TradesTable trades={trades} />
    </>
  );
}

// ─── Main Drawer ─────────────────────────────────────────────────────

export default function BacktestReportDrawer({ jobId, pipelineGroupId, open, onClose }: BacktestReportDrawerProps) {
  const isPipeline = !!pipelineGroupId;

  const { data: job } = useQuery({
    queryKey: ['backtest', jobId],
    queryFn: () => getBacktest(jobId),
    enabled: open && !isPipeline,
  });

  // Pipeline mode: fetch all pipeline jobs with full results
  const { data: pipelineStatus } = useQuery({
    queryKey: ['pipeline', pipelineGroupId],
    queryFn: () => getPipelineStatus(pipelineGroupId!),
    enabled: open && isPipeline,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'completed' || status === 'failed') return false;
      return 3000;
    },
  });

  // Fetch full job details for each pipeline job (to get results)
  const pipelineJobIds = pipelineStatus?.jobs.map((j) => j.id) ?? [];
  const pipelineJobQueries = useQuery({
    queryKey: ['pipeline-jobs', pipelineGroupId, pipelineJobIds],
    queryFn: async () => {
      const results = await Promise.all(pipelineJobIds.map((id) => getBacktest(id)));
      return results;
    },
    enabled: open && isPipeline && pipelineJobIds.length > 0,
    refetchInterval: (query) => {
      const jobs = query.state.data;
      if (!jobs) return 3000;
      const hasActive = jobs.some((j) => j.status === 'pending' || j.status === 'running');
      return hasActive ? 3000 : false;
    },
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

  // Pipeline mode rendering
  if (isPipeline) {
    const pipelineJobs = pipelineJobQueries.data ?? [];
    const modeOrder = ['complete', 'montecarlo', 'monkey', 'stress'];
    const modeLabels: Record<string, string> = { complete: 'Backtest', montecarlo: 'Monte Carlo', monkey: 'Monkey Test', stress: 'Stress Test' };
    const modeBorderColors: Record<string, string> = { complete: 'border-accent', montecarlo: 'border-purple-500', monkey: 'border-orange-500', stress: 'border-rose-500' };
    const sortedPipelineJobs = [...pipelineJobs].sort((a, b) => modeOrder.indexOf(a.mode) - modeOrder.indexOf(b.mode));
    const firstJob = sortedPipelineJobs[0];

    const overallStatus = pipelineStatus?.status ?? 'pending';
    const statusColor = overallStatus === 'completed' ? 'text-green-400' : overallStatus === 'failed' ? 'text-red-400' : overallStatus === 'running' ? 'text-accent' : 'text-text-muted';

    return (
      <div className="fixed inset-0 z-50 flex justify-end">
        <div className="absolute inset-0 bg-black/50 transition-opacity" onClick={onClose} />
        <div className="relative w-4/5 max-w-[1400px] h-full bg-surface-0 border-l border-border shadow-2xl overflow-y-auto animate-slide-in-right">
          {/* Header */}
          <div className="sticky top-0 z-10 bg-surface-0 border-b border-border px-6 py-4 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-text-primary">
                Pipeline Report
                <span className={`ml-2 text-sm font-medium ${statusColor}`}>
                  ({overallStatus})
                </span>
              </h2>
              {firstJob && (
                <p className="text-xs text-text-muted mt-1">
                  {firstJob.symbol} &middot; {firstJob.timeframe} &middot; {firstJob.start_date} &rarr; {firstJob.end_date}
                  &middot; {sortedPipelineJobs.length} steps
                </p>
              )}
            </div>
            <button onClick={onClose} className="p-2 text-text-muted hover:text-text-primary transition-colors rounded hover:bg-surface-2">
              <X size={18} />
            </button>
          </div>

          {/* Body */}
          <div className="p-6 space-y-8">
            {pipelineJobs.length === 0 ? (
              <p className="text-sm text-text-muted italic">Loading pipeline data...</p>
            ) : (
              sortedPipelineJobs.map((pJob) => (
                <div key={pJob.id} className={`border-l-4 ${modeBorderColors[pJob.mode] ?? 'border-border'} pl-4 space-y-4`}>
                  <h3 className="text-sm font-bold text-text-primary">
                    {modeLabels[pJob.mode] ?? pJob.mode}
                    <span className={`ml-2 text-xs font-medium ${
                      pJob.status === 'completed' ? 'text-green-400'
                      : pJob.status === 'failed' ? 'text-red-400'
                      : pJob.status === 'running' ? 'text-accent'
                      : 'text-text-muted'
                    }`}>
                      ({pJob.status})
                    </span>
                  </h3>
                  <PipelineSectionReport job={pJob} />
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    );
  }

  // Single-job mode (existing behavior)
  const isMC = job?.mode === 'montecarlo';
  const isMonkey = job?.mode === 'monkey';
  const isStress = job?.mode === 'stress';
  const rawMetrics = job?.result?.metrics as unknown;
  const metrics = rawMetrics as BacktestMetrics | undefined;

  const isObj = rawMetrics != null && typeof rawMetrics === 'object';
  const mcMetrics = (isMC && isObj && 'raw_metrics' in (rawMetrics as object))
    ? (rawMetrics as unknown as MonteCarloMetrics) : undefined;
  const monkeyMetrics = (isMonkey && isObj && 'strategy_results' in (rawMetrics as object))
    ? (rawMetrics as unknown as MonkeyTestMetrics) : undefined;
  const stressMetrics = (isStress && isObj && ('robustness' in (rawMetrics as object) || 'summary' in (rawMetrics as object)))
    ? ('summary' in (rawMetrics as object)
        ? (rawMetrics as unknown as StressTestMetrics)
        : normalizeStressMetrics(rawMetrics as Record<string, unknown>))
    : undefined;
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
              {isStress ? 'Stress Test Report' : isMonkey ? 'Monkey Test Report' : isMC ? 'Monte Carlo Report' : 'Backtest Report'}
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
                {isMonkey && job.n_simulations && (
                  <span> &middot; {job.n_simulations} simulations &middot; Mode {job.monkey_mode ?? '?'}</span>
                )}
                {isStress && stressMetrics && (
                  <span>
                    {job.stress_test_name && <span> &middot; {job.stress_test_name}</span>}
                    <span> &middot; {stressMetrics.summary.total_variations} variations</span>
                  </span>
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
          ) : isStress && stressMetrics ? (
            <StressTestReport stress={stressMetrics} />
          ) : isMonkey && monkeyMetrics ? (
            <MonkeyTestReport monkey={monkeyMetrics} />
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
