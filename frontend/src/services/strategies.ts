import api from './api';
import type { StrategiesResponse, Strategy } from '../types/strategy';
import type { DraftsResponse, DraftDetail } from '../types/draft';

interface StrategyFilters {
  channel?: string;
  search?: string;
  session_id?: number;
  has_draft?: boolean;
  has_todos?: boolean;
  status?: 'pending' | 'idea' | 'validated';
}

export async function getStrategies(filters: StrategyFilters = {}): Promise<StrategiesResponse> {
  const params = new URLSearchParams();
  if (filters.channel) params.set('channel', filters.channel);
  if (filters.search) params.set('search', filters.search);
  if (filters.session_id) params.set('session_id', String(filters.session_id));
  if (filters.has_draft !== undefined) params.set('has_draft', String(filters.has_draft));
  if (filters.has_todos !== undefined) params.set('has_todos', String(filters.has_todos));
  if (filters.status) params.set('status', filters.status);

  const { data } = await api.get<StrategiesResponse>(`/strategies?${params.toString()}`);
  return data;
}

export async function getStrategy(name: string): Promise<Strategy> {
  const { data } = await api.get<Strategy>(`/strategies/${encodeURIComponent(name)}`);
  return data;
}

export async function setStrategyStatus(
  name: string,
  status: 'pending' | 'idea' | 'validated',
): Promise<Strategy> {
  const { data } = await api.patch<Strategy>(
    `/strategies/${encodeURIComponent(name)}/status`,
    { status },
  );
  return data;
}

export async function getDraftsByStrategy(name: string): Promise<DraftDetail[]> {
  const { data } = await api.get<DraftDetail[]>(`/strategies/${encodeURIComponent(name)}/drafts`);
  return data;
}

export async function getDrafts(hasTodos?: boolean): Promise<DraftsResponse> {
  const params = hasTodos !== undefined ? `?has_todos=${hasTodos}` : '';
  const { data } = await api.get<DraftsResponse>(`/strategies/drafts${params}`);
  return data;
}

export async function getDraft(stratCode: number): Promise<DraftDetail> {
  const { data } = await api.get<DraftDetail>(`/strategies/drafts/${stratCode}`);
  return data;
}
