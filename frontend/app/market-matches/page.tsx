import Link from "next/link";

import { getMarketMatches } from "../../lib/api";
import { MarketMatchReviewClient } from "./MarketMatchReviewClient";

export default async function MarketMatchesPage() {
  const reviews = await getMarketMatches().catch(() => []);

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <h1 className="title">Market Match Review</h1>
          <p className="subtitle">Cross-platform pair candidates. Manual approval required.</p>
        </div>
        <div className="health">
          <Link className="pill" href="/">
            Scanner
          </Link>
        </div>
      </header>
      <section className="content">
        <MarketMatchReviewClient initial={reviews} />
      </section>
    </main>
  );
}
