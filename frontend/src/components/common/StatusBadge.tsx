import { Activity, CheckCircle2, XCircle, MinusCircle } from 'lucide-react';

interface StatusBadgeProps {
  status: 'running' | 'completed' | 'error' | 'idle';
  text?: string;
}

const config = {
  running: {
    icon: Activity,
    classes: 'bg-accent/10 text-accent border-accent/20',
    dotClass: 'bg-accent animate-pulse',
    label: 'Running',
  },
  completed: {
    icon: CheckCircle2,
    classes: 'bg-accent/10 text-accent border-accent/20',
    dotClass: 'bg-accent',
    label: 'Completed',
  },
  error: {
    icon: XCircle,
    classes: 'bg-danger/10 text-danger border-danger/20',
    dotClass: 'bg-danger',
    label: 'Error',
  },
  idle: {
    icon: MinusCircle,
    classes: 'bg-surface-2 text-text-muted border-border',
    dotClass: 'bg-text-muted',
    label: 'Idle',
  },
};

export default function StatusBadge({ status, text }: StatusBadgeProps) {
  const { classes, dotClass, label } = config[status] || config.idle;

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${classes}`}>
      <span className={`inline-block w-1.5 h-1.5 rounded-full ${dotClass}`} />
      {text || label}
    </span>
  );
}
