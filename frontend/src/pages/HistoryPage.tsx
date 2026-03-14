import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getHistory, getHistoryStats } from '../services/history';
import HistoryFilters from '../components/history/HistoryFilters';
import HistoryTable from '../components/history/HistoryTable';
import LoadingSpinner from '../components/common/LoadingSpinner';

export default function HistoryPage() {
  const [topic, setTopic] = useState('');
  const [channel, setChannel] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(1);
  const limit = 50;

  const { data: stats } = useQuery({
    queryKey: ['historyStats'],
    queryFn: getHistoryStats,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['history', topic, channel, dateFrom, dateTo, page],
    queryFn: () =>
      getHistory({
        topic: topic || undefined,
        channel: channel || undefined,
        from: dateFrom || undefined,
        to: dateTo || undefined,
        page,
        limit,
      }),
  });

  const topics = stats ? Object.keys(stats.by_topic) : [];
  const channels = stats
    ? topic
      ? Object.keys(stats.by_channel).filter(() => true) // Show all channels when topic-filtered channels aren't available
      : Object.keys(stats.by_channel)
    : [];

  const totalPages = data ? Math.ceil(data.total / limit) : 1;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Historial de investigacion</h1>
        <span className="text-sm text-slate-400">Total: {data?.total ?? 0} videos</span>
      </div>

      <HistoryFilters
        topics={topics}
        channels={channels}
        selectedTopic={topic}
        selectedChannel={channel}
        dateFrom={dateFrom}
        dateTo={dateTo}
        onTopicChange={(t) => { setTopic(t); setChannel(''); setPage(1); }}
        onChannelChange={(c) => { setChannel(c); setPage(1); }}
        onDateFromChange={(d) => { setDateFrom(d); setPage(1); }}
        onDateToChange={(d) => { setDateTo(d); setPage(1); }}
      />

      {isLoading ? (
        <LoadingSpinner />
      ) : (
        <>
          <HistoryTable items={data?.items ?? []} />

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 text-sm bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 text-slate-300 rounded transition-colors"
              >
                Anterior
              </button>
              <span className="text-sm text-slate-400">
                Pagina {page} de {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1 text-sm bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 text-slate-300 rounded transition-colors"
              >
                Siguiente
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
