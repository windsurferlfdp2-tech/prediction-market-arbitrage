import { HealthResponse } from "../../lib/types";

export function HealthBar({ health }: { health: HealthResponse }) {
  return (
    <div className="health" aria-label="Platform health indicators">
      <span className="pill">Mode: {health.mode}</span>
      {health.test_mode ? <span className="pill">TEST DATA</span> : null}
      {health.is_live_data ? <span className="pill">LIVE MARKET DATA</span> : null}
      <span className="pill">Read-only: {health.read_only ? "yes" : "no"}</span>
      {health.exchanges.map((exchange) => (
        <span className="pill" key={exchange.exchange}>
          <span className={`dot ${exchange.ok ? "ok" : ""}`} />
          {exchange.exchange}: {exchange.message}
        </span>
      ))}
    </div>
  );
}
