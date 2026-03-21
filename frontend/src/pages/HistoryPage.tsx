import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getHistory, getHistoryStats } from '../services/history';
import { getResearchSessions } from '../services/research';
import type { ResearchSessionDetail } from '../services/research';
import HistoryFilters from '../components/history/HistoryFilters';
import HistoryTable from '../components/history/HistoryTable';
import LoadingSpinner from '../components/common/LoadingSpinner';
import StatusBadge from '../components/common/StatusBadge';

type ViewMode = 'flat' | 'grouped';

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
}

function SessionGroup({
  session,
  isExpanded,
  onToggle,
}: {
  session: ResearchSessionDetail;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const totalVideos =
    session.result_summary?.total_videos ?? session.videos?.length ?? 0;
  const totalStrategies = session.result_summary?.total_strategies ?? 0;

  return (
    <div className="bg-surface-1 border border-border rounded-lg overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-2/50 transition-colors text-left"
      >
        <div className="flex items-center gap-3">
          <span className="text-text-muted text-xs">{isExpanded ? '\u25BC' : '\u25B6'}</span>
          <div>
            <span className="text-sm font-medium text-text-primary">
              {session.topic ?? 'Sin topic'}
            </span>
            <span className="text-xs text-text-muted ml-3">
              {session.started_at
                ? new Date(session.started_at).toLocaleString('es-ES', {
                    day: 'numeric',
                    month: 'short',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })
                : '-'}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-xs text-text-muted">
            {totalVideos}v / {totalStrategies}s
          </span>
          {session.duration_seconds != null && (
            <span className="text-xs text-text-muted">
              {formatDuration(session.duration_seconds)}
            </span>
          )}
          <StatusBadge status={session.status === 'completed' ? 'completed' : 'error'} />
          <Link
            to={`/research/${session.id}`}
            onClick={(e) => e.stopPropagation()}
            className="text-xs text-accent hover:text-accent-hover"
          >
            Detalle
          </Link>
        </div>
      </button>

      {isExpanded && session.videos && session.videos.length > 0 && (
        <div className="border-t border-border px-4 py-2">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 px-3 text-text-muted font-medium">Video ID</th>
                <th className="text-left py-2 px-3 text-text-muted font-medium">Canal</th>
                <th className="text-left py-2 px-3 text-text-muted font-medium">Estrategias</th>
              </tr>
            </thead>
            <tbody>
              {session.videos.map((v, i) => (
                <tr key={`${v.video_id}-${i}`} className="border-b border-border/50 hover:bg-surface-2/30">
                  <td className="py-2 px-3">
                    <a
                      href={`https://www.youtube.com/watch?v=${v.video_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent hover:text-accent-hover"
                    >
                      {v.title || v.video_id}
                    </a>
                  </td>
                  <td className="py-2 px-3 text-text-secondary">{v.channel || '-'}</td>
                  <td className="py-2 px-3 text-text-secondary">{v.strategies_found}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {isExpanded && (!session.videos || session.videos.length === 0) && (
        <div className="border-t border-border px-4 py-3">
          <p className="text-xs text-text-muted">Sin videos en esta sesion</p>
        </div>
      )}
    </div>
  );
}

export default function HistoryPage() {
  const [viewMode, setViewMode] = useState<ViewMode>('grouped');
  const [topic, setTopic] = useState('');
  const [channel, setChannel] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(1);
  const [expandedSessions, setExpandedSessions] = useState<Set<number>>(new Set());
  const limit = 50;

  const { data: stats } = useQuery({
    queryKey: ['historyStats'],
    queryFn: getHistoryStats,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['history', topic, channel, dateFrom, dateTo, page],
    queryFn: () =>
      getHistory({
        topic: topic || undefined,
        channel: channel || undefined,
        from: dateFrom || undefined,
        to: dateTo || undefined,
        page,
        limit,
      }),
    enabled: viewMode === 'flat',
  });

  const { data: sessionsData, isLoading: loadingSessions } = useQuery({
    queryKey: ['research-sessions-history'],
    queryFn: () => getResearchSessions(50),
    enabled: viewMode === 'grouped',
  });

  const topics = stats ? Object.keys(stats.by_topic) : [];
  const channels = stats
    ? topic
      ? Object.keys(stats.by_channel).filter(() => true)
      : Object.keys(stats.by_channel)
    : [];

  const totalPages = data ? Math.ceil(data.total / limit) : 1;

  const toggleSession = (id: number) => {
    setExpandedSessions((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-text-primary">Historial de investigacion</h1>
        <div className="flex items-center gap-3">
          {viewMode === 'flat' && (
            <span className="text-sm text-text-muted">Total: {data?.total ?? 0} videos</span>
          )}
          <div className="flex gap-1 bg-surface-1 border border-border rounded p-0.5">
            <button
              onClick={() => setViewMode('grouped')}
              className={`px-3 py-1 text-xs rounded transition-colors ${
                viewMode === 'grouped'
                  ? 'bg-accent text-text-primary'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              Por sesion
            </button>
            <button
              onClick={() => setViewMode('flat')}
              className={`px-3 py-1 text-xs rounded transition-colors ${
                viewMode === 'flat'
                  ? 'bg-accent text-text-primary'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              Lista plana
            </button>
          </div>
        </div>
      </div>

      {viewMode === 'flat' && (
        <>
          <HistoryFilters
            topics={topics}
            channels={channels}
            selectedTopic={topic}
            selectedChannel={channel}
            dateFrom={dateFrom}
            dateTo={dateTo}
            onTopicChange={(t) => { setTopic(t); setChannel(''); setPage(1); }}
            onChannelChange={(c) => { setChannel(c); setPage(1); }}
            onDateFromChange={(d) => { setDateFrom(d); setPage(1); }}
            onDateToChange={(d) => { setDateTo(d); setPage(1); }}
          />

          {isLoading ? (
            <LoadingSpinner />
          ) : (
            <>
              <HistoryTable items={data?.items ?? []} />

              {totalPages > 1 && (
                <div className="flex items-center justify-center gap-2">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="px-3 py-1 text-sm bg-surface-2 hover:bg-surface-3 disabled:bg-surface-1 disabled:text-text-muted text-text-secondary rounded transition-colors"
                  >
                    Anterior
                  </button>
                  <span className="text-sm text-text-muted">
                    Pagina {page} de {totalPages}
                  </span>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                    className="px-3 py-1 text-sm bg-surface-2 hover:bg-surface-3 disabled:bg-surface-1 disabled:text-text-muted text-text-secondary rounded transition-colors"
                  >
                    Siguiente
                  </button>
                </div>
              )}
            </>
          )}
        </>
      )}

      {viewMode === 'grouped' && (
        <>
          {loadingSessions ? (
            <LoadingSpinner />
          ) : (
            <div className="space-y-3">
              {(sessionsData?.sessions ?? []).length === 0 ? (
                <p className="text-sm text-text-muted py-8 text-center">
                  No se han realizado investigaciones todavia
                </p>
              ) : (
                (sessionsData?.sessions ?? []).map((session) => (
                  <SessionGroup
                    key={session.id}
                    session={session}
                    isExpanded={expandedSessions.has(session.id)}
                    onToggle={() => toggleSession(session.id)}
                  />
                ))
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
