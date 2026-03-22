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
        <label className="block text-xs text-text-muted mb-1">Topic</label>
        <select
          value={selectedTopic}
          onChange={(e) => onTopicChange(e.target.value)}
          className="px-3 py-1.5 bg-surface-2 border border-border rounded text-sm text-text-primary focus:outline-none focus:border-accent/50"
        >
          <option value="">All</option>
          {topics.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-xs text-text-muted mb-1">Channel</label>
        <select
          value={selectedChannel}
          onChange={(e) => onChannelChange(e.target.value)}
          className="px-3 py-1.5 bg-surface-2 border border-border rounded text-sm text-text-primary focus:outline-none focus:border-accent/50"
        >
          <option value="">All</option>
          {channels.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-xs text-text-muted mb-1">From</label>
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => onDateFromChange(e.target.value)}
          className="px-3 py-1.5 bg-surface-2 border border-border rounded text-sm text-text-primary focus:outline-none focus:border-accent/50"
        />
      </div>

      <div>
        <label className="block text-xs text-text-muted mb-1">To</label>
        <input
          type="date"
          value={dateTo}
          onChange={(e) => onDateToChange(e.target.value)}
          className="px-3 py-1.5 bg-surface-2 border border-border rounded text-sm text-text-primary focus:outline-none focus:border-accent/50"
        />
      </div>
    </div>
  );
}
