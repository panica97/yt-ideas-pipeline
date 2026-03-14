export interface TodoField {
  path: string;
  context: string | null;
}

export interface TodoSummary {
  count: number;
  fields: TodoField[];
}

export interface DraftSummary {
  strat_code: number;
  strat_name: string;
  symbol: string | null;
  active: boolean;
  tested: boolean;
  prod: boolean;
  todo_count: number;
  todo_fields: string[] | null;
}

export interface DraftDetail {
  strat_code: number;
  strat_name: string;
  active: boolean;
  tested: boolean;
  prod: boolean;
  todo_count: number;
  todo_fields: string[] | null;
  data: Record<string, unknown>;
  _todo_summary: TodoSummary;
  created_at: string | null;
  updated_at: string | null;
}

export interface DraftsResponse {
  total: number;
  drafts: DraftSummary[];
}
