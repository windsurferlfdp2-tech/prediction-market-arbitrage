import { HealthResponse } from "../../lib/types";

export function HealthBar({ health }: { health: HealthResponse }) {
  return (
    <div className="health" aria-label="Platform health indicators">
      <span className="pill">Mode: {health.mode}</span>
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
