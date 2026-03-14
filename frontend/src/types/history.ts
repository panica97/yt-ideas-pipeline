export interface HistoryItem {
  video_id: string;
  url: string;
  channel: string | null;
  topic: string | null;
  researched_at: string | null;
  strategies_found: number;
}

export interface HistoryResponse {
  total: number;
  page: number;
  limit: number;
  items: HistoryItem[];
}

export interface LastResearch {
  topic: string | null;
  date: string | null;
  videos: number;
  strategies: number;
}

export interface HistoryStats {
  total_videos: number;
  total_strategies_found: number;
  by_topic: Record<string, number>;
  by_channel: Record<string, number>;
  last_research: LastResearch | null;
}
