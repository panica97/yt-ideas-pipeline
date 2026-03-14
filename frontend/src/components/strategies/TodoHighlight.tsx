interface TodoHighlightProps {
  children: React.ReactNode;
}

export default function TodoHighlight({ children }: TodoHighlightProps) {
  return (
    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-red-500/20 border border-red-500/30 rounded text-red-400 text-xs font-medium">
      <span>{'\u26A0'}</span>
      {children}
    </span>
  );
}
