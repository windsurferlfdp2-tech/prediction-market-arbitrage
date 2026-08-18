export type Exchange = "polymarket" | "kalshi";
export type DataMode = "live" | "test";

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
  simulation?: boolean;
  test_mode?: boolean;
  data_source?: string;
  is_live_data?: boolean;
  read_only: boolean;
  exchanges: ExchangeHealth[];
}

export interface OpportunityAnalytics {
  analytics_data_type?: string;
  analytics_scope?: string;
  server_time_utc?: string;
  latest_scan_timestamp?: string | null;
  latest_record_seen_timestamp?: string | null;
  latest_opportunity_detected_timestamp?: string | null;
  opportunities_detected_per_day: Record<string, number>;
  median_opportunity_duration_seconds: string;
  median_net_roi: string;
  maximum_theoretical_profit: string;
  percentage_lasting_over_1_seconds: string;
  percentage_lasting_over_3_seconds: string;
  percentage_lasting_over_5_seconds: string;
  percentage_lasting_over_10_seconds: string;
  total_candidates_recorded: number;
  unique_opportunities?: number;
  raw_detections?: number;
  duplicate_updates?: number;
  active_opportunities?: number;
  historical_records_excluded?: number;
  simulated_records_excluded?: number;
  paper_label?: string;
  simulated_trade_count?: number;
  simulated_fill_rate?: string;
  partial_fill_rate?: string;
  hedge_failure_rate?: string;
  cumulative_simulated_pnl?: string;
  median_projected_roi?: string;
  median_executable_roi?: string;
  paper_trades_per_day?: Record<string, number>;
  results_by_platform?: Record<string, number>;
  results_by_category?: Record<string, number>;
}

export interface ScannerStatus {
  data_mode: DataMode | string;
  running: boolean;
  last_started_at: string | null;
  last_completed_at: string | null;
  last_error: string | null;
  markets_checked: number;
  books_checked: number;
  verified_pairs_checked: number;
  opportunities_found: number;
  scan_duration_seconds: number | null;
  latest_market_fetch_timestamp: string | null;
  latest_order_book_update_timestamp: string | null;
  latest_opportunity_detected_timestamp: string | null;
  order_book_ages_seconds: Array<{
    exchange: Exchange;
    market_id: string;
    side: "yes" | "no";
    age_seconds: string;
  }>;
  diagnostics?: {
    first_zero_stage?: string | null;
    healthy_zero_message?: string;
    funnel?: Record<string, number>;
    rejection_counts?: Record<string, number>;
    thresholds?: Record<string, string | number>;
    strategies_active?: Record<string, boolean>;
    exchange_status?: Array<Record<string, unknown>>;
  };
}

export type MarketPairStatus =
  | "pending_review"
  | "verified_equivalent"
  | "related_not_equivalent"
  | "rejected";

export interface MarketPairReview {
  id: string;
  polymarket_market_id: string;
  kalshi_market_id: string;
  polymarket_title: string;
  kalshi_title: string;
  polymarket_resolution_criteria: string;
  kalshi_resolution_criteria: string;
  polymarket_close_date: string | null;
  kalshi_close_date: string | null;
  polymarket_settlement_date: string | null;
  kalshi_settlement_date: string | null;
  polymarket_resolution_sources: string[];
  kalshi_resolution_sources: string[];
  polymarket_entities: string[];
  kalshi_entities: string[];
  polymarket_numbers: string[];
  kalshi_numbers: string[];
  similarity_score: string;
  mismatches: string[];
  status: MarketPairStatus;
  created_at: string;
  updated_at: string;
}

export interface PaperLegFill {
  exchange: Exchange;
  market_id: string;
  side: "yes" | "no";
  requested_quantity: string;
  filled_quantity: string;
  average_price: string;
  status: "filled" | "partial" | "failed";
}

export interface PaperTradeSimulation {
  id: string;
  opportunity_id: string;
  same_market_key: string;
  label: "PAPER TRADING";
  created_at: string;
  latency_ms: number;
  requested_quantity: string;
  filled_quantity: string;
  projected_net_profit: string;
  realized_pnl: string;
  status: "complete" | "partial_fill" | "hedge_failed" | "disappeared" | "skipped";
  partial_fill: boolean;
  hedge_failure: boolean;
  fills: PaperLegFill[];
}

export type MarketCategory =
  | "politics"
  | "economics"
  | "crypto"
  | "sports"
  | "technology"
  | "general";

export type ModelStatus = "candidate" | "approved_for_paper" | "rejected" | "retired";

