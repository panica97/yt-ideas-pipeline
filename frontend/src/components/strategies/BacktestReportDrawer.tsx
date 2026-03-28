import { useState, useEffect, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { X, ArrowUpDown, Shuffle, TrendingDown, DollarSign, Percent, ShieldAlert, BarChart3, Table } from 'lucide-react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
  AreaChart, Area, BarChart, Bar, Cell, ReferenceLine,
} from 'recharts';
import { getBacktest } from '../../services/backtests';
import type { BacktestTradeComplete, BacktestMetrics, MonteCarloMetrics, MCEquityCurvePoint } from '../../types/backtest';

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

// ─── Monte Carlo Report Components ───────────────────────────────────

function MCFanChart({ data }: { data: MCEquityCurvePoint[] }) {
  if (data.length === 0) {
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
            tickFormatter={(v: number) => `$${v.toFixed(0)}`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'var(--color-surface-2)',
              border: '1px solid var(--color-border)',
              borderRadius: '0.375rem',
              fontSize: '0.75rem',
            }}
            labelStyle={{ color: '#9ca3af' }}
            formatter={(value, name) => {
              const labels: Record<string, string> = {
                p5: 'P5', p25: 'P25', p50: 'P50 (Median)',
                p75: 'P75', p95: 'P95', baseline: 'Baseline',
              };
              return [`$${Number(value).toFixed(2)}`, labels[String(name)] ?? String(name)];
            }}
          />
          {/* P5-P95 band (lightest) */}
          <Area type="monotone" dataKey="p95" stackId="band" stroke="none" fill="#3b82f6" fillOpacity={0.1} />
          <Area type="monotone" dataKey="p5" stackId="band2" stroke="none" fill="transparent" fillOpacity={0} />
          {/* P25-P75 band (medium) */}
          <Area type="monotone" dataKey="p75" stroke="none" fill="#3b82f6" fillOpacity={0.2} />
          <Area type="monotone" dataKey="p25" stroke="none" fill="#3b82f6" fillOpacity={0.1} />
          {/* P50 median line */}
          <Line type="monotone" dataKey="p50" stroke="#3b82f6" strokeWidth={2} dot={false} />
          {/* Baseline overlay */}
          {data[0]?.baseline != null && (
            <Line type="monotone" dataKey="baseline" stroke="#f59e0b" strokeWidth={2} strokeDasharray="5 3" dot={false} />
          )}
        </AreaChart>
      </ResponsiveContainer>
      <div className="flex items-center gap-4 mt-2 text-xs text-text-muted justify-center">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded" style={{ backgroundColor: '#3b82f6', opacity: 0.1 }} /> P5-P95
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded" style={{ backgroundColor: '#3b82f6', opacity: 0.3 }} /> P25-P75
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-2 rounded" style={{ backgroundColor: '#3b82f6' }} /> Median
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-0.5 rounded" style={{ backgroundColor: '#f59e0b' }} /> Baseline
        </span>
      </div>
    </div>
  );
}

