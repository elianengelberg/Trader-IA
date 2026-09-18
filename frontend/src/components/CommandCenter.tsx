/**
 * Command center — the neon "trading terminal" view of the same honest numbers.
 *
 * One glowing hero (the session's P&L, in dollars, simulated and labelled so), then three
 * live panels: a streak strip of the last trades (one tick per closed trade, won or lost),
 * the order ladder (what is resting, working, filled or refused right now) and a market
 * map of recent trades plotted by result. Everything on it comes from the same record the
 * rest of the site reads — the design is louder; the numbers are not.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type JournalRow, type Order } from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { useStreamEvent } from "../lib/stream";
import { Empty } from "./ui";
import { clock, money, qty, signedMoney } from "../lib/format";

interface LiveSnap {
  active: boolean;
  state: string;
  symbol?: string;
  capital?: { equity?: number; allocated_capital?: number; realised_pnl?: number; unrealised_pnl?: number; fees_paid?: number };
  counters?: Record<string, number>;
  position?: { open?: boolean; stop_price?: number | null; target_price?: number | null; protected?: boolean; stop_kind?: string | null; r_multiple?: number | null };
  trend?: { available?: boolean; bias?: string; mode?: string };
  execution?: { resting_order?: unknown };
  account?: {
    simulated?: boolean;
    starting_capital?: number;
    prior_realised_pnl?: number;
    equity?: number;
    return_pct?: number | null;
    leverage_max?: number;
    leverage_used?: number | null;
    margin_used_pct?: number | null;
    liquidation_price?: number | null;
    liquidations?: number;
    funding?: { payments?: number; paid_usd?: number; last_rate?: number | null };
  };
}

const STREAK_LENGTH = 40;
const MAP_LENGTH = 60;

/** Consecutive wins (positive) or losses (negative) at the head of the record. */
function currentStreak(rows: JournalRow[]): number {
  if (rows.length === 0) return 0;
  const sign = rows[0].is_win ? 1 : -1;
  let n = 0;
  for (const row of rows) {
    if ((row.is_win ? 1 : -1) !== sign) break;
    n += 1;
  }
  return n * sign;
}

function StreakStrip({ rows }: { rows: JournalRow[] }) {
  const recent = rows.slice(0, STREAK_LENGTH).reverse();
  if (recent.length === 0) return <Empty message="No closed trades yet — each one becomes a tick here." />;
  const scale = Math.max(1, ...recent.map((r) => Math.abs(r.net_usd)));
  return (
    <div className="ticks" aria-label="Recent trades, oldest to newest">
      {recent.map((row, index) => {
        const height = 18 + Math.round((Math.abs(row.net_usd) / scale) * 42);
        const latest = index === recent.length - 1;
        return (
          <div
            key={row.outcome_id}
            className={`tick ${row.is_win ? "win" : "loss"} ${latest ? "latest" : ""} ${row.exploratory ? "explore" : ""}`}
            style={{ height }}
            title={`${row.direction} in ${row.regime} · ${signedMoney(row.net_usd)} · ${row.exit_reason ?? "reversal"}${row.exploratory ? " · exploration" : ""}`}
          />
        );
      })}
    </div>
  );
}

/** Order states in one word each, so the ladder reads at a glance and fits its column. */
const LADDER_STATE: Record<string, { word: string; tone: string }> = {
  filled: { word: "filled", tone: "pos" },
  partially_filled: { word: "partial", tone: "pos" },
  acknowledged: { word: "working", tone: "" },
  pending_new: { word: "pending", tone: "" },
  new: { word: "working", tone: "" },
  cancelled: { word: "cancelled", tone: "neg" },
  canceled: { word: "cancelled", tone: "neg" },
  rejected: { word: "rejected", tone: "neg" },
  expired: { word: "expired", tone: "warn" },
};

