import { useResearchStatus } from '../hooks/useResearchStatus';
import ResearchStatus from '../components/live/ResearchStatus';

export default function LivePage() {
  const { sessions, isConnected } = useResearchStatus();

  const runningSessions = sessions.filter((s) => s.status === 'running');
  const completedSessions = sessions.filter((s) => s.status === 'completed');
  const errorSessions = sessions.filter((s) => s.status === 'error');

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-text-primary">Live Research Status</h1>
        <span className={`text-xs ${isConnected ? 'text-accent' : 'text-danger'}`}>
          {isConnected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      {/* No active sessions */}
      {runningSessions.length === 0 && completedSessions.length === 0 && errorSessions.length === 0 && (
        <div className="bg-surface-1 border border-border rounded-lg p-12 text-center">
          <span className="inline-block w-4 h-4 rounded-full bg-surface-3 mb-3" />
          <p className="text-text-muted text-sm">No research in progress</p>
          <p className="text-text-muted text-xs mt-1">
            Launch one with /research {'<topic>'} in the CLI
          </p>
        </div>
      )}

      {/* Running sessions */}
      {runningSessions.length > 0 && (
        <div className="space-y-3">
          {runningSessions.map((session) => (
            <ResearchStatus key={session.id} session={session} />
          ))}
        </div>
      )}

      {/* Completed sessions */}
      {completedSessions.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-text-muted">Completed</h2>
          {completedSessions.map((session) => (
            <ResearchStatus key={session.id} session={session} />
          ))}
        </div>
      )}

      {/* Error sessions */}
      {errorSessions.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-text-muted">With Errors</h2>
          {errorSessions.map((session) => (
            <ResearchStatus key={session.id} session={session} />
          ))}
        </div>
      )}
    </div>
  );
}
