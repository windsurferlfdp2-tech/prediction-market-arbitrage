"use client";

import { useState } from "react";

import {
  approveModelForPaper,
  generateModelOpportunities,
  generatePredictions,
  getModelAnalytics,
  getModelOpportunities,
  getModelPaperTrades,
  getModelReadiness,
  getModels,
  getPredictions,
  retireModel,
  runModelPaperTrades
} from "../../lib/api";
import {
  ModelAnalytics,
  ModelOpportunity,
  ModelPaperTrade,
  ModelReadiness,
  PredictionModelSummary,
  PredictionResult
} from "../../lib/types";
import {
  canApproveModel,
  canRetireModel,
  dateOnly,
  modelStatusLabel,
  shortId
} from "../../lib/modelRegistryView";

export function ModelDashboardClient({
  initialModels,
  initialPredictions,
  initialOpportunities,
  initialTrades,
  initialAnalytics,
  initialReadiness
}: {
  initialModels: PredictionModelSummary[];
  initialPredictions: PredictionResult[];
  initialOpportunities: ModelOpportunity[];
  initialTrades: ModelPaperTrade[];
  initialAnalytics: ModelAnalytics | null;
  initialReadiness: ModelReadiness | null;
}) {
  const [models, setModels] = useState(initialModels);
  const [predictions, setPredictions] = useState(initialPredictions);
  const [opportunities, setOpportunities] = useState(initialOpportunities);
  const [trades, setTrades] = useState(initialTrades);
  const [analytics, setAnalytics] = useState(initialAnalytics);
  const [readiness, setReadiness] = useState(initialReadiness);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function refresh() {
    const [
      nextModels,
      nextPredictions,
      nextOpportunities,
      nextTrades,
      nextAnalytics,
      nextReadiness
    ] =
      await Promise.all([
        getModels(),
        getPredictions(),
        getModelOpportunities(),
        getModelPaperTrades(),
        getModelAnalytics().catch(() => null),
        getModelReadiness().catch(() => null)
      ]);
    setModels(nextModels);
    setPredictions(nextPredictions);
    setOpportunities(nextOpportunities);
    setTrades(nextTrades);
    setAnalytics(nextAnalytics);
    setReadiness(nextReadiness);
  }

  async function runStep(step: "predict" | "opportunities" | "paper") {
    setBusy(true);
    setMessage("");
    try {
      if (step === "predict") {
        await generatePredictions("live");
      }
      if (step === "opportunities") {
        await generateModelOpportunities("live");
      }
      if (step === "paper") {
        await runModelPaperTrades("live");
      }
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Model action failed");
    } finally {
      setBusy(false);
    }
  }

  async function setModelStatus(id: string, action: "approve" | "retire") {
    setBusy(true);
    setMessage("");
    try {
      if (action === "approve") {
        await approveModelForPaper(id);
      } else {
        await retireModel(id);
      }
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Model status update failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="detail">
      <div className="filters">
        <span className="pill">LIVE MARKET DATA</span>
        <button className="actionButton" disabled={busy} onClick={() => runStep("predict")}>
          Generate predictions
        </button>
        <button className="actionButton" disabled={busy} onClick={() => runStep("opportunities")}>
          Detect model EV
        </button>
        <button
          className="actionButton"
          disabled={busy || Boolean(analytics?.model_paper_trading_paused)}
          onClick={() => runStep("paper")}
        >
          Run paper trades
        </button>
      </div>
      {analytics?.model_paper_trading_paused ? (
        <div className="warningPanel">
          <strong>MODEL TRADING PAUSED</strong>
          <span>{analytics.model_paper_trading_freeze_reason}</span>
          <span>
            Freeze enabled: {analytics.model_paper_trading_freeze_enabled_at ?? "unknown"}
          </span>
        </div>
      ) : null}
      {message ? <p className="subtitle warning">{message}</p> : null}
      {analytics ? <ModelAnalyticsPanel analytics={analytics} /> : null}
      {readiness ? <DatasetReadinessPanel readiness={readiness} /> : null}
      <ModelRegistry models={models} busy={busy} onStatus={setModelStatus} />
      <PredictionTable predictions={predictions} />
      <ModelOpportunityTable opportunities={opportunities} />
      <ModelTradeTable trades={trades} />
    </section>
  );
}

function DatasetReadinessPanel({ readiness }: { readiness: ModelReadiness }) {
  const baseline = readiness.market_baseline;
  const checks = readiness.approval_requirements?.checks ?? {};
  return (
    <section className="detail">
      <h2>Dataset Readiness</h2>
      <div className="metrics">
        <Metric label="Rows" value={String(readiness.total_prediction_rows ?? 0)} />
        <Metric label="Unique markets" value={String(readiness.unique_markets ?? 0)} />
        <Metric
          label="Resolved markets"
          value={String(readiness.unique_resolved_markets ?? 0)}
        />
        <Metric
          label="YES / NO"
          value={`${readiness.outcome_balance?.yes ?? 0} / ${readiness.outcome_balance?.no ?? 0}`}
        />
        <Metric
          label="Oldest"
          value={dateOnly(readiness.oldest_prediction_timestamp ?? null)}
        />
        <Metric
          label="Newest"
          value={dateOnly(readiness.newest_prediction_timestamp ?? null)}
        />
        <Metric
          label="Snapshots / market"
          value={`${readiness.snapshots_per_market?.median ?? 0} median`}
        />
        <Metric
          label="Baseline Brier"
          value={baseline ? baseline.brier_score.toFixed(4) : "n/a"}
        />
        <Metric
          label="Baseline log loss"
          value={baseline?.log_loss == null ? "n/a" : baseline.log_loss.toFixed(4)}
        />
        <Metric
          label="Baseline calibration"
          value={baseline ? baseline.calibration_error.toFixed(4) : "n/a"}
        />
      </div>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Approval requirement</th>
              <th>Required</th>
              <th>Actual</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(checks).map(([name, check]) => (
              <tr key={name}>
                <td>{name.replaceAll("_", " ")}</td>
                <td>{String(check.required)}</td>
                <td>{String(check.actual)}</td>
                <td>{check.passed ? "passed" : "failed"}</td>
              </tr>
            ))}
            {Object.keys(checks).length === 0 ? (
              <tr>
                <td colSpan={4}>No dataset readiness information available.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ModelAnalyticsPanel({ analytics }: { analytics: ModelAnalytics }) {
  return (
    <div className="metrics">
      <Metric label="Predictions" value={String(analytics.prediction_count)} />
      <Metric label="Model opportunities" value={String(analytics.model_opportunity_count)} />
      <Metric label="MODEL PAPER TRADES" value={String(analytics.model_paper_trade_count)} />
      <Metric
        label="Resolved trades"
        value={String(analytics.resolved_model_paper_trade_count ?? 0)}
      />
      <Metric label="Open trades" value={String(analytics.open_model_paper_trade_count ?? 0)} />
      <Metric label="Paper P&L" value={`$${money(analytics.cumulative_model_paper_pnl)}`} />
      <Metric label="Return on capital" value={percent(analytics.return_on_deployed_paper_capital)} />
      <Metric label="Resolved win rate" value={percent(analytics.resolved_win_rate ?? "0")} />
      <Metric label="Average entry edge" value={`$${money(analytics.average_edge_at_entry)}`} />
      <Metric label="Max drawdown" value={`$${money(analytics.maximum_drawdown)}`} />
    </div>
  );
}

function ModelRegistry({
  models,
  busy,
  onStatus
}: {
  models: PredictionModelSummary[];
  busy: boolean;
  onStatus: (id: string, action: "approve" | "retire") => void;
}) {
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Model</th>
            <th>Status</th>
            <th>Training window</th>
            <th>Dataset</th>
            <th>Samples</th>
            <th>Validation</th>
            <th>Scores</th>
            <th>Calibration</th>
            <th>Fingerprint</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {models.map((model) => {
            const canApprove = canApproveModel(model.status);
            const canRetire = canRetireModel(model.status);
            return (
              <tr key={model.id}>
                <td>
                  {model.name}
                  <div className="subtitle">{model.version}</div>
                </td>
                <td>{modelStatusLabel(model.status)}</td>
                <td>
                  {dateOnly(model.training_start)} to {dateOnly(model.training_end)}
                </td>
                <td>
                  {shortId(model.dataset_version)}
                  <div className="subtitle">resolved {model.resolved_market_count ?? "n/a"}</div>
                </td>
                <td className="number">{model.training_sample_count}</td>
                <td className="number">{model.validation_sample_count ?? "n/a"}</td>
                <td>
                  <div>baseline {metric(model.baseline_score)}</div>
                  <div>model {metric(model.model_score)}</div>
                </td>
                <td>{model.calibration_method}</td>
                <td>
                  {shortId(model.artifact_hash ?? model.training_fingerprint)}
                  <div className="subtitle">{shortId(model.training_fingerprint)}</div>
                </td>
                <td>
                  {canApprove ? (
                    <button disabled={busy} onClick={() => onStatus(model.id, "approve")}>
                      Approve paper
                    </button>
                  ) : null}
                  {canRetire ? (
                    <button disabled={busy} onClick={() => onStatus(model.id, "retire")}>
                      Retire
                    </button>
                  ) : null}
                </td>
              </tr>
            );
          })}
          {models.length === 0 ? (
            <tr>
              <td colSpan={10}>No models registered.</td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

function PredictionTable({ predictions }: { predictions: PredictionResult[] }) {
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Prediction</th>
            <th>Market</th>
            <th>Fair</th>
            <th>Market</th>
            <th>Confidence</th>
            <th>Uncertainty</th>
            <th>No-trade reasons</th>
          </tr>
        </thead>
        <tbody>
          {predictions.map((prediction) => (
            <tr key={prediction.id}>
              <td>{prediction.label}</td>
              <td>
                {prediction.market_title}
                <div className="subtitle">
                  {prediction.exchange} / {prediction.category}
                </div>
              </td>
              <td className="number">{percent(prediction.fair_probability)}</td>
              <td className="number">{percent(prediction.market_probability)}</td>
              <td className="number">{percent(prediction.confidence_score)}</td>
              <td className="number">{percent(prediction.uncertainty_score)}</td>
              <td>{prediction.no_trade_reasons.join(", ") || "eligible"}</td>
            </tr>
          ))}
          {predictions.length === 0 ? (
            <tr>
              <td colSpan={7}>No model predictions recorded.</td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

function ModelOpportunityTable({ opportunities }: { opportunities: ModelOpportunity[] }) {
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Opportunity</th>
            <th>Direction</th>
            <th>Entry</th>
            <th>Quantity</th>
            <th>Net EV</th>
            <th>Expected ROI</th>
            <th>Freshness</th>
            <th>Execution</th>
          </tr>
        </thead>
        <tbody>
          {opportunities.map((opportunity) => (
            <tr key={opportunity.id}>
              <td>
                {opportunity.label}
                <div className="subtitle">{opportunity.market_title}</div>
              </td>
              <td>{opportunity.direction.toUpperCase()}</td>
              <td className="number">{money(opportunity.weighted_average_entry_price)}</td>
              <td className="number">{money(opportunity.executable_quantity)}</td>
              <td className="number profit">${money(opportunity.net_expected_value)}</td>
              <td className="number">{percent(opportunity.expected_roi)}</td>
              <td className="number">{Number(opportunity.book_freshness_seconds).toFixed(1)}s</td>
              <td>
                {opportunity.paper_execution_status ?? "NOT ELIGIBLE FOR PAPER EXECUTION"}
                {opportunity.paper_execution_reason ? (
                  <div className="subtitle">{opportunity.paper_execution_reason}</div>
                ) : null}
              </td>
            </tr>
          ))}
          {opportunities.length === 0 ? (
            <tr>
              <td colSpan={8}>No model EV opportunities recorded.</td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

function ModelTradeTable({ trades }: { trades: ModelPaperTrade[] }) {
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Trade</th>
            <th>Status</th>
            <th>Direction</th>
            <th>Filled</th>
            <th>Entry</th>
            <th>Position</th>
            <th>P&L</th>
            <th>Resolution</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => (
            <tr key={trade.id}>
              <td>
                {trade.label}
                <div className="subtitle">{trade.market_id}</div>
              </td>
              <td>
                {trade.status.replaceAll("_", " ")}
                {trade.exit_reason ? <div className="subtitle">{trade.exit_reason}</div> : null}
              </td>
              <td>{trade.direction.toUpperCase()}</td>
              <td className="number">
                {money(trade.filled_quantity)} / {money(trade.requested_quantity)}
              </td>
              <td className="number">{money(trade.entry_price)}</td>
              <td className="number">${money(trade.position_size)}</td>
              <td className="number">
                {trade.status === "closed"
                  ? `$${money(trade.realized_pnl)} realized`
                  : `$${money(trade.mark_to_market_pnl)} mark`}
              </td>
              <td>
                {trade.resolved_outcome ? `Resolved ${trade.resolved_outcome.toUpperCase()}` : "Pending"}
                <div className="subtitle">
                  {trade.resolution_timestamp
                    ? new Date(trade.resolution_timestamp).toISOString()
                    : "No settlement timestamp"}
                </div>
              </td>
            </tr>
          ))}
          {trades.length === 0 ? (
            <tr>
              <td colSpan={8}>No MODEL PAPER TRADE records.</td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
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

function metric(value: unknown) {
  if (typeof value === "number") {
    return value.toFixed(4);
  }
  if (typeof value === "string" && value !== "") {
    return Number(value).toFixed(4);
  }
  return "n/a";
}
