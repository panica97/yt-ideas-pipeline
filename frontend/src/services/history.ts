import api from './api';
import type { HistoryResponse, HistoryStats } from '../types/history';

interface HistoryFilters {
  topic?: string;
  channel?: string;
  from?: string;
  to?: string;
  sort?: string;
  order?: 'asc' | 'desc';
  page?: number;
  limit?: number;
}

export async function getHistory(filters: HistoryFilters = {}): Promise<HistoryResponse> {
  const params = new URLSearchParams();
  if (filters.topic) params.set('topic', filters.topic);
  if (filters.channel) params.set('channel', filters.channel);
  if (filters.from) params.set('from', filters.from);
  if (filters.to) params.set('to', filters.to);
  if (filters.sort) params.set('sort', filters.sort);
  if (filters.order) params.set('order', filters.order);
  if (filters.page) params.set('page', String(filters.page));
  if (filters.limit) params.set('limit', String(filters.limit));

  const { data } = await api.get<HistoryResponse>(`/history?${params.toString()}`);
  return data;
}

export async function getHistoryStats(): Promise<HistoryStats> {
  const { data } = await api.get<HistoryStats>('/history/stats');
  return data;
}
