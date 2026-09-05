import { useCallback, useEffect, useState } from "react";
import {
  api,
  type Decision,
  type Fill,
  type Position,
  type MoneyRecord,
  type MoneySlice,
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
  state_machine?: { history?: { reason?: string; at?: string }[] };
  evidence?: { absorbed_since_start?: number; buckets_ready?: number };
  position?: {
    open?: boolean;
    stop_price?: number | null;
    target_price?: number | null;
    protected?: boolean;
  };
  execution?: { entry_order_type?: string; resting_order?: unknown };
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
  // Why the session is not RUNNING is the whole content of the news that it is not.
  // The reason lives in the state machine's last transition; showing it here saves a
  // trip to Live Trading just to find out nothing is actually wrong.
  const history = snap.state_machine?.history ?? [];
  const stateReason = snap.state !== "running" ? history[history.length - 1]?.reason : null;

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
      {(snap.position?.open || snap.execution?.entry_order_type) && (
        <p className="footnote" style={{ marginTop: 12 }}>
          {snap.position?.open
            ? `Open position: ${snap.position.protected ? "protected by a stop" : "NOT protected"}` +
              (snap.position.stop_price ? ` at $${money(snap.position.stop_price, 0)}` : "") +
              (snap.position.target_price ? ` · target $${money(snap.position.target_price, 0)}` : "") +
              ". "
            : "Flat. "}
          Entries: {snap.execution?.entry_order_type === "limit" ? "resting maker orders" : "market"}
          {snap.execution?.resting_order ? " · one order resting now" : ""}
          {(counters.exits_stop ?? 0) + (counters.exits_target ?? 0) + (counters.exits_reversal ?? 0) > 0
            ? ` · exits: ${counters.exits_stop ?? 0} by stop, ${counters.exits_target ?? 0} at target, ${counters.exits_reversal ?? 0} on reversal`
            : ""}
        </p>
      )}
      {stateReason && (
        <p
          className="footnote"
          style={{ marginTop: 12, borderLeft: "3px solid var(--warn, #c90)", paddingLeft: 10 }}
        >
          Entries are paused: {stateReason} — lift it from <strong>Live Trading → Resume
          entries</strong> when the cause is resolved. Lessons and evidence keep updating
          while paused.
        </p>
      )}
      <p className="footnote" style={{ marginTop: 12 }}>
        {starving
          ? "The session is producing signals but refusing to trade them — the honest " +
            "behaviour with no proven edge in these conditions. Feed it evidence with the " +
            "training buttons below; new trades fold in automatically within a minute. " +
            "It will not guess."
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
    async (kind: "start" | "stop" | "absorb", runs = 0) => {
      setBusy(kind);
      setNote("");
      try {
        if (kind === "start") await api.trainingStart(runs);
        else if (kind === "stop") await api.trainingStop();
        else {
          const result = await api.trainingAbsorb();
          setNote(
            result.reason ??
              result.error ??
              (result.absorbed > 0
                ? `Folded ${result.absorbed.toLocaleString("en-US")} new trades into the ` +
                  `session — ${result.buckets_ready ?? 0} buckets now at the evidence floor.`
                : "The session is already up to date with every persisted trade."),
          );
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
  // A 50,000-run batch takes days. "Run 1,240 of 50,000" answers where it is but not
  // when it ends, and the second question is the one someone actually has. Measured
  // from this batch's own pace rather than assumed — scenarios differ in length.
  const eta = (() => {
    if (!running || !status.started_at || run < 2 || total <= run) return null;
    const elapsed = Date.now() / 1000 - status.started_at;
    if (elapsed <= 0) return null;
    const remaining = (elapsed / run) * (total - run);
    const hours = remaining / 3600;
    if (hours < 1) return `~${Math.max(1, Math.round(remaining / 60))} min left`;
    if (hours < 48) return `~${hours.toFixed(1)} h left`;
    return `~${(hours / 24).toFixed(1)} days left`;
  })();

  return (
    <Card
      title="Training simulations — evidence for the learning engine"
      actions={<Pill value={status.state} tone={running ? "ok" : status.state === "finished" ? "info" : ""} />}
    >
      {running ? (
        <>
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
            <span style={{ fontSize: 12.5 }}>
              Run <strong>{run.toLocaleString("en-US")}</strong> of{" "}
              {total.toLocaleString("en-US")} · {status.scenario ?? ""}
            </span>
            <span className="mono" style={{ fontSize: 12.5 }}>
              {percent}%{eta ? ` · ${eta}` : ""}
            </span>
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
                ". The 24/7 session folds new evidence in by itself within a minute — " +
                "no restart, nothing to press."
              : status.state === "interrupted"
                ? "The last trainer died mid-run — every completed run's evidence is safe. Launch a new batch (fresh seeds are automatic)."
                : "Simulations teach the learning engine which setups win and lose after costs. They never count toward the real-money gate. Fresh seeds every launch — duplicates are impossible."}
          </p>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            {[500, 1000, 5000, 10000, 50000].map((n) => (
              <button
                key={n}
                className="btn small"
                disabled={busy !== ""}
                onClick={() => act("start", n)}
              >
                {busy === "start" ? "Starting…" : `Run ${n.toLocaleString("en-US")} sims`}
              </button>
            ))}
            <button
              className="btn small primary"
              disabled={busy !== ""}
              onClick={() => act("absorb")}
              title="The session folds new trades in by itself every minute; this does it now, with no restart"
            >
              {busy === "absorb" ? "Loading…" : "Load evidence now"}
            </button>
          </div>
        </>
      )}
      {note && <p style={{ marginTop: 10, fontSize: 12, color: "var(--text-dim)" }}>{note}</p>}
    </Card>
  );
}

/**
 * "If this had been real money, where would we be?"
 *
 * Two answers, kept apart on purpose. The 24/7 session is one continuous account, so its
 * balance is a real answer. The training total is the sum of thousands of independent
 * simulations — it says whether the strategy makes money at that trade size, not what an
 * account holding them in sequence would be worth, and the panel says so rather than
 * letting a big number imply the stronger claim.
 */
function MoneyPanel() {
  const [money, setMoney] = useState<MoneyRecord | null>(null);

  const load = useCallback(() => {
    api.money().then(setMoney).catch(() => undefined);
  }, []);

  useEffect(() => {
    load();
    const id = window.setInterval(() => {
      if (!document.hidden) load();
    }, 30_000);
    return () => window.clearInterval(id);
  }, [load]);

  if (!money?.available) return null;
  const base = money.starting_usd ?? 0;
  const session = money.session;
  const training = money.training;

  const slice = (label: string, data: MoneySlice | undefined, note: string) => {
    if (!data || data.trades === 0) {
      return (
        <div className="card">
          <Stat label={label} value="—" sub="no closed trades yet" />
        </div>
      );
    }
    return (
      <div className="card">
        <MoneyStat
          label={label}
          value={data.ending_usd}
          sub={`${signedMoney(data.pnl_usd)} over ${data.trades.toLocaleString("en-US")} trades · ${(data.win_rate * 100).toFixed(0)}% won`}
        />
        <p className="footnote" style={{ marginTop: 8, marginBottom: 0 }}>
          {note} Average trade {signedMoney(data.mean_trade_usd)} on a typical position of $
          {data.typical_notional_usd.toLocaleString("en-US", { maximumFractionDigits: 0 })}.
        </p>
      </div>
    );
  };

  return (
    <Card title="If this had been real money — simulated, from $100,000">
      <p style={{ marginTop: 0, fontSize: 12.5, color: "var(--text-dim)" }}>
        Starting balance ${money.starting_usd?.toLocaleString("en-US")} (simulated). Every
        trade is priced at the size it actually carried, not an assumed one.
      </p>
      <div className="grid cols-2" style={{ gap: 12 }}>
        {slice(
          "24/7 session — a real account",
          session,
          "One continuous account against the live Binance market, so this balance is a genuine answer for the trades it took.",
        )}
        {slice(
          "Training simulations — pooled",
          training,
          "The sum of thousands of INDEPENDENT runs. It answers whether the strategy makes money at this size; no single account ever held this sequence.",
        )}
      </div>
      {(training?.curve?.length ?? 0) > 1 && (
        <div style={{ marginTop: 14 }}>
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
            <span style={{ fontSize: 12.5, color: "var(--text-dim)" }}>
              Cumulative result of the training record
            </span>
            <span className={`mono ${(training?.pnl_usd ?? 0) >= 0 ? "pos" : "neg"}`} style={{ fontSize: 12.5 }}>
              {signedMoney(training?.pnl_usd ?? 0)}
            </span>
          </div>
          <EquityChart
            points={(training?.curve ?? []).map((value, index) => ({
              at: String(index),
              equity: base + value,
              drawdown_pct: 0,
            }))}
            height={170}
          />
        </div>
      )}
      <p className="footnote" style={{ marginTop: 12 }}>{money.explanation}</p>
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
          <MoneyPanel />
        </div>
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
        <MoneyPanel />
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
