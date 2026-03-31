import { useMemo, useState } from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts';
import { ShieldCheck, BarChart3, Table, ArrowUpDown } from 'lucide-react';
import type { StressTestMetrics, StressTestVariation } from '../../types/backtest';

// ─── Helpers ────────────────────────────────────────────────────────

function formatCurrency(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}$${value.toFixed(2)}`;
}

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

const tooltipStyle = {
  backgroundColor: 'var(--color-surface-2)',
  border: '1px solid var(--color-border)',
  borderRadius: '0.375rem',
  fontSize: '0.75rem',
};

// ─── Robustness Score Badge ─────────────────────────────────────────

function RobustnessBadge({ robustness }: { robustness: StressTestMetrics['robustness'] }) {
  const score = robustness.score;

  let bgClass: string;
  let textClass: string;
  let label: string;

  if (score >= 80) {
    bgClass = 'bg-green-500/20 border-green-500/40';
    textClass = 'text-green-400';
    label = 'Robust';
  } else if (score >= 60) {
    bgClass = 'bg-emerald-500/20 border-emerald-500/40';
    textClass = 'text-emerald-400';
    label = 'Moderate';
  } else if (score >= 40) {
    bgClass = 'bg-amber-500/20 border-amber-500/40';
    textClass = 'text-amber-400';
    label = 'Weak';
  } else {
    bgClass = 'bg-red-500/20 border-red-500/40';
    textClass = 'text-red-400';
    label = 'Fragile';
  }

  return (
    <div className={`border rounded-lg p-4 ${bgClass}`}>
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className={`text-3xl font-bold ${textClass}`}>
            {score.toFixed(0)}
          </div>
          <div className={`px-3 py-1 rounded-full text-sm font-semibold ${bgClass} ${textClass}`}>
            {label}
          </div>
        </div>
        <div className="flex items-center gap-4 text-sm text-text-secondary">
          <span>Profitable: <span className="font-semibold text-text-primary">{formatPercent(robustness.profitable_pct)}</span></span>
          <span>Positive Sharpe: <span className="font-semibold text-text-primary">{formatPercent(robustness.positive_sharpe_pct)}</span></span>
          <span>Low DD: <span className="font-semibold text-text-primary">{formatPercent(robustness.low_drawdown_pct)}</span></span>
        </div>
      </div>
    </div>
  );
}

// ─── Summary Card ───────────────────────────────────────────────────

function StressSummaryCard({ summary }: { summary: StressTestMetrics['summary'] }) {
  const bgClass = summary.failed > 0 ? 'border-amber-500/30 bg-amber-500/5' : 'border-green-500/30 bg-green-500/5';

  return (
    <div className={`border rounded-lg p-4 ${bgClass}`}>
      <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
        <ShieldCheck size={14} />
        Test Summary
      </h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div>
          <p className="text-xs text-text-muted mb-1">Total Variations</p>
          <p className="text-lg font-bold text-text-primary">{summary.total_variations}</p>
        </div>
        <div>
          <p className="text-xs text-text-muted mb-1">Completed</p>
          <p className="text-lg font-bold text-green-400">{summary.completed}</p>
        </div>
        <div>
          <p className="text-xs text-text-muted mb-1">Failed</p>
          <p className={`text-lg font-bold ${summary.failed > 0 ? 'text-red-400' : 'text-text-primary'}`}>{summary.failed}</p>
        </div>
        <div>
          <p className="text-xs text-text-muted mb-1">Duration</p>
          <p className="text-lg font-bold text-text-primary">{summary.duration_seconds.toFixed(1)}s</p>
        </div>
      </div>
    </div>
  );
}

// ─── Multi-Param Variations Table ───────────────────────────────────

type SortField = 'name' | 'total_pnl' | 'sharpe_ratio' | 'max_drawdown_pct' | 'win_rate' | 'profit_factor';
type SortDir = 'asc' | 'desc';

function VariationsTable({ variations }: { variations: StressTestVariation[] }) {
  const [sortField, setSortField] = useState<SortField>('total_pnl');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const completed = useMemo(
    () => variations.filter((v) => v.status === 'completed'),
    [variations],
  );

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const sorted = useMemo(() => {
    const arr = [...completed];
    arr.sort((a, b) => {
      let aVal: number;
      let bVal: number;
      if (sortField === 'name') {
        const cmp = a.name.localeCompare(b.name);
        return sortDir === 'asc' ? cmp : -cmp;
      }
      aVal = a.metrics[sortField] ?? 0;
      bVal = b.metrics[sortField] ?? 0;
      return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
    });
    return arr;
  }, [completed, sortField, sortDir]);

  if (completed.length === 0) {
    return (
      <div className="border border-border rounded-lg p-6 bg-surface-1/30 text-center">
        <p className="text-sm text-text-muted">No completed multi-param variations</p>
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
      <h3 className="text-sm font-semibold text-text-primary p-4 pb-2 flex items-center gap-2">
        <Table size={14} />
        Multi-Param Variations ({completed.length})
      </h3>
      <div className="max-h-96 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="bg-surface-2/50 sticky top-0">
            <tr>
              <SortHeader field="name" label="Params" />
              <SortHeader field="total_pnl" label="Total PnL" align="right" />
              <SortHeader field="sharpe_ratio" label="Sharpe" align="right" />
              <SortHeader field="max_drawdown_pct" label="Max DD %" align="right" />
              <SortHeader field="win_rate" label="Win Rate" align="right" />
              <SortHeader field="profit_factor" label="Profit Factor" align="right" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((v) => {
              const pnl = v.metrics.total_pnl ?? 0;
              const isProfitable = pnl >= 0;
              return (
                <tr key={v.name} className={`border-t border-border/50 ${isProfitable ? 'hover:bg-green-500/5' : 'hover:bg-red-500/5'}`}>
                  <td className="px-2 py-1.5 text-text-secondary font-mono text-[10px]">
                    {Object.entries(v.params).map(([k, val]) => `${k}=${val}`).join(', ')}
                  </td>
                  <td className={`px-2 py-1.5 text-right font-medium ${isProfitable ? 'text-accent' : 'text-danger'}`}>
                    {formatCurrency(pnl)}
                  </td>
                  <td className={`px-2 py-1.5 text-right ${(v.metrics.sharpe_ratio ?? 0) > 0 ? 'text-accent' : 'text-danger'}`}>
                    {(v.metrics.sharpe_ratio ?? 0).toFixed(2)}
                  </td>
                  <td className="px-2 py-1.5 text-right text-danger">
                    {formatPercent(v.metrics.max_drawdown_pct ?? 0)}
                  </td>
                  <td className="px-2 py-1.5 text-right text-text-secondary">
                    {formatPercent(v.metrics.win_rate ?? 0)}
                  </td>
                  <td className={`px-2 py-1.5 text-right ${(v.metrics.profit_factor ?? 0) > 1 ? 'text-accent' : 'text-danger'}`}>
                    {(v.metrics.profit_factor ?? 0).toFixed(2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Single-Param Sensitivity Charts ────────────────────────────────

function SingleParamChart({ paramName, variations }: { paramName: string; variations: StressTestVariation[] }) {
  const data = useMemo(() => {
    const completed = variations.filter((v) => v.status === 'completed');
    return completed
      .map((v) => ({
        paramValue: v.params[paramName] ?? 0,
        total_pnl: v.metrics.total_pnl ?? 0,
        sharpe_ratio: v.metrics.sharpe_ratio ?? 0,
      }))
      .sort((a, b) => a.paramValue - b.paramValue);
  }, [variations, paramName]);

  if (data.length === 0) return null;

  return (
    <div className="border border-border rounded-lg p-4 bg-surface-1/30">
      <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
        <BarChart3 size={14} />
        {paramName}
      </h3>
      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="paramValue"
            tick={{ fontSize: 10, fill: 'var(--color-text-muted)' }}
            tickLine={false}
            label={{ value: paramName, position: 'insideBottom', offset: -5, fontSize: 10, fill: 'var(--color-text-muted)' }}
          />
          <YAxis
            tick={{ fontSize: 10, fill: 'var(--color-text-muted)' }}
            tickLine={false}
            tickFormatter={(v: number) => formatCurrency(v)}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            labelFormatter={(label) => `${paramName}: ${label}`}
            formatter={(value, name) => [
              name === 'total_pnl' ? formatCurrency(Number(value)) : Number(value).toFixed(2),
              name === 'total_pnl' ? 'Total PnL' : 'Sharpe',
            ]}
          />
          <Line
            type="monotone"
            dataKey="total_pnl"
            stroke="#10b981"
            strokeWidth={2}
            dot={{ fill: '#10b981', r: 3 }}
            name="total_pnl"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function SingleParamCharts({ singleVariations }: { singleVariations: Record<string, StressTestVariation[]> }) {
  const paramNames = Object.keys(singleVariations);
  if (paramNames.length === 0) return null;

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
        <BarChart3 size={14} />
        Single-Parameter Sensitivity
      </h3>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {paramNames.map((name) => (
          <SingleParamChart key={name} paramName={name} variations={singleVariations[name]} />
        ))}
      </div>
    </div>
  );
}

// ─── Main Component ─────────────────────────────────────────────────

export default function StressTestReport({ stress }: { stress: StressTestMetrics }) {
  return (
    <div className="space-y-6">
      {/* Robustness Score */}
      <RobustnessBadge robustness={stress.robustness} />

      {/* Summary */}
      <StressSummaryCard summary={stress.summary} />

      {/* Multi-Param Variations Table */}
      {stress.multi_variations && stress.multi_variations.length > 0 && (
        <VariationsTable variations={stress.multi_variations} />
      )}

      {/* Single-Param Sensitivity Charts */}
      {stress.single_variations && Object.keys(stress.single_variations).length > 0 && (
        <SingleParamCharts singleVariations={stress.single_variations} />
      )}
    </div>
  );
}
