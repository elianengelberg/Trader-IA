/**
 * Market Maker — the paper market maker, live on real Binance data.
 *
 * Everything on this page is simulated: quotes that were never sent, fills that only
 * happen when a real print reaches a resting simulated order past its estimated queue,
 * a $10,000 paper account of its own. It shows what the machine sees (book, features,
 * fair value), what it decides (quotes and why), what would have happened (fills,
 * inventory, P&L gross, fees, adverse selection, net), and the verdict on evidence —
 * which reads NO EDGE DETECTED until the out-of-sample rules hold.
 */
import { useCallback, useEffect, useState } from "react";
import { api, type MMJournalRow, type MMMetrics, type MMState } from "../lib/api";
import { Card, Empty, Pill, Stat } from "../components/ui";
import type { Subscribe } from "../lib/stream";

const REFRESH_MS = 3_000;
const METRICS_MS = 15_000;

const usd = (v: number | null | undefined, digits = 2) =>
  v == null ? "—" : `${v < 0 ? "-" : ""}$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
const px = (v: number | null | undefined) => (v == null ? "—" : v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const bps = (v: number | null | undefined, digits = 2) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(digits)} bps`);
const num = (v: number | null | undefined, digits = 3) => (v == null ? "—" : v.toFixed(digits));
const btc = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(5)} BTC`);
const when = (ms: number | null | undefined) => (ms ? new Date(ms).toISOString().slice(11, 23) : "—");
const tone = (v: number | null | undefined): "pos" | "neg" | "flat" => (v == null || v === 0 ? "flat" : v > 0 ? "pos" : "neg");

function gateTone(state?: string): string {
  if (state === "safe") return "pos";
  if (state === "data_invalid") return "warn";
  return "neg";
}

export function MarketMaker({ subscribe }: { subscribe: Subscribe }) {
  const [state, setState] = useState<MMState | null>(null);
  const [journal, setJournal] = useState<MMJournalRow[]>([]);
  const [metrics, setMetrics] = useState<MMMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, j] = await Promise.all([api.mmState(), api.mmJournal(80)]);
      setState(s);
      setJournal(j);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);
  const loadMetrics = useCallback(async () => {
    try {
      setMetrics(await api.mmMetrics());
    } catch {
      /* the state poll reports errors */
    }
  }, []);

  useEffect(() => {
    void load();
    void loadMetrics();
    const a = window.setInterval(() => void load(), REFRESH_MS);
    const b = window.setInterval(() => void loadMetrics(), METRICS_MS);
    return () => {
      window.clearInterval(a);
      window.clearInterval(b);
    };
  }, [load, loadMetrics]);

  useEffect(
    () =>
      subscribe("mm.state", (data) => {
        setState((prev) => ({ ...(prev ?? ({} as MMState)), ...(data as MMState) }));
      }),
    [subscribe],
  );
  useEffect(
    () =>
      subscribe("mm.journal", (data) => {
        setJournal((prev) => [...prev.slice(-79), data as MMJournalRow]);
      }),
    [subscribe],
  );

  const heading = <h1>Market Maker — paper only, simulated on real Binance data</h1>;
  if (error && !state) return <div className="stack">{heading}<Empty message={`Market maker: ${error}`} /></div>;
  if (!state) return <div className="stack">{heading}<Empty message="Loading the market maker…" /></div>;

  const led = state.ledger ?? {};
  const feats = state.features ?? {};
  const d = state.last_decision ?? null;
  const lat = state.latency as Partial<import("../lib/api").MMLatency> & { profile_path?: string; scenario?: string };
  const horizons = state.markouts?.horizons ?? {};
  const edge = metrics?.edge;

  return (
    <div className="stack">
      {heading}
      <Card
        title="Status"
        actions={
          <div className="row" style={{ gap: 6 }}>
            <Pill value={state.phase3_status} tone={state.running ? "pos" : "flat"} />
            {state.evidence_status && <Pill value={state.evidence_status} tone="warn" />}
            <Pill value={state.real_money ? "REAL MONEY" : "real money: disabled"} tone={state.real_money ? "neg" : "pos"} />
          </div>
        }
      >
        {!state.running ? (
          <p className="dim">
            {state.reason ?? "The paper market maker is not running."} Market data {state.market_data_enabled ? "is" : "is not"} enabled. Paper capital {usd(state.paper_capital, 0)}.
            Maker fee {state.fees.status.toLowerCase().replace(/_/g, " ")}: {String(state.fees.scenarios_bps.assumed)} bps assumed, {String(state.fees.scenarios_bps.adverse)} bps adverse.
          </p>
        ) : (
          <div className="grid cols-4" style={{ gap: 12 }}>
            <Stat label="Safety gate" value={<Pill value={state.gate?.state ?? "—"} tone={gateTone(state.gate?.state)} />} sub={state.gate?.reason || "quoting allowed"} />
            <Stat label="Book" value={state.book?.valid ? "valid" : state.book?.state ?? "—"} sub={`update ${state.book?.update_id ?? "—"} · data age ${feats.data_age_ms ?? "—"} ms`} />
            <Stat label="Latency scenario" value={lat.name ?? lat.scenario ?? "—"} sub={lat.order_latency_ms != null ? `order ${lat.order_latency_ms} ms · cancel ${lat.cancel_latency_ms} ms · profile ${lat.profile_id}` : lat.basis ?? ""} />
            <Stat label="Journal" value={state.journal_rows ?? 0} sub={`hash ${(state.journal_hash ?? "").slice(0, 12)} · config ${state.config_id ?? ""}`} />
          </div>
        )}
        <p className="dim" style={{ fontSize: 12, marginTop: 10 }}>
          {state.execution}. Quotes and fills here are simulated against real Binance prints; a fill needs a real trade to reach the resting simulated order past its estimated queue. Nothing on this page places an order.
        </p>
      </Card>

      {state.running && (
        <>
          <div className="grid cols-2">
            <Card title="Market">
              <div className="grid cols-4" style={{ gap: 12 }}>
                <Stat label="BTC mid" value={px(feats.mid as number)} sub={`bid ${px(state.book?.best_bid?.[0])} · ask ${px(state.book?.best_ask?.[0])}`} />
                <Stat label="Spread" value={bps(state.book?.spread_bps)} sub={`regime ${feats.spread_regime ?? "—"}`} />
                <Stat label="Microprice" value={px(feats.microprice as number)} sub={bps(feats.microprice_delta_bps as number)} />
                <Stat label="Fair value" value={px(d?.fair_value)} sub={d ? `${bps(d.components.fair_value_offset_bps as number)} · conf ${num(d.quote_confidence, 2)}` : "—"} />
                <Stat label="Imbalance" value={num(feats.imbalance_t1 as number, 2)} sub={`t5 ${num(feats.imbalance_t5 as number, 2)} · t10 ${num(feats.imbalance_t10 as number, 2)} · t20 ${num(feats.imbalance_t20 as number, 2)}`} />
                <Stat label="OFI (norm)" value={num(feats.ofi_norm as number, 2)} sub="1 s window" />
                <Stat label="Trade flow 5s" value={num(feats.flow_norm_5s as number, 2)} sub="net aggressive / total" />
                <Stat label="Volatility 5s" value={bps(feats.vol_5s_bps as number)} sub="std of mid changes" />
                <Stat label="Toxicity" value={state.toxicity?.overall.score == null ? "no evidence" : num(state.toxicity.overall.score, 2)} sub={state.toxicity?.overall.reason ?? ""} />
              </div>
            </Card>
            <Card title="Simulated quotes">
              {d ? (
                <>
                  <div className="grid cols-4" style={{ gap: 12 }}>
                    <Stat label="Sim bid" value={px(d.bid_price)} sub={d.bid_price ? `${d.bid_size.toFixed(5)} BTC` : "no bid"} tone={d.bid_price ? "pos" : "flat"} />
                    <Stat label="Sim ask" value={px(d.ask_price)} sub={d.ask_price ? `${d.ask_size.toFixed(5)} BTC` : "no ask"} tone={d.ask_price ? "neg" : "flat"} />
                    <Stat label="Half-spread" value={bps(d.half_spread_bps)} sub={`target ${bps(d.spread_target_bps)} · ${String(d.components.spread_binding ?? "")}`} />
                    <Stat label="Inventory adj." value={bps(d.components.inventory_adjustment_bps as number)} sub={`toxicity +${num(d.components.toxicity_widen_bps as number, 2)} bps`} />
                  </div>
                  <p className="dim" style={{ fontSize: 12, marginTop: 8 }}>{d.quote_reason}</p>
                </>
              ) : (
                <Empty message={state.last_block_reason ? `No quotes: ${state.last_block_reason}` : "No decision yet."} />
              )}
              <table style={{ marginTop: 8 }}>
                <thead><tr><th>Order</th><th>Side</th><th>Price</th><th>Size</th><th>Filled</th><th>Queue est.</th><th>State</th><th>Arrives</th></tr></thead>
                <tbody>
                  {(state.active_orders ?? []).length === 0 && <tr><td colSpan={8} className="dim">no active simulated orders</td></tr>}
                  {(state.active_orders ?? []).map((o) => (
                    <tr key={o.order_id}>
                      <td className="mono">{o.order_id.slice(-6)}</td>
                      <td>{o.side}</td>
                      <td className="mono">{px(o.price)}</td>
                      <td className="mono">{o.quantity.toFixed(5)}</td>
                      <td className="mono">{o.filled.toFixed(5)}{o.unresolved > 0 ? ` (+${o.unresolved.toFixed(5)} unresolved)` : ""}</td>
                      <td className="mono">{o.queue ? `${o.queue.estimated_queue_position.toFixed(3)} ahead` : "in flight"}</td>
                      <td>{o.state}</td>
                      <td className="mono">{when(o.t_arrival_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>

          <div className="grid cols-2">
            <Card title="Paper account ($10,000, separate)">
              <div className="grid cols-4" style={{ gap: 12 }}>
                <Stat label="Equity" value={usd(led.equity_usd as number)} sub={`conservative ${usd(led.equity_conservative_usd as number)}`} />
                <Stat label="Net P&L" value={usd(led.net_pnl_usd as number)} tone={tone(led.net_pnl_usd as number)} sub={`conservative ${usd(led.net_pnl_conservative_usd as number)}`} />
                <Stat label="Gross P&L" value={usd(led.gross_pnl_usd as number)} sub={`realised ${usd(led.realised_pnl_usd as number)}`} />
                <Stat label="Fees" value={usd(led.fees_usd as number)} sub={`adverse sel. ${usd(led.adverse_selection_usd as number)} · slippage ${usd(led.slippage_usd as number)}`} />
                <Stat label="Inventory" value={btc(led.inventory_btc as number)} sub={`max ${btc(led.max_inventory_btc as number)} · limit ${btc(state.controller?.limits.max_inventory_btc)}`} />
                <Stat label="Drawdown" value={`${num(led.drawdown_pct as number, 2)}%`} sub={`daily ${usd(led.daily_pnl_usd as number)}`} />
                <Stat label="Fills" value={String(led.fills ?? 0)} sub={`unresolved events ${String((state.execution_stats as Record<string, unknown> | undefined)?.unresolved_fill_events ?? state.markouts?.expired_unresolved ?? 0)}`} />
                <Stat label="Kill switch" value={state.controller?.kill_switch ? "ENGAGED" : "clear"} tone={state.controller?.kill_switch ? "neg" : "pos"} sub={state.controller?.kill_switch_reason || `${state.controller?.quotes_last_minute ?? 0} quotes/min`} />
              </div>
            </Card>
            <Card title="Activity & data quality">
              <div className="grid cols-4" style={{ gap: 12 }}>
                <Stat label="Decisions" value={state.decisions ?? 0} sub={`quotes ${state.quotes ?? 0} · requotes ${state.requotes ?? 0}`} />
                <Stat label="Cancels" value={state.cancels ?? 0} sub={`gate blocks ${state.gate_blocks ?? 0} · data blocks ${state.data_blocks ?? 0}`} />
                <Stat label="Markouts" value={state.markouts?.resolved ?? 0} sub={`pending ${state.markouts?.pending ?? 0} · expired ${state.markouts?.expired_unresolved ?? 0}`} />
                <Stat label="Events" value={state.events ?? 0} sub={`processed in order of arrival`} />
              </div>
              <table style={{ marginTop: 8 }}>
                <thead><tr><th>Horizon</th><th>Fills</th><th>Mean markout</th><th>Adverse share</th><th>Mean adverse</th></tr></thead>
                <tbody>
                  {Object.entries(horizons).map(([h, v]) => (
                    <tr key={h}><td>{Number(h) >= 1000 ? `${Number(h) / 1000} s` : `${h} ms`}</td><td className="mono">{v.count}</td><td className="mono">{bps(v.mean_bps)}</td><td className="mono">{v.adverse_share == null ? "—" : `${(v.adverse_share * 100).toFixed(0)}%`}</td><td className="mono">{bps(v.mean_adverse_bps)}</td></tr>
                  ))}
                </tbody>
              </table>
              {Object.keys(state.no_quote_reasons ?? {}).length > 0 && (
                <p className="dim" style={{ fontSize: 12, marginTop: 8 }}>
                  No-quote reasons: {Object.entries(state.no_quote_reasons ?? {}).map(([k, v]) => `${k} ×${v}`).join(" · ")}
                </p>
              )}
            </Card>
          </div>

          <Card title="Evidence">
            {!metrics?.available ? (
              <Empty message={metrics?.reason ?? "no metrics yet"} />
            ) : (
              <>
                <div className="row" style={{ gap: 8, alignItems: "center" }}>
                  <Pill value={edge?.verdict ?? "NO EDGE DETECTED"} tone={edge?.verdict === "EDGE DETECTED" ? "pos" : "warn"} />
                  <span className="dim" style={{ fontSize: 12 }}>scenario latency {metrics.scenario?.latency} · fees {metrics.scenario?.fees}</span>
                </div>
                <ul className="dim" style={{ fontSize: 12, marginTop: 8 }}>
                  {(edge?.failed_rules ?? []).map((r) => <li key={r}>{r}</li>)}
                </ul>
                <div className="grid cols-4" style={{ gap: 12, marginTop: 8 }}>
                  <Stat label="Fill ratio" value={metrics.ratios?.fill_ratio == null ? "—" : `${(metrics.ratios.fill_ratio * 100).toFixed(1)}%`} sub={`cancel ratio ${metrics.ratios?.cancel_ratio == null ? "—" : `${(metrics.ratios.cancel_ratio * 100).toFixed(1)}%`}`} />
                  <Stat label="P&L per fill" value={usd((metrics.pnl?.pnl_per_fill_usd as number | null) ?? null, 4)} sub={`per quote ${usd((metrics.pnl?.pnl_per_quote_usd as number | null) ?? null, 4)}`} />
                  <Stat label="Spread capture" value={usd((metrics.pnl?.gross_spread_capture_usd as number | null) ?? null, 4)} sub={`adverse sel. ${usd((metrics.pnl?.adverse_selection_usd as number | null) ?? null, 4)}`} />
                  <Stat label="Unresolved share" value={metrics.counts?.unresolved_share == null ? "—" : `${((metrics.counts.unresolved_share as number) * 100).toFixed(1)}%`} sub={`utilisation ${metrics.inventory?.inventory_utilization == null ? "—" : `${((metrics.inventory.inventory_utilization as number) * 100).toFixed(0)}%`}`} />
                </div>
                {metrics.by_regime && (
                  <table style={{ marginTop: 8 }}>
                    <thead><tr><th>Split</th><th>Bucket</th><th>Fills</th><th>Net</th><th>Net / fill</th><th>Markout 1 s</th></tr></thead>
                    <tbody>
                      {Object.entries(metrics.by_regime).flatMap(([key, buckets]) =>
                        Object.entries(buckets).map(([label, v]) => (
                          <tr key={`${key}-${label}`}><td>{key}</td><td>{label}</td><td className="mono">{v.fills}</td><td className="mono">{usd(v.net_usd, 4)}</td><td className="mono">{usd(v.net_per_fill_usd, 4)}</td><td className="mono">{bps(v.markout_1s_bps_mean)}</td></tr>
                        )),
                      )}
                    </tbody>
                  </table>
                )}
              </>
            )}
          </Card>

          <Card title="Journal (why each quote, cancel and fill)">
            <table>
              <thead><tr><th>Time</th><th>Kind</th><th>Decision</th><th>Fair value</th><th>Bid</th><th>Ask</th><th>Inventory</th><th>Reason / result</th></tr></thead>
              <tbody>
                {journal.length === 0 && <tr><td colSpan={8} className="dim">no journal rows yet</td></tr>}
                {[...journal].reverse().map((r, i) => (
                  <tr key={`${r.t}-${i}`}>
                    <td className="mono">{when(r.t)}</td>
                    <td>{r.kind}{r.layer ? ` (${r.layer})` : ""}</td>
                    <td>{r.decision ?? (r.kind === "fill" ? `${r.side} fill` : r.kind === "markout" ? "markout" : "")}</td>
                    <td className="mono">{px(r.fair_value)}</td>
                    <td className="mono">{r.kind === "fill" ? px(r.price) : px(r.bid ?? null)}</td>
                    <td className="mono">{r.kind === "fill" ? `${(r.quantity ?? 0).toFixed(5)} BTC` : px(r.ask ?? null)}</td>
                    <td className="mono">{r.inventory_btc == null ? "—" : r.inventory_btc.toFixed(5)}</td>
                    <td className="dim" style={{ fontSize: 11.5 }}>
                      {r.kind === "fill"
                        ? `fee ${usd(r.fee_usd, 4)} · realised ${usd(r.realised_usd, 4)} · trades ${String(r.venue_trade_ids ?? "")}`
                        : r.kind === "markout"
                          ? Object.entries(r.markout_bps ?? {}).map(([h, v]) => `${h}ms ${bps(v)}`).join(" · ")
                          : r.reason}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  );
}
