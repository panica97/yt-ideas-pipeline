import type { DraftDetail as DraftDetailType } from '../../types/draft';
import TodoBadge from '../common/TodoBadge';
import TodoHighlight from './TodoHighlight';
import IndicatorTable from './IndicatorTable';
import ConditionList from './ConditionList';

interface DraftDetailProps {
  draft: DraftDetailType;
  onClose: () => void;
}

function isTodo(value: unknown): boolean {
  return typeof value === 'string' && value === '_TODO';
}

function renderField(label: string, value: unknown, todoFields: string[], fieldPath: string): React.ReactNode {
  const hasTodo = isTodo(value) || todoFields.includes(fieldPath);
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-text-muted">{label}:</span>
      <span className="text-xs text-text-secondary">
        {hasTodo ? <TodoHighlight>_TODO</TodoHighlight> : String(value ?? '-')}
      </span>
    </div>
  );
}

export default function DraftDetail({ draft, onClose }: DraftDetailProps) {
  const data = draft.data;
  const todoFields = draft.todo_fields ?? [];
  const instrument = data.instrument as Record<string, unknown> | undefined;
  const indicators = (data.indicators || data.indicadores) as Record<string, unknown>[] | undefined;
  const condLong = (data.conditions_long || data.condiciones_long) as Record<string, unknown>[] | undefined;
  const condShort = (data.conditions_short || data.condiciones_short) as Record<string, unknown>[] | undefined;
  const stopLoss = (data.stop_loss_init || data.stop_loss) as Record<string, unknown> | undefined;
  const takeProfit = (data.take_profit_init || data.take_profit) as Record<string, unknown> | undefined;
  const controlParams = (data.parametros_control || data.control_params) as Record<string, unknown> | undefined;
  const notes = data._notes as Record<string, unknown> | string | undefined;

  return (
    <div className="bg-surface-1 border border-border rounded-lg p-5 space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-muted font-mono">{draft.strat_code}</span>
            <TodoBadge count={draft.todo_count} />
          </div>
          <h3 className="text-base font-semibold text-text-primary mt-1">{draft.strat_name}</h3>
        </div>
        <button
          onClick={onClose}
          className="text-text-muted hover:text-text-secondary text-sm transition-colors"
        >
          Close
        </button>
      </div>

      {/* Instrumento */}
      {instrument && (
        <div>
          <h4 className="text-xs font-semibold text-text-muted uppercase mb-2">Instrument</h4>
          <div className="bg-surface-2/30 rounded p-3 space-y-1">
            {renderField('Symbol', instrument.symbol, todoFields, 'instrument.symbol')}
            {renderField('Type', instrument.secType, todoFields, 'instrument.secType')}
            {renderField('Exchange', instrument.exchange, todoFields, 'instrument.exchange')}
            {renderField('Currency', instrument.currency, todoFields, 'instrument.currency')}
            {renderField('Multiplier', instrument.multiplier, todoFields, 'instrument.multiplier')}
          </div>
        </div>
      )}

      {/* Indicadores */}
      {indicators && indicators.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-text-muted uppercase mb-2">Indicators</h4>
          <IndicatorTable indicators={indicators} todoFields={todoFields} />
        </div>
      )}

      {/* Condiciones Long */}
      {condLong && condLong.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-text-muted uppercase mb-2">Long Conditions</h4>
          <ConditionList conditions={condLong} todoFields={todoFields} basePath="conditions_long" />
        </div>
      )}

      {/* Condiciones Short */}
      {condShort && condShort.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-text-muted uppercase mb-2">Short Conditions</h4>
          <ConditionList conditions={condShort} todoFields={todoFields} basePath="conditions_short" />
        </div>
      )}

      {/* Stop Loss / Take Profit */}
      {(stopLoss || takeProfit) && (
        <div>
          <h4 className="text-xs font-semibold text-text-muted uppercase mb-2">Stop Loss / Take Profit</h4>
          <div className="bg-surface-2/30 rounded p-3 space-y-2">
            {stopLoss && (
              <div>
                <p className="text-xs text-text-muted font-medium mb-1">Stop Loss</p>
                {Object.entries(stopLoss).map(([key, val]) => (
                  <div key={key}>
                    {renderField(key, val, todoFields, `stop_loss_init.${key}`)}
                  </div>
                ))}
              </div>
            )}
            {takeProfit && (
              <div>
                <p className="text-xs text-text-muted font-medium mb-1">Take Profit</p>
                {Object.entries(takeProfit).map(([key, val]) => (
                  <div key={key}>
                    {renderField(key, val, todoFields, `take_profit_init.${key}`)}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Parametros de control */}
      {controlParams && (
        <div>
          <h4 className="text-xs font-semibold text-text-muted uppercase mb-2">Control Parameters</h4>
          <div className="bg-surface-2/30 rounded p-3 space-y-1">
            {Object.entries(controlParams).map(([key, val]) => (
              <div key={key}>
                {renderField(key, val, todoFields, `parametros_control.${key}`)}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Notas */}
      {notes && (
        <div>
          <h4 className="text-xs font-semibold text-text-muted uppercase mb-2">Notes</h4>
          <div className="bg-surface-2/30 rounded p-3 text-xs text-text-secondary leading-relaxed">
            {typeof notes === 'string' ? (
              <p>{notes}</p>
            ) : (
              Object.entries(notes).map(([key, val]) => (
                <div key={key} className="mb-1">
                  <span className="text-text-muted font-medium">{key}:</span>{' '}
                  <span>{String(val)}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
