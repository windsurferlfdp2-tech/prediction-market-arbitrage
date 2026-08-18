import Link from "next/link";

import { getOpportunity } from "../../../lib/api";

export default async function OpportunityDetail({
  params
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const opportunity = await getOpportunity(id, "live").catch(() => null);

  if (!opportunity) {
    return (
      <main className="shell">
        <header className="topbar">
          <div>
            <h1 className="title">Opportunity unavailable</h1>
            <p className="subtitle">Backend API is unavailable or this estimate no longer exists.</p>
          </div>
          <Link className="pill" href="/">
            Back
          </Link>
        </header>
      </main>
    );
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <h1 className="title">{opportunity.title}</h1>
          <p className="subtitle">{opportunity.read_only_label}</p>
        </div>
        <Link className="pill" href="/">
          Back
        </Link>
      </header>
      <section className="content detail">
        <div className="metrics">
          <Metric label="Net profit" value={`$${money(opportunity.net_profit)}`} tone="profit" />
          <Metric label="ROI" value={percent(opportunity.roi)} />
          <Metric label="Executable size" value={money(opportunity.max_quantity)} />
          <Metric label="Freshness" value={`${Number(opportunity.freshness_seconds).toFixed(1)}s`} />
        </div>
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Exchange</th>
                <th>Market ID</th>
                <th>Outcome</th>
                <th>Price</th>
                <th>Quantity</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {opportunity.used_levels.map((level, index) => (
                <tr key={`${level.exchange}-${level.market_id}-${level.side}-${index}`}>
                  <td>{level.exchange}</td>
                  <td>{level.market_id}</td>
                  <td>{level.side.toUpperCase()}</td>
                  <td className="number">{money(level.price)}</td>
                  <td className="number">{money(level.quantity)}</td>
                  <td>{level.source_side}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="subtitle warning">
          Gross profit, net profit, fees, slippage, ROI, and executable size are estimates based on
          the captured order-book snapshot.
        </p>
      </section>
    </main>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
    </div>
  );
}

function money(value: string) {
  return Number(value).toFixed(4);
}

function percent(value: string) {
  return `${(Number(value) * 100).toFixed(2)}%`;
}
