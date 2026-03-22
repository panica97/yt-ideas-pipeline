import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { setStrategyStatus, getDraftsByStrategy } from '../../services/strategies';
import ConfirmDialog from '../common/ConfirmDialog';
import DraftCard from './DraftCard';
import type { Strategy } from '../../types/strategy';

interface StrategyDetailProps {
  strategy: Strategy;
  onClose: () => void;
  onStatusChange?: () => void;
}

function RuleList({ title, rules }: { title: string; rules: Record<string, unknown>[] | null }) {
  if (!rules || rules.length === 0) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold text-text-muted uppercase mb-2">{title}</h4>
      <ul className="space-y-1">
        {rules.map((rule, i) => (
          <li key={i} className="text-sm text-text-secondary bg-surface-2/30 rounded px-3 py-1.5">
            {typeof rule === 'string' ? rule : JSON.stringify(rule)}
          </li>
        ))}
      </ul>
    </div>
  );
}

type TargetStatus = 'pending' | 'idea' | 'validated';

interface ConfirmAction {
  targetStatus: TargetStatus;
  title: string;
  message: string;
  confirmLabel: string;
  confirmVariant: 'danger' | 'success' | 'primary';
}

export default function StrategyDetail({ strategy, onClose, onStatusChange }: StrategyDetailProps) {
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null);
  const [updating, setUpdating] = useState(false);
  const queryClient = useQueryClient();

  const { data: drafts } = useQuery({
    queryKey: ['drafts-by-strategy', strategy.name],
    queryFn: () => getDraftsByStrategy(strategy.name),
  });

  const handleConfirm = async () => {
    if (!confirmAction) return;
    setUpdating(true);
    try {
      await setStrategyStatus(strategy.name, confirmAction.targetStatus);
      await queryClient.invalidateQueries({ queryKey: ['pending-strategies'] });
      await queryClient.invalidateQueries({ queryKey: ['ideas'] });
      await queryClient.invalidateQueries({ queryKey: ['validated-strategies'] });
      await queryClient.invalidateQueries({ queryKey: ['strategies-by-session'] });
      onStatusChange?.();
    } catch (err) {
      console.error('Error updating strategy status:', err);
    } finally {
      setConfirmAction(null);
      setUpdating(false);
    }
  };

  const openConfirm = (action: ConfirmAction) => setConfirmAction(action);

  const renderStatusButtons = () => {
    switch (strategy.status) {
      case 'pending':
        return (
          <>
            <button
              onClick={() => openConfirm({
                targetStatus: 'idea',
                title: 'Mark as Idea',
                message: 'This strategy will move to the Ideas tab.',
                confirmLabel: 'Mark as Idea',
                confirmVariant: 'primary',
              })}
              disabled={updating}
              className="px-3 py-1 text-sm rounded transition-colors disabled:opacity-50 text-text-primary bg-accent hover:bg-accent-hover"
            >
              Mark as Idea
            </button>
            <button
              onClick={() => openConfirm({
                targetStatus: 'validated',
                title: 'Mark as Strategy',
                message: 'This strategy will move directly to the Strategies tab.',
                confirmLabel: 'Mark as Strategy',
                confirmVariant: 'success',
              })}
              disabled={updating}
              className="px-3 py-1 text-sm rounded transition-colors disabled:opacity-50 text-text-primary bg-accent hover:bg-accent-hover"
            >
              Mark as Strategy
            </button>
          </>
        );
      case 'idea':
        return (
          <>
            <button
              onClick={() => openConfirm({
                targetStatus: 'validated',
                title: 'Promote to Strategy',
                message: 'This idea will move to the Strategies tab.',
                confirmLabel: 'Promote',
                confirmVariant: 'success',
              })}
              disabled={updating}
              className="px-3 py-1 text-sm rounded transition-colors disabled:opacity-50 text-text-primary bg-accent hover:bg-accent-hover"
            >
              Promote to Strategy
            </button>
            <button
              onClick={() => openConfirm({
                targetStatus: 'pending',
                title: 'Return to Pending',
                message: 'This idea will return to the Pending tab.',
                confirmLabel: 'Return',
                confirmVariant: 'danger',
              })}
              disabled={updating}
              className="px-3 py-1 text-sm rounded transition-colors disabled:opacity-50 text-text-primary bg-surface-3 hover:bg-surface-2"
            >
              Return to Pending
            </button>
          </>
        );
      case 'validated':
        return (
          <button
            onClick={() => openConfirm({
              targetStatus: 'idea',
              title: 'Return to Ideas',
              message: 'This strategy will return to the Ideas tab.',
              confirmLabel: 'Return',
              confirmVariant: 'danger',
            })}
            disabled={updating}
            className="px-3 py-1 text-sm rounded transition-colors disabled:opacity-50 text-text-primary bg-warn hover:bg-warn-hover"
          >
            Return to Ideas
          </button>
        );
    }
  };

  return (
    <div className="bg-surface-1 border border-border rounded-lg p-5 space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-base font-semibold text-text-primary">{strategy.name}</h3>
          {strategy.source_channel && (
            <p className="text-xs text-accent mt-0.5">{strategy.source_channel}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {renderStatusButtons()}
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-secondary text-sm transition-colors"
          >
            Close
          </button>
        </div>
      </div>

      <ConfirmDialog
        open={!!confirmAction}
        title={confirmAction?.title ?? ''}
        message={confirmAction?.message ?? ''}
        confirmLabel={confirmAction?.confirmLabel ?? 'Confirm'}
        confirmVariant={confirmAction?.confirmVariant ?? 'danger'}
        onConfirm={handleConfirm}
        onCancel={() => setConfirmAction(null)}
      />

      {strategy.description && (
        <div>
          <h4 className="text-xs font-semibold text-text-muted uppercase mb-1">Description</h4>
          <p className="text-sm text-text-secondary leading-relaxed">{strategy.description}</p>
        </div>
      )}

      {/* Parameters table */}
      {strategy.parameters && strategy.parameters.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-text-muted uppercase mb-2">Parameters</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-1 px-2 text-text-muted">Name</th>
                  <th className="text-left py-1 px-2 text-text-muted">Type</th>
                  <th className="text-left py-1 px-2 text-text-muted">Default</th>
                  <th className="text-left py-1 px-2 text-text-muted">Range</th>
                </tr>
              </thead>
              <tbody>
                {strategy.parameters.map((param, i) => (
                  <tr key={i} className="border-b border-border/50">
                    <td className="py-1 px-2 text-text-secondary">{String(param.name || param.parameter || '-')}</td>
                    <td className="py-1 px-2 text-text-muted">{String(param.type || '-')}</td>
                    <td className="py-1 px-2 text-text-muted">{String(param.default ?? '-')}</td>
                    <td className="py-1 px-2 text-text-muted">{String(param.range || '-')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <RuleList title="Entry Rules" rules={strategy.entry_rules} />
      <RuleList title="Exit Rules" rules={strategy.exit_rules} />
      <RuleList title="Risk Management" rules={strategy.risk_management} />
      <RuleList title="Notes" rules={strategy.notes} />

      {/* Source videos */}
      {strategy.source_videos && strategy.source_videos.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-text-muted uppercase mb-2">Source Videos</h4>
          <div className="flex flex-wrap gap-2">
            {strategy.source_videos.map((vid, i) => (
              <a
                key={i}
                href={vid.startsWith('http') ? vid : `https://www.youtube.com/watch?v=${vid}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-accent hover:text-accent-hover bg-surface-2/50 rounded px-2 py-1"
              >
                {vid.startsWith('http') ? new URL(vid).searchParams.get('v') || vid : vid}
              </a>
            ))}
          </div>
        </div>
      )}

      {/* IBKR Drafts */}
      {drafts && drafts.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-text-muted uppercase mb-2">
            IBKR Drafts ({drafts.length})
          </h4>
          <div className="space-y-2">
            {drafts.map((draft) => (
              <DraftCard key={draft.strat_code} draft={draft} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
