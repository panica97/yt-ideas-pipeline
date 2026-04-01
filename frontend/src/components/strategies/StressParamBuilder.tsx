import { useState, useEffect, useMemo } from 'react';
import { ChevronDown, ChevronUp, Activity, Timer, AlertTriangle, Crosshair, Shield } from 'lucide-react';

interface ParamConfig {
  key: string;        // e.g. "ind_list.1 day.0.period"
  label: string;      // e.g. "RSI_1D — period"
  category: 'indicator' | 'condition' | 'exit' | 'risk';
  currentValue: number;
}

interface ParamRange {
  min: number;
  max: number;
  step: number;
}

interface ParamState {
  enabled: boolean;
  mode: 'grid' | 'sweep';
  range: ParamRange;
}

interface StressParamBuilderProps {
  draftData: any;
  onParamOverridesChange: (overrides: Record<string, any>) => void;
  onSingleOverridesChange: (overrides: Record<string, any>) => void;
}

function smartDefaults(value: number): ParamRange {
  const min = Math.max(1, Math.round(value * 0.5));
  const max = Math.round(value * 2);
  // Step: roughly 5-10 values in the range
  const range = max - min;
  let step = Math.max(1, Math.round(range / 6));
  if (value <= 5) step = 1;
  return { min, max, step };
}

function extractParams(draftData: any): ParamConfig[] {
  const params: ParamConfig[] = [];
  if (!draftData) return params;

  // Extract indicator periods from ind_list
  const indList = draftData.ind_list;
  if (indList && typeof indList === 'object') {
    for (const [timeframe, indicators] of Object.entries(indList)) {
      if (!Array.isArray(indicators)) continue;
      indicators.forEach((ind: any, idx: number) => {
        // Skip PRICE-type indicators — their period is not a meaningful tunable parameter
        const indType = (ind.indicator || '').toUpperCase();
        if (indType === 'PRICE' || indType === 'DATA') return;
        // period can be at ind.period or ind.params.timePeriod_1
        const indCode = ind.params?.indCode || ind.indCode || `Indicator ${idx}`;
        const period = ind.period ?? ind.params?.timePeriod_1;
        if (period != null && typeof period === 'number') {
          const periodKey = ind.period != null
            ? `ind_list.${timeframe}.${idx}.period`
            : `ind_list.${timeframe}.${idx}.params.timePeriod_1`;
          params.push({
            key: periodKey,
            label: `${indCode} — period`,
            category: 'indicator',
            currentValue: period,
          });
        }
      });
    }
  }

  // Extract entry condition thresholds from long_conds and short_conds
  const condSections: Array<{ key: string; conds: any[] }> = [];
  if (Array.isArray(draftData.long_conds)) {
    condSections.push({ key: 'long_conds', conds: draftData.long_conds });
  }
  if (Array.isArray(draftData.short_conds)) {
    condSections.push({ key: 'short_conds', conds: draftData.short_conds });
  }
  for (const section of condSections) {
    section.conds.forEach((cond: any, idx: number) => {
      if (cond.cond_type === 'num_relation' && typeof cond.cond === 'string') {
        const match = cond.cond.match(/[<>=!]+\s*(-?\d+\.?\d*)/);
        if (match) {
          const threshold = parseFloat(match[1]);
          const condCode = cond.condCode || `${section.key}_${idx}`;
          params.push({
            key: `${section.key}.${idx}.cond_value`,
            label: `${condCode} — ${cond.cond}`,
            category: 'condition',
            currentValue: threshold,
          });
        }
      }
    });
  }

  // Extract exit bars from exit_conds
  if (Array.isArray(draftData.exit_conds)) {
    draftData.exit_conds.forEach((cond: any, idx: number) => {
      if (cond.cond_type === 'num_bars') {
        const value = parseFloat(cond.cond);
        if (!isNaN(value)) {
          const condCode = cond.condCode || `exit_${idx}`;
          params.push({
            key: `exit_conds.${idx}.cond`,
            label: `${condCode} — max bars`,
            category: 'exit',
            currentValue: value,
          });
        }
      }
    });
  }

  // Extract max_bars_in_trade from control_params
  const maxBars = draftData.control_params?.max_bars_in_trade;
  if (maxBars != null && typeof maxBars === 'number') {
    params.push({
      key: 'control_params.max_bars_in_trade',
      label: 'max_bars_in_trade',
      category: 'exit',
      currentValue: maxBars,
    });
  }

  // Extract SL/TP parameters
  const sltp: Array<{ prefix: string; label: string; data: any }> = [
    { prefix: 'stop_loss_init', label: 'SL', data: draftData.stop_loss_init },
    { prefix: 'take_profit_init', label: 'TP', data: draftData.take_profit_init },
  ];
  for (const { prefix, label, data } of sltp) {
    if (!data || typeof data !== 'object') continue;
    const types = ['pips', 'percent', 'indicator'] as const;
    for (const type of types) {
      if (data[type] === true) {
        const paramsObj = data[`${type}_params`];
        if (paramsObj && typeof paramsObj === 'object') {
          for (const [key, value] of Object.entries(paramsObj)) {
            if (typeof value === 'number') {
              params.push({
                key: `${prefix}.${type}_params.${key}`,
                label: `${label} ${type} — ${key}`,
                category: 'risk',
                currentValue: value,
              });
            }
          }
        }
      }
    }
  }

  // Extract trailing/breakeven ratios from stop_loss_mgmt
  const mgmt = draftData.stop_loss_mgmt;
  if (mgmt && typeof mgmt === 'object') {
    if (mgmt.trailing?.action === true && typeof mgmt.trailing.trailingRatio === 'number') {
      params.push({
        key: 'stop_loss_mgmt.trailing.trailingRatio',
        label: 'Trailing Ratio',
        category: 'risk',
        currentValue: mgmt.trailing.trailingRatio,
      });
    }
    if (mgmt.breakeven?.action === true && typeof mgmt.breakeven.profitRatio === 'number') {
      params.push({
        key: 'stop_loss_mgmt.breakeven.profitRatio',
        label: 'Breakeven Profit Ratio',
        category: 'risk',
        currentValue: mgmt.breakeven.profitRatio,
      });
    }
  }

  return params;
}