function MCSummaryCards({ mc }: { mc: MonteCarloMetrics }) {
  const medianPnl = mc.statistics.total_pnl?.median ?? 0;
  const medianDD = mc.statistics.max_drawdown_pct?.median ?? 0;
  const probLoss = mc.risk_metrics.prob_negative_return ?? 0;
  const var95 = mc.risk_metrics.var_95 ?? 0;

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
        <p className={`text-lg font-bold ${probLoss > 50 ? 'text-red-400' : probLoss > 30 ? 'text-amber-400' : 'text-green-400'}`}>
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

function MCOverfittingCard({ mc }: { mc: MonteCarloMetrics }) {
  const pctile = mc.comparison.return_percentile ?? 50;
  const assessment = mc.comparison.assessment ?? '';

  let colorClass: string;
  let bgClass: string;
  let label: string;
  if (pctile <= 30) {
    colorClass = 'text-green-400';
    bgClass = 'border-green-500/30 bg-green-500/5';
    label = 'Robust — baseline performs worse than most simulations';
  } else if (pctile <= 70) {
    colorClass = 'text-amber-400';
    bgClass = 'border-amber-500/30 bg-amber-500/5';
    label = 'Typical — baseline consistent with simulations';
  } else {
    colorClass = 'text-red-400';
    bgClass = 'border-red-500/30 bg-red-500/5';
    label = 'Caution — baseline may be overfit';
  }

  return (
    <div className={`border rounded-lg p-4 ${bgClass}`}>
      <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
        <ShieldAlert size={14} />
        Overfitting Assessment
      </h3>
      <div className="flex items-center gap-3 mb-2">
        <span className={`text-2xl font-bold ${colorClass}`}>
          {pctile.toFixed(0)}th
        </span>
        <span className="text-xs text-text-muted">percentile</span>
      </div>
      <p className={`text-sm font-medium ${colorClass} mb-1`}>{label}</p>
      {assessment && (
        <p className="text-xs text-text-muted mt-2">{assessment}</p>
      )}
    </div>
  );
}

interface HistogramBin {
  binStart: number;
  binEnd: number;
  label: string;
  count: number;
  isAboveBaseline: boolean;
}

function MCPnlHistogram({ mc, baselinePnl }: { mc: MonteCarloMetrics; baselinePnl?: number }) {
  const bins = useMemo<HistogramBin[]>(() => {
    const rawPnls = mc.statistics.raw_metrics?.total_pnl;
    if (!rawPnls || rawPnls.length === 0) return [];

    const min = Math.min(...rawPnls);
    const max = Math.max(...rawPnls);
    if (min === max) return [{ binStart: min, binEnd: max, label: `$${min.toFixed(0)}`, count: rawPnls.length, isAboveBaseline: false }];

    const nBins = 20;
    const binWidth = (max - min) / nBins;
    const result: HistogramBin[] = [];
    for (let i = 0; i < nBins; i++) {
      const binStart = min + i * binWidth;
      const binEnd = i === nBins - 1 ? max + 0.01 : min + (i + 1) * binWidth;
      const count = rawPnls.filter(v => v >= binStart && v < binEnd).length;
      result.push({
        binStart,
        binEnd,
        label: `$${binStart.toFixed(0)}`,
        count,
        isAboveBaseline: baselinePnl != null ? binStart >= baselinePnl : false,
      });
    }
    return result;
  }, [mc, baselinePnl]);

  if (bins.length === 0) {
    return (
      <div className="border border-border rounded-lg p-6 bg-surface-1/30 text-center">
        <p className="text-sm text-text-muted">No PnL distribution data available</p>
      </div>
    );
  }

  return (
    <div className="border border-border rounded-lg p-4 bg-surface-1/30">
      <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
        <BarChart3 size={14} />
        PnL Distribution
      </h3>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={bins} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 9, fill: '#9ca3af' }}
            tickLine={false}
            interval={Math.max(0, Math.floor(bins.length / 6) - 1)}
          />
          <YAxis
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            tickLine={false}
            label={{ value: 'Paths', angle: -90, position: 'insideLeft', fontSize: 10, fill: '#9ca3af' }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'var(--color-surface-2)',
              border: '1px solid var(--color-border)',
              borderRadius: '0.375rem',
              fontSize: '0.75rem',
            }}
            formatter={(value) => [`${value} paths`, 'Count']}
            labelFormatter={(label) => `PnL: ${label}`}
          />
          <Bar dataKey="count" radius={[2, 2, 0, 0]}>
            {bins.map((bin, i) => (
              <Cell key={i} fill={bin.binStart >= 0 ? '#10b981' : '#ef4444'} fillOpacity={0.7} />
            ))}
          </Bar>
          {baselinePnl != null && (
            <ReferenceLine x={`$${baselinePnl.toFixed(0)}`} stroke="#f59e0b" strokeWidth={2} strokeDasharray="5 3" label={{ value: 'Baseline', position: 'top', fill: '#f59e0b', fontSize: 10 }} />
          )}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function MCPercentileTable({ mc }: { mc: MonteCarloMetrics }) {
  const rows = [
    { label: 'Total PnL', key: 'total_pnl', fmt: (v: number) => `$${v.toFixed(2)}` },
    { label: 'Max DD %', key: 'max_drawdown_pct', fmt: (v: number) => `${v.toFixed(1)}%` },
    { label: 'Sharpe', key: 'sharpe_ratio', fmt: (v: number) => v.toFixed(2) },
    { label: 'Win Rate', key: 'win_rate', fmt: (v: number) => `${v.toFixed(1)}%` },
    { label: 'Profit Factor', key: 'profit_factor', fmt: (v: number) => v.toFixed(2) },
  ];

  return (
    <div className="border border-border rounded-lg bg-surface-1/30">
      <h3 className="text-sm font-semibold text-text-primary p-4 pb-2 flex items-center gap-2">
        <Table size={14} />
        Percentile Table
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-surface-2/50">
            <tr>
              <th className="text-left px-3 py-2 text-text-muted font-medium">Metric</th>
              <th className="text-right px-3 py-2 text-text-muted font-medium">P5</th>
              <th className="text-right px-3 py-2 text-text-muted font-medium">P25</th>
              <th className="text-right px-3 py-2 text-text-muted font-medium">P50</th>
              <th className="text-right px-3 py-2 text-text-muted font-medium">P75</th>
              <th className="text-right px-3 py-2 text-text-muted font-medium">P95</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const stat = mc.statistics[row.key] as { p5: number; p25: number; p50: number; p75: number; p95: number } | undefined;
              if (!stat) return null;
              return (
                <tr key={row.key} className="border-t border-border/50">
                  <td className="px-3 py-2 text-text-secondary font-medium">{row.label}</td>
                  <td className="px-3 py-2 text-right text-text-secondary">{row.fmt(stat.p5)}</td>
                  <td className="px-3 py-2 text-right text-text-secondary">{row.fmt(stat.p25)}</td>
                  <td className="px-3 py-2 text-right text-text-primary font-semibold">{row.fmt(stat.p50)}</td>
                  <td className="px-3 py-2 text-right text-text-secondary">{row.fmt(stat.p75)}</td>
                  <td className="px-3 py-2 text-right text-text-secondary">{row.fmt(stat.p95)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MCRiskTable({ mc }: { mc: MonteCarloMetrics }) {
  const rm = mc.risk_metrics;
  const rows = [
    { label: 'Probability of negative return', value: `${(rm.prob_negative_return * 100).toFixed(1)}%`, color: rm.prob_negative_return > 0.5 ? 'text-red-400' : 'text-green-400' },
    { label: 'Probability of >20% drawdown', value: `${(rm.prob_dd_20 * 100).toFixed(1)}%`, color: rm.prob_dd_20 > 0.5 ? 'text-red-400' : rm.prob_dd_20 > 0.3 ? 'text-amber-400' : 'text-green-400' },
    { label: 'Probability of >30% drawdown', value: `${(rm.prob_dd_30 * 100).toFixed(1)}%`, color: rm.prob_dd_30 > 0.3 ? 'text-red-400' : rm.prob_dd_30 > 0.15 ? 'text-amber-400' : 'text-green-400' },
    { label: 'Probability of >50% drawdown', value: `${(rm.prob_dd_50 * 100).toFixed(1)}%`, color: rm.prob_dd_50 > 0.1 ? 'text-red-400' : 'text-green-400' },
    { label: 'VaR 95%', value: `$${rm.var_95.toFixed(2)}`, color: 'text-red-400' },
    { label: 'CVaR 95%', value: `$${rm.cvar_95.toFixed(2)}`, color: 'text-red-400' },
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

function MonteCarloReport({ mc, baselinePnl }: { mc: MonteCarloMetrics; baselinePnl?: number }) {
  return (
    <div className="space-y-6">
      {/* Config info */}
      <div className="flex items-center gap-3 text-xs text-text-muted">
        <Shuffle size={14} />
        <span>{mc.n_paths} paths &middot; {mc.fit_years} years</span>
      </div>

      {/* Summary cards */}
      <MCSummaryCards mc={mc} />

      {/* Overfitting assessment */}
      <MCOverfittingCard mc={mc} />

      {/* Fan chart */}
      <MCFanChart data={mc.equity_curve_percentiles ?? []} />

      {/* PnL histogram */}
      <MCPnlHistogram mc={mc} baselinePnl={baselinePnl} />

      {/* Percentile table */}
      <MCPercentileTable mc={mc} />

      {/* Risk table */}
      <MCRiskTable mc={mc} />
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

  // For MC histogram, try to get baseline PnL from comparison or first equity curve point
  const baselinePnl = isMC && mcMetrics?.equity_curve_percentiles?.length
    ? mcMetrics.equity_curve_percentiles[mcMetrics.equity_curve_percentiles.length - 1]?.baseline
    : undefined;

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
            <MonteCarloReport mc={mcMetrics} baselinePnl={baselinePnl} />
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
