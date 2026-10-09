export type ChartPoint = {
  x: number | string;
  y: number;
  low?: number;
  high?: number;
  count?: number;
};

export type ChartSeries = {
  key: string;
  title: string;
  kind: "line" | "bar" | "histogram" | "calibration";
  x_label: string;
  y_label: string;
  points: ChartPoint[];
};

export type Metric = { key: string; label: string; unit: string; value: number; formatted: string };

export type ParameterSpec = {
  name: string;
  type: "number" | "integer";
  default: number;
  minimum: number | null;
  maximum: number | null;
  description: string;
};

export type Definition = { name: string; description: string; parameters: ParameterSpec[] };
export type Catalog = { strategies: Definition[]; stake_rules: Definition[] };

export type Filters = {
  tour: string | null;
  surfaces: string[];
  from_season: number | null;
  to_season: number | null;
};

export type BacktestRequest = {
  strategy: string;
  strategy_parameters: Record<string, number>;
  filters: Filters;
  stake_rule: string;
  stake_parameters: Record<string, number>;
  slippage: number;
  starting_bankroll: number;
  [key: string]: unknown;
};

export type BacktestResponse = {
  run_id: string;
  request: BacktestRequest;
  universe: { matches_seen: number; bets_placed: number };
  ruined: boolean;
  metrics: Metric[];
  charts: ChartSeries[];
};

export type Health = { source: string; translation_enabled: boolean };
export type Translation = { interpretation: string; request: BacktestRequest };

export type StudySummary = {
  study_id: string;
  title: string;
  verdict: Verdict;
  conclusion: string;
  statement: string;
};

export type Verdict = "supported" | "not_supported" | "inconclusive";

export type Study = StudySummary & {
  hypothesis: Record<string, string>;
  tables: { title: string; columns: string[]; rows: (string | number)[][] }[];
  charts: ChartSeries[];
};

export class ApiError extends Error {}

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new ApiError(typeof detail?.detail === "string" ? detail.detail : response.statusText);
  }
  return response.json();
}

export const api = {
  health: () => request<Health>("/api/health"),
  catalog: () => request<Catalog>("/api/catalog"),
  backtest: (payload: unknown) => request<BacktestResponse>("/api/backtest", payload),
  translate: (question: string) => request<Translation>("/api/translate", { question }),
  studies: () => request<StudySummary[]>("/api/studies"),
  study: (id: string) => request<Study>(`/api/studies/${encodeURIComponent(id)}`),
};
