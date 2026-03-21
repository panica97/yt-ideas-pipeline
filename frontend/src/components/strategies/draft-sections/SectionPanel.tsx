import { useState, useRef, useEffect } from 'react';

interface SectionPanelProps {
  id: string;
  title: string;
  icon: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  forceOpen?: boolean;
}

export default function SectionPanel({ id, title, icon, children, defaultOpen = false, forceOpen }: SectionPanelProps) {
  const [open, setOpen] = useState(defaultOpen);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (forceOpen && !open) {
      setOpen(true);
      // Scroll into view after opening
      setTimeout(() => {
        ref.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }, 100);
    }
  }, [forceOpen, open]);

  return (
    <div ref={ref} id={`section-${id}`} className="border border-border rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left bg-surface-1/50 hover:bg-surface-2/50 transition-colors"
      >
        <span className="text-sm">{icon}</span>
        <span className="text-sm font-medium text-text-primary flex-1">{title}</span>
        <span className="text-xs text-text-muted">{open ? '\u25B2' : '\u25BC'}</span>
      </button>
      {open && (
        <div className="p-3 bg-surface-1/20">
          {children}
        </div>
      )}
    </div>
  );
}
