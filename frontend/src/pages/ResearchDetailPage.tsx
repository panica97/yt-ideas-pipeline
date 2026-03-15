import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams, Link } from 'react-router-dom';
import { getResearchSessionDetail } from '../services/research';
import { getStrategies } from '../services/strategies';
import type { PipelineStep, ChannelProcessed, SessionVideo } from '../services/research';
import StatusBadge from '../components/common/StatusBadge';
import LoadingSpinner from '../components/common/LoadingSpinner';

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
}

function ClassificationBadge({ classification }: { classification: string | null }) {
  if (classification === 'irrelevant') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-600 text-slate-300">
        irrelevant
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-500/20 text-green-400">
      strategy
    </span>
  );
}

function IrrelevantVideosSection({
  videos,
  renderTable,
}: {
  videos: SessionVideo[];
  renderTable: (videos: SessionVideo[]) => React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-sm font-semibold text-slate-400 hover:text-slate-300 transition-colors w-full text-left"
      >
        <span className="transition-transform" style={{ transform: open ? 'rotate(90deg)' : 'rotate(0deg)' }}>
          {'\u25B6'}
        </span>
        Videos irrelevantes ({videos.length})
      </button>
      {open && <div className="mt-3">{renderTable(videos)}</div>}
    </div>
  );
}

function StepStatusIcon({ status }: { status: PipelineStep['status'] }) {
  if (status === 'ok') {
    return <span className="text-green-400 text-sm font-bold">{'\u2713'}</span>;
  }
  if (status === 'skipped') {
    return <span className="text-slate-500 text-sm font-bold">{'\u2192'}</span>;
  }
  return <span className="text-red-400 text-sm font-bold">{'\u2717'}</span>;
}

