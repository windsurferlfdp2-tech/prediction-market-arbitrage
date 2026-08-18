"use client";

import { useMemo, useState } from "react";

import { generateMarketMatches, updateMarketMatchStatus } from "../../lib/api";
import { MarketPairReview, MarketPairStatus } from "../../lib/types";

const STATUSES: MarketPairStatus[] = [
  "pending_review",
  "verified_equivalent",
  "related_not_equivalent",
  "rejected"
];

export function MarketMatchReviewClient({
  initial
}: {
  initial: MarketPairReview[];
}) {
  const [reviews, setReviews] = useState(initial);
  const [statusFilter, setStatusFilter] = useState<MarketPairStatus | "all">("all");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const filtered = useMemo(() => {
    return [...reviews]
      .filter((review) => statusFilter === "all" || review.status === statusFilter)
      .sort((a, b) => Number(b.similarity_score) - Number(a.similarity_score));
  }, [reviews, statusFilter]);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      setReviews(await generateMarketMatches("live"));
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Unknown error";
      setError(`Unable to generate live market match candidates. ${message}`);
    } finally {
      setBusy(false);
    }
  }

  async function updateStatus(review: MarketPairReview, status: MarketPairStatus) {
    setBusy(true);
    setError(null);
    try {
      const updated = await updateMarketMatchStatus(review.id, status);
      setReviews((items) => items.map((item) => (item.id === updated.id ? updated : item)));
    } catch {
      setError("Unable to update market match status.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="filters">
        <span className="pill">LIVE MARKET DATA</span>
        <label>
          Status
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as MarketPairStatus | "all")}
          >
            <option value="all">All</option>
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {statusLabel(status)}
              </option>
            ))}
          </select>
        </label>
        <button className="actionButton" disabled={busy} onClick={generate} type="button">
          Generate candidates
        </button>
      </div>
      {error ? <p className="subtitle warning">{error}</p> : null}
      <div className="reviewList">
        {filtered.map((review) => (
          <article className="reviewCard" key={review.id}>
            <div className="reviewHeader">
              <div>
                <div className="subtitle">{review.id}</div>
                <h2>{review.polymarket_title}</h2>
                <h2>{review.kalshi_title}</h2>
              </div>
              <label>
                Review status
                <select
                  disabled={busy}
                  value={review.status}
                  onChange={(event) =>
                    updateStatus(review, event.target.value as MarketPairStatus)
                  }
                >
                  {STATUSES.map((status) => (
                    <option key={status} value={status}>
                      {statusLabel(status)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="metrics">
              <Metric label="Similarity" value={`${(Number(review.similarity_score) * 100).toFixed(1)}%`} />
              <Metric label="Polymarket close" value={review.polymarket_close_date ?? "Unknown"} />
              <Metric label="Kalshi close" value={review.kalshi_close_date ?? "Unknown"} />
              <Metric label="Updated" value={new Date(review.updated_at).toLocaleString()} />
            </div>
            <div className="reviewGrid">
              <MarketSide
                criteria={review.polymarket_resolution_criteria}
                entities={review.polymarket_entities}
                marketId={review.polymarket_market_id}
                numbers={review.polymarket_numbers}
                settlementDate={review.polymarket_settlement_date}
                sources={review.polymarket_resolution_sources}
                title="Polymarket"
              />
              <MarketSide
                criteria={review.kalshi_resolution_criteria}
                entities={review.kalshi_entities}
                marketId={review.kalshi_market_id}
                numbers={review.kalshi_numbers}
                settlementDate={review.kalshi_settlement_date}
                sources={review.kalshi_resolution_sources}
                title="Kalshi"
              />
            </div>
            <section>
              <h3>Detected mismatches</h3>
              {review.mismatches.length ? (
                <ul className="plainList">
                  {review.mismatches.map((mismatch) => (
                    <li key={mismatch}>{mismatch}</li>
                  ))}
                </ul>
              ) : (
                <p className="subtitle">No structured mismatches detected.</p>
              )}
            </section>
          </article>
        ))}
        {filtered.length === 0 ? (
          <div className="tableWrap emptyState">No market match reviews found.</div>
        ) : null}
      </div>
    </>
  );
}

function statusLabel(status: MarketPairStatus) {
  return status.replaceAll("_", " ");
}

function MarketSide({
  criteria,
  entities,
  marketId,
  numbers,
  settlementDate,
  sources,
  title
}: {
  criteria: string;
  entities: string[];
  marketId: string;
  numbers: string[];
  settlementDate: string | null;
  sources: string[];
  title: string;
}) {
  return (
    <section>
      <h3>{title}</h3>
      <dl className="reviewFields">
        <dt>Market ID</dt>
        <dd>{marketId}</dd>
        <dt>Full resolution criteria</dt>
        <dd>{criteria}</dd>
        <dt>Settlement date</dt>
        <dd>{settlementDate ?? "Unknown"}</dd>
        <dt>Resolution sources</dt>
        <dd>{sources.length ? sources.join(", ") : "Unknown"}</dd>
        <dt>Extracted entities</dt>
        <dd>{entities.length ? entities.join(", ") : "None"}</dd>
        <dt>Extracted numbers and thresholds</dt>
        <dd>{numbers.length ? numbers.join(", ") : "None"}</dd>
      </dl>
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
