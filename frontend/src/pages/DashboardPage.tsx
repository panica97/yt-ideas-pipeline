import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getStats } from '../services/stats';
import { getResearchSessions } from '../services/research';
import type { PipelineStep, ChannelProcessed } from '../services/research';
import StatsCard from '../components/common/StatsCard';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { useResearchStatus } from '../hooks/useResearchStatus';
import StatusBadge from '../components/common/StatusBadge';
import {
  FolderOpen,
  Tv,
  Film,
  Lightbulb,
  Trophy,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  XCircle,
  SkipForward,
} from 'lucide-react';

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
}

function StepStatusIcon({ status }: { status: PipelineStep['status'] }) {
  if (status === 'ok') return <CheckCircle2 size={12} className="text-accent" />;
  if (status === 'skipped') return <SkipForward size={12} className="text-text-muted" />;
  return <XCircle size={12} className="text-danger" />;
}

function ChannelBreakdown({ channels }: { channels: ChannelProcessed[] }) {
  return (
    <div className="space-y-1.5">
      {channels.map((ch) => (
        <div key={ch.name} className="flex items-center justify-between text-xs">
          <span className="text-text-secondary truncate mr-2">{ch.name}</span>
          <span className="text-text-muted font-mono whitespace-nowrap">
            {ch.videos}v / {ch.strategies}s
          </span>
        </div>
      ))}
    </div>
  );
}

function PipelineSteps({ steps }: { steps: PipelineStep[] }) {
  return (
    <div className="space-y-1.5">
      {steps.map((step) => (
        <div key={step.step} className="flex items-center gap-2 text-xs">
          <StepStatusIcon status={step.status} />
          <span className="text-text-secondary w-32 truncate">{step.name}</span>
          {step.detail && (
            <span className="text-text-muted truncate">{step.detail}</span>
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
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-lg font-semibold text-text-primary">Dashboard</h1>

      {/* Stats cards 3x2 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <StatsCard icon={FolderOpen} label="Topics" value={stats?.total_topics ?? 0} />
        <StatsCard icon={Tv} label="Channels" value={stats?.total_channels ?? 0} />
        <StatsCard icon={Film} label="Researched Videos" value={stats?.total_videos_researched ?? 0} />
        <StatsCard icon={Lightbulb} label="Ideas" value={stats?.total_strategies ?? 0} />
        <StatsCard icon={Trophy} label="Strategies" value={stats?.total_drafts ?? 0} color="accent" />
        <StatsCard icon={AlertTriangle} label="With TODOs" value={stats?.drafts_with_todos ?? 0} color="warn" />
      </div>

      {/* Bottom sections */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Estado actual */}
        <div className="card p-5">
          <h2 className="text-xs text-text-muted uppercase tracking-wider mb-3">Current Status</h2>
          {runningSessions.length > 0 ? (
            <div className="space-y-3">
              {runningSessions.map((session) => (
                <div key={session.id} className="flex items-center gap-2">
                  <StatusBadge status="running" />
                  <span className="text-sm text-text-secondary">
                    {session.topic} - {session.step_display || session.step_name}
                  </span>
                </div>
              ))}
              <Link to="/live" className="inline-flex items-center gap-1 text-xs text-accent hover:text-accent-hover transition-colors">
                View Details <ArrowRight size={12} />
              </Link>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-text-muted" />
              <span className="text-sm text-text-muted">No Activity</span>
            </div>
          )}
        </div>

        {/* Ultima investigacion */}
        <Link
          to={lastSession ? `/research/${lastSession.id}` : '/research'}
          className="card card-interactive p-5 block"
        >
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs text-text-muted uppercase tracking-wider">Last Research</h2>
            <span className="text-xs text-text-muted flex items-center gap-1">
              View Details <ArrowRight size={12} />
            </span>
          </div>
          {lastSession ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
                <p>
                  <span className="text-text-muted text-xs">Topic:</span>{' '}
                  <span className="text-text-secondary">{lastSession.topic ?? '-'}</span>
                </p>
                <p>
                  <span className="text-text-muted text-xs">Status:</span>{' '}
                  <span className={lastSession.status === 'completed' ? 'text-accent' : 'text-danger'}>
                    {lastSession.status === 'completed' ? 'Completed' : 'Error'}
                  </span>
                </p>
                <p>
                  <span className="text-text-muted text-xs">Date:</span>{' '}
                  <span className="text-text-secondary">
                    {lastSession.started_at ? new Date(lastSession.started_at).toLocaleDateString('en-US') : '-'}
                  </span>
                </p>
                <p>
                  <span className="text-text-muted text-xs">Duration:</span>{' '}
                  <span className="text-text-secondary font-mono">
                    {lastSession.duration_seconds != null ? formatDuration(lastSession.duration_seconds) : '-'}
                  </span>
                </p>
                <p>
                  <span className="text-text-muted text-xs">Videos:</span>{' '}
                  <span className="text-text-secondary font-mono">
                    {lastSession.result_summary?.total_videos ?? lastSession.videos?.length ?? 0}
                  </span>
                </p>
                <p>
                  <span className="text-text-muted text-xs">Ideas:</span>{' '}
                  <span className="text-text-secondary font-mono">
                    {lastSession.result_summary?.total_strategies ?? 0}
                  </span>
                </p>
              </div>

              {lastSession.result_summary?.channels_processed &&
                lastSession.result_summary.channels_processed.length > 0 && (
                  <div>
                    <h3 className="text-[10px] text-text-muted uppercase tracking-wider mb-1">
                      Processed Channels
                    </h3>
                    <ChannelBreakdown channels={lastSession.result_summary.channels_processed} />
                  </div>
                )}

              {lastSession.result_summary?.pipeline_steps &&
                lastSession.result_summary.pipeline_steps.length > 0 && (
                  <div>
                    <h3 className="text-[10px] text-text-muted uppercase tracking-wider mb-1">Pipeline</h3>
                    <PipelineSteps steps={lastSession.result_summary.pipeline_steps} />
                  </div>
                )}

              {lastSession.error_detail && (
                <p className="text-xs text-danger mt-1">{lastSession.error_detail}</p>
              )}
            </div>
          ) : (
            <p className="text-sm text-text-muted">No research has been performed yet</p>
          )}
        </Link>
      </div>

      {/* Quick links */}
      <div className="flex gap-2">
        <Link
          to="/channels"
          className="px-4 py-2 text-xs bg-surface-1 border border-border rounded-lg hover:border-border-hover hover:bg-surface-2 text-text-secondary transition-all flex items-center gap-2"
        >
          <Tv size={14} /> Channels
        </Link>
        <Link
          to="/history"
          className="px-4 py-2 text-xs bg-surface-1 border border-border rounded-lg hover:border-border-hover hover:bg-surface-2 text-text-secondary transition-all flex items-center gap-2"
        >
          <Film size={14} /> History
        </Link>
        <Link
          to="/strategies"
          className="px-4 py-2 text-xs bg-surface-1 border border-border rounded-lg hover:border-border-hover hover:bg-surface-2 text-text-secondary transition-all flex items-center gap-2"
        >
          <Trophy size={14} /> Results
        </Link>
      </div>
    </div>
  );
}
