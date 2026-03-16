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
      <h4 className="text-xs font-semibold text-slate-400 uppercase mb-2">{title}</h4>
      <ul className="space-y-1">
        {rules.map((rule, i) => (
          <li key={i} className="text-sm text-slate-300 bg-slate-700/30 rounded px-3 py-1.5">
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
                title: 'Marcar como idea',
                message: 'Esta estrategia pasara a la pestana Ideas.',
                confirmLabel: 'Marcar como idea',
                confirmVariant: 'primary',
              })}
              disabled={updating}
              className="px-3 py-1 text-sm rounded transition-colors disabled:opacity-50 text-white bg-cyan-600 hover:bg-cyan-700"
            >
              Marcar como idea
            </button>
            <button
              onClick={() => openConfirm({
                targetStatus: 'validated',
                title: 'Marcar como final',
                message: 'Esta estrategia pasara directamente a la pestana Finales.',
                confirmLabel: 'Marcar como final',
                confirmVariant: 'success',
              })}
              disabled={updating}
              className="px-3 py-1 text-sm rounded transition-colors disabled:opacity-50 text-white bg-green-600 hover:bg-green-700"
            >
              Marcar como final
            </button>
          </>
        );
      case 'idea':
        return (
          <>
            <button
              onClick={() => openConfirm({
                targetStatus: 'validated',
                title: 'Promover a final',
                message: 'Esta idea pasara a la pestana Finales.',
                confirmLabel: 'Promover',
                confirmVariant: 'success',
              })}
              disabled={updating}
              className="px-3 py-1 text-sm rounded transition-colors disabled:opacity-50 text-white bg-green-600 hover:bg-green-700"
            >
              Promover a final
            </button>
            <button
              onClick={() => openConfirm({
                targetStatus: 'pending',
                title: 'Devolver a pendientes',
                message: 'Esta idea volvera a la pestana Pendientes.',
                confirmLabel: 'Devolver',
                confirmVariant: 'danger',
              })}
              disabled={updating}
              className="px-3 py-1 text-sm rounded transition-colors disabled:opacity-50 text-white bg-slate-600 hover:bg-slate-700"
            >
              Devolver a pendientes
            </button>
          </>
        );
      case 'validated':
        return (
          <button
            onClick={() => openConfirm({
              targetStatus: 'idea',
              title: 'Devolver a ideas',
              message: 'Esta estrategia volvera a la pestana Ideas.',
              confirmLabel: 'Devolver',
              confirmVariant: 'danger',
            })}
            disabled={updating}
            className="px-3 py-1 text-sm rounded transition-colors disabled:opacity-50 text-white bg-amber-600 hover:bg-amber-700"
          >
            Devolver a ideas
          </button>
        );
    }
  };

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-5 space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-base font-semibold text-white">{strategy.name}</h3>
          {strategy.source_channel && (
            <p className="text-xs text-primary-400 mt-0.5">{strategy.source_channel}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {renderStatusButtons()}
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-300 text-sm transition-colors"
          >
            Cerrar
          </button>
        </div>
      </div>

      <ConfirmDialog
        open={!!confirmAction}
        title={confirmAction?.title ?? ''}
        message={confirmAction?.message ?? ''}
        confirmLabel={confirmAction?.confirmLabel ?? 'Confirmar'}
        confirmVariant={confirmAction?.confirmVariant ?? 'danger'}
        onConfirm={handleConfirm}
        onCancel={() => setConfirmAction(null)}
      />

      {strategy.description && (
        <div>
          <h4 className="text-xs font-semibold text-slate-400 uppercase mb-1">Descripcion</h4>
          <p className="text-sm text-slate-300 leading-relaxed">{strategy.description}</p>
        </div>
      )}

      {/* Parameters table */}
      {strategy.parameters && strategy.parameters.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-slate-400 uppercase mb-2">Parametros</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left py-1 px-2 text-slate-500">Nombre</th>
                  <th className="text-left py-1 px-2 text-slate-500">Tipo</th>
                  <th className="text-left py-1 px-2 text-slate-500">Default</th>
                  <th className="text-left py-1 px-2 text-slate-500">Rango</th>
                </tr>
              </thead>
              <tbody>
                {strategy.parameters.map((param, i) => (
                  <tr key={i} className="border-b border-slate-700/50">
                    <td className="py-1 px-2 text-slate-300">{String(param.name || param.parameter || '-')}</td>
                    <td className="py-1 px-2 text-slate-400">{String(param.type || '-')}</td>
                    <td className="py-1 px-2 text-slate-400">{String(param.default ?? '-')}</td>
                    <td className="py-1 px-2 text-slate-400">{String(param.range || '-')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <RuleList title="Reglas de entrada" rules={strategy.entry_rules} />
      <RuleList title="Reglas de salida" rules={strategy.exit_rules} />
      <RuleList title="Gestion de riesgo" rules={strategy.risk_management} />
      <RuleList title="Notas" rules={strategy.notes} />

      {/* Source videos */}
      {strategy.source_videos && strategy.source_videos.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-slate-400 uppercase mb-2">Videos fuente</h4>
          <div className="flex flex-wrap gap-2">
            {strategy.source_videos.map((vid, i) => (
              <a
                key={i}
                href={vid.startsWith('http') ? vid : `https://www.youtube.com/watch?v=${vid}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-primary-400 hover:text-primary-300 bg-slate-700/50 rounded px-2 py-1"
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
          <h4 className="text-xs font-semibold text-slate-400 uppercase mb-2">
            Propuestas IBKR ({drafts.length})
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
