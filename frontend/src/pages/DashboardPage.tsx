import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getStats } from '../services/stats';
import { getResearchSessions } from '../services/research';
import type { PipelineStep, ChannelProcessed } from '../services/research';
import StatsCard from '../components/common/StatsCard';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { useResearchStatus } from '../hooks/useResearchStatus';
import StatusBadge from '../components/common/StatusBadge';

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
}

function StepStatusIcon({ status }: { status: PipelineStep['status'] }) {
  if (status === 'ok') {
    return <span className="text-green-400 text-xs font-bold">{'\u2713'}</span>;
  }
  if (status === 'skipped') {
    return <span className="text-slate-500 text-xs font-bold">{'\u2192'}</span>;
  }
  return <span className="text-red-400 text-xs font-bold">{'\u2717'}</span>;
}

function ChannelBreakdown({ channels }: { channels: ChannelProcessed[] }) {
  return (
    <div className="space-y-1">
      {channels.map((ch) => (
        <div key={ch.name} className="flex items-center justify-between text-xs">
          <span className="text-slate-300 truncate mr-2">{ch.name}</span>
          <span className="text-slate-500 whitespace-nowrap">
            {ch.videos}v / {ch.strategies}s
          </span>
        </div>
      ))}
    </div>
  );
}

function PipelineSteps({ steps }: { steps: PipelineStep[] }) {
  return (
    <div className="space-y-1">
      {steps.map((step) => (
        <div key={step.step} className="flex items-center gap-2 text-xs">
          <StepStatusIcon status={step.status} />
          <span className="text-slate-400 w-32 truncate">{step.name}</span>
          {step.detail && (
            <span className="text-slate-500 truncate">{step.detail}</span>
          )}
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: getStats,
  });

  const { data: sessionsData } = useQuery({
    queryKey: ['research-sessions'],
    queryFn: () => getResearchSessions(1),
  });

  const { sessions } = useResearchStatus();
  const runningSessions = sessions.filter((s) => s.status === 'running');
  const lastSession = sessionsData?.sessions?.[0] ?? null;

  if (isLoading) return <LoadingSpinner />;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-white">Dashboard</h1>

      {/* Stats cards 3x2 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatsCard icon={'\u{1F4C1}'} label="Topics" value={stats?.total_topics ?? 0} />
        <StatsCard icon={'\u25B6'} label="Canales" value={stats?.total_channels ?? 0} />
        <StatsCard icon={'\u{1F3AC}'} label="Videos investigados" value={stats?.total_videos_researched ?? 0} />
        <StatsCard icon={'\u{1F4A1}'} label="Ideas" value={stats?.total_strategies ?? 0} />
        <StatsCard icon={'\u2605'} label="Estrategias" value={stats?.total_drafts ?? 0} color="text-yellow-400" />
        <StatsCard icon={'\u26A0'} label="Con TODOs" value={stats?.drafts_with_todos ?? 0} color="text-orange-400" />
      </div>

      {/* Bottom sections */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Estado actual */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Estado actual</h2>
          {runningSessions.length > 0 ? (
            <div className="space-y-2">
              {runningSessions.map((session) => (
                <div key={session.id} className="flex items-center gap-2">
                  <StatusBadge status="running" />
                  <span className="text-sm text-slate-300">
                    {session.topic} - {session.step_display || session.step_name}
                  </span>
                </div>
              ))}
              <Link to="/live" className="text-xs text-primary-400 hover:text-primary-300">
                Ver detalle completo
              </Link>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-slate-500" />
              <span className="text-sm text-slate-400">Sin actividad</span>
            </div>
          )}
        </div>

        {/* Ultima investigacion - resumen enriquecido */}
        <Link
          to={lastSession ? `/research/${lastSession.id}` : '/research'}
          className="block bg-slate-800 border border-slate-700 rounded-lg p-5 hover:border-slate-600 hover:bg-slate-800/80 transition-colors"
        >
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-slate-300">Ultima investigacion</h2>
            <span className="text-xs text-slate-500">Ver detalle {'\u2192'}</span>
          </div>
          {lastSession ? (
            <div className="space-y-3">
              {/* Header info */}
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                <p className="text-slate-300">
                  <span className="text-slate-500">Topic:</span> {lastSession.topic ?? '-'}
                </p>
                <p className="text-slate-300">
                  <span className="text-slate-500">Estado:</span>{' '}
                  <span
                    className={
                      lastSession.status === 'completed'
                        ? 'text-green-400'
                        : 'text-red-400'
                    }
                  >
                    {lastSession.status === 'completed' ? 'Completado' : 'Error'}
                  </span>
                </p>
                <p className="text-slate-300">
                  <span className="text-slate-500">Fecha:</span>{' '}
                  {lastSession.started_at
                    ? new Date(lastSession.started_at).toLocaleDateString('es-ES')
                    : '-'}
                </p>
                <p className="text-slate-300">
                  <span className="text-slate-500">Duracion:</span>{' '}
                  {lastSession.duration_seconds != null
                    ? formatDuration(lastSession.duration_seconds)
                    : '-'}
                </p>
                <p className="text-slate-300">
                  <span className="text-slate-500">Videos:</span>{' '}
                  {lastSession.result_summary?.total_videos ?? lastSession.videos?.length ?? 0}
                </p>
                <p className="text-slate-300">
                  <span className="text-slate-500">Ideas:</span>{' '}
                  {lastSession.result_summary?.total_strategies ?? 0}
                </p>
              </div>

              {/* Channel breakdown */}
              {lastSession.result_summary?.channels_processed &&
                lastSession.result_summary.channels_processed.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-slate-400 mb-1">
                      Canales procesados
                    </h3>
                    <ChannelBreakdown
                      channels={lastSession.result_summary.channels_processed}
                    />
                  </div>
                )}

              {/* Pipeline steps */}
              {lastSession.result_summary?.pipeline_steps &&
                lastSession.result_summary.pipeline_steps.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-slate-400 mb-1">
                      Pipeline
                    </h3>
                    <PipelineSteps
                      steps={lastSession.result_summary.pipeline_steps}
                    />
                  </div>
                )}

              {/* Error detail */}
              {lastSession.error_detail && (
                <p className="text-xs text-red-400 mt-1">
                  {lastSession.error_detail}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-slate-500">
              No se han realizado investigaciones todavia
            </p>
          )}
        </Link>
      </div>

      {/* Quick links */}
      <div className="flex gap-3">
        <Link
          to="/channels"
          className="px-4 py-2 text-sm bg-slate-800 border border-slate-700 rounded hover:bg-slate-700 text-slate-300 transition-colors"
        >
          Gestionar canales
        </Link>
        <Link
          to="/history"
          className="px-4 py-2 text-sm bg-slate-800 border border-slate-700 rounded hover:bg-slate-700 text-slate-300 transition-colors"
        >
          Ver historial
        </Link>
        <Link
          to="/strategies"
          className="px-4 py-2 text-sm bg-slate-800 border border-slate-700 rounded hover:bg-slate-700 text-slate-300 transition-colors"
        >
          Ver estrategias
        </Link>
      </div>
    </div>
  );
}
