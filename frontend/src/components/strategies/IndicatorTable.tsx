import TodoHighlight from './TodoHighlight';

interface Indicator {
  indicator?: string;
  params?: Record<string, unknown>;
  timeframe?: string;
  alias?: string;
  [key: string]: unknown;
}

interface IndicatorTableProps {
  indicators: Indicator[];
  todoFields?: string[];
}

function isTodo(value: unknown): boolean {
  return typeof value === 'string' && value === '_TODO';
}

function renderValue(value: unknown, fieldPath: string, todoFields: string[]): React.ReactNode {
  if (isTodo(value) || todoFields.includes(fieldPath)) {
    return <TodoHighlight>_TODO</TodoHighlight>;
  }
  if (typeof value === 'object' && value !== null) {
    return JSON.stringify(value);
  }
  return String(value ?? '-');
}

export default function IndicatorTable({ indicators, todoFields = [] }: IndicatorTableProps) {
  if (!indicators || indicators.length === 0) return null;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border">
            <th className="text-left py-1 px-2 text-text-muted">Indicator</th>
            <th className="text-left py-1 px-2 text-text-muted">Parameters</th>
            <th className="text-left py-1 px-2 text-text-muted">Timeframe</th>
            <th className="text-left py-1 px-2 text-text-muted">Alias</th>
          </tr>
        </thead>
        <tbody>
          {indicators.map((ind, i) => (
            <tr key={i} className="border-b border-border/50">
              <td className="py-1 px-2 text-text-secondary font-medium">
                {renderValue(ind.indicator, `indicators.${i}.indicator`, todoFields)}
              </td>
              <td className="py-1 px-2 text-text-muted">
                {ind.params ? renderValue(ind.params, `indicators.${i}.params`, todoFields) : '-'}
              </td>
              <td className="py-1 px-2 text-text-muted">
                {renderValue(ind.timeframe, `indicators.${i}.timeframe`, todoFields)}
              </td>
              <td className="py-1 px-2 text-text-muted">
                {renderValue(ind.alias, `indicators.${i}.alias`, todoFields)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
