interface StatusBadgeProps {
  status: 'running' | 'completed' | 'error' | 'idle';
  text?: string;
}

const statusStyles: Record<string, string> = {
  running: 'bg-green-500/20 text-green-400 border-green-500/30',
  completed: 'bg-green-500/20 text-green-400 border-green-500/30',
  error: 'bg-red-500/20 text-red-400 border-red-500/30',
  idle: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
};

const defaultLabels: Record<string, string> = {
  running: 'En curso',
  completed: 'Completado',
  error: 'Error',
  idle: 'Inactivo',
};

export default function StatusBadge({ status, text }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium border ${statusStyles[status] || statusStyles.idle}`}
    >
      <span
        className={`inline-block w-1.5 h-1.5 rounded-full ${
          status === 'running'
            ? 'bg-green-400 animate-pulse'
            : status === 'completed'
              ? 'bg-green-400'
              : status === 'error'
                ? 'bg-red-400'
                : 'bg-slate-400'
        }`}
      />
      {text || defaultLabels[status] || status}
    </span>
  );
}
