import type { DraftData } from '../../../types/draft-data';
import { formatStopLevel } from '../draft-utils';
import TodoHighlight from '../TodoHighlight';

interface Props {
  data: DraftData;
  todoFields: string[];
}

function StopLevelCard({ label, params, todoFields, prefix }: {
  label: string;
  params: DraftData['stop_loss_init'];
  todoFields: string[];
  prefix: string;
}) {
  const formatted = formatStopLevel(params);
  const hasTodoInSection = todoFields.some(f => f.startsWith(prefix));

  return (
    <div className="bg-surface-1/40 rounded-lg p-3 border border-border/50">
      <div className="text-xs font-semibold uppercase text-text-muted mb-2">{label}</div>
      <div className="text-sm text-text-primary">
        {formatted === 'Not defined' ? (
          <span className="text-text-muted italic">{formatted}</span>
        ) : (
          <span className="font-mono">
            {formatted}
            {hasTodoInSection && (
              <span className="ml-2"><TodoHighlight>_TODO</TodoHighlight></span>
            )}
          </span>
        )}
      </div>
      <div className="flex gap-3 mt-2 text-[10px]">
        <span className={params.indicator ? 'text-accent' : 'text-text-muted'}>
          {params.indicator ? '\u2713' : '\u2717'} Indicator
        </span>
        <span className={params.pips ? 'text-accent' : 'text-text-muted'}>
          {params.pips ? '\u2713' : '\u2717'} Pips
        </span>
        <span className={params.percent ? 'text-accent' : 'text-text-muted'}>
          {params.percent ? '\u2713' : '\u2717'} Percent
        </span>
      </div>
    </div>
  );
}

export default function RiskSection({ data, todoFields }: Props) {
  const { stop_loss_mgmt: mgmt } = data;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <StopLevelCard label="Stop Loss" params={data.stop_loss_init} todoFields={todoFields} prefix="stop_loss_init" />
        <StopLevelCard label="Take Profit" params={data.take_profit_init} todoFields={todoFields} prefix="take_profit_init" />
      </div>

      {/* Management */}
      {mgmt && (
        <div className="flex gap-4 text-xs">
          <div className={`flex items-center gap-1.5 px-2 py-1 rounded ${mgmt.breakeven?.action ? 'bg-accent/10 text-accent' : 'bg-surface-1/40 text-text-muted'}`}>
            <span>{mgmt.breakeven?.action ? '\u2713' : '\u2717'}</span>
            <span>Breakeven (ratio: {mgmt.breakeven?.profitRatio ?? '-'})</span>
          </div>
          <div className={`flex items-center gap-1.5 px-2 py-1 rounded ${mgmt.trailing?.action ? 'bg-accent/10 text-accent' : 'bg-surface-1/40 text-text-muted'}`}>
            <span>{mgmt.trailing?.action ? '\u2713' : '\u2717'}</span>
            <span>Trailing (ratio: {mgmt.trailing?.trailingRatio ?? '-'})</span>
          </div>
        </div>
      )}
    </div>
  );
}
