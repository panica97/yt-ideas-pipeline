export interface Instrument {
  id: number;
  symbol: string;
  sec_type: string;
  exchange: string;
  currency: string;
  multiplier: number;
  min_tick: number;
  description: string | null;
  data_from: string | null;
  data_to: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface InstrumentsListResponse {
  total: number;
  instruments: Instrument[];
}

export interface ScanJobResponse {
  id: number;
  status: 'pending' | 'running' | 'completed' | 'failed';
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  results: { symbol: string; data_from: string | null; data_to: string | null }[] | null;
}
