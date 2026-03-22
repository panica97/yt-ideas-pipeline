import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams, Link } from 'react-router-dom';
import { getResearchSessionDetail } from '../services/research';
import { getStrategies, getStrategy } from '../services/strategies';
import type { PipelineStep, ChannelProcessed, SessionVideo } from '../services/research';
import type { Strategy } from '../types/strategy';
import StatusBadge from '../components/common/StatusBadge';
import StrategyDetail from '../components/strategies/StrategyDetail';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { formatDuration } from '../utils/formatDuration';

function ClassificationBadge({ classification }: { classification: string | null }) {
  if (classification === 'irrelevant') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-surface-3 text-text-secondary">
        irrelevant
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-accent/20 text-accent">
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
    <div className="bg-surface-1 border border-border rounded-lg p-5">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-sm font-semibold text-text-muted hover:text-text-secondary transition-colors w-full text-left"
      >
        <span className="transition-transform" style={{ transform: open ? 'rotate(90deg)' : 'rotate(0deg)' }}>
          {'\u25B6'}
        </span>
        Irrelevant videos ({videos.length})
      </button>
      {open && <div className="mt-3">{renderTable(videos)}</div>}
    </div>
  );
}

function StepStatusIcon({ status }: { status: PipelineStep['status'] }) {
  if (status === 'ok') {
    return <span className="text-accent text-sm font-bold">{'\u2713'}</span>;
  }
  if (status === 'skipped') {
    return <span className="text-text-muted text-sm font-bold">{'\u2192'}</span>;
  }
  return <span className="text-danger text-sm font-bold">{'\u2717'}</span>;
}

