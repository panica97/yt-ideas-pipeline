export interface Strategy {
  id: number;
  name: string;
  status: 'idea' | 'validated';
  description: string | null;
  source_channel: string | null;
  source_videos: string[] | null;
  parameters: Record<string, unknown>[] | null;
  entry_rules: Record<string, unknown>[] | null;
  exit_rules: Record<string, unknown>[] | null;
  risk_management: Record<string, unknown>[] | null;
  notes: Record<string, unknown>[] | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface StrategiesResponse {
  total: number;
  strategies: Strategy[];
}
