export interface ResearchSession {
  id: number;
  status: 'running' | 'completed' | 'error';
  topic: string | null;
  step: number;
  step_name: string | null;
  step_display: string | null;
  total_steps: number;
  channel: string | null;
  videos_processing: string[] | null;
  started_at: string | null;
  completed_at: string | null;
  error_detail: string | null;
  result_summary: Record<string, unknown> | null;
}

export interface ResearchStatusMessage {
  sessions: ResearchSession[];
}
