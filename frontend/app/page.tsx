import Link from "next/link";

import { HealthBar } from "./components/HealthBar";
import { OpportunityDashboard } from "./components/OpportunityDashboard";
import {
  ApiConfigurationError,
  getHealth,
  getOpportunities,
  getOpportunityAnalytics
} from "../lib/api";
import { HealthResponse } from "../lib/types";

export default async function Home() {
  const healthResult = await getHealth("live")
    .then((health) => ({ health, configurationError: null as string | null }))
    .catch((caught: unknown) => ({
      health: {
        ok: false,
        mode: "unavailable",
        read_only: true,
        exchanges: []
      } satisfies HealthResponse,
      configurationError:
        caught instanceof ApiConfigurationError ? caught.message : null
    }));

  const [opportunities, analytics] = await Promise.all([
    getOpportunities("live").catch(() => []),
    getOpportunityAnalytics("live").catch(() => null)
  ]);

  const { health, configurationError } = healthResult;

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <h1 className="title">Prediction Market Arbitrage Scanner</h1>
          <p className="subtitle">Estimated same-market binary arbitrage. Read-only.</p>
        </div>
        <div className="health">
          <Link className="pill" href="/models">
            Models
          </Link>
          <Link className="pill" href="/market-matches">
            Market matches
          </Link>
          <HealthBar health={health} />
        </div>
      </header>
      <section className="content">
        {configurationError ? (
          <p className="subtitle warning">{configurationError}</p>
        ) : !health.ok ? (
          <p className="subtitle warning">
            Backend API is unavailable. No estimates are being calculated right now.
          </p>
        ) : null}
        <OpportunityDashboard
          initial={opportunities}
          initialAnalytics={analytics}
        />
      </section>
    </main>
  );
}