function countVariations(states: Record<string, ParamState>): number {
  let gridProduct = 1;
  let hasGrid = false;
  let sweepSum = 0;

  for (const s of Object.values(states)) {
    if (!s.enabled) continue;
    const { min, max, step } = s.range;
    const count = step > 0 ? Math.floor((max - min) / step) + 1 : 1;
    if (s.mode === 'grid') {
      gridProduct *= count;
      hasGrid = true;
    } else {
      sweepSum += count;
    }
  }

  return (hasGrid ? gridProduct : 0) + sweepSum;
}

function ParamRow({
  param,
  state,
  onChange,
}: {
  param: ParamConfig;
  state: ParamState;
  onChange: (update: Partial<ParamState>) => void;
}) {
  return (
    <div className="flex items-center gap-2 py-1">
      {/* Enable checkbox */}
      <input
        type="checkbox"
        checked={state.enabled}
        onChange={(e) => onChange({ enabled: e.target.checked })}
        className="w-3.5 h-3.5 rounded border-border accent-accent shrink-0"
      />

      {/* Label + current value */}
      <span className="text-xs text-text-secondary w-44 truncate" title={param.label}>
        {param.label}
      </span>
      <span className="text-xs text-text-muted w-10 text-right font-mono">
        {param.currentValue}
      </span>

      {/* Grid / Sweep toggle */}
      <button
        disabled={!state.enabled}
        onClick={() => onChange({ mode: state.mode === 'grid' ? 'sweep' : 'grid' })}
        className={`text-[10px] px-1.5 py-0.5 rounded font-medium border transition-colors ${
          !state.enabled
            ? 'bg-surface-2 text-text-muted border-border opacity-50'
            : state.mode === 'grid'
              ? 'bg-rose-500/10 text-rose-400 border-rose-500/20'
              : 'bg-blue-500/10 text-blue-400 border-blue-500/20'
        }`}
      >
        {state.mode === 'grid' ? 'Grid' : 'Sweep'}
      </button>

      {/* Min / Max / Step inputs */}
      <div className="flex items-center gap-1">
        <label className="text-[10px] text-text-muted">min</label>
        <input
          type="number"
          disabled={!state.enabled}
          value={state.range.min}
          onChange={(e) =>
            onChange({ range: { ...state.range, min: Number(e.target.value) } })
          }
          className="w-14 text-xs bg-surface-2 text-text-primary border border-border rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-40 font-mono"
        />
        <label className="text-[10px] text-text-muted">max</label>
        <input
          type="number"
          disabled={!state.enabled}
          value={state.range.max}
          onChange={(e) =>
            onChange({ range: { ...state.range, max: Number(e.target.value) } })
          }
          className="w-14 text-xs bg-surface-2 text-text-primary border border-border rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-40 font-mono"
        />
        <label className="text-[10px] text-text-muted">step</label>
        <input
          type="number"
          disabled={!state.enabled}
          value={state.range.step}
          onChange={(e) =>
            onChange({ range: { ...state.range, step: Number(e.target.value) } })
          }
          className="w-14 text-xs bg-surface-2 text-text-primary border border-border rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-40 font-mono"
        />
      </div>
    </div>
  );
}

