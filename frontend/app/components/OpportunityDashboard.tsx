"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Opportunity } from "../../lib/types";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/opportunities";

export function OpportunityDashboard({ initial }: { initial: Opportunity[] }) {
  const [items, setItems] = useState(initial);
  const [exchange, setExchange] = useState("all");
  const [minRoi, setMinRoi] = useState("0");
  const [minLiquidity, setMinLiquidity] = useState("0");
  const [maxFreshness, setMaxFreshness] = useState("30");
  const [socketState, setSocketState] = useState("connecting");

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    ws.onopen = () => setSocketState("live");
    ws.onclose = () => setSocketState("closed");
    ws.onerror = () => setSocketState("error");
    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data) as Opportunity[];
      setItems(payload);
    };
    return () => ws.close();
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
                  <Link href={`/opportunities/${item.id}`}>{item.title}</Link>
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

function money(value: string) {
  return Number(value).toFixed(4);
}

function percent(value: string) {
  return `${(Number(value) * 100).toFixed(2)}%`;
}
