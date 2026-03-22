import { useState } from 'react';
import type { DraftDetail } from '../../types/draft';
import DraftViewer from './DraftViewer';

interface DraftCardProps {
  draft: DraftDetail;
}

function StatusTag({ label, active }: { label: string; active: boolean }) {
  return (
    <span
      className={`text-xs px-1.5 py-0.5 rounded ${
        active
          ? 'bg-accent/20 text-accent border border-accent/30'
          : 'bg-surface-2/50 text-text-muted border border-border'
      }`}
    >
      {label}
    </span>
  );
}

export default function DraftCard({ draft }: DraftCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-surface-1 border border-border rounded-lg overflow-hidden">
      {/* Collapsed header — always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 text-left hover:bg-surface-2/30 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-sm font-semibold text-text-primary truncate">{draft.strat_name}</span>
          <span className="text-xs font-mono text-text-muted bg-surface-2/50 px-1.5 py-0.5 rounded shrink-0">
            {draft.strat_code}
          </span>
          <span
            className={`text-xs px-1.5 py-0.5 rounded shrink-0 ${
              draft.todo_count > 0
                ? 'bg-warn/20 text-warn border border-warn/30'
                : 'bg-accent/20 text-accent border border-accent/30'
            }`}
          >
            {draft.todo_count > 0 ? `${draft.todo_count} TODOs` : 'Complete'}
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-2">
          <StatusTag label="active" active={draft.active} />
          <StatusTag label="tested" active={draft.tested} />
          <StatusTag label="prod" active={draft.prod} />
          <span className="text-text-muted text-xs ml-1">{expanded ? '\u25B2' : '\u25BC'}</span>
        </div>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-border p-3">
          <DraftViewer draft={draft} />
        </div>
      )}
    </div>
  );
}
