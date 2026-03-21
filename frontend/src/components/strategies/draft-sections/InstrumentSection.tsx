import type { DraftData } from '../../../types/draft-data';
interface Props {
  data: DraftData;
  todoFields: string[];
}

const SEC_TYPE_COLORS: Record<string, string> = {
  FUT: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  STK: 'bg-accent/20 text-green-300 border-accent/30',
  OPT: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
  CASH: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
};

export default function InstrumentSection({ data }: Props) {
  const secTypeColor = SEC_TYPE_COLORS[data.secType] ?? 'bg-surface-3/30 text-text-secondary border-border-hover/30';

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {/* Symbol - large badge */}
      <div className="col-span-2 sm:col-span-1">
        <div className="text-xs text-text-muted mb-1">Symbol</div>
        <span className="inline-block text-lg font-bold text-cyan-300 bg-cyan-500/10 border border-cyan-500/20 rounded-lg px-3 py-1">
          {data.symbol}
        </span>
      </div>

      {/* SecType */}
      <div>
        <div className="text-xs text-text-muted mb-1">Tipo</div>
        <span className={`inline-block text-xs font-medium px-2 py-1 rounded border ${secTypeColor}`}>
          {data.secType}
        </span>
      </div>

      {/* Exchange */}
      <div>
        <div className="text-xs text-text-muted mb-1">Exchange</div>
        <span className="text-sm text-text-primary">{data.exchange}</span>
      </div>

      {/* Currency */}
      <div>
        <div className="text-xs text-text-muted mb-1">Moneda</div>
        <span className="text-sm text-text-primary">{data.currency}</span>
      </div>

      {/* Multiplier */}
      <div>
        <div className="text-xs text-text-muted mb-1">Multiplicador</div>
        <span className="text-sm text-text-primary">{data.multiplier}</span>
      </div>

      {/* MinTick */}
      <div>
        <div className="text-xs text-text-muted mb-1">Min Tick</div>
        <span className="text-sm text-text-primary">{data.minTick}</span>
      </div>

      {/* Timeframe */}
      <div>
        <div className="text-xs text-text-muted mb-1">Timeframe</div>
        <span className="inline-block text-xs font-medium px-2 py-1 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
          {data.process_freq ?? 'N/A'}
        </span>
      </div>

      {/* Process freq / rolling */}
      {data.rolling_days != null && (
        <div>
          <div className="text-xs text-text-muted mb-1">Rolling</div>
          <span className="text-sm text-text-primary">{data.rolling_days} dias</span>
        </div>
      )}

      {/* UTC Timezone */}
      {data.UTC_tz != null && (
        <div>
          <div className="text-xs text-text-muted mb-1">Timezone</div>
          <span className="text-sm text-text-primary">UTC{data.UTC_tz >= 0 ? '+' : ''}{data.UTC_tz}</span>
        </div>
      )}

      {/* Trading Hours */}
      {data.trading_hours != null && (
        <div className="col-span-2">
          <div className="text-xs text-text-muted mb-1">Horario Trading</div>
          <span className="text-sm text-text-primary">
            {'mode' in data.trading_hours
              ? `Entradas: ${data.trading_hours.entries.start}-${data.trading_hours.entries.end} | Salidas: ${data.trading_hours.exits.start}-${data.trading_hours.exits.end}`
              : `${data.trading_hours.start} - ${data.trading_hours.end}`
            }
          </span>
        </div>
      )}
    </div>
  );
}
