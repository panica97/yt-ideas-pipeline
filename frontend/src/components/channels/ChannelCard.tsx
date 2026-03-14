import type { Channel } from '../../types/channel';

interface ChannelCardProps {
  channel: Channel;
  onDelete: () => void;
}

export default function ChannelCard({ channel, onDelete }: ChannelCardProps) {
  const lastFetched = channel.last_fetched
    ? new Date(channel.last_fetched).toLocaleDateString('es-ES')
    : 'Nunca';

  return (
    <div className="flex items-center justify-between py-2 px-3 bg-slate-700/30 border border-slate-700 rounded">
      <div className="flex items-center gap-4 min-w-0">
        <span className="text-sm font-medium text-slate-200 truncate">{channel.name}</span>
        <a
          href={channel.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-primary-400 hover:text-primary-300 truncate"
        >
          {channel.url.replace('https://www.youtube.com/', '')}
        </a>
        <span className="text-xs text-slate-500 whitespace-nowrap">{lastFetched}</span>
      </div>
      <button
        onClick={onDelete}
        className="text-xs text-slate-500 hover:text-red-400 ml-2 transition-colors"
        title="Eliminar canal"
      >
        Borrar
      </button>
    </div>
  );
}
