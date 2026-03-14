import type { ResearchSession } from '../../types/research';
import ProgressBar from './ProgressBar';
import StepIndicator from './StepIndicator';

interface ResearchStatusProps {
  session: ResearchSession;
}

const STEP_DISPLAY: Record<string, string> = {
  preflight: 'Comprobacion de autenticacion',
  'yt-scraper': 'Buscando videos',
  'notebooklm-analyst': 'Extrayendo estrategias',
  translator: 'Traduciendo a JSON',
  cleanup: 'Limpieza',
  'db-manager': 'Guardando en base de datos',
  summary: 'Resumen final',
};

function getStepDisplay(stepName: string | null, stepDisplay: string | null): string {
  if (stepDisplay) return stepDisplay;
  if (stepName && STEP_DISPLAY[stepName]) return STEP_DISPLAY[stepName];
  return stepName || 'Iniciando...';
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'hace un momento';
  if (mins === 1) return 'hace 1 minuto';
  if (mins < 60) return `hace ${mins} minutos`;
  const hours = Math.floor(mins / 60);
  if (hours === 1) return 'hace 1 hora';
  return `hace ${hours} horas`;
}

export default function ResearchStatus({ session }: ResearchStatusProps) {
  const statusLabel =
    session.status === 'running'
      ? 'EN CURSO'
      : session.status === 'completed'
        ? 'COMPLETADO'
        : 'ERROR';

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-5 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <StepIndicator status={session.status} />
          <span className="text-sm font-semibold text-white">
            Sesion #{session.id} - {session.topic}
          </span>
        </div>
        <span className="text-xs text-slate-400">{statusLabel}</span>
      </div>

      {/* Progress bar */}
      {session.status === 'running' && (
        <ProgressBar step={session.step} totalSteps={session.total_steps} />
      )}

      {/* Details */}
      <div className="space-y-1 text-sm">
        <p className="text-slate-300">
          <span className="text-slate-500">Paso:</span>{' '}
          {session.step} - {getStepDisplay(session.step_name, session.step_display)}
        </p>
        {session.channel && (
          <p className="text-slate-300">
            <span className="text-slate-500">Canal:</span> {session.channel}
          </p>
        )}
        {session.videos_processing && session.videos_processing.length > 0 && (
          <div className="text-slate-300">
            <span className="text-slate-500">Videos:</span>{' '}
            {session.videos_processing.map((vid, i) => (
              <span key={i}>
                {i > 0 && ', '}
                <a
                  href={`https://www.youtube.com/watch?v=${vid}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary-400 hover:text-primary-300"
                >
                  {vid}
                </a>
              </span>
            ))}
          </div>
        )}
        {session.started_at && (
          <p className="text-slate-400 text-xs">{timeAgo(session.started_at)}</p>
        )}
      </div>

      {/* Error detail */}
      {session.status === 'error' && session.error_detail && (
        <div className="bg-red-500/10 border border-red-500/20 rounded p-3 text-xs text-red-400">
          {session.error_detail}
        </div>
      )}

      {/* Completion summary */}
      {session.status === 'completed' && session.result_summary && (
        <div className="bg-green-500/10 border border-green-500/20 rounded p-3 text-xs text-green-400">
          <p className="font-medium mb-1">Investigacion completada</p>
          <p>{JSON.stringify(session.result_summary)}</p>
          <a
            href="/strategies"
            className="text-primary-400 hover:text-primary-300 mt-1 inline-block"
          >
            Ver estrategias
          </a>
        </div>
      )}
    </div>
  );
}
