import api from './api';
import type { BacktestJob, BacktestListResponse, CreateBacktestParams } from '../types/backtest';

export async function createBacktest(params: CreateBacktestParams): Promise<BacktestJob> {
  const { data } = await api.post<BacktestJob>('/backtests', params);
  return data;
}

export async function getBacktest(jobId: number): Promise<BacktestJob> {
  const { data } = await api.get<BacktestJob>(`/backtests/${jobId}`);
  return data;
}

export async function getBacktestsByDraft(stratCode: number): Promise<BacktestListResponse> {
  const { data } = await api.get<BacktestListResponse>(`/backtests?draft_strat_code=${stratCode}`);
  return data;
}

export async function deleteBacktest(jobId: number): Promise<void> {
  await api.delete(`/backtests/${jobId}`);
}