export interface PredictionModelSummary {
  id: string;
  name: string;
  category: MarketCategory;
  version: string;
  status: ModelStatus;
  model_type: string;
  training_timestamp: string;
  training_sample_count: number;
  validation_metrics: Record<string, unknown>;
  calibration_method: string;
  calibration_metrics: Record<string, unknown>;
  artifact_path: string;
  feature_schema_version: string;
  training_fingerprint: string | null;
  artifact_hash: string | null;
  dataset_version: string | null;
  training_start: string | null;
  training_end: string | null;
  resolved_market_count: number | null;
  validation_sample_count: number | null;
  baseline_score: string | null;
  model_score: string | null;
}

export interface PredictionResult {
  id: string;
  model_id: string;
  market_id: string;
  exchange: Exchange;
  category: MarketCategory;
  market_title: string;
  fair_probability: string;
  raw_model_probability: string;
  calibrated_probability: string;
  market_probability: string;
  cross_platform_probability: string | null;
  confidence_score: string;
  uncertainty_score: string;
  model_version: string;
  calibration_version: string;
  feature_timestamp: string;
  prediction_timestamp: string;
  important_features: string[];
  no_trade_reasons: string[];
  label: "MODEL PREDICTION";
}

export interface ModelOpportunity {
  id: string;
  prediction_id: string;
  model_id: string;
  market_id: string;
  exchange: Exchange;
  category: MarketCategory;
  market_title: string;
  direction: "yes" | "no";
  executable_quantity: string;
  weighted_average_entry_price: string;
  gross_expected_value: string;
  fees: string;
  expected_slippage: string;
  uncertainty_buffer: string;
  net_expected_value: string;
  expected_roi: string;
  confidence_score: string;
  uncertainty_score: string;
  book_freshness_seconds: string;
  detected_at: string;
  no_trade_reasons: string[];
  model_version: string;
  calibration_version: string;
  label: string;
  paper_execution_eligible?: boolean;
  paper_execution_status?: string;
  paper_execution_reason?: string | null;
}

export interface ModelPaperTrade {
  id: string;
  opportunity_id: string;
  prediction_id: string;
  model_id: string;
  market_id: string;
  exchange: Exchange;
  category: MarketCategory;
  direction: "yes" | "no";
  label: string;
  created_at: string;
  status: "open" | "closed" | "partial_fill" | "cancelled";
  requested_quantity: string;
  filled_quantity: string;
  entry_price: string;
  position_size: string;
  expected_edge: string;
  mark_to_market_pnl: string;
  realized_pnl: string;
  exit_reason: string | null;
  resolved_outcome?: "yes" | "no" | null;
  resolution_timestamp?: string | null;
  last_resolution_check_timestamp?: string | null;
  settlement_value?: string | null;
  model_version: string;
  calibration_version: string;
}

export interface ModelAnalytics {
  label: "MODEL PAPER TRADE";
  model_paper_trading_paused?: boolean;
  model_paper_trading_freeze_enabled_at?: string | null;
  model_paper_trading_freeze_reason?: string | null;
  prediction_count: number;
  model_opportunity_count: number;
  model_paper_trade_count: number;
  resolved_model_paper_trade_count?: number;
  open_model_paper_trade_count?: number;
  predictions_by_probability_bucket: Record<string, number>;
  results_by_category: Record<string, number>;
  cumulative_model_paper_pnl: string;
  return_on_deployed_paper_capital: string;
  win_rate: string;
  resolved_win_rate?: string;
  average_edge_at_entry: string;
  maximum_drawdown: string;
  sample_size_warning: boolean;
  arbitrage_pnl_excluded: boolean;
}

export interface ModelReadiness {
  ready: boolean;
  reason?: string;
  model_paper_trading_paused: boolean;
  freeze_reason?: string | null;
  total_prediction_rows?: number;
  unique_markets?: number;
  unique_resolved_markets?: number;
  category_distribution?: Record<string, number>;
  exchange_distribution?: Record<string, number>;
  outcome_balance?: { yes: number; no: number };
  oldest_prediction_timestamp?: string;
  newest_prediction_timestamp?: string;
  snapshots_per_market?: {
    minimum: number;
    median: number;
    maximum: number;
    top_markets: Record<string, number>;
  };
  chronological_splits?: Record<string, unknown>;
  market_baseline?: {
    brier_score: number;
    log_loss: number | null;
    calibration_error: number;
    sample_count: number;
    unique_market_count: number;
  };
  model_comparison?: Record<string, unknown>;
  approval_requirements?: {
    all_passed: boolean;
    checks: Record<string, { required: unknown; actual: unknown; passed: boolean }>;
  };
}
