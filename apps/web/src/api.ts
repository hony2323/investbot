// Typed fetch helpers for the investbot API. In dev, "/api/*" is proxied to the
// FastAPI service (see vite.config.ts).

export interface Position {
  ticker: string;
  name: string | null;
  quantity: number;
  avg_cost: number;
  market_price: number;
  sector: string | null;
  asset_class: string;
  weight_pct: number;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
}

export interface SectorWeight {
  sector: string;
  weight_pct: number;
}

export interface PortfolioSummary {
  account_id: string | null;
  as_of: string;
  base_currency: string;
  total_value: number;
  invested_value: number;
  cash: number;
  cash_pct: number;
  position_count: number;
  top_positions: Position[];
  sector_weights: SectorWeight[];
}

export interface Violation {
  severity: "info" | "warn" | "breach";
  rule: string;
  detail: string;
}

export interface RiskReport {
  violations: Violation[];
}

export interface PortfolioResponse {
  summary: PortfolioSummary;
  risk: RiskReport;
}

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export function getPortfolio(source = "mock"): Promise<PortfolioResponse> {
  return getJSON<PortfolioResponse>(`/api/portfolio?source=${encodeURIComponent(source)}`);
}
