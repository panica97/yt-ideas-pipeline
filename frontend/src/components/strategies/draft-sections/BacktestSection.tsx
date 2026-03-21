import type { DraftData } from '../../../types/draft-data';
import { isTodo } from '../draft-utils';
import TodoHighlight from '../TodoHighlight';

interface Props {
  data: DraftData;
  todoFields: string[];
}

function StatCell({ label, value, isTodoVal }: { label: string; value: unknown; isTodoVal: boolean }) {
  return (
    <div className="bg-slate-800/40 rounded p-2 border border-slate-700/50">
      <div className="text-[10px] text-slate-500 uppercase mb-0.5">{label}</div>
      <div className="text-sm">
        {isTodoVal ? (
          <TodoHighlight>_TODO</TodoHighlight>
        ) : (
          <span className="text-slate-200 font-mono">{String(value ?? 'N/A')}</span>
        )}
      </div>
    </div>
  );
}

export default function BacktestSection({ data }: Props) {
  const cp = data.control_params;
  const op = data.order_params;

  if (!cp || !op) {
    return (
      <div className="bg-slate-800/40 rounded p-3 border border-slate-700/50 text-sm text-slate-500 italic">
        Parámetros de control no disponibles
      </div>
    );
  }

  const stats = [
    { label: 'Start Date', value: cp.start_date, todo: isTodo(cp.start_date) },
    { label: 'End Date', value: cp.end_date, todo: isTodo(cp.end_date) },
    { label: 'Slippage', value: cp.slippage_amount, todo: isTodo(cp.slippage_amount) },
    { label: 'Comision/contrato', value: cp.comm_per_contract, todo: isTodo(cp.comm_per_contract) },
    { label: 'Timeframe', value: cp.primary_timeframe, todo: false },
    { label: 'Max RPO', value: op.max_rpo, todo: false },
    { label: 'Min Volume', value: op.min_volume, todo: false },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
      {stats.map(s => (
        <StatCell key={s.label} label={s.label} value={s.value} isTodoVal={s.todo} />
      ))}
    </div>
  );
}
