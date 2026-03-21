import type { HistoryItem } from '../../types/history';

interface HistoryTableProps {
  items: HistoryItem[];
}

export default function HistoryTable({ items }: HistoryTableProps) {
  if (items.length === 0) {
    return (
      <p className="text-sm text-text-muted py-8 text-center">
        No se han investigado videos todavia
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            <th className="text-left py-2 px-3 text-text-muted font-medium">Video ID</th>
            <th className="text-left py-2 px-3 text-text-muted font-medium">Canal</th>
            <th className="text-left py-2 px-3 text-text-muted font-medium">Topic</th>
            <th className="text-left py-2 px-3 text-text-muted font-medium">Fecha</th>
            <th className="text-left py-2 px-3 text-text-muted font-medium">Estrategias</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, i) => (
            <tr key={`${item.video_id}-${i}`} className="border-b border-border/50 hover:bg-surface-1/50">
              <td className="py-2 px-3">
                <a
                  href={`https://www.youtube.com/watch?v=${item.video_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent hover:text-accent-hover"
                  title={item.video_id}
                >
                  {item.title || item.video_id}
                </a>
              </td>
              <td className="py-2 px-3 text-text-secondary">{item.channel || '-'}</td>
              <td className="py-2 px-3 text-text-secondary">{item.topic || '-'}</td>
              <td className="py-2 px-3 text-text-muted">
                {item.researched_at
                  ? new Date(item.researched_at).toLocaleDateString('es-ES')
                  : '-'}
              </td>
              <td className="py-2 px-3 text-text-secondary">{item.strategies_found}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