export default function StressParamBuilder({
  draftData,
  onParamOverridesChange,
  onSingleOverridesChange,
}: StressParamBuilderProps) {
  const params = useMemo(() => extractParams(draftData), [draftData]);

  const [states, setStates] = useState<Record<string, ParamState>>({});
  const [indicatorsOpen, setIndicatorsOpen] = useState(true);
  const [conditionsOpen, setConditionsOpen] = useState(true);
  const [exitOpen, setExitOpen] = useState(true);
  const [riskOpen, setRiskOpen] = useState(true);

  // Initialize states when params change
  useEffect(() => {
    const initial: Record<string, ParamState> = {};
    for (const p of params) {
      initial[p.key] = states[p.key] ?? {
        enabled: false,
        mode: 'grid',
        range: smartDefaults(p.currentValue),
      };
    }
    setStates(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  // Build overrides whenever states change
  useEffect(() => {
    const paramOverrides: Record<string, any> = {};
    const singleOverrides: Record<string, any> = {};

    for (const [key, s] of Object.entries(states)) {
      if (!s.enabled) continue;
      const rangeObj = { min: s.range.min, max: s.range.max, step: s.range.step };
      if (s.mode === 'grid') {
        paramOverrides[key] = rangeObj;
      } else {
        singleOverrides[key] = rangeObj;
      }
    }

    onParamOverridesChange(paramOverrides);
    onSingleOverridesChange(singleOverrides);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [states]);

  const updateParam = (key: string, update: Partial<ParamState>) => {
    setStates((prev) => ({
      ...prev,
      [key]: { ...prev[key], ...update },
    }));
  };

  const indicatorParams = params.filter((p) => p.category === 'indicator');
  const conditionParams = params.filter((p) => p.category === 'condition');
  const exitParams = params.filter((p) => p.category === 'exit');
  const riskParams = params.filter((p) => p.category === 'risk');
  const totalVariations = countVariations(states);

  if (params.length === 0) {
    return (
      <div className="text-xs text-text-muted italic py-2">
        No tunable parameters found in draft JSON.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Indicators section */}
      {indicatorParams.length > 0 && (
        <div className="border border-border rounded-lg overflow-hidden">
          <button
            onClick={() => setIndicatorsOpen(!indicatorsOpen)}
            className="w-full flex items-center gap-2 px-3 py-1.5 bg-surface-2/50 hover:bg-surface-2/80 transition-colors"
          >
            <Activity size={12} className="text-text-muted" />
            <span className="text-xs font-medium text-text-secondary">Indicators</span>
            <span className="text-[10px] text-text-muted">({indicatorParams.length})</span>
            <span className="flex-1" />
            {indicatorsOpen ? <ChevronUp size={12} className="text-text-muted" /> : <ChevronDown size={12} className="text-text-muted" />}
          </button>
          {indicatorsOpen && (
            <div className="px-3 py-1.5">
              {indicatorParams.map((p) => (
                <ParamRow
                  key={p.key}
                  param={p}
                  state={states[p.key] ?? { enabled: false, mode: 'grid', range: smartDefaults(p.currentValue) }}
                  onChange={(update) => updateParam(p.key, update)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Conditions section */}
      {conditionParams.length > 0 && (
        <div className="border border-border rounded-lg overflow-hidden">
          <button
            onClick={() => setConditionsOpen(!conditionsOpen)}
            className="w-full flex items-center gap-2 px-3 py-1.5 bg-surface-2/50 hover:bg-surface-2/80 transition-colors"
          >
            <Crosshair size={12} className="text-text-muted" />
            <span className="text-xs font-medium text-text-secondary">Conditions</span>
            <span className="text-[10px] text-text-muted">({conditionParams.length})</span>
            <span className="flex-1" />
            {conditionsOpen ? <ChevronUp size={12} className="text-text-muted" /> : <ChevronDown size={12} className="text-text-muted" />}
          </button>
          {conditionsOpen && (
            <div className="px-3 py-1.5">
              {conditionParams.map((p) => (
                <ParamRow
                  key={p.key}
                  param={p}
                  state={states[p.key] ?? { enabled: false, mode: 'grid', range: smartDefaults(p.currentValue) }}
                  onChange={(update) => updateParam(p.key, update)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Exit section */}
      {exitParams.length > 0 && (
        <div className="border border-border rounded-lg overflow-hidden">
          <button
            onClick={() => setExitOpen(!exitOpen)}
            className="w-full flex items-center gap-2 px-3 py-1.5 bg-surface-2/50 hover:bg-surface-2/80 transition-colors"
          >
            <Timer size={12} className="text-text-muted" />
            <span className="text-xs font-medium text-text-secondary">Exit</span>
            <span className="flex-1" />
            {exitOpen ? <ChevronUp size={12} className="text-text-muted" /> : <ChevronDown size={12} className="text-text-muted" />}
          </button>
          {exitOpen && (
            <div className="px-3 py-1.5">
              {exitParams.map((p) => (
                <ParamRow
                  key={p.key}
                  param={p}
                  state={states[p.key] ?? { enabled: false, mode: 'grid', range: smartDefaults(p.currentValue) }}
                  onChange={(update) => updateParam(p.key, update)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Risk Management section */}
      {riskParams.length > 0 && (
        <div className="border border-border rounded-lg overflow-hidden">
          <button
            onClick={() => setRiskOpen(!riskOpen)}
            className="w-full flex items-center gap-2 px-3 py-1.5 bg-surface-2/50 hover:bg-surface-2/80 transition-colors"
          >
            <Shield size={12} className="text-text-muted" />
            <span className="text-xs font-medium text-text-secondary">Risk Management</span>
            <span className="text-[10px] text-text-muted">({riskParams.length})</span>
            <span className="flex-1" />
            {riskOpen ? <ChevronUp size={12} className="text-text-muted" /> : <ChevronDown size={12} className="text-text-muted" />}
          </button>
          {riskOpen && (
            <div className="px-3 py-1.5">
              {riskParams.map((p) => (
                <ParamRow
                  key={p.key}
                  param={p}
                  state={states[p.key] ?? { enabled: false, mode: 'grid', range: smartDefaults(p.currentValue) }}
                  onChange={(update) => updateParam(p.key, update)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Variation count warning */}
      {totalVariations > 0 && (
        <div
          className={`flex items-center gap-2 text-xs px-3 py-1.5 rounded border ${
            totalVariations > 500
              ? 'bg-danger/10 border-danger/20 text-danger'
              : totalVariations > 100
                ? 'bg-warn/10 border-warn/20 text-warn'
                : 'bg-surface-2/50 border-border text-text-secondary'
          }`}
        >
          {totalVariations > 100 && <AlertTriangle size={12} />}
          <span>
            <strong>{totalVariations}</strong> variation{totalVariations !== 1 ? 's' : ''} will be generated
          </span>
        </div>
      )}
    </div>
  );
}
