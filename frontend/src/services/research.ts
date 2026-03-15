import api from './api';

export interface SessionVideo {
  video_id: string;
  url: string;
  channel: string | null;
  strategies_found: number;
}

export interface PipelineStep {
  step: number;
  name: string;
  status: 'ok' | 'skipped' | 'error';
  detail?: string;
}

export interface ChannelProcessed {
  name: string;
  videos: number;
  strategies: number;
}

export interface ResultSummary {
  topic: string;
  total_videos: number;
  total_strategies: number;
  channels_processed: ChannelProcessed[];
  pipeline_steps: PipelineStep[];
}

export interface ResearchSessionDetail {
  id: number;
  status: 'completed' | 'error';
  topic: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  result_summary: ResultSummary | null;
  error_detail: string | null;
  videos: SessionVideo[];
}

export interface ResearchSessionsResponse {
  sessions: ResearchSessionDetail[];
}

export async function getResearchSessions(
  limit: number = 1,
): Promise<ResearchSessionsResponse> {
  const { data } = await api.get<ResearchSessionsResponse>(
    `/research/sessions`,
    { params: { limit } },
  );
  return data;
}

export async function getResearchSessionDetail(
  sessionId: number,
): Promise<ResearchSessionDetail> {
  const { data } = await api.get<ResearchSessionDetail>(
    `/research/sessions/${sessionId}`,
  );
  return data;
}