export default function ResearchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const sessionId = Number(id);
  const [selectedIdea, setSelectedIdea] = useState<Strategy | null>(null);
  const [loadingIdea, setLoadingIdea] = useState(false);

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

  const handleIdeaClick = async (name: string) => {
    setLoadingIdea(true);
    try {
      const detail = await getStrategy(name);
      setSelectedIdea(detail);
    } finally {
      setLoadingIdea(false);
    }
  };

  if (isLoading) return <LoadingSpinner />;

  if (!session) {
    return (
      <div className="text-center py-12">
        <p className="text-text-muted">Session not found</p>
        <Link to="/research" className="text-accent hover:text-accent-hover text-sm mt-2 inline-block">
          Back to Research
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
          className="text-text-muted hover:text-text-primary transition-colors"
        >
          {'\u2190'}
        </Link>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-text-primary">
            {session.topic ?? 'No topic'}
          </h1>
          <p className="text-sm text-text-muted">
            {session.started_at
              ? new Date(session.started_at).toLocaleDateString('en-US', {
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
        <div className="bg-surface-1 border border-border rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-text-primary">{totalVideos}</p>
          <p className="text-xs text-text-muted mt-1">Processed Videos</p>
        </div>
        <div className="bg-surface-1 border border-border rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-warn">{totalStrategies}</p>
          <p className="text-xs text-text-muted mt-1">Ideas Found</p>
        </div>
        <div className="bg-surface-1 border border-border rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-text-secondary">
            {channelsProcessed.length}
          </p>
          <p className="text-xs text-text-muted mt-1">Channels</p>
        </div>
        <div className="bg-surface-1 border border-border rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-text-secondary">
            {session.duration_seconds != null
              ? formatDuration(session.duration_seconds)
              : '-'}
          </p>
          <p className="text-xs text-text-muted mt-1">Duration</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Pipeline steps */}
        {pipelineSteps.length > 0 && (
          <div className="bg-surface-1 border border-border rounded-lg p-5">
            <h2 className="text-sm font-semibold text-text-secondary mb-3">
              Pipeline
            </h2>
            <div className="space-y-2">
              {pipelineSteps.map((step) => (
                <div key={step.step} className="flex items-center gap-3 text-sm">
                  <StepStatusIcon status={step.status} />
                  <span className="text-text-secondary w-44 truncate">{step.name}</span>
                  {step.detail && (
                    <span className="text-text-muted truncate text-xs">
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
          <div className="bg-surface-1 border border-border rounded-lg p-5">
            <h2 className="text-sm font-semibold text-text-secondary mb-3">
              Processed Channels
            </h2>
            <div className="space-y-2">
              {channelsProcessed.map((ch) => (
                <div
                  key={ch.name}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="text-text-secondary truncate">{ch.name}</span>
                  <span className="text-text-muted whitespace-nowrap">
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
        <div className="bg-red-500/10 border border-danger/30 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-danger mb-1">Error</h2>
          <p className="text-sm text-danger-hover">{session.error_detail}</p>
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
                <tr className="border-b border-border">
                  <th className="text-left py-2 px-3 text-text-muted font-medium">
                    Video ID
                  </th>
                  <th className="text-left py-2 px-3 text-text-muted font-medium">
                    Channel
                  </th>
                  <th className="text-left py-2 px-3 text-text-muted font-medium">
                    Classification
                  </th>
                  <th className="text-left py-2 px-3 text-text-muted font-medium">
                    Ideas
                  </th>
                </tr>
              </thead>
              <tbody>
                {videos.map((v, i) => (
                  <tr
                    key={`${v.video_id}-${i}`}
                    className="border-b border-border/50 hover:bg-surface-2/30"
                  >
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
                    <td className="py-2 px-3 text-text-secondary">
                      {v.channel || '-'}
                    </td>
                    <td className="py-2 px-3">
                      <ClassificationBadge classification={v.classification} />
                    </td>
                    <td className="py-2 px-3 text-text-secondary">
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
            <div className="bg-surface-1 border border-border rounded-lg p-5">
              <h2 className="text-sm font-semibold text-text-secondary mb-3">
                Processed Videos ({strategyVideos.length})
              </h2>
              {strategyVideos.length > 0 ? (
                renderVideoTable(strategyVideos)
              ) : (
                <p className="text-sm text-text-muted">
                  No videos processed in this session
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

      {/* Ideas found — detail view or grouped list */}
      {selectedIdea ? (
        <div className="bg-surface-1 border border-border rounded-lg p-5">
          <StrategyDetail
            strategy={selectedIdea}
            onClose={() => setSelectedIdea(null)}
            onStatusChange={() => setSelectedIdea(null)}
          />
        </div>
      ) : (
        <div className="bg-surface-1 border border-border rounded-lg p-5">
          <h2 className="text-sm font-semibold text-text-secondary mb-3">
            Ideas Found ({strategies.length})
          </h2>
          {loadingIdea && <LoadingSpinner />}
          {strategies.length > 0 ? (
            <div className="space-y-4">
              {(() => {
                const groups = new Map<string, { channel: string | null; ideas: typeof strategies }>();
                for (const s of strategies) {
                  const videoKey = s.source_videos?.[0] ?? 'no-video';
                  if (!groups.has(videoKey)) {
                    groups.set(videoKey, { channel: s.source_channel, ideas: [] });
                  }
                  groups.get(videoKey)!.ideas.push(s);
                }
                return Array.from(groups.entries()).map(([videoId, { channel, ideas }]) => (
                  <div key={videoId}>
                    <div className="flex items-center gap-2 mb-2">
                      {videoId !== 'no-video' ? (
                        <a
                          href={`https://www.youtube.com/watch?v=${videoId}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-accent hover:text-accent-hover font-medium"
                        >
                          {videoId}
                        </a>
                      ) : (
                        <span className="text-xs text-text-muted font-medium">No video</span>
                      )}
                      {channel && (
                        <span className="text-xs text-text-muted">/ {channel}</span>
                      )}
                      <span className="text-xs text-text-muted">({ideas.length})</span>
                    </div>
                    <div className="space-y-1 ml-3">
                      {ideas.map((s) => (
                        <button
                          key={s.id}
                          onClick={() => handleIdeaClick(s.name)}
                          className="w-full text-left flex items-center justify-between py-1.5 px-3 bg-surface-2/30 rounded hover:bg-surface-2/60 cursor-pointer transition-colors"
                        >
                          <div>
                            <p className="text-sm text-text-primary font-medium">{s.name}</p>
                            {s.description && (
                              <p className="text-xs text-text-muted mt-0.5 truncate max-w-md">
                                {s.description}
                              </p>
                            )}
                          </div>
                          <span className="text-text-muted text-xs ml-2">{'\u203A'}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                ));
              })()}
            </div>
          ) : (
            <p className="text-sm text-text-muted">
              No ideas found in this session
            </p>
          )}
        </div>
      )}
    </div>
  );
}