export default function ResearchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const sessionId = Number(id);

  const { data: session, isLoading } = useQuery({
    queryKey: ['research-session', sessionId],
    queryFn: () => getResearchSessionDetail(sessionId),
    enabled: !isNaN(sessionId),
  });

  const { data: strategiesData } = useQuery({
    queryKey: ['strategies-by-session', sessionId],
    queryFn: () => getStrategies({ session_id: sessionId }),
    enabled: !isNaN(sessionId),
  });

  if (isLoading) return <LoadingSpinner />;

  if (!session) {
    return (
      <div className="text-center py-12">
        <p className="text-slate-400">Sesion no encontrada</p>
        <Link to="/research" className="text-primary-400 hover:text-primary-300 text-sm mt-2 inline-block">
          Volver a investigaciones
        </Link>
      </div>
    );
  }

  const totalVideos =
    session.result_summary?.total_videos ?? session.videos?.length ?? 0;
  const totalStrategies = session.result_summary?.total_strategies ?? 0;
  const channelsProcessed: ChannelProcessed[] =
    session.result_summary?.channels_processed ?? [];
  const pipelineSteps: PipelineStep[] =
    session.result_summary?.pipeline_steps ?? [];
  const strategies = strategiesData?.strategies ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          to="/research"
          className="text-slate-400 hover:text-white transition-colors"
        >
          {'\u2190'}
        </Link>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-white">
            {session.topic ?? 'Sin topic'}
          </h1>
          <p className="text-sm text-slate-400">
            {session.started_at
              ? new Date(session.started_at).toLocaleDateString('es-ES', {
                  day: 'numeric',
                  month: 'long',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })
              : '-'}
          </p>
        </div>
        <StatusBadge status={session.status === 'completed' ? 'completed' : 'error'} />
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-white">{totalVideos}</p>
          <p className="text-xs text-slate-400 mt-1">Videos procesados</p>
        </div>
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-yellow-400">{totalStrategies}</p>
          <p className="text-xs text-slate-400 mt-1">Ideas encontradas</p>
        </div>
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-slate-300">
            {channelsProcessed.length}
          </p>
          <p className="text-xs text-slate-400 mt-1">Canales</p>
        </div>
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-slate-300">
            {session.duration_seconds != null
              ? formatDuration(session.duration_seconds)
              : '-'}
          </p>
          <p className="text-xs text-slate-400 mt-1">Duracion</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Pipeline steps */}
        {pipelineSteps.length > 0 && (
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
            <h2 className="text-sm font-semibold text-slate-300 mb-3">
              Pipeline
            </h2>
            <div className="space-y-2">
              {pipelineSteps.map((step) => (
                <div key={step.step} className="flex items-center gap-3 text-sm">
                  <StepStatusIcon status={step.status} />
                  <span className="text-slate-300 w-44 truncate">{step.name}</span>
                  {step.detail && (
                    <span className="text-slate-500 truncate text-xs">
                      {step.detail}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Channels breakdown */}
        {channelsProcessed.length > 0 && (
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
            <h2 className="text-sm font-semibold text-slate-300 mb-3">
              Canales procesados
            </h2>
            <div className="space-y-2">
              {channelsProcessed.map((ch) => (
                <div
                  key={ch.name}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="text-slate-300 truncate">{ch.name}</span>
                  <span className="text-slate-500 whitespace-nowrap">
                    {ch.videos} videos / {ch.strategies} ideas
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Error detail */}
      {session.error_detail && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-red-400 mb-1">Error</h2>
          <p className="text-sm text-red-300">{session.error_detail}</p>
        </div>
      )}

      {/* Videos processed */}
      {(() => {
        const allVideos: SessionVideo[] = session.videos ?? [];
        const strategyVideos = allVideos.filter((v) => v.classification !== 'irrelevant');
        const irrelevantVideos = allVideos.filter((v) => v.classification === 'irrelevant');

        const renderVideoTable = (videos: SessionVideo[]) => (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left py-2 px-3 text-slate-400 font-medium">
                    Video ID
                  </th>
                  <th className="text-left py-2 px-3 text-slate-400 font-medium">
                    Canal
                  </th>
                  <th className="text-left py-2 px-3 text-slate-400 font-medium">
                    Clasificacion
                  </th>
                  <th className="text-left py-2 px-3 text-slate-400 font-medium">
                    Ideas
                  </th>
                </tr>
              </thead>
              <tbody>
                {videos.map((v, i) => (
                  <tr
                    key={`${v.video_id}-${i}`}
                    className="border-b border-slate-700/50 hover:bg-slate-700/30"
                  >
                    <td className="py-2 px-3">
                      <a
                        href={`https://www.youtube.com/watch?v=${v.video_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary-400 hover:text-primary-300"
                      >
                        {v.title || v.video_id}
                      </a>
                    </td>
                    <td className="py-2 px-3 text-slate-300">
                      {v.channel || '-'}
                    </td>
                    <td className="py-2 px-3">
                      <ClassificationBadge classification={v.classification} />
                    </td>
                    <td className="py-2 px-3 text-slate-300">
                      {v.strategies_found}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );

        return (
          <>
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
              <h2 className="text-sm font-semibold text-slate-300 mb-3">
                Videos procesados ({strategyVideos.length})
              </h2>
              {strategyVideos.length > 0 ? (
                renderVideoTable(strategyVideos)
              ) : (
                <p className="text-sm text-slate-500">
                  No se procesaron videos en esta sesion
                </p>
              )}
            </div>

            {irrelevantVideos.length > 0 && (
              <IrrelevantVideosSection
                videos={irrelevantVideos}
                renderTable={renderVideoTable}
              />
            )}
          </>
        );
      })()}

      {/* Ideas found, grouped by source video */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
        <h2 className="text-sm font-semibold text-slate-300 mb-3">
          Ideas encontradas ({strategies.length})
        </h2>
        {strategies.length > 0 ? (
          <div className="space-y-4">
            {(() => {
              // Group ideas by first source video (or "Sin video")
              const groups = new Map<string, { channel: string | null; ideas: typeof strategies }>();
              for (const s of strategies) {
                const videoKey = s.source_videos?.[0] ?? 'sin-video';
                if (!groups.has(videoKey)) {
                  groups.set(videoKey, { channel: s.source_channel, ideas: [] });
                }
                groups.get(videoKey)!.ideas.push(s);
              }
              return Array.from(groups.entries()).map(([videoId, { channel, ideas }]) => (
                <div key={videoId}>
                  <div className="flex items-center gap-2 mb-2">
                    {videoId !== 'sin-video' ? (
                      <a
                        href={`https://www.youtube.com/watch?v=${videoId}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-primary-400 hover:text-primary-300 font-medium"
                      >
                        {videoId}
                      </a>
                    ) : (
                      <span className="text-xs text-slate-500 font-medium">Sin video</span>
                    )}
                    {channel && (
                      <span className="text-xs text-slate-500">/ {channel}</span>
                    )}
                    <span className="text-xs text-slate-600">({ideas.length})</span>
                  </div>
                  <div className="space-y-1 ml-3">
                    {ideas.map((s) => (
                      <div
                        key={s.id}
                        className="flex items-center justify-between py-1.5 px-3 bg-slate-700/30 rounded"
                      >
                        <div>
                          <p className="text-sm text-white font-medium">{s.name}</p>
                          {s.description && (
                            <p className="text-xs text-slate-400 mt-0.5 truncate max-w-md">
                              {s.description}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ));
            })()}
          </div>
        ) : (
          <p className="text-sm text-slate-500">
            No se encontraron ideas en esta sesion
          </p>
        )}
      </div>
    </div>
  );
}
