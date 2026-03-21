import { AlertTriangle } from 'lucide-react';

interface TodoBadgeProps {
  count: number;
}

export default function TodoBadge({ count }: TodoBadgeProps) {
  if (count === 0) return null;

  const isHigh = count > 3;
  const classes = isHigh
    ? 'bg-danger/10 text-danger border-danger/20'
    : 'bg-warn/10 text-warn border-warn/20';

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${classes}`}>
      <AlertTriangle size={12} />
      {count} TODO{count > 1 ? 's' : ''}
    </span>
  );
}
