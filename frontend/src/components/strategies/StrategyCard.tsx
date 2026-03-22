import type { Strategy } from '../../types/strategy';

interface StrategyCardProps {
  strategy: Strategy;
  onClick: () => void;
}

export default function StrategyCard({ strategy, onClick }: StrategyCardProps) {
  const descPreview = strategy.description
    ? strategy.description.length > 150
      ? strategy.description.slice(0, 150) + '...'
      : strategy.description
    : 'No description';

  return (
    <div
      onClick={onClick}
      className="bg-surface-1 border border-border rounded-lg p-4 cursor-pointer hover:border-border-hover transition-colors"
    >
      <h3 className="text-sm font-semibold text-text-primary mb-1">{strategy.name}</h3>
      <div className="flex items-center gap-2 mb-2">
        {strategy.source_channel && (
          <span className="text-xs text-accent">{strategy.source_channel}</span>
        )}
        {strategy.source_videos && strategy.source_videos.length > 0 && (
          <span className="text-xs text-text-muted">
            {strategy.source_videos.length} source video{strategy.source_videos.length > 1 ? 's' : ''}
          </span>
        )}
      </div>
      <p className="text-xs text-text-muted leading-relaxed">{descPreview}</p>
    </div>
  );
}
