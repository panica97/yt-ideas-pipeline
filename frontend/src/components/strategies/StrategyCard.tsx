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
    : 'Sin descripcion';

  return (
    <div
      onClick={onClick}
      className="bg-slate-800 border border-slate-700 rounded-lg p-4 cursor-pointer hover:border-slate-600 transition-colors"
    >
      <h3 className="text-sm font-semibold text-white mb-1">{strategy.name}</h3>
      <div className="flex items-center gap-2 mb-2">
        {strategy.source_channel && (
          <span className="text-xs text-primary-400">{strategy.source_channel}</span>
        )}
        {strategy.source_videos && strategy.source_videos.length > 0 && (
          <span className="text-xs text-slate-500">
            {strategy.source_videos.length} video{strategy.source_videos.length > 1 ? 's' : ''} fuente
          </span>
        )}
      </div>
      <p className="text-xs text-slate-400 leading-relaxed">{descPreview}</p>
    </div>
  );
}
