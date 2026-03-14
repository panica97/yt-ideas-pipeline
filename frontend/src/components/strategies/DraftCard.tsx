import type { DraftSummary } from '../../types/draft';
import TodoBadge from '../common/TodoBadge';

interface DraftCardProps {
  draft: DraftSummary;
  onClick: () => void;
}

function StatusTag({ label, active }: { label: string; active: boolean }) {
  return (
    <span
      className={`text-xs px-1.5 py-0.5 rounded ${
        active
          ? 'bg-green-500/20 text-green-400 border border-green-500/30'
          : 'bg-slate-700/50 text-slate-500 border border-slate-600'
      }`}
    >
      {label}
    </span>
  );
}

export default function DraftCard({ draft, onClick }: DraftCardProps) {
  return (
    <div
      onClick={onClick}
      className="bg-slate-800 border border-slate-700 rounded-lg p-4 cursor-pointer hover:border-slate-600 transition-colors"
    >
      <div className="flex items-start justify-between mb-2">
        <div>
          <span className="text-xs text-slate-500 font-mono">{draft.strat_code}</span>
          <h3 className="text-sm font-semibold text-white">{draft.strat_name}</h3>
          {draft.symbol && <span className="text-xs text-primary-400">{draft.symbol}</span>}
        </div>
        <TodoBadge count={draft.todo_count} />
      </div>
      <div className="flex items-center gap-2">
        <StatusTag label="active" active={draft.active} />
        <StatusTag label="tested" active={draft.tested} />
        <StatusTag label="prod" active={draft.prod} />
      </div>
    </div>
  );
}