function Ladder({ orders }: { orders: Order[] }) {
  if (orders.length === 0) return <Empty message="No orders yet. Resting, working and filled orders stack here." />;
  return (
    <table className="ladder">
      <tbody>
        {orders.map((order) => {
          const extra = order as unknown as { limit_price?: number | null; stop_price?: number | null };
          const price = order.average_fill_price || extra.limit_price || extra.stop_price || 0;
          const state = LADDER_STATE[order.state.toLowerCase()] ?? { word: order.state.toLowerCase().replace("_", " "), tone: "" };
          return (
            <tr key={order.order_id} title={`${order.order_type.toLowerCase()} · ${order.state.toLowerCase()}${order.reject_reason ? ` · ${order.reject_reason}` : ""}`}>
              <td className="faint">{clock(order.updated_at || order.created_at)}</td>
              <td className={order.side === "buy" ? "pos" : "neg"} style={{ fontWeight: 700 }}>
                {order.side.toUpperCase()} <span className="faint" style={{ fontWeight: 400 }}>{order.order_type.toLowerCase().slice(0, 3)}</span>
              </td>
              <td className="num">{qty(order.quantity)}</td>
              <td className="num">{price ? money(price, 0) : "mkt"}</td>
              <td className={`num ${state.tone}`}>{state.word}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/** Trades as dots: time left to right, result below or above the zero line. */
function MarketMap({ rows }: { rows: JournalRow[] }) {
  const recent = rows.slice(0, MAP_LENGTH).reverse();
  const width = 520, height = 170, pad = 14;
  if (recent.length === 0) return <Empty message="Trades plot here as they close — above the line won, below lost." />;
  const scale = Math.max(1, ...recent.map((r) => Math.abs(r.net_usd)));
  const notionalMax = Math.max(1, ...recent.map((r) => r.notional_usd));
  const x = (i: number) => pad + (i / Math.max(1, recent.length - 1)) * (width - pad * 2);
  const y = (v: number) => height / 2 - (v / scale) * (height / 2 - pad);
  return (
    <svg className="mmap" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="Recent trades by result">
      <defs>
        <pattern id="mmap-grid" width="26" height="26" patternUnits="userSpaceOnUse">
          <path d="M 26 0 L 0 0 0 26" className="mmap-grid" />
        </pattern>
      </defs>
      <rect width={width} height={height} fill="url(#mmap-grid)" />
      <line x1={0} x2={width} y1={height / 2} y2={height / 2} className="mmap-zero" />
      {recent.map((row, i) => {
        const r = 3 + (row.notional_usd / notionalMax) * 5;
        const latest = i === recent.length - 1;
        return (
          <g key={row.outcome_id}>
            <title>{`${row.direction} · ${signedMoney(row.net_usd)} · ${row.exit_reason ?? "reversal"}`}</title>
            {latest && <circle cx={x(i)} cy={y(row.net_usd)} r={r + 6} className={`mmap-pulse ${row.is_win ? "win" : "loss"}`} />}
            <circle cx={x(i)} cy={y(row.net_usd)} r={r} className={`mmap-dot ${row.is_win ? "win" : "loss"} ${row.exploratory ? "explore" : ""}`} />
          </g>
        );
      })}
    </svg>
  );
}

export function CommandCenter({ subscribe }: { subscribe: Subscribe }) {
  const [snap, setSnap] = useState<LiveSnap | null>(null);
  const [rows, setRows] = useState<JournalRow[]>([]);
  const [source, setSource] = useState<"live" | "record">("live");
  const [orders, setOrders] = useState<Order[]>([]);
  const [startingUsd, setStartingUsd] = useState<number>(10_000);
  const [persistedEquity, setPersistedEquity] = useState<number | null>(null);

  const loadSnap = useCallback(() => {
    api.liveSnapshot().then((s) => setSnap(s as unknown as LiveSnap)).catch(() => undefined);
  }, []);
  const loadTrades = useCallback(() => {
    api.journal({ source: "live", limit: MAP_LENGTH })
      .then((page) => {
        if (page.rows.length > 0) {
          setRows(page.rows);
          setSource("live");
          return;
        }
        // Before the session has closed anything, the whole record (training simulations
        // and demo runs) is the only tape there is — shown, and labelled as such.
        return api.journal({ limit: MAP_LENGTH }).then((record) => {
          setRows(record.rows);
          setSource("record");
        });
      })
      .catch(() => undefined);
  }, []);
  const loadOrders = useCallback(() => {
    api.orders(14).then(setOrders).catch(() => undefined);
  }, []);

  useEffect(() => {
    loadSnap();
    loadTrades();
    loadOrders();
    api.money()
      .then((m) => {
        if (m.session_starting_usd) setStartingUsd(m.session_starting_usd);
        if (m.session && m.session.trades > 0) setPersistedEquity(m.session.ending_usd);
      })
      .catch(() => undefined);
    const id = window.setInterval(() => { if (!document.hidden) { loadSnap(); loadOrders(); } }, 10_000);
    return () => window.clearInterval(id);
  }, [loadSnap, loadTrades, loadOrders]);

  useStreamEvent(subscribe, "trade.closed", () => { loadTrades(); loadSnap(); });
  useStreamEvent(subscribe, "order.state_changed", loadOrders);
  useStreamEvent(subscribe, "order.fill_simulated", loadOrders);
  useStreamEvent(subscribe, "live.evidence_absorbed", loadTrades);

  const cap = snap?.capital ?? {};
  const counters = snap?.counters ?? {};
  const active = snap?.active ?? false;
  const account = snap?.account;
  // One account, simulated, starting from the configured capital. While the session
  // runs, its ledger is the balance (realised, carried and unrealised together); when it
  // is offline the persisted record still knows where the account stands.
  const starting = account?.starting_capital ?? startingUsd;
  const equity = active ? (account?.equity ?? cap.equity ?? starting) : (persistedEquity ?? starting);
  const pnl = equity - starting;
  const returnPct = starting > 0 ? (pnl / starting) * 100 : 0;
  const leverageUsed = account?.leverage_used ?? null;
  const wins = rows.filter((r) => r.is_win).length;
  const winRate = rows.length > 0 ? (wins / rows.length) * 100 : null;
  const streak = useMemo(() => currentStreak(rows), [rows]);
  const today = new Date().toDateString();
  const closedToday = rows.filter((r) => r.closed_at && new Date(r.closed_at).toDateString() === today).length;

  return (
    <section className="cc">
      <div className="cc-hero">
        <div className="cc-hero-main">
          <div className="cc-kicker">
            <span className={`cc-live ${active && snap?.state === "running" ? "" : "off"}`}><i /> {active ? (snap?.state ?? "").toUpperCase() : "OFFLINE"}</span>
            <span>PAPER · REAL {snap?.symbol ?? "BTC/USDT"} MARKET · 24/7 · simulated fills</span>
            {account?.leverage_max != null && account.leverage_max > 1 && (
              <span className="cc-lev">LEVERAGE {account.leverage_max.toFixed(0)}x</span>
            )}
            {snap?.trend?.mode !== "off" && (
              <span className={`cc-tide ${snap?.trend?.available ? snap.trend.bias : "unknown"}`}>
                TIDE {snap?.trend?.available ? String(snap.trend.bias).toUpperCase() : "UNKNOWN"}
              </span>
            )}
          </div>
          <div className={`cc-big ${pnl > 0 ? "pos" : pnl < 0 ? "neg" : "neon"}`}>{money(equity, 2)}</div>
          <div className="cc-sub">
            <span className={pnl > 0 ? "pos" : pnl < 0 ? "neg" : ""}>{signedMoney(pnl)} ({returnPct >= 0 ? "+" : ""}{returnPct.toFixed(2)}%)</span>
            {` · started with ${money(starting, 0)} · simulated`}
            {leverageUsed != null && account?.leverage_max ? ` · leverage ${leverageUsed.toFixed(2)}x of ${account.leverage_max.toFixed(0)}x` : ""}
            {account?.liquidation_price != null ? ` · liquidation ≈ ${money(account.liquidation_price, 0)}` : ""}
            {(account?.funding?.payments ?? 0) > 0 ? ` · funding ${signedMoney(-(account?.funding?.paid_usd ?? 0))}` : ""}
            {(account?.liquidations ?? 0) > 0 ? ` · ${account?.liquidations} liquidation${(account?.liquidations ?? 0) > 1 ? "s" : ""}` : ""}
          </div>
        </div>
        <div className="cc-hero-side">
          <div className="stat">
            <span className="label">Win rate · last {rows.length}</span>
            <span className={`value ${(winRate ?? 0) >= 50 ? "pos" : "neon"}`}>{winRate == null ? "—" : `${winRate.toFixed(0)}%`}</span>
            <span className="sub">{source === "record" ? "simulation record until the session closes a trade" : "closed by the 24/7 session"}</span>
          </div>
          <div className="stat">
            <span className="label">Streak now</span>
            <span className={`value ${streak > 0 ? "pos" : streak < 0 ? "neg" : ""}`}>{streak === 0 ? "—" : `${Math.abs(streak)} ${streak > 0 ? "W" : "L"}`}</span>
            <span className="sub">{closedToday} closed today</span>
          </div>
          <div className="stat">
            <span className="label">Signals → orders</span>
            <span className="value">{counters.signals ?? 0} → {counters.orders ?? 0}</span>
            <span className="sub">
              {snap?.position?.open
                ? snap.position.protected
                  ? `in a trade · ${snap.position.stop_kind && snap.position.stop_kind !== "protective" ? snap.position.stop_kind : "protective"} stop${snap.position.r_multiple != null ? ` · ${snap.position.r_multiple.toFixed(1)}R` : ""}`
                  : "in a trade · NO STOP"
                : "flat"}
              {snap?.execution?.resting_order ? " · order resting" : ""}
            </span>
          </div>
        </div>
      </div>

      <div className="cc-grid">
        <div className="cc-panel">
          <div className="cc-title"><i /> Live streak <span className="faint">· last {Math.min(rows.length, STREAK_LENGTH)} trades</span></div>
          <StreakStrip rows={rows} />
          <div className="cc-legend"><span className="win">won</span><span className="loss">lost</span><span className="explore">exploration</span></div>
        </div>
        <div className="cc-panel">
          <div className="cc-title"><i /> Order ladder <span className="faint">· newest first</span></div>
          <div className="scroll" style={{ maxHeight: 190 }}><Ladder orders={orders} /></div>
        </div>
        <div className="cc-panel">
          <div className="cc-title"><i /> Market map <span className="faint">· result per trade</span></div>
          <MarketMap rows={rows} />
        </div>
      </div>
    </section>
  );
}
