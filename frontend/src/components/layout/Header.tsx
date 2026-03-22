import { useResearchStatus } from '../../hooks/useResearchStatus';
import { useTheme } from '../../hooks/useTheme';
import { Activity, Wifi, WifiOff, Sun, Moon } from 'lucide-react';

export default function Header() {
  const { sessions, isConnected } = useResearchStatus();
  const { isDark, toggle } = useTheme();
  const hasRunning = sessions.some((s) => s.status === 'running');

  return (
    <header className="relative h-14 bg-surface-1/80 backdrop-blur-sm border-b border-border flex items-center justify-between px-6 z-20">
      <div className="flex items-center gap-3">
        <h2 className="text-sm font-medium text-text-secondary">IRT Dashboard</h2>
      </div>

      <div className="flex items-center gap-4">
        {/* Research status */}
        {hasRunning && (
          <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-accent/10 border border-accent/20 animate-fade-in">
            <Activity size={14} className="text-accent animate-pulse" />
            <span className="text-xs text-accent font-medium">Researching...</span>
          </div>
        )}

        {/* Theme toggle */}
        <button
          onClick={toggle}
          className="w-8 h-8 rounded-lg flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-surface-2 transition-all duration-200"
          title={isDark ? 'Light mode' : 'Dark mode'}
        >
          {isDark ? <Sun size={16} /> : <Moon size={16} />}
        </button>

        {/* Connection indicator */}
        <div className="flex items-center gap-1.5">
          {isConnected ? (
            <Wifi size={14} className="text-text-muted" />
          ) : (
            <WifiOff size={14} className="text-danger" />
          )}
          <span className="text-[11px] text-text-muted">
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>

      {/* Bottom gradient line */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-border-accent to-transparent opacity-50" />
    </header>
  );
}
