export type Exchange = "polymarket" | "kalshi";

export interface UsedLevel {
  exchange: Exchange;
  market_id: string;
  outcome_id: string;
  side: "yes" | "no";
  price: string;
  quantity: string;
  source_side: string;
}

export interface Opportunity {
  id: string;
  same_market_key: string;
  title: string;
  yes_exchange: Exchange;
  no_exchange: Exchange;
  yes_market_id: string;
  no_market_id: string;
  yes_avg_price: string;
  no_avg_price: string;
  gross_profit: string;
  net_profit: string;
  total_fees: string;
  slippage_cost: string;
  roi: string;
  max_quantity: string;
  freshness_seconds: string;
  confidence: "high" | "medium" | "low";
  detected_at: string;
  read_only_label: string;
  used_levels: UsedLevel[];
}

export interface ExchangeHealth {
  exchange: Exchange;
  ok: boolean;
  message: string;
  checked_at: string;
}

export interface HealthResponse {
  ok: boolean;
  mode: string;
  read_only: boolean;
  exchanges: ExchangeHealth[];
}
