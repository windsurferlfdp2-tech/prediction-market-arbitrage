import {
  DataMode,
  HealthResponse,
  MarketPairReview,
  MarketPairStatus,
  ModelAnalytics,
  ModelOpportunity,
  ModelPaperTrade,
  ModelReadiness,
  Opportunity,
  OpportunityAnalytics,
  PaperTradeSimulation,
  PredictionModelSummary,
  PredictionResult,
  ScannerStatus
} from "./types";
import { buildApiUrl } from "./apiConfig";

export { ApiConfigurationError } from "./apiConfig";

const REQUEST_TIMEOUT_MS = 30000;

export class ApiRequestError extends Error {
  endpoint: string;
  method: string;
  status?: number;
  details?: unknown;

  constructor({
    endpoint,
    method,
    message,
    status,
    details
  }: {
    endpoint: string;
    method: string;
    message: string;
    status?: number;
    details?: unknown;
  }) {
    super(message);
    this.name = "ApiRequestError";
    this.endpoint = endpoint;
    this.method = method;
    this.status = status;
    this.details = details;
  }
}

export async function getOpportunities(dataMode?: DataMode): Promise<Opportunity[]> {
  return apiJson<Opportunity[]>(withDataMode(apiUrl("/opportunities"), dataMode));
}

export async function getOpportunity(id: string, dataMode?: DataMode): Promise<Opportunity> {
  return apiJson<Opportunity>(withDataMode(apiUrl(`/opportunities/${id}`), dataMode));
}

export async function getHealth(dataMode?: DataMode): Promise<HealthResponse> {
  return apiJson<HealthResponse>(withDataMode(apiUrl("/health"), dataMode));
}

export async function getOpportunityAnalytics(dataMode?: DataMode): Promise<OpportunityAnalytics> {
  return apiJson<OpportunityAnalytics>(
    withDataMode(apiUrl("/analytics/opportunities"), dataMode)
  );
}

export async function getScannerStatus(dataMode?: DataMode): Promise<ScannerStatus> {
  return apiJson<ScannerStatus>(withDataMode(apiUrl("/scanner/status"), dataMode));
}

export async function getMarketMatches(): Promise<MarketPairReview[]> {
  return apiJson<MarketPairReview[]>(apiUrl("/market-matches"));
}

export async function getPaperTrades(limit = 20): Promise<PaperTradeSimulation[]> {
  const url = apiUrl("/paper-trades");
  url.searchParams.set("limit", String(limit));
  return apiJson<PaperTradeSimulation[]>(url);
}

export async function generateMarketMatches(dataMode: DataMode): Promise<MarketPairReview[]> {
  return apiJson<MarketPairReview[]>(withDataMode(apiUrl("/market-matches/generate"), dataMode), {
    method: "POST",
    headers: { "Content-Type": "application/json" }
  });
}

