import api from './api';
import type { Instrument, InstrumentsListResponse, ScanJobResponse } from '../types/instrument';

export async function getInstruments(): Promise<InstrumentsListResponse> {
  const { data } = await api.get<InstrumentsListResponse>('/instruments');
  return data;
}

export async function createInstrument(
  instrument: Omit<Instrument, 'id' | 'created_at' | 'updated_at' | 'data_from' | 'data_to'>
): Promise<Instrument> {
  const { data } = await api.post<Instrument>('/instruments', instrument);
  return data;
}

export async function updateInstrument(
  symbol: string,
  updates: Partial<Instrument>
): Promise<Instrument> {
  const { data } = await api.put<Instrument>(`/instruments/${symbol}`, updates);
  return data;
}

export async function deleteInstrument(symbol: string): Promise<void> {
  await api.delete(`/instruments/${symbol}`);
}

export async function triggerScanData(): Promise<ScanJobResponse> {
  const { data } = await api.post<ScanJobResponse>('/instruments/scan-data');
  return data;
}

export async function getScanJobStatus(jobId: number): Promise<ScanJobResponse> {
  const { data } = await api.get<ScanJobResponse>(`/instruments/scan-data/${jobId}`);
  return data;
}
