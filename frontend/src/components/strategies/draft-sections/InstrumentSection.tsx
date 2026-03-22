import type { DraftData } from '../../../types/draft-data';
import type { Instrument } from '../../../types/instrument';

interface Props {
  data: DraftData;
  todoFields: string[];
  instruments?: Instrument[];
  onSymbolChange?: (instrument: Instrument) => void;
  isMutating?: boolean;
}

const SEC_TYPE_COLORS: Record<string, string> = {
  FUT: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  STK: 'bg-accent/20 text-green-300 border-accent/30',
  OPT: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
  CASH: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
};

export default function InstrumentSection({ data, instruments, onSymbolChange, isMutating }: Props) {
  const secTypeColor = SEC_TYPE_COLORS[data.secType] ?? 'bg-surface-3/30 text-text-secondary border-border-hover/30';

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {/* Symbol - dropdown or static badge */}
      <div className="col-span-2 sm:col-span-1">
        <div className="text-xs text-text-muted mb-1">Symbol</div>
        {instruments && instruments.length > 0 && onSymbolChange ? (
          <select
            value={data.symbol}
            disabled={isMutating}
            onChange={(e) => {
              const selected = instruments.find(i => i.symbol === e.target.value);
              if (selected) onSymbolChange(selected);
            }}
            className="text-lg font-bold text-cyan-300 bg-cyan-500/10 border border-cyan-500/20 rounded-lg px-3 py-1 focus:outline-none focus:ring-1 focus:ring-cyan-400 disabled:opacity-50"
          >
            {!instruments.some(i => i.symbol === data.symbol) && (
              <option value={data.symbol} disabled>{data.symbol} (not found)</option>
            )}
            {instruments.map(i => (
              <option key={i.symbol} value={i.symbol}>
                {i.symbol} ({i.exchange})
              </option>
            ))}
          </select>
        ) : (
          <span className="inline-block text-lg font-bold text-cyan-300 bg-cyan-500/10 border border-cyan-500/20 rounded-lg px-3 py-1">
            {data.symbol}
          </span>
        )}
      </div>

      {/* SecType */}
      <div>
        <div className="text-xs text-text-muted mb-1">Type</div>
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
        <div className="text-xs text-text-muted mb-1">Currency</div>
        <span className="text-sm text-text-primary">{data.currency}</span>
      </div>

      {/* Multiplier */}
      <div>
        <div className="text-xs text-text-muted mb-1">Multiplier</div>
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
          <span className="text-sm text-text-primary">{data.rolling_days} days</span>
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
          <div className="text-xs text-text-muted mb-1">Trading Hours</div>
          <span className="text-sm text-text-primary">
            {'mode' in data.trading_hours
              ? `Entries: ${data.trading_hours.entries.start}-${data.trading_hours.entries.end} | Exits: ${data.trading_hours.exits.start}-${data.trading_hours.exits.end}`
              : `${data.trading_hours.start} - ${data.trading_hours.end}`
            }
          </span>
        </div>
      )}
    </div>
  );
}
