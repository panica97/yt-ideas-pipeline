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
        <h1 className="text-xl font-bold text-white">Estado del Research en Tiempo Real</h1>
        <span className={`text-xs ${isConnected ? 'text-green-400' : 'text-red-400'}`}>
          {isConnected ? 'Conectado' : 'Desconectado'}
        </span>
      </div>

      {/* No active sessions */}
      {runningSessions.length === 0 && completedSessions.length === 0 && errorSessions.length === 0 && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-12 text-center">
          <span className="inline-block w-4 h-4 rounded-full bg-slate-500 mb-3" />
          <p className="text-slate-400 text-sm">No hay investigacion en curso</p>
          <p className="text-slate-600 text-xs mt-1">
            Lanza una con /research {'<topic>'} en el CLI
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
          <h2 className="text-sm font-semibold text-slate-400">Completadas</h2>
          {completedSessions.map((session) => (
            <ResearchStatus key={session.id} session={session} />
          ))}
        </div>
      )}

      {/* Error sessions */}
      {errorSessions.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-400">Con errores</h2>
          {errorSessions.map((session) => (
            <ResearchStatus key={session.id} session={session} />
          ))}
        </div>
      )}
    </div>
  );
}
