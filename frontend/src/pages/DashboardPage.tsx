import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getStats } from '../services/stats';
import StatsCard from '../components/common/StatsCard';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { useResearchStatus } from '../hooks/useResearchStatus';
import StatusBadge from '../components/common/StatusBadge';

export default function DashboardPage() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: getStats,
  });

  const { sessions } = useResearchStatus();
  const runningSessions = sessions.filter((s) => s.status === 'running');

  if (isLoading) return <LoadingSpinner />;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-white">Dashboard</h1>

      {/* Stats cards 3x2 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatsCard icon={'\u{1F4C1}'} label="Topics" value={stats?.total_topics ?? 0} />
        <StatsCard icon={'\u25B6'} label="Canales" value={stats?.total_channels ?? 0} />
        <StatsCard icon={'\u{1F3AC}'} label="Videos investigados" value={stats?.total_videos_researched ?? 0} />
        <StatsCard icon={'\u2605'} label="Estrategias" value={stats?.total_strategies ?? 0} color="text-yellow-400" />
        <StatsCard icon={'\u{1F4DD}'} label="Borradores" value={stats?.total_drafts ?? 0} />
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

        {/* Ultima investigacion */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Ultima investigacion</h2>
          {stats?.last_research ? (
            <div className="space-y-1 text-sm">
              <p className="text-slate-300">
                <span className="text-slate-500">Topic:</span> {stats.last_research.topic}
              </p>
              <p className="text-slate-300">
                <span className="text-slate-500">Fecha:</span>{' '}
                {stats.last_research.date
                  ? new Date(stats.last_research.date).toLocaleDateString('es-ES')
                  : '-'}
              </p>
              <p className="text-slate-300">
                <span className="text-slate-500">Estrategias:</span> {stats.last_research.strategies_found}
              </p>
            </div>
          ) : (
            <p className="text-sm text-slate-500">No se han realizado investigaciones todavia</p>
          )}
        </div>
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
