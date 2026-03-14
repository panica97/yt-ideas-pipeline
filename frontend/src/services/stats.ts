import api from './api';
import type { DashboardStats } from '../types/stats';

export async function getStats(): Promise<DashboardStats> {
  const { data } = await api.get<DashboardStats>('/stats');
  return data;
}
