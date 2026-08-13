import { useCallback, useEffect, useState } from "react";
import { api, type Decision, type Fill, type Position, type RuntimeSnapshot } from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { useStreamEvent } from "../lib/stream";
import { EquityChart } from "../components/charts";
import { Card, Empty, MoneyStat, PctStat, Pill, SimulationFootnote, Stat } from "../components/ui";
import { clock, money, qty, signedMoney } from "../lib/format";

type EquityPoint = { at: string; equity: number; drawdown_pct: number };

export function Dashboard({
  runtime,
  subscribe,
}: {
  runtime: RuntimeSnapshot | null;
  subscribe: Subscribe;
}) {
  const [curve, setCurve] = useState<EquityPoint[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [fills, setFills] = useState<Fill[]>([]);

  const load = useCallback(() => {
    api.portfolio().then((p) => {
      setCurve(p.equity_curve ?? []);
      setPositions(p.positions ?? []);
    }).catch(() => undefined);
    api.decisions(12, true).then(setDecisions).catch(() => undefined);
    api.fills(10).then(setFills).catch(() => undefined);
  }, []);

  useEffect(load, [load, runtime?.run_id]);

  // Appending on the stream rather than refetching: the curve grows a point at a time and
  // a refetch per bar would move more data than the whole page is worth.
  useStreamEvent(subscribe, "portfolio.updated", (data) => {
    const point = data as EquityPoint;
    setCurve((previous) => [...previous.slice(-1400), point]);
  });
  useStreamEvent(subscribe, "order.fill_simulated", () => {
    api.fills(10).then(setFills).catch(() => undefined);
    api.positions().then(setPositions).catch(() => undefined);
  });
  useStreamEvent(subscribe, "decision.created", (data) => {
    const decision = data as Decision;
    if (decision.direction === "long" || decision.direction === "short") {
      setDecisions((previous) => [decision, ...previous].slice(0, 12));
    }
  });

  const capital = runtime?.capital;
  const counters = runtime?.counters ?? {};

  if (!runtime?.run_id) {
    return (
      <>
        <h1>Dashboard</h1>
        <p className="section-note">
          No run is active. Pick a scenario above and start paper trading — the system will
          generate market data, analyse it, decide, size, and execute against a simulated
          matching engine, showing every step as it happens.
        </p>
        <SimulationFootnote />
      </>
    );
  }

  return (
    <>
      <h1>Dashboard</h1>
      <p className="section-note">
        {runtime.scenario?.title}. {runtime.scenario?.demonstrates}
      </p>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="card">
          <MoneyStat
            label="Equity (simulated)"
            value={capital?.equity ?? 0}
            sub={`from $${money(capital?.starting ?? 0, 0)} starting`}
          />
        </div>
        <div className="card">
          <MoneyStat label="Total P&L" value={capital?.total_pnl ?? 0} signed
            sub={`realised ${signedMoney(capital?.realized_pnl ?? 0)}`} />
        </div>
        <div className="card">
          <PctStat label="Return" value={capital?.return_pct ?? 0}
            sub={`fees ${money(capital?.fees_paid ?? 0)}`} />
        </div>
        <div className="card">
          <Stat
            label="Max drawdown"
            value={`${(capital?.max_drawdown_pct ?? 0).toFixed(2)}%`}
            tone={(capital?.max_drawdown_pct ?? 0) > 5 ? "warn" : "flat"}
            sub={`peak $${money(capital?.peak_equity ?? 0, 0)}`}
          />
        </div>
      </div>

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <Card title="Equity curve (simulated)">
          {curve.length > 1 ? (
            <EquityChart points={curve} height={230} />
          ) : (
            <Empty message="Waiting for the first bars…" />
          )}
        </Card>

        <Card title="Pipeline this run">
          <div className="grid cols-3" style={{ gap: 12 }}>
            <Stat label="Bars processed" value={counters.bars ?? 0} />
            <Stat label="Signals" value={counters.signals ?? 0}
              sub={`${counters.no_trade ?? 0} no-trade`} />
            <Stat label="Risk approved" value={counters.approved ?? 0}
              sub={`${counters.risk_rejected ?? 0} rejected`} />
            <Stat label="Orders" value={counters.intents ?? 0}
              sub={`${counters.orders_rejected ?? 0} rejected`} />
            <Stat label="Fills" value={counters.fills ?? 0} />
            <Stat label="Skipped on data" value={counters.quality_skipped ?? 0}
              tone={(counters.quality_skipped ?? 0) > 0 ? "warn" : "flat"} />
          </div>
          <p className="footnote" style={{ marginTop: 14, paddingTop: 10 }}>
            The declines matter as much as the trades. A run that produced 500 signals and
            two orders is behaving as designed — the gates between them are the point.
          </p>
        </Card>
      </div>

      <div className="grid cols-2">
        <Card title={`Open positions (${positions.length})`}>
          {positions.length === 0 ? (
            <Empty message="Flat. No open positions." />
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th className="num">Qty</th>
                  <th className="num">Entry</th>
                  <th className="num">Last</th>
                  <th className="num">Unrealised</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((position) => (
                  <tr key={position.symbol}>
                    <td>{position.symbol}</td>
                    <td><Pill value={position.direction} tone={position.direction === "long" ? "ok" : "warn"} /></td>
                    <td className="num">{qty(position.quantity)}</td>
                    <td className="num">{money(position.average_price)}</td>
                    <td className="num">{money(position.last_price)}</td>
                    <td className={`num ${position.unrealized_pnl >= 0 ? "pos" : "neg"}`}>
                      {signedMoney(position.unrealized_pnl)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="Recent fills">
          {fills.length === 0 ? (
            <Empty message="No fills yet." />
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th className="num">Qty</th>
                  <th className="num">Price</th>
                  <th className="num">Slip (bps)</th>
                </tr>
              </thead>
              <tbody>
                {fills.map((fill) => (
                  <tr key={fill.fill_id}>
                    <td className="faint">{clock(fill.filled_at)}</td>
                    <td>{fill.symbol}</td>
                    <td className={fill.side === "buy" ? "pos" : "neg"}>{fill.side}</td>
                    <td className="num">{qty(fill.quantity)}</td>
                    <td className="num">{money(fill.price)}</td>
                    <td className="num faint">{fill.slippage_bps.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <div style={{ marginTop: 16 }}>
        <Card title="Latest actionable decisions">
          {decisions.length === 0 ? (
            <Empty message="No actionable signals yet — the strategies have not found a setup that cleared the gates." />
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Symbol</th>
                  <th>Direction</th>
                  <th className="num">Confidence</th>
                  <th className="num">AI effect</th>
                  <th>Regime</th>
                  <th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((decision) => (
                  <tr key={decision.decision_id}>
                    <td className="faint">{clock(decision.decided_at)}</td>
                    <td>{decision.symbol}</td>
                    <td className={decision.direction === "long" ? "pos" : "neg"}>
                      {decision.direction}
                    </td>
                    <td className="num">{decision.confidence.toFixed(3)}</td>
                    <td className={`num ${decision.context_modifier < 0 ? "warn" : "faint"}`}>
                      {decision.context_modifier.toFixed(3)}
                    </td>
                    <td className="faint">{decision.regime}</td>
                    <td><Pill value={decision.verdict} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <SimulationFootnote />
    </>
  );
}
