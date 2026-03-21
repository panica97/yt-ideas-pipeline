export interface Instrument {
  id: number;
  symbol: string;
  sec_type: string;
  exchange: string;
  currency: string;
  multiplier: number;
  min_tick: number;
  description: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface InstrumentsListResponse {
  total: number;
  instruments: Instrument[];
}
