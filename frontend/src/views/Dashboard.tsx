import { useCallback, useEffect, useState } from "react";
import {
  api,
  type Decision,
  type Fill,
  type Position,
  type RuntimeSnapshot,
  type TrainingStatus,
} from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { useStreamEvent } from "../lib/stream";
import { EquityChart } from "../components/charts";
import { Card, Empty, MoneyStat, PctStat, Pill, SimulationFootnote, Stat } from "../components/ui";
import { bpsUsd, clock, money, qty, signedMoney } from "../lib/format";

type EquityPoint = { at: string; equity: number; drawdown_pct: number };

/** The 24/7 session's snapshot, as this panel reads it. The API returns more. */
interface LiveSnap {
  active: boolean;
  state: string;
  mode?: string;
  symbol?: string;
  heartbeat_age_seconds?: number | null;
  market_data_age_seconds?: number | null;
  capital?: {
    equity?: number;
    allocated_capital?: number;
    realised_pnl?: number;
    unrealised_pnl?: number;
    fees_paid?: number;
    net_return_pct?: number;
  };
  counters?: Record<string, number>;
  expected_value?: { threshold_bps?: number; coverage?: Record<string, number> };
}

/** Every bucket needs this many closed trades before the session will trade it. */
const EVIDENCE_FLOOR = 30;

function LiveSessionPanel({ subscribe }: { subscribe: Subscribe }) {
  const [snap, setSnap] = useState<LiveSnap | null>(null);

  const load = useCallback(() => {
    api.liveSnapshot()
      .then((s) => setSnap(s as unknown as LiveSnap))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 10_000);
    return () => window.clearInterval(timer);
  }, [load]);
  useStreamEvent(subscribe, "trade.closed", load);

  if (!snap?.active) return null;

  const cap = snap.capital ?? {};
  const counters = snap.counters ?? {};
  const pnl = (cap.realised_pnl ?? 0) + (cap.unrealised_pnl ?? 0);
  const coverage = snap.expected_value?.coverage ?? {};
  const bucketsSeen = Object.keys(coverage).length;
  const bucketsReady = Object.values(coverage).filter((n) => n >= EVIDENCE_FLOOR).length;
  const refusals =
    (counters.ev_rejected ?? 0) +
    (counters.risk_rejected ?? 0) +
    (counters.budget_rejected ?? 0) +
    (counters.guardrail_rejected ?? 0);
  const starving = (counters.signals ?? 0) > 0 && (counters.orders ?? 0) === 0;

  return (
    <Card
      title="24/7 session — real Binance market, simulated fills"
      actions={<Pill value={snap.state} tone={snap.state === "running" ? "ok" : "warn"} />}
    >
      <div className="grid cols-4" style={{ gap: 12 }}>
        <MoneyStat
          label="Equity (simulated)"
          value={cap.equity ?? 0}
          sub={`from $${money(cap.allocated_capital ?? 0, 0)} allocated`}
        />
        <MoneyStat
          label="Session P&L"
          value={pnl}
          signed
          sub={`fees ${money(cap.fees_paid ?? 0)}`}
        />
        <Stat
          label="Signals → orders"
          value={`${counters.signals ?? 0} → ${counters.orders ?? 0}`}
          sub={
            `${refusals} refused by the gates · ${counters.fills ?? 0} fills` +
            ((counters.exploration_trades ?? 0) > 0
              ? ` · ${counters.exploration_trades} exploration`
              : "")
          }
        />
        <Stat
          label="Evidence buckets ready"
          value={`${bucketsReady}`}
          tone={bucketsReady > 0 ? "pos" : "warn"}
          sub={`of ${bucketsSeen} seen · needs ${EVIDENCE_FLOOR} trades each`}
        />
      </div>
      <p className="footnote" style={{ marginTop: 12 }}>
        {starving
          ? "The session is producing signals but refusing to trade them — the honest " +
            "behaviour with no proven edge in these conditions. Feed it evidence: run the " +
            "training simulations (scripts/train_sims.py) and restart the session, or let " +
            "it keep watching. It will not guess."
          : "Bars " + (counters.bars ?? 0) + " · cycles " + (counters.cycles ?? 0) +
            " · every entry must clear risk, budget, expected value and the learning " +
            "guardrails. Lessons from each closed trade appear under Learning."}
      </p>
    </Card>
  );
}

