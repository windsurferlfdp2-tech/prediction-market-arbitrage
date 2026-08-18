"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  getOpportunities,
  getOpportunityAnalytics,
  getPaperTrades,
  getScannerStatus
} from "../../lib/api";
import { Opportunity, OpportunityAnalytics, PaperTradeSimulation, ScannerStatus } from "../../lib/types";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://127.0.0.1:8000/ws/opportunities";

export function OpportunityDashboard({
  initial,
  initialAnalytics
}: {
  initial: Opportunity[];
  initialAnalytics: OpportunityAnalytics | null;
}) {
  const [items, setItems] = useState(initial);
  const [analytics, setAnalytics] = useState<OpportunityAnalytics | null>(initialAnalytics);
  const [scannerStatus, setScannerStatus] = useState<ScannerStatus | null>(null);
  const [paperTrades, setPaperTrades] = useState<PaperTradeSimulation[]>([]);
  const [exchange, setExchange] = useState("all");
  const [minRoi, setMinRoi] = useState("0");
  const [minLiquidity, setMinLiquidity] = useState("0");
  const [maxFreshness, setMaxFreshness] = useState("30");
  const [socketState, setSocketState] = useState("connecting");

  useEffect(() => {
    let cancelled = false;
    getOpportunities("live")
      .then((payload) => {
        if (!cancelled) {
          setItems(payload);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setItems([]);
          setSocketState("error");
        }
      });
    getOpportunityAnalytics("live")
      .then((payload) => {
        if (!cancelled) {
          setAnalytics(payload);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAnalytics(null);
        }
      });
    getScannerStatus("live")
      .then((payload) => {
        if (!cancelled) {
          setScannerStatus(payload);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setScannerStatus(null);
        }
      });
    getPaperTrades()
      .then((payload) => {
        if (!cancelled) {
          setPaperTrades(payload);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPaperTrades([]);
        }
      });

    const wsUrl = new URL(WS_URL);
    wsUrl.searchParams.set("data_mode", "live");
    const ws = new WebSocket(wsUrl.toString());
    ws.onopen = () => setSocketState("live");
    ws.onclose = () => setSocketState("closed");
    ws.onerror = () => setSocketState("error");
    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data) as Opportunity[];
      setItems(payload);
    };
    return () => {
      cancelled = true;
      ws.close();
    };
  }, []);

  const filtered = useMemo(() => {
    return [...items]
      .filter((item) => {
        const exchangeMatch =
          exchange === "all" || item.yes_exchange === exchange || item.no_exchange === exchange;
        return (
          exchangeMatch &&
          Number(item.roi) >= Number(minRoi) &&
          Number(item.max_quantity) >= Number(minLiquidity) &&
          Number(item.freshness_seconds) <= Number(maxFreshness)
        );
      })
      .sort((a, b) => Number(b.net_profit) - Number(a.net_profit) || Number(b.roi) - Number(a.roi));
  }, [exchange, items, maxFreshness, minLiquidity, minRoi]);

  return (
    <>
      <div className="filters">
        <span className="pill">LIVE MARKET DATA</span>
        <label>
          Exchange
          <select value={exchange} onChange={(event) => setExchange(event.target.value)}>
            <option value="all">All</option>
            <option value="polymarket">Polymarket</option>
            <option value="kalshi">Kalshi</option>
          </select>
        </label>
        <label>
          Minimum ROI
          <input value={minRoi} onChange={(event) => setMinRoi(event.target.value)} inputMode="decimal" />
        </label>
        <label>
          Minimum liquidity
          <input
            value={minLiquidity}
            onChange={(event) => setMinLiquidity(event.target.value)}
            inputMode="decimal"
          />
        </label>
        <label>
          Max freshness seconds
          <input
            value={maxFreshness}
            onChange={(event) => setMaxFreshness(event.target.value)}
            inputMode="decimal"
          />
        </label>
      </div>
      {analytics ? <ScannerStatusPanel analytics={analytics} scannerStatus={scannerStatus} /> : null}
      {analytics ? <AnalyticsPanel analytics={analytics} /> : null}
      {analytics ? <PaperTradingPanel analytics={analytics} trades={paperTrades} /> : null}
      <p className="subtitle">Auto-refresh: {socketState}. All results are estimates and read-only.</p>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Market</th>
              <th>YES</th>
              <th>NO</th>
              <th>Size</th>
              <th>Avg Entry</th>
              <th>Net Profit</th>
              <th>ROI</th>
              <th>Freshness</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((item) => (
              <tr key={item.id}>
                <td>
                  <Link
                    href={{
                      pathname: `/opportunities/${item.id}`
                    }}
                  >
                    {item.title}
                  </Link>
                  <div className="subtitle">{item.same_market_key}</div>
                </td>
                <td>{item.yes_exchange}</td>
                <td>{item.no_exchange}</td>
                <td className="number">{money(item.max_quantity)}</td>
                <td className="number">
                  {money(item.yes_avg_price)} / {money(item.no_avg_price)}
                </td>
                <td className="number profit">${money(item.net_profit)}</td>
                <td className="number">{percent(item.roi)}</td>
                <td className="number">{Number(item.freshness_seconds).toFixed(1)}s</td>
                <td>{item.confidence}</td>
              </tr>
            ))}
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={9}>No opportunities match the current filters.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </>
  );
}