export async function updateMarketMatchStatus(
  id: string,
  status: MarketPairStatus
): Promise<MarketPairReview> {
  return apiJson<MarketPairReview>(apiUrl(`/market-matches/${id}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status })
  });
}

export async function getModels(): Promise<PredictionModelSummary[]> {
  return apiJson<PredictionModelSummary[]>(apiUrl("/models"));
}

export async function trainModel(): Promise<PredictionModelSummary> {
  return apiJson<PredictionModelSummary>(apiUrl("/models/train"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category: "general", data_mode: "live", model_type: "ensemble" })
  });
}

export async function approveModelForPaper(id: string): Promise<PredictionModelSummary> {
  return apiJson<PredictionModelSummary>(apiUrl(`/models/${id}/approve-paper`), {
    method: "POST",
    headers: { "Content-Type": "application/json" }
  });
}

export async function retireModel(id: string): Promise<PredictionModelSummary> {
  return apiJson<PredictionModelSummary>(apiUrl(`/models/${id}/retire`), {
    method: "POST",
    headers: { "Content-Type": "application/json" }
  });
}

export async function generatePredictions(dataMode: DataMode): Promise<PredictionResult[]> {
  return apiJson<PredictionResult[]>(
    withDataMode(apiUrl("/predictions/generate"), dataMode),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    }
  );
}

export async function getPredictions(): Promise<PredictionResult[]> {
  return apiJson<PredictionResult[]>(withDataMode(apiUrl("/predictions"), "live"));
}

export async function generateModelOpportunities(dataMode: DataMode): Promise<ModelOpportunity[]> {
  return apiJson<ModelOpportunity[]>(
    withDataMode(apiUrl("/model-opportunities/generate"), dataMode),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    }
  );
}

export async function getModelOpportunities(): Promise<ModelOpportunity[]> {
  return apiJson<ModelOpportunity[]>(withDataMode(apiUrl("/model-opportunities"), "live"));
}

export async function runModelPaperTrades(dataMode: DataMode): Promise<ModelPaperTrade[]> {
  return apiJson<ModelPaperTrade[]>(
    withDataMode(apiUrl("/model-paper-trades/run"), dataMode),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    }
  );
}

export async function getModelPaperTrades(): Promise<ModelPaperTrade[]> {
  return apiJson<ModelPaperTrade[]>(withDataMode(apiUrl("/model-paper-trades"), "live"));
}

export async function getModelAnalytics(): Promise<ModelAnalytics> {
  return apiJson<ModelAnalytics>(withDataMode(apiUrl("/model-analytics"), "live"));
}

export async function getModelReadiness(): Promise<ModelReadiness> {
  return apiJson<ModelReadiness>(apiUrl("/models/readiness"));
}

function apiUrl(path: string): URL {
  return buildApiUrl(path);
}

function withDataMode(url: URL, dataMode?: DataMode): URL {
  const nextUrl = new URL(url);
  if (dataMode) {
    nextUrl.searchParams.set("data_mode", dataMode);
  }
  return nextUrl;
}

async function apiJson<T>(url: URL, init: RequestInit = {}): Promise<T> {
  const response = await fetchWithTimeout(url, init);
  const contentType = response.headers.get("content-type") ?? "";
  let payload: unknown = null;
  if (contentType.includes("application/json")) {
    try {
      payload = await response.json();
    } catch (caught) {
      throw requestError(url, init, "Backend returned invalid JSON.", response.status, caught);
    }
  } else if (!response.ok) {
    payload = await response.text().catch(() => null);
  }

  if (!response.ok) {
    throw requestError(
      url,
      init,
      backendMessage(payload, `Backend returned HTTP ${response.status}.`),
      response.status,
      payload
    );
  }
  return payload as T;
}

async function fetchWithTimeout(url: URL, init: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const method = init.method ?? "GET";
  const started = performance.now();
  try {
    const response = await fetch(url, {
      cache: "no-store",
      signal: controller.signal,
      ...init
    });
    logApi("debug", {
      method,
      url,
      status: response.status,
      durationMs: performance.now() - started
    });
    return response;
  } catch (caught) {
    const message =
      caught instanceof DOMException && caught.name === "AbortError"
        ? "Request timed out."
        : "Network request failed. The backend may be unreachable or CORS may have blocked the request.";
    const error = requestError(url, init, message, undefined, caught);
    logApi("error", {
      method,
      url,
      durationMs: performance.now() - started,
      error: error.message
    });
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function requestError(
  url: URL,
  init: RequestInit,
  message: string,
  status?: number,
  details?: unknown
) {
  const method = init.method ?? "GET";
  const statusText = status ? ` HTTP ${status}.` : "";
  return new ApiRequestError({
    endpoint: sanitizeUrl(url),
    method,
    status,
    details,
    message: `${method} ${sanitizeUrl(url)} failed.${statusText} ${message}`
  });
}

function backendMessage(payload: unknown, fallback: string): string {
  if (typeof payload === "string" && payload) {
    return payload;
  }
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
    return `Validation error: ${JSON.stringify(detail)}`;
  }
  return fallback;
}

function logApi(
  level: "debug" | "error",
  event: {
    method: string;
    url: URL;
    status?: number;
    durationMs: number;
    error?: string;
  }
) {
  if (process.env.NODE_ENV === "production") {
    return;
  }
  const payload = {
    method: event.method,
    url: sanitizeUrl(event.url),
    status: event.status,
    durationMs: Math.round(event.durationMs),
    error: event.error
  };
  if (level === "error") {
    console.error("api_request_failed", payload);
  } else {
    console.debug("api_request_completed", payload);
  }
}

function sanitizeUrl(url: URL): string {
  return `${url.origin}${url.pathname}${url.search}`;
}
