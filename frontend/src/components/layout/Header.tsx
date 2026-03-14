import { useResearchStatus } from '../../hooks/useResearchStatus';

export default function Header() {
  const { sessions, isConnected } = useResearchStatus();
  const hasRunning = sessions.some((s) => s.status === 'running');

  let dotClass = 'bg-slate-500'; // grey — disconnected or idle
  if (isConnected && hasRunning) {
    dotClass = 'bg-green-500 animate-pulse';
  } else if (isConnected) {
    dotClass = 'bg-slate-500';
  }

  return (
    <header className="h-14 bg-slate-800 border-b border-slate-700 flex items-center justify-between px-6">
      <h2 className="text-base font-semibold text-slate-200">IRT Dashboard</h2>
      <div className="flex items-center gap-2">
        <span className={`inline-block w-2.5 h-2.5 rounded-full ${dotClass}`} />
        <span className="text-xs text-slate-400">
          {!isConnected
            ? 'Desconectado'
            : hasRunning
              ? 'Investigando...'
              : 'Sin actividad'}
        </span>
      </div>
    </header>
  );
}
