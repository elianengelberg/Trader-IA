import { useCallback, useEffect, useState } from "react";
import {
  api,
  type ActivityEvent,
  type Decision,
  type Fill,
  type Position,
  type MoneyRecord,
  type MoneySlice,
  type RuntimeSnapshot,
  type TrainingStatus,
} from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { LIVE_EVENT_TYPES, useStreamEvent } from "../lib/stream";
import { EquityChart } from "../components/charts";
import { CommandCenter } from "../components/CommandCenter";
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
    entry_price?: number | null;
    stop_price?: number | null;
    initial_stop?: number | null;
    stop_kind?: string | null;
    target_price?: number | null;
    best_price?: number | null;
    r_multiple?: number | null;
    protected?: boolean;
  };
  execution?: { entry_order_type?: string; resting_order?: unknown };
  exits?: { breakeven_after_r?: number; trail_atr_multiple?: number };
  market?: { quote?: { spread_bps?: number } | null; max_spread_bps?: number; spread_source?: string };
  sizing?: { conviction?: boolean; last?: { fraction?: number; reason?: string } | null };
  trend?: { mode?: string; available?: boolean; bias?: string; z_1w?: number | null; z_4w?: number | null; return_4w_pct?: number | null; reason?: string };
  funnel?: {
    stages?: Record<string, number>;
    risk_reasons?: Record<string, number>;
    recent_refusals?: { at: string; stage: string; reason: string }[];
    exploration?: { enabled?: boolean; per_day?: number; used_today?: number };
  };
  account?: {
    starting_capital?: number;
    prior_realised_pnl?: number;
    equity?: number;
    leverage_max?: number;
    leverage_used?: number | null;
    margin_used_pct?: number | null;
    maintenance_margin_pct?: number;
    liquidation_price?: number | null;
    liquidations?: number;
    funding?: { payments?: number; paid_usd?: number; last_rate?: number | null; skipped_no_rate?: number };
    charge_funding?: boolean;
  };
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
    (counters.guardrail_rejected ?? 0) +
    (counters.spread_rejected ?? 0) +
    (counters.strategy_muted ?? 0) +
    (counters.htf_rejected ?? 0);
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
          label="Account balance (simulated)"
          value={snap.account?.equity ?? cap.equity ?? 0}
          sub={
            `started with $${money(snap.account?.starting_capital ?? cap.allocated_capital ?? 0, 0)}` +
            ((snap.account?.prior_realised_pnl ?? 0) !== 0 ? ` · ${signedMoney(snap.account?.prior_realised_pnl ?? 0)} carried` : "") +
            ((snap.account?.leverage_max ?? 1) > 1 ? ` · up to ${snap.account?.leverage_max}x` : "")
          }
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
            ? `Open position: ${
                snap.position.protected
                  ? `protected by a ${snap.position.stop_kind && snap.position.stop_kind !== "protective" ? snap.position.stop_kind + " " : ""}stop`
                  : "NOT protected"
              }` +
              (snap.position.stop_price ? ` at $${money(snap.position.stop_price, 0)}` : "") +
              (snap.position.r_multiple != null ? ` · ${snap.position.r_multiple.toFixed(1)}R in favour at best` : "") +
              (snap.position.target_price ? ` · target $${money(snap.position.target_price, 0)}` : "") +
              ". "
            : "Flat. "}
          Entries: {snap.execution?.entry_order_type === "limit" ? "resting maker orders" : "market"}
          {snap.execution?.resting_order ? " · one order resting now" : ""}
          {snap.sizing?.last?.fraction != null && snap.sizing.last.fraction < 1
            ? ` · last entry sized at ${Math.round(snap.sizing.last.fraction * 100)}% of the approved size (${snap.sizing.last.reason ?? "conviction"})`
            : ""}
          {snap.market?.quote?.spread_bps != null
            ? ` · live spread ${snap.market.quote.spread_bps.toFixed(2)} bps`
            : ""}
          {(counters.exits_stop ?? 0) + (counters.exits_target ?? 0) + (counters.exits_reversal ?? 0) > 0
            ? ` · exits: ${counters.exits_stop ?? 0} by stop (${counters.exits_breakeven ?? 0} break-even, ${counters.exits_trail ?? 0} trailing), ${counters.exits_target ?? 0} at target, ${counters.exits_reversal ?? 0} on reversal`
            : ""}
          {(counters.stops_tightened ?? 0) > 0 ? ` · stops tightened ${counters.stops_tightened}` : ""}
          {(counters.strategy_muted ?? 0) > 0 ? ` · ${counters.strategy_muted} refused from a muted strategy` : ""}
          {(counters.spread_rejected ?? 0) > 0 ? ` · ${counters.spread_rejected} waited out a wide spread` : ""}
          {(counters.htf_rejected ?? 0) > 0 ? ` · ${counters.htf_rejected} refused against the tide` : ""}
        </p>
      )}
      {snap.funnel?.stages && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-faint)", marginBottom: 6 }}>
            Why no trade — since the session started
          </div>
          <div className="row" style={{ gap: 6 }}>
            {(() => {
              const s = snap.funnel?.stages ?? {};
              const items: [string, number, string][] = [
                ["bars evaluated", s.evaluated ?? 0, ""],
                ["no signal", s.not_actionable ?? 0, ""],
                ["signals", s.actionable ?? 0, "info"],
                ["risk engine", s.risk ?? 0, "warn"],
                ["against the tide", s.tide ?? 0, "warn"],
                ["muted strategy", s.muted ?? 0, "warn"],
                ["wide spread", s.spread ?? 0, "warn"],
                ["position already open", s.position_open ?? 0, ""],
                ["order resting", s.resting ?? 0, ""],
                ["budget", s.budget ?? 0, "warn"],
                ["no proven edge", s.expected_value ?? 0, "bad"],
                ["guardrail", s.guardrail ?? 0, "bad"],
                ["halted", s.halted ?? 0, "bad"],
                ["exploration", s.exploration ?? 0, "info"],
                ["orders", s.orders ?? 0, "ok"],
              ];
              return items
                .filter(([, n]) => n > 0)
                .map(([label, n, tone]) => <Pill key={label} value={`${label} ${n}`} tone={tone} />);
            })()}
          </div>
          {Object.keys(snap.funnel?.risk_reasons ?? {}).length > 0 && (
            <p className="footnote" style={{ marginTop: 8 }}>
              Risk engine refusals: {Object.entries(snap.funnel?.risk_reasons ?? {}).map(([r, n]) => `${r} (${n})`).join(" · ")}
            </p>
          )}
          {(snap.funnel?.recent_refusals?.length ?? 0) > 0 && (
            <p className="footnote" style={{ marginTop: 8 }}>
              Last refusal: <span className="mono">{snap.funnel?.recent_refusals?.[0]?.reason}</span>
            </p>
          )}
          {snap.funnel?.exploration?.enabled ? (
            <p className="footnote" style={{ marginTop: 8 }}>
              Exploration: {snap.funnel.exploration.used_today ?? 0} of {snap.funnel.exploration.per_day} lessons bought today — trades in buckets with no evidence or an unproven edge, at reduced size, never counted toward the real-money track record.
            </p>
          ) : (
            <p className="footnote" style={{ marginTop: 8 }}>
              Exploration is off: the session trades only on a proven edge. With most buckets unproven that can mean days without a trade — set <span className="mono">TIA_LIVE__EXPLORATION_TRADES_PER_DAY</span> to let it buy lessons with simulated money.
            </p>
          )}
        </div>
      )}
      {snap.account && (snap.account.leverage_max ?? 1) > 1 && (
        <p className="footnote" style={{ marginTop: 12 }}>
          <strong>Leveraged account (simulated perpetual): </strong>
          {snap.account.leverage_used != null ? `using ${snap.account.leverage_used.toFixed(2)}x of ${snap.account.leverage_max}x` : `up to ${snap.account.leverage_max}x, flat now`}
          {snap.account.margin_used_pct != null ? ` · margin used ${snap.account.margin_used_pct.toFixed(0)}%` : ""}
          {snap.account.liquidation_price != null ? ` · liquidation at ≈ $${money(snap.account.liquidation_price, 0)} (maintenance ${snap.account.maintenance_margin_pct}%)` : ""}
          {snap.account.charge_funding
            ? ` · funding ${(snap.account.funding?.payments ?? 0)} payments, ${signedMoney(-(snap.account.funding?.paid_usd ?? 0))} net`
            : " · funding not charged"}
          {(snap.account.funding?.skipped_no_rate ?? 0) > 0 ? ` (${snap.account.funding?.skipped_no_rate} periods without a rate reading)` : ""}
          {(snap.account.liquidations ?? 0) > 0 ? ` · ${snap.account.liquidations} liquidation(s)` : ""}
          . Leverage lets a tight stop carry a bigger position; the risk per trade is unchanged.
        </p>
      )}
      {snap.trend && snap.trend.mode !== "off" && (
        <p className="footnote" style={{ marginTop: 12 }}>
          <strong>Tide (1–4 week momentum): </strong>
          {snap.trend.available ? (
            <>
              <span className={snap.trend.bias === "up" ? "pos" : snap.trend.bias === "down" ? "neg" : "dim"}>
                {String(snap.trend.bias).toUpperCase()}
              </span>
              {` · 1w ${(snap.trend.z_1w ?? 0).toFixed(1)}σ, 4w ${(snap.trend.z_4w ?? 0).toFixed(1)}σ`}
              {snap.trend.return_4w_pct != null ? ` · 4 weeks ${snap.trend.return_4w_pct >= 0 ? "+" : ""}${snap.trend.return_4w_pct.toFixed(1)}%` : ""}
              {snap.trend.mode === "hard"
                ? " · entries against it are refused"
                : " · entries against it are halved"}
            </>
          ) : (
            <span className="dim">unknown — {snap.trend.reason ?? "not read yet"}; no bias is imposed</span>
          )}
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

/** One line of English per session event. Unknown types fall back to their name. */
function describe(event: ActivityEvent): { text: string; tone: string } {
  const d = event.data ?? {};
  const usd = (v: unknown) => (typeof v === "number" ? signedMoney(v) : "");
  switch (event.type) {
    case "trade.closed": {
      // The 24/7 session reports dollars; the demo engine reports basis points only.
      const result =
        typeof d.net_usd === "number"
          ? usd(d.net_usd)
          : typeof d.net_bps === "number"
            ? `${d.net_bps >= 0 ? "+" : ""}${d.net_bps.toFixed(1)} bps`
            : "";
      const value = typeof d.net_usd === "number" ? d.net_usd : typeof d.net_bps === "number" ? d.net_bps : 0;
      return {
        text: `Closed ${d.direction} in ${String(d.regime ?? "").replace("_", " ")}${result ? `: ${result}` : ""} (${d.exit_reason ?? "reversal"})${d.exploratory ? " · exploration" : ""}`,
        tone: value > 0 ? "pos" : "neg",
      };
    }
    case "live.exploration":
      return { text: String(d.reason ?? "Exploration trade"), tone: "info" };
    case "live.no_trade":
      return { text: `No trade — ${String(d.reason ?? "").slice(0, 140)}`, tone: "faint" };
    case "live.order_resting":
      return { text: `Resting ${d.side} entry at $${money(Number(d.limit_price ?? 0), 0)} (up to ${d.timeout_bars} bars)`, tone: "" };
    case "live.order_expired":
      return { text: `Resting ${d.side} order expired after ${d.waited_bars} bars${d.reducing ? " — exit re-sent at market" : ""}`, tone: "warn" };
    case "live.stop_placed":
      return { text: `Protective stop placed at $${money(Number(d.stop_price ?? 0), 0)}`, tone: "" };
    case "live.funding":
      return { text: `Funding settled: ${usd(-Number(d.paid_usd ?? 0))} on a $${money(Number(d.notional ?? 0), 0)} ${d.side} position (rate ${(Number(d.rate ?? 0) * 10_000).toFixed(2)} bps)`, tone: Number(d.paid_usd ?? 0) > 0 ? "neg" : "pos" };
    case "live.liquidation":
      return { text: `LIQUIDATED: equity $${money(Number(d.equity ?? 0), 0)} fell below the maintenance margin $${money(Number(d.maintenance ?? 0), 0)} on $${money(Number(d.notional ?? 0), 0)} notional · fee ${usd(-Number(d.fee_usd ?? 0))}`, tone: "neg" };
    case "live.trend":
      return { text: `Tide re-read: ${String(d.bias ?? "unknown").toUpperCase()} — ${d.reason ?? ""}`, tone: d.bias === "up" ? "pos" : d.bias === "down" ? "neg" : "faint" };
    case "live.stop_tightened":
      return { text: `Stop tightened to $${money(Number(d.stop_price ?? 0), 0)} (${d.kind}: ${d.reason ?? ""})`, tone: "info" };
    case "live.exit":
      return { text: `Exit at market: ${d.reason}`, tone: "warn" };
    case "live.evidence_absorbed":
      return { text: `Absorbed ${d.absorbed ?? d.absorbed_outcomes ?? 0} new trades of evidence · ${d.buckets_ready ?? "?"} buckets ready`, tone: "info" };
    case "live.state":
      return { text: `Session state: ${d.state}`, tone: d.state === "running" ? "pos" : "warn" };
    default:
      return { text: event.type, tone: "faint" };
  }
}

/**
 * The session's own diary, live. Loaded once from the server (so a page opened at 9am
 * shows what happened at 3am) and then prepended to as events arrive on the stream.
 */
function ActivityPanel({ subscribe }: { subscribe: Subscribe }) {
  const [events, setEvents] = useState<ActivityEvent[]>([]);

  useEffect(() => {
    api.liveActivity(60).then(setEvents).catch(() => undefined);
  }, []);

  useEffect(() => {
    const unsubscribes = LIVE_EVENT_TYPES.map((type) =>
      subscribe(type, (data) => {
        setEvents((previous) =>
          [{ type, at: new Date().toISOString(), data: (data ?? {}) as Record<string, unknown> }, ...previous].slice(0, 80),
        );
      }),
    );
    return () => unsubscribes.forEach((off) => off());
  }, [subscribe]);

  return (
    <Card title="Session activity — live">
      {events.length === 0 ? (
        <Empty message="Nothing yet. Entries, stops, exits, refusals and absorbed evidence appear here as they happen." />
      ) : (
        <div className="scroll" style={{ maxHeight: 320 }}>
          <table>
            <tbody>
              {events.map((event, index) => {
                const { text, tone } = describe(event);
                return (
                  <tr key={`${event.at}-${index}`}>
                    <td className="mono faint" style={{ whiteSpace: "nowrap", width: 80 }}>{clock(event.at)}</td>
                    <td className={tone} style={{ fontSize: 12.5 }}>{text}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
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
          sub={`${signedMoney(data.pnl_usd)} over ${data.trades.toLocaleString("en-US")} trades · ${(data.win_rate * 100).toFixed(0)}% won · from $${(data.starting_usd ?? base).toLocaleString("en-US")}`}
        />
        <p className="footnote" style={{ marginTop: 8, marginBottom: 0 }}>
          {note} Average trade {signedMoney(data.mean_trade_usd)} on a typical position of $
          {data.typical_notional_usd.toLocaleString("en-US", { maximumFractionDigits: 0 })}.
        </p>
      </div>
    );
  };

  return (
    <Card title="If this had been real money — simulated">
      <p style={{ marginTop: 0, fontSize: 12.5, color: "var(--text-dim)" }}>
        The 24/7 account starts from ${(money.session_starting_usd ?? money.starting_usd)?.toLocaleString("en-US")};
        the training simulations from ${money.starting_usd?.toLocaleString("en-US")} each (simulated). Every
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
        <CommandCenter subscribe={subscribe} />
        <div style={{ marginTop: 16 }}>
          <LiveSessionPanel subscribe={subscribe} />
        </div>
        <div style={{ marginTop: 16 }}>
          <ActivityPanel subscribe={subscribe} />
        </div>
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
        <CommandCenter subscribe={subscribe} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <LiveSessionPanel subscribe={subscribe} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <ActivityPanel subscribe={subscribe} />
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
