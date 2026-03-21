import type { DraftData } from '../../types/draft-data';

/**
 * Safely parse the Record<string, unknown> from DraftDetail.data into DraftData.
 * Returns the typed data, or null if parsing fails.
 */
export function parseDraftData(data: Record<string, unknown>): DraftData | null {
  try {
    // The data already has the right shape from the API, just cast with basic validation
    const d = data as unknown as DraftData;
    if (!d.strat_code || !d.symbol) return null;
    return d;
  } catch {
    return null;
  }
}

/** Check if a value is a _TODO marker */
export function isTodo(value: unknown): boolean {
  return typeof value === 'string' && value.trim() === '_TODO';
}

/** Indicator type categories for color coding */
const INDICATOR_CATEGORIES: Record<string, string> = {
  // Trend
  SMA: 'trend', EMA: 'trend', DEMA: 'trend', TEMA: 'trend', WMA: 'trend',
  ADX: 'trend', PLUS_DI: 'trend', MINUS_DI: 'trend', SUPERTREND: 'trend', ICHIMOKU: 'trend',
  // Oscillators
  RSI: 'oscillator', STOCH: 'oscillator', MACD: 'oscillator', CCI: 'oscillator', WILLR: 'oscillator', MFI: 'oscillator',
  ULTOSC: 'oscillator',
  // Volatility
  ATR: 'volatility', NATR: 'volatility', TRANGE: 'volatility', BBANDS: 'volatility',
  KELTNER_CHANNELS: 'volatility', ULCER_INDEX: 'volatility',
  // Price
  PRICE: 'price',
  // Custom
  PMax: 'custom', PMin: 'custom', BEARS_POWER: 'custom', SRPERCENTRANK: 'custom', price_formula: 'custom',
  // Data
  DATA: 'data',
};

export function getIndicatorCategory(type: string): string {
  return INDICATOR_CATEGORIES[type] ?? 'other';
}

/** Color classes by indicator category */
export function getIndicatorColors(category: string): string {
  switch (category) {
    case 'trend': return 'bg-blue-500/20 text-blue-300 border-blue-500/30';
    case 'oscillator': return 'bg-purple-500/20 text-purple-300 border-purple-500/30';
    case 'volatility': return 'bg-orange-500/20 text-orange-300 border-orange-500/30';
    case 'price': return 'bg-slate-600/30 text-slate-300 border-slate-500/30';
    case 'custom': return 'bg-teal-500/20 text-teal-300 border-teal-500/30';
    case 'data': return 'bg-slate-500/20 text-slate-400 border-slate-500/30';
    default: return 'bg-slate-600/30 text-slate-300 border-slate-500/30';
  }
}

/** Format stop-loss/take-profit in human-readable form */
export function formatStopLevel(params: DraftData['stop_loss_init']): string {
  if (params.indicator && params.indicator_params?.col) {
    const mult = params.indicator_params.multiple;
    const col = params.indicator_params.col;
    if (isTodo(mult)) return `${col} x _TODO`;
    return `${col} x ${mult}`;
  }
  if (params.pips) {
    const pv = params.pips_params?.pip_value ?? params.pips_params?.pips;
    const ps = params.pips_params?.pip_size;
    if (pv != null) {
      return ps != null ? `${pv} pips (x${ps})` : `${pv} pips`;
    }
  }
  if (params.percent && params.percent_params?.percent != null) {
    return `${params.percent_params.percent}%`;
  }
  return 'No definido';
}

/** Human-readable labels for TODO field paths */
const TOP_LEVEL_LABELS: Record<string, string> = {
  multiplier: 'Multiplicador del contrato',
  minTick: 'Tick mínimo',
  max_timePeriod: 'Período máximo',
  symbol: 'Símbolo',
  secType: 'Tipo de instrumento',
  exchange: 'Exchange',
  currency: 'Moneda',
};

const PARAM_LABELS: Record<string, string> = {
  timePeriod_1: 'Período',
  price_1: 'Precio',
  price_2: 'Precio 2',
  price_3: 'Precio 3',
  nbdevup: 'Desviación superior',
  nbdevdn: 'Desviación inferior',
  multiple: 'Múltiple',
};

export function humanizeFieldPath(path: string, data: DraftData | null): string {
  // Top-level fields
  if (TOP_LEVEL_LABELS[path]) return TOP_LEVEL_LABELS[path];

  // ind_list paths: ind_list.TIMEFRAME[INDEX].params.PARAM
  const indMatch = path.match(/^ind_list\.(.+)\[(\d+)]\.params\.(\w+)$/);
  if (indMatch && data) {
    const [, tf, idxStr, param] = indMatch;
    const idx = parseInt(idxStr, 10);
    const indicators = data.ind_list?.[tf];
    const ind = indicators?.[idx];
    const indCode = ind?.params?.indCode ?? ind?.indicator ?? `#${idx}`;
    const paramLabel = PARAM_LABELS[param] ?? param;
    return `${indCode}: ${paramLabel}`;
  }

  // control_params / order_params (kept for backward compat, even if section removed)
  const cpMatch = path.match(/^control_params\.(\w+)$/);
  if (cpMatch) {
    const labels: Record<string, string> = {
      start_date: 'Fecha inicio backtest',
      end_date: 'Fecha fin backtest',
      timestamp: 'Timestamp',
      slippage_amount: 'Slippage',
      comm_per_contract: 'Comisión/contrato',
      primary_timeframe: 'Timeframe principal',
    };
    return labels[cpMatch[1]] ?? cpMatch[1];
  }

  // stop_loss / take_profit
  const slMatch = path.match(/^(stop_loss|take_profit)_init\.indicator_params\.(\w+)$/);
  if (slMatch) {
    const side = slMatch[1] === 'stop_loss' ? 'Stop Loss' : 'Take Profit';
    const paramLabel = PARAM_LABELS[slMatch[2]] ?? slMatch[2];
    return `${side}: ${paramLabel}`;
  }

  // Fallback: return path as-is
  return path;
}

/** Sections that field paths map to, for TODO click-to-scroll */
type SectionId = 'instrument' | 'indicators' | 'conditions' | 'risk' | 'notes' | 'backtest';

export function fieldToSection(fieldPath: string): SectionId {
  if (fieldPath.startsWith('ind_list')) return 'indicators';
  if (fieldPath.startsWith('long_conds') || fieldPath.startsWith('short_conds') || fieldPath.startsWith('exit_conds')) return 'conditions';
  if (fieldPath.startsWith('stop_loss') || fieldPath.startsWith('take_profit')) return 'risk';
  if (fieldPath.startsWith('_notes')) return 'notes';
  if (fieldPath.startsWith('control_params') || fieldPath.startsWith('order_params')) return 'backtest';
  // Top-level fields like symbol, secType, etc.
  return 'instrument';
}

/** Get TODO fields that belong to a given section */
export function getTodoFieldsForSection(todoFields: string[] | null, sectionId: SectionId): string[] {
  if (!todoFields) return [];
  return todoFields.filter(f => fieldToSection(f) === sectionId);
}
