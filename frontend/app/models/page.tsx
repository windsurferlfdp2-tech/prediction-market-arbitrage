import Link from "next/link";

import {
  getModelAnalytics,
  getModelOpportunities,
  getModelPaperTrades,
  getModelReadiness,
  getModels,
  getPredictions
} from "../../lib/api";
import { ModelDashboardClient } from "./ModelDashboardClient";

export default async function ModelsPage() {
  const [models, predictions, opportunities, trades, analytics, readiness] = await Promise.all([
    getModels().catch(() => []),
    getPredictions().catch(() => []),
    getModelOpportunities().catch(() => []),
    getModelPaperTrades().catch(() => []),
    getModelAnalytics().catch(() => null),
    getModelReadiness().catch(() => null)
  ]);

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <h1 className="title">Prediction Models</h1>
          <p className="subtitle">
            Calibrated positive expected-value estimates. Paper trading only.
          </p>
        </div>
        <div className="health">
          <Link className="pill" href="/">
            Arbitrage
          </Link>
          <Link className="pill" href="/market-matches">
            Market matches
          </Link>
        </div>
      </header>
      <section className="content">
        <ModelDashboardClient
          initialModels={models}
          initialPredictions={predictions}
          initialOpportunities={opportunities}
          initialTrades={trades}
          initialAnalytics={analytics}
          initialReadiness={readiness}
        />
      </section>
    </main>
  );
}
