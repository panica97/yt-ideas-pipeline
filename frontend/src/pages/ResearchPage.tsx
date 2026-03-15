import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getResearchSessions } from '../services/research';
import type { ResearchSessionDetail } from '../services/research';
import StatusBadge from '../components/common/StatusBadge';
import LoadingSpinner from '../components/common/LoadingSpinner';

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
}

function SessionCard({ session }: { session: ResearchSessionDetail }) {
  const totalVideos =
    session.result_summary?.total_videos ?? session.videos?.length ?? 0;
  const totalStrategies = session.result_summary?.total_strategies ?? 0;

  return (
    <Link
      to={`/research/${session.id}`}
      className="block bg-slate-800 border border-slate-700 rounded-lg p-5 hover:border-slate-600 hover:bg-slate-800/80 transition-colors"
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-white">
            {session.topic ?? 'Sin topic'}
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            {session.started_at
              ? new Date(session.started_at).toLocaleDateString('es-ES', {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })
              : '-'}
          </p>
        </div>
        <StatusBadge status={session.status === 'completed' ? 'completed' : 'error'} />
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        <div>
          <p className="text-lg font-bold text-white">{totalVideos}</p>
          <p className="text-xs text-slate-400">Videos</p>
        </div>
        <div>
          <p className="text-lg font-bold text-yellow-400">{totalStrategies}</p>
          <p className="text-xs text-slate-400">Estrategias</p>
        </div>
        <div>
          <p className="text-lg font-bold text-slate-300">
            {session.duration_seconds != null
              ? formatDuration(session.duration_seconds)
              : '-'}
          </p>
          <p className="text-xs text-slate-400">Duracion</p>
        </div>
      </div>

      {session.result_summary?.channels_processed &&
        session.result_summary.channels_processed.length > 0 && (
          <div className="mt-3 pt-3 border-t border-slate-700">
            <div className="flex flex-wrap gap-1.5">
              {session.result_summary.channels_processed.map((ch) => (
                <span
                  key={ch.name}
                  className="px-2 py-0.5 bg-slate-700 rounded text-xs text-slate-300"
                >
                  {ch.name}
                </span>
              ))}
            </div>
          </div>
        )}

      {session.error_detail && (
        <p className="text-xs text-red-400 mt-2 truncate">
          {session.error_detail}
        </p>
      )}
    </Link>
  );
}

export default function ResearchPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['research-sessions-all'],
    queryFn: () => getResearchSessions(50),
  });

  if (isLoading) return <LoadingSpinner />;

  const sessions = data?.sessions ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Investigaciones</h1>
        <span className="text-sm text-slate-400">
          Total: {sessions.length} sesiones
        </span>
      </div>

      {sessions.length === 0 ? (
        <p className="text-sm text-slate-500 py-8 text-center">
          No se han realizado investigaciones todavia
        </p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {sessions.map((session) => (
            <SessionCard key={session.id} session={session} />
          ))}
        </div>
      )}
    </div>
  );
}
