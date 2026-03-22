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
      className="block bg-surface-1 border border-border rounded-lg p-5 hover:border-border-hover hover:bg-surface-1/80 transition-colors"
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-text-primary">
            {session.topic ?? 'No topic'}
          </h3>
          <p className="text-xs text-text-muted mt-0.5">
            {session.started_at
              ? new Date(session.started_at).toLocaleDateString('en-US', {
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
          <p className="text-lg font-bold text-text-primary">{totalVideos}</p>
          <p className="text-xs text-text-muted">Videos</p>
        </div>
        <div>
          <p className="text-lg font-bold text-warn">{totalStrategies}</p>
          <p className="text-xs text-text-muted">Ideas</p>
        </div>
        <div>
          <p className="text-lg font-bold text-text-secondary">
            {session.duration_seconds != null
              ? formatDuration(session.duration_seconds)
              : '-'}
          </p>
          <p className="text-xs text-text-muted">Duration</p>
        </div>
      </div>

      {session.result_summary?.channels_processed &&
        session.result_summary.channels_processed.length > 0 && (
          <div className="mt-3 pt-3 border-t border-border">
            <div className="flex flex-wrap gap-1.5">
              {session.result_summary.channels_processed.map((ch) => (
                <span
                  key={ch.name}
                  className="px-2 py-0.5 bg-surface-2 rounded text-xs text-text-secondary"
                >
                  {ch.name}
                </span>
              ))}
            </div>
          </div>
        )}

      {session.error_detail && (
        <p className="text-xs text-danger mt-2 truncate">
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
        <h1 className="text-xl font-bold text-text-primary">Research Sessions</h1>
        <span className="text-sm text-text-muted">
          Total: {sessions.length} sessions
        </span>
      </div>

      {sessions.length === 0 ? (
        <p className="text-sm text-text-muted py-8 text-center">
          No research has been performed yet
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
