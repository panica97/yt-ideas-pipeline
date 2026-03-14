export interface LastResearchStat {
  topic: string | null;
  date: string | null;
  strategies_found: number;
}

export interface DashboardStats {
  total_topics: number;
  total_channels: number;
  total_videos_researched: number;
  total_strategies: number;
  total_drafts: number;
  drafts_with_todos: number;
  last_research: LastResearchStat | null;
}
