import type { ResearchSession } from '../../types/research';
import ProgressBar from './ProgressBar';
import StepIndicator from './StepIndicator';

interface ResearchStatusProps {
  session: ResearchSession;
}

const STEP_DISPLAY: Record<string, string> = {
  preflight: 'Authentication Check',
  'yt-scraper': 'Searching Videos',
  'notebooklm-analyst': 'Extracting Strategies',
  translator: 'Translating to JSON',
  cleanup: 'Cleanup',
  'db-manager': 'Saving to Database',
  summary: 'Final Summary',
};

function getStepDisplay(stepName: string | null, stepDisplay: string | null): string {
  if (stepDisplay) return stepDisplay;
  if (stepName && STEP_DISPLAY[stepName]) return STEP_DISPLAY[stepName];
  return stepName || 'Starting...';
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'a moment ago';
  if (mins === 1) return '1 minute ago';
  if (mins < 60) return `${mins} minutes ago`;
  const hours = Math.floor(mins / 60);
  if (hours === 1) return '1 hour ago';
  return `${hours} hours ago`;
}

export default function ResearchStatus({ session }: ResearchStatusProps) {
  const statusLabel =
    session.status === 'running'
      ? 'RUNNING'
      : session.status === 'completed'
        ? 'COMPLETED'
        : 'ERROR';

  return (
    <div className="bg-surface-1 border border-border rounded-lg p-5 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <StepIndicator status={session.status} />
          <span className="text-sm font-semibold text-text-primary">
            Session #{session.id} - {session.topic}
          </span>
        </div>
        <span className="text-xs text-text-muted">{statusLabel}</span>
      </div>

      {/* Progress bar */}
      {session.status === 'running' && (
        <ProgressBar step={session.step} totalSteps={session.total_steps} />
      )}

      {/* Details */}
      <div className="space-y-1 text-sm">
        <p className="text-text-secondary">
          <span className="text-text-muted">Step:</span>{' '}
          {session.step} - {getStepDisplay(session.step_name, session.step_display)}
        </p>
        {session.channel && (
          <p className="text-text-secondary">
            <span className="text-text-muted">Channel:</span> {session.channel}
          </p>
        )}
        {session.videos_processing && session.videos_processing.length > 0 && (
          <div className="text-text-secondary">
            <span className="text-text-muted">Videos:</span>{' '}
            {session.videos_processing.map((vid, i) => (
              <span key={i}>
                {i > 0 && ', '}
                <a
                  href={`https://www.youtube.com/watch?v=${vid}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent hover:text-accent-hover"
                >
                  {vid}
                </a>
              </span>
            ))}
          </div>
        )}
        {session.started_at && (
          <p className="text-text-muted text-xs">{timeAgo(session.started_at)}</p>
        )}
      </div>

      {/* Error detail */}
      {session.status === 'error' && session.error_detail && (
        <div className="bg-red-500/10 border border-red-500/20 rounded p-3 text-xs text-danger">
          {session.error_detail}
        </div>
      )}

      {/* Completion summary */}
      {session.status === 'completed' && session.result_summary && (
        <div className="bg-accent/10 border border-green-500/20 rounded p-3 text-xs text-accent">
          <p className="font-medium mb-1">Research Completed</p>
          <p>{JSON.stringify(session.result_summary)}</p>
          <a
            href="/strategies"
            className="text-accent hover:text-accent-hover mt-1 inline-block"
          >
            View Strategies
          </a>
        </div>
      )}
    </div>
  );
}
