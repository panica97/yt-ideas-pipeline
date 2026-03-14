interface HistoryFiltersProps {
  topics: string[];
  channels: string[];
  selectedTopic: string;
  selectedChannel: string;
  dateFrom: string;
  dateTo: string;
  onTopicChange: (topic: string) => void;
  onChannelChange: (channel: string) => void;
  onDateFromChange: (date: string) => void;
  onDateToChange: (date: string) => void;
}

export default function HistoryFilters({
  topics,
  channels,
  selectedTopic,
  selectedChannel,
  dateFrom,
  dateTo,
  onTopicChange,
  onChannelChange,
  onDateFromChange,
  onDateToChange,
}: HistoryFiltersProps) {
  return (
    <div className="flex flex-wrap gap-3 items-end">
      <div>
        <label className="block text-xs text-slate-400 mb-1">Topic</label>
        <select
          value={selectedTopic}
          onChange={(e) => onTopicChange(e.target.value)}
          className="px-3 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-slate-100 focus:outline-none focus:border-primary-500"
        >
          <option value="">Todos</option>
          {topics.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-xs text-slate-400 mb-1">Canal</label>
        <select
          value={selectedChannel}
          onChange={(e) => onChannelChange(e.target.value)}
          className="px-3 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-slate-100 focus:outline-none focus:border-primary-500"
        >
          <option value="">Todos</option>
          {channels.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-xs text-slate-400 mb-1">Desde</label>
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => onDateFromChange(e.target.value)}
          className="px-3 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-slate-100 focus:outline-none focus:border-primary-500"
        />
      </div>

      <div>
        <label className="block text-xs text-slate-400 mb-1">Hasta</label>
        <input
          type="date"
          value={dateTo}
          onChange={(e) => onDateToChange(e.target.value)}
          className="px-3 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-slate-100 focus:outline-none focus:border-primary-500"
        />
      </div>
    </div>
  );
}