function PaperTradingPanel({
  analytics,
  trades
}: {
  analytics: OpportunityAnalytics;
  trades: PaperTradeSimulation[];
}) {
  return (
    <section className="detail">
      <p className="subtitle">PAPER TRADING results are simulated only.</p>
      <div className="metrics">
        <Metric label="Paper trades" value={String(analytics.simulated_trade_count ?? 0)} />
        <Metric label="Fill rate" value={percentFromWhole(analytics.simulated_fill_rate ?? "0")} />
        <Metric label="Partial-fill rate" value={percentFromWhole(analytics.partial_fill_rate ?? "0")} />
        <Metric label="Hedge-failure rate" value={percentFromWhole(analytics.hedge_failure_rate ?? "0")} />
        <Metric label="Cumulative paper P&L" value={`$${money(analytics.cumulative_simulated_pnl ?? "0")}`} />
        <Metric label="Median projected ROI" value={percent(analytics.median_projected_roi ?? "0")} />
        <Metric label="Median executable ROI" value={percent(analytics.median_executable_roi ?? "0")} />
      </div>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Label</th>
              <th>Status</th>
              <th>Quantity</th>
              <th>Projected Net</th>
              <th>Realized P&L</th>
              <th>Latency</th>
            </tr>
          </thead>
          <tbody>
            {trades.slice(0, 5).map((trade) => (
              <tr key={trade.id}>
                <td>{trade.label}</td>
                <td>{trade.status.replaceAll("_", " ")}</td>
                <td className="number">
                  {money(trade.filled_quantity)} / {money(trade.requested_quantity)}
                </td>
                <td className="number">${money(trade.projected_net_profit)}</td>
                <td className="number">${money(trade.realized_pnl)}</td>
                <td className="number">{trade.latency_ms}ms</td>
              </tr>
            ))}
            {trades.length === 0 ? (
              <tr>
                <td colSpan={6}>No LIVE-DATA PAPER TRADE records yet.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function AnalyticsPanel({ analytics }: { analytics: OpportunityAnalytics }) {
  const dailyCount = Object.values(analytics.opportunities_detected_per_day).reduce(
    (sum, value) => sum + value,
    0
  );
  return (
    <div className="metrics">
      <Metric label="Detected today UTC" value={String(dailyCount)} />
      <Metric label="Unique today" value={String(analytics.unique_opportunities ?? dailyCount)} />
      <Metric
        label="Median duration"
        value={`${Number(analytics.median_opportunity_duration_seconds).toFixed(2)}s`}
      />
      <Metric label="Median ROI" value={percent(analytics.median_net_roi)} />
      <Metric label="Max theoretical profit" value={`$${money(analytics.maximum_theoretical_profit)}`} />
      <Metric label=">1s" value={percentFromWhole(analytics.percentage_lasting_over_1_seconds)} />
      <Metric label=">3s" value={percentFromWhole(analytics.percentage_lasting_over_3_seconds)} />
      <Metric label=">5s" value={percentFromWhole(analytics.percentage_lasting_over_5_seconds)} />
      <Metric label=">10s" value={percentFromWhole(analytics.percentage_lasting_over_10_seconds)} />
    </div>
  );
}

function ScannerStatusPanel({
  analytics,
  scannerStatus
}: {
  analytics: OpportunityAnalytics;
  scannerStatus: ScannerStatus | null;
}) {
  const dataType = analytics.analytics_data_type?.toUpperCase() ?? "HISTORICAL";
  const hasRecentScan = Boolean(scannerStatus?.last_completed_at ?? analytics.latest_scan_timestamp);
  const statusLabel = scannerStatus?.last_error
    ? "DEGRADED"
    : dataType === "TEST"
      ? "TEST"
      : dataType === "LIVE" && hasRecentScan
        ? "LIVE"
        : "HISTORICAL";
  const latestBookAge = scannerStatus?.order_book_ages_seconds.length
    ? Math.max(
        ...scannerStatus.order_book_ages_seconds.map((book) => Number(book.age_seconds))
      ).toFixed(1)
    : "n/a";
  const diagnostics = scannerStatus?.diagnostics;
  const funnel = diagnostics?.funnel ?? {};
  const rejections = diagnostics?.rejection_counts ?? {};
  const rejectionEntries = Object.entries(rejections)
    .filter(([, count]) => Number(count) > 0)
    .sort((left, right) => Number(right[1]) - Number(left[1]))
    .slice(0, 6);
  const healthyZero =
    !scannerStatus?.last_error &&
    hasRecentScan &&
    (scannerStatus?.opportunities_found ?? analytics.active_opportunities ?? 0) === 0 &&
    diagnostics?.healthy_zero_message;
  return (
    <section className="detail">
      <p className="subtitle">
        {statusLabel} analytics, scoped to {analytics.analytics_scope ?? "current data"}.
      </p>
      {healthyZero ? <p className="subtitle">{diagnostics.healthy_zero_message}</p> : null}
      <div className="metrics">
        <Metric label="Status" value={statusLabel} />
        <Metric label="Last scan" value={formatTime(scannerStatus?.last_completed_at)} />
        <Metric label="Last DB record" value={formatTime(analytics.latest_record_seen_timestamp)} />
        <Metric
          label="Last opportunity"
          value={formatTime(analytics.latest_opportunity_detected_timestamp)}
        />
        <Metric label="Last order book" value={formatTime(scannerStatus?.latest_order_book_update_timestamp)} />
        <Metric label="Max book age" value={latestBookAge === "n/a" ? latestBookAge : `${latestBookAge}s`} />
        <Metric label="Raw detections" value={String(analytics.raw_detections ?? 0)} />
        <Metric label="Duplicate updates" value={String(analytics.duplicate_updates ?? 0)} />
        <Metric label="Historical excluded" value={String(analytics.historical_records_excluded ?? 0)} />
        <Metric label="Simulation excluded" value={String(analytics.simulated_records_excluded ?? 0)} />
        <Metric label="Funnel zero" value={diagnostics?.first_zero_stage ?? "n/a"} />
        <Metric label="Live markets fetched" value={String(funnel.markets_fetched ?? 0)} />
        <Metric label="Usable books" value={String(funnel.usable_order_books_loaded ?? 0)} />
        <Metric label="Active verified pairs" value={String(funnel.verified_pairs_active_on_both_exchanges ?? 0)} />
        <Metric label="Pairs evaluated" value={String(funnel.verified_pairs_with_fresh_books ?? 0)} />
        <Metric label="Raw discrepancies" value={String(funnel.raw_pricing_discrepancies ?? 0)} />
      </div>
      {rejectionEntries.length ? (
        <div className="compact-list">
          {rejectionEntries.map(([reason, count]) => (
            <span key={reason}>
              {reason.replaceAll("_", " ")}: {count}
            </span>
          ))}
        </div>
      ) : null}
      {scannerStatus?.last_error ? <p className="error">{scannerStatus.last_error}</p> : null}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function money(value: string) {
  return Number(value).toFixed(4);
}

function percent(value: string) {
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function percentFromWhole(value: string) {
  return `${Number(value).toFixed(2)}%`;
}

function formatTime(value: string | null | undefined) {
  if (!value) {
    return "n/a";
  }
  return new Date(value).toISOString();
}