function TrainingPanel() {
  const [status, setStatus] = useState<TrainingStatus | null>(null);
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");

  const load = useCallback(() => {
    api.training().then(setStatus).catch(() => undefined);
  }, []);

  useEffect(() => {
    load();
    const id = window.setInterval(() => {
      if (!document.hidden) load();
    }, 3_000);
    return () => window.clearInterval(id);
  }, [load]);

  const act = useCallback(
    async (kind: "start" | "stop" | "reload", runs = 0) => {
      setBusy(kind);
      setNote("");
      try {
        if (kind === "start") await api.trainingStart(runs);
        else if (kind === "stop") await api.trainingStop();
        else {
          const result = await api.trainingReload();
          setNote(result.detail);
        }
        load();
      } catch (error) {
        setNote(error instanceof Error ? error.message : "request failed");
      } finally {
        setBusy("");
      }
    },
    [load],
  );

  if (!status) return null;
  const running = status.running;
  const total = status.total ?? 0;
  const run = status.run ?? 0;
  const percent = total > 0 ? Math.round((run / total) * 100) : 0;

  return (
    <Card
      title="Training simulations — evidence for the learning engine"
      actions={<Pill value={status.state} tone={running ? "ok" : status.state === "finished" ? "info" : ""} />}
    >
      {running ? (
        <>
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
            <span style={{ fontSize: 12.5 }}>
              Run <strong>{run}</strong> of {total} · {status.scenario ?? ""}
            </span>
            <span className="mono" style={{ fontSize: 12.5 }}>{percent}%</span>
          </div>
          <div className="progress">
            <div className="progress-fill" style={{ width: `${percent}%` }} />
          </div>
          <div className="row" style={{ marginTop: 10, gap: 18 }}>
            <Stat label="Trades persisted" value={String(status.closed_trades ?? 0)} />
            <Stat
              label="Mean net per trade"
              value={
                status.mean_bps == null
                  ? "—"
                  : bpsUsd(status.mean_bps, status.typical_notional_usd)
              }
              tone={(status.mean_bps ?? 0) > 0 ? "pos" : "neg"}
            />
            <Stat label="Wins" value={String(status.wins ?? 0)} />
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn small danger" disabled={busy !== ""} onClick={() => act("stop")}>
              {busy === "stop" ? "Stopping…" : "Stop training"}
            </button>
            <span style={{ fontSize: 11.5, color: "var(--text-faint)" }}>
              Stopping keeps every completed run&apos;s evidence.
            </span>
          </div>
        </>
      ) : (
        <>
          <p style={{ marginTop: 0, fontSize: 12.5, color: "var(--text-dim)" }}>
            {status.state === "finished" || status.state === "stopped"
              ? `Last batch: ${status.closed_trades ?? 0} trades persisted` +
                (status.mean_bps != null && (status.typical_notional_usd ?? 0) > 0
                  ? ` (mean ${bpsUsd(status.mean_bps, status.typical_notional_usd)} per trade)`
                  : "") +
                (status.buckets_ready != null ? ` · ${status.buckets_ready} buckets at the 30-trade floor` : "") +
                ". Load it into the session to act on it."
              : status.state === "interrupted"
                ? "The last trainer died mid-run — every completed run's evidence is safe. Launch a new batch (fresh seeds are automatic)."
                : "Simulations teach the learning engine which setups win and lose after costs. They never count toward the real-money gate. Fresh seeds every launch — duplicates are impossible."}
          </p>
          <div className="row" style={{ gap: 8 }}>
            {[100, 500, 1000].map((n) => (
              <button
                key={n}
                className="btn small"
                disabled={busy !== ""}
                onClick={() => act("start", n)}
              >
                {busy === "start" ? "Starting…" : `Run ${n} sims`}
              </button>
            ))}
            <button
              className="btn small primary"
              disabled={busy !== ""}
              onClick={() => act("reload")}
              title="Restarts the engine (~30s); the 24/7 session resumes by itself with the enlarged evidence"
            >
              {busy === "reload" ? "Restarting…" : "Load evidence into session"}
            </button>
          </div>
        </>
      )}
      {note && <p style={{ marginTop: 10, fontSize: 12, color: "var(--text-dim)" }}>{note}</p>}
    </Card>
  );
}

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
          The 24/7 session lives in <strong>Live Trading</strong>. While it runs, its
          activity shows right here; the live price is under <strong>Markets</strong> and
          the lessons from every closed trade under <strong>Learning</strong>.
        </p>
        <LiveSessionPanel subscribe={subscribe} />
        <div style={{ marginTop: 16 }}>
          <TrainingPanel />
        </div>
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

      <div style={{ marginBottom: 16 }}>
        <LiveSessionPanel subscribe={subscribe} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <TrainingPanel />
      </div>

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
                  <th className="num">Slippage</th>
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
                    <td className="num faint">
                      {bpsUsd(fill.slippage_bps, fill.price * fill.quantity, { signed: false })}
                    </td>
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
