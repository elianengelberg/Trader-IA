/**
 * The trade-or-not page.
 *
 * Every other page shows what the system did. This one shows the arithmetic behind why
 * it mostly didn't — which is the more useful number, because a system that trades rarely
 * and a system that is broken look identical until you can see the reason.
 *
 * The layout puts the cost breakdown next to the edge on purpose. A 23 bps edge sounds
 * like a strategy right up until you see the 22 bps of costs beside it.
 */
import { useCallback, useEffect, useState } from "react";
import { api, type Economics } from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { useStreamEvent } from "../lib/stream";
import { Bar, Card, Empty, Pill, SimulationFootnote, Stat } from "../components/ui";
import { bpsUsd, medianNotional, money } from "../lib/format";

const COST_LABELS: Record<string, string> = {
  fee_bps: "Fees",
  spread_bps: "Spread",
  slippage_bps: "Slippage",
  latency_bps: "Latency",
  impact_bps: "Impact",
};

export function StrategyView({ subscribe }: { subscribe: Subscribe }) {
  const [data, setData] = useState<Economics | null>(null);

  const load = useCallback(() => {
    api.economics().then(setData).catch(() => undefined);
  }, []);

  useEffect(load, [load]);
  useStreamEvent(subscribe, "evaluation.created", load);
  useStreamEvent(subscribe, "trade.closed", load);

  if (!data?.available) {
    return (
      <>
        <h1>Strategy</h1>
        <Card>
          <Empty message={data?.reason ?? "Loading…"} />
        </Card>
      </>
    );
  }

  const ev = data.expected_value!;
  const fees = data.fees!;
  const budget = data.budget!;
  const closed = data.closed_trades!;
  const latest = ev.latest;
  // The engine reasons in basis points because they compare trades of any size; people
  // reason in dollars. Everything below converts at the typical trade size of the recent
  // closed round trips — each table row uses its own trade's actual size where recorded.
  const notional = medianNotional(closed.recent);
  const tradeUsd = (
    bps: number,
    trade?: { entry_price?: number; quantity?: number },
    opts?: { signed?: boolean },
  ) => {
    const own = (trade?.entry_price ?? 0) * (trade?.quantity ?? 0);
    return bpsUsd(bps, own > 0 ? own : notional, opts);
  };
  const costs = latest?.expected_value.costs;
  const components = costs
    ? Object.entries(COST_LABELS).map(([key, label]) => ({
        label,
        value: costs[key as keyof typeof costs] as number,
      }))
    : [];
  const maxComponent = Math.max(...components.map((c) => c.value), 0.0001);

  return (
    <>
      <h1>Strategy</h1>
      <p className="section-note">
        A signal is not a trade. After the risk engine approves one, two more gates run: the
        risk budget decides how much may be risked right now, and the expected-value engine
        subtracts the round-trip cost from a <em>measured</em> edge. The edge comes from
        closed trades bucketed by regime, direction and confidence — never from the
        confidence score itself, which is a number on an arbitrary scale until something has
        demonstrated what it means.
      </p>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="card">
          <Stat
            label="Expected-value engine"
            value={<Pill value={ev.enforcing ? "enforcing" : "observing"} tone={ev.enforcing ? "ok" : "warn"} />}
            sub={`${ev.evaluations} evaluations`}
          />
        </div>
        <div className="card">
          <Stat
            label="Would refuse"
            value={ev.would_reject}
            tone={ev.would_reject > 0 ? "warn" : "flat"}
            sub={`${ev.no_evidence} for lack of evidence`}
          />
        </div>
        <div className="card">
          <Stat
            label="Round-trip fees"
            value={bpsUsd(fees.round_trip_taker_bps, notional, { signed: false })}
            tone={fees.requires_verification ? "warn" : "flat"}
            sub={fees.verified_at_source ? "per trade, read from account" : "per trade — configured, unverified"}
          />
        </div>
        <div className="card">
          <Stat
            label="Min profit demanded"
            value={bpsUsd(ev.threshold_bps, notional, { signed: false })}
            sub={`per trade after costs · costs capped at ${(ev.max_cost_ratio * 100).toFixed(0)}% of edge`}
          />
        </div>
      </div>

      {notional != null && (
        <p className="footnote" style={{ marginTop: -6, marginBottom: 16 }}>
          Dollar figures are per trade, at the typical trade size of ≈${money(notional, 0)}{" "}
          (simulated money). Rows in the trade table use each trade&apos;s actual size.
        </p>
      )}

      {!ev.enforcing && (
        <div className="card" style={{ marginBottom: 16, borderLeft: "3px solid var(--warn, #c90)" }}>
          <strong>Observing, not enforcing.</strong>
          <p style={{ margin: "8px 0 0", color: "var(--muted)" }}>{ev.mode_explanation}</p>
        </div>
      )}

      <div className="grid cols-2">
        <Card title="The most recent decision">
          {!latest ? (
            <Empty message="No signal has reached the pricing stage yet." />
          ) : (
            <>
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
                <Pill value={latest.direction} />
                <Pill
                  value={latest.tradeable ? "trade" : "no trade"}
                  tone={latest.tradeable ? "ok" : ""}
                />
              </div>
              <div className="grid cols-3" style={{ marginBottom: 12 }}>
                <Stat
                  label="Expected gross"
                  value={bpsUsd(latest.expected_value.gross_edge_bps, notional)}
                  sub={
                    latest.expected_value.edge
                      ? `from ${latest.expected_value.edge.samples} past trades`
                      : "no measured edge"
                  }
                />
                <Stat
                  label="Round-trip cost"
                  value={bpsUsd(latest.expected_value.costs.total_bps, notional, { signed: false })}
                  sub={`${latest.expected_value.costs.dominant} dominant`}
                />
                <Stat
                  label="Expected net profit"
                  value={bpsUsd(latest.expected_value.net_edge_bps, notional)}
                  tone={latest.expected_value.net_edge_bps >= ev.threshold_bps ? "pos" : "neg"}
                  sub={`must clear ${bpsUsd(ev.threshold_bps, notional, { signed: false })}`}
                />
              </div>
              <p style={{ margin: 0, color: "var(--muted)" }}>
                {latest.expected_value.explanation}
              </p>
            </>
          )}
        </Card>

        <Card title="Where the cost goes">
          {components.length === 0 ? (
            <Empty message="Nothing priced yet." />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {components.map((component) => (
                <div key={component.label}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <span>{component.label}</span>
                    <span className="mono">{bpsUsd(component.value, notional, { signed: false })}</span>
                  </div>
                  <Bar value={component.value} max={maxComponent} />
                </div>
              ))}
              <p className="footnote" style={{ marginTop: 4 }}>
                Both legs are priced. A one-way cost estimate flatters every strategy that
                has to get out again.
              </p>
            </div>
          )}
        </Card>
      </div>

      <div className="grid cols-2" style={{ marginTop: 16 }}>
        <Card title="Evidence collected">
          <div className="grid cols-3" style={{ marginBottom: 12 }}>
            <Stat label="Closed round trips" value={closed.count} />
            <Stat
              label="Mean net per trade"
              value={closed.mean_net_bps === null ? "—" : bpsUsd(closed.mean_net_bps, notional)}
              tone={
                closed.mean_net_bps === null ? "flat" : closed.mean_net_bps > 0 ? "pos" : "neg"
              }
            />
            <Stat label="Wins / losses" value={`${closed.wins} / ${closed.losses}`} />
          </div>
          {Object.keys(ev.coverage).length === 0 ? (
            <Empty message={`No bucket has any samples yet. ${ev.min_samples} are needed before an edge can be estimated at all.`} />
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Bucket (regime | direction | confidence)</th>
                  <th style={{ textAlign: "right" }}>Samples</th>
                  <th style={{ textAlign: "right" }}>Usable</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(ev.coverage)
                  .sort((a, b) => b[1] - a[1])
                  .map(([bucket, count]) => (
                    <tr key={bucket}>
                      <td className="mono">{bucket}</td>
                      <td style={{ textAlign: "right" }}>{count}</td>
                      <td style={{ textAlign: "right" }}>
                        {count >= ev.min_samples ? (
                          <Pill value="yes" tone="ok" />
                        ) : (
                          <span className="mono">{count}/{ev.min_samples}</span>
                        )}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="Risk budget right now">
          <div className="grid cols-2" style={{ marginBottom: 12 }}>
            <Stat
              label="Drawdown state"
              value={<Pill value={budget.state} tone={budget.state === "normal" ? "ok" : budget.state === "defensive" ? "warn" : "bad"} />}
              sub={`profile: ${budget.profile}`}
            />
            <Stat
              label="Risk on next trade"
              value={`${(budget.risk_pct * 100).toFixed(3)}%`}
              sub={budget.allows_new_trades ? budget.binding_constraint : "no new trades"}
            />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {[
              ["Drawdown", budget.drawdown_multiplier],
              ["Volatility", budget.volatility_multiplier],
              ["Loss streak", budget.streak_multiplier],
            ].map(([label, value]) => (
              <div key={label as string}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <span>{label}</span>
                  <span className="mono">×{(value as number).toFixed(3)}</span>
                </div>
                <Bar value={value as number} max={1} tone={(value as number) < 1 ? "warn" : ""} />
              </div>
            ))}
          </div>
          <p className="footnote" style={{ marginTop: 10 }}>
            Every multiplier is capped at 1.0 and none of them ever rises because the
            account is losing. There is no code path that increases risk after a loss —
            that shape is martingale, and it is asserted against as a property test.
          </p>
        </Card>
      </div>

      {closed.recent.length > 0 && (
        <Card title="Closed round trips" >
          <table className="table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Direction</th>
                <th>Regime</th>
                <th style={{ textAlign: "right" }}>Gross</th>
                <th style={{ textAlign: "right" }}>Fees</th>
                <th style={{ textAlign: "right" }}>Net</th>
                <th style={{ textAlign: "right" }}>Expected</th>
              </tr>
            </thead>
            <tbody>
              {closed.recent.map((trade, index) => (
                <tr key={`${trade.closed_at}-${index}`}>
                  <td>{trade.symbol}</td>
                  <td><Pill value={trade.direction} /></td>
                  <td className="mono">{trade.regime}</td>
                  <td style={{ textAlign: "right" }} className="mono">
                    {tradeUsd(trade.gross_bps, trade)}
                  </td>
                  <td style={{ textAlign: "right" }} className="mono">
                    −{tradeUsd(trade.fees_bps, trade, { signed: false })}
                  </td>
                  <td
                    style={{ textAlign: "right" }}
                    className={`mono ${trade.net_bps > 0 ? "pos" : "neg"}`}
                  >
                    {tradeUsd(trade.net_bps, trade)}
                  </td>
                  <td style={{ textAlign: "right" }} className="mono">
                    {tradeUsd(trade.expected_net_bps, trade)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="footnote">
            Realised returns are recorded net of the fees actually paid on both legs.
            Recording them gross would double-count, because the expected-value engine
            subtracts costs again downstream — and every estimate would come out a full
            round trip too optimistic.
          </p>
        </Card>
      )}

      <SimulationFootnote />
    </>
  );
}
