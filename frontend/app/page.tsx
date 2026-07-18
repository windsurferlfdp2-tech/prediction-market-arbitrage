import { HealthBar } from "./components/HealthBar";
import { OpportunityDashboard } from "./components/OpportunityDashboard";
import { getHealth, getOpportunities } from "../lib/api";

export default async function Home() {
  const [health, opportunities] = await Promise.all([getHealth(), getOpportunities()]);

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <h1 className="title">Prediction Market Arbitrage Scanner</h1>
          <p className="subtitle">Estimated same-market binary arbitrage. Read-only.</p>
        </div>
        <HealthBar health={health} />
      </header>
      <section className="content">
        <OpportunityDashboard initial={opportunities} />
      </section>
    </main>
  );
}
