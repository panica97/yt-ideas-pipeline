interface Props {
  notes: Record<string, string> | string;
}

export default function NotesSection({ notes }: Props) {
  // Handle string notes (legacy format)
  if (typeof notes === 'string') {
    if (!notes) return <p className="text-sm text-text-muted italic">No notes</p>;
    return (
      <div className="bg-surface-1/40 rounded p-2.5 border border-border/50">
        <div className="text-sm text-text-secondary leading-relaxed">{notes}</div>
      </div>
    );
  }

  const entries = Object.entries(notes);

  if (entries.length === 0) {
    return <p className="text-sm text-text-muted italic">No notes</p>;
  }

  return (
    <div className="space-y-2">
      {entries.map(([key, value]) => (
        <div key={key} className="bg-surface-1/40 rounded p-2.5 border border-border/50">
          <div className="text-xs font-mono text-text-muted mb-1">{key}</div>
          <div className="text-sm text-text-secondary leading-relaxed">{value}</div>
        </div>
      ))}
    </div>
  );
}
