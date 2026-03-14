interface TodoBadgeProps {
  count: number;
}

export default function TodoBadge({ count }: TodoBadgeProps) {
  if (count === 0) return null;

  const bgClass = count > 3 ? 'bg-red-500/20 text-red-400 border-red-500/30' : 'bg-orange-500/20 text-orange-400 border-orange-500/30';

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border ${bgClass}`}>
      <span className="text-sm">{'\u26A0'}</span>
      {count} TODO{count > 1 ? 's' : ''}
    </span>
  );
}
