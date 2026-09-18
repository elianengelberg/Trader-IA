/**
 * Arbitrage — the viral claim, measured instead of believed.
 *
 * A post says a student turned less than a dollar into four hundred thousand by scanning
 * exchanges for small price gaps. This page runs that idea against real quotes: the same
 * bitcoin on Binance, Coinbase and Kraken, every gap between them recorded, every venue's
 * taker fee subtracted. What it shows is what was measured — the best gap, how often fees
 * were cleared, and the most a perfect executor with $100 could have made.
 *
 * Read-only public data. Nothing here places an order or reaches the trading pipeline.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type ArbGap, type ArbVenue, type ArbitrageReport, type FundingReport, type SpreadCheck } from "../lib/api";
import { Card, Empty, Pill, Stat } from "../components/ui";
import { clock, money } from "../lib/format";

const REFRESH_MS = 15_000;

const usd = (v: number, digits = 2) =>
  `${v < 0 ? "-" : ""}$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
const bps = (v: number | null | undefined, digits = 1) =>
  v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(digits)} bps`;

function age(iso: string | null): string {
  if (!iso) return "never";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  return s < 90 ? `${s}s ago` : `${Math.round(s / 60)}m ago`;
}

function span(seconds: number): string {
  if (seconds < 90) return `${Math.round(seconds)}s`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

/** Best net gap over time, with the zero line — above it fees were cleared. */
function GapChart({ points, height = 160 }: { points: ArbitrageReport["history"]; height?: number }) {
  const width = 720;
  const pad = { l: 44, r: 10, t: 10, b: 20 };
  const nets = points.map((p) => p.net_bps);
  const lo = Math.min(0, ...nets), hi = Math.max(0, ...nets);
  const range = hi - lo || 1;
  const x = (i: number) => pad.l + (i / Math.max(1, points.length - 1)) * (width - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - (v - lo) / range) * (height - pad.t - pad.b);
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.net_bps).toFixed(1)}`).join(" ");
  const zero = y(0);
  const ticks = [hi, (hi + lo) / 2, lo];
  return (
    <svg className="arb-chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="Best net gap over time">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={pad.l} x2={width - pad.r} y1={y(t)} y2={y(t)} className="arb-grid" />
          <text x={pad.l - 6} y={y(t) + 3.5} className="arb-tick">{t.toFixed(0)}</text>
        </g>
      ))}
      <line x1={pad.l} x2={width - pad.r} y1={zero} y2={zero} className="arb-zero" />
      <text x={width - pad.r} y={zero - 4} className="arb-tick" textAnchor="end">fees cleared ↑</text>
      {points.length > 1 && <path d={path} className="arb-line" />}
      {points.map((p, i) =>
        p.net_bps > 0 ? <circle key={i} cx={x(i)} cy={y(p.net_bps)} r={3} className="arb-hit" /> : null,
      )}
    </svg>
  );
}

function VenueCard({ venue }: { venue: ArbVenue }) {
  const tone = venue.ok === null ? "" : venue.ok ? "ok" : "bad";
  return (
    <div className={`arb-venue ${venue.ok === false ? "down" : ""}`}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <strong>{venue.name}</strong>
        <Pill value={venue.ok === null ? "pending" : venue.ok ? "quoted" : "down"} tone={tone} />
      </div>
      {venue.bid != null && venue.ask != null ? (
        <div className="arb-quote">
          <div><span className="label">bid</span><span className="pos mono">{money(venue.bid, 2)}</span></div>
          <div><span className="label">ask</span><span className="neg mono">{money(venue.ask, 2)}</span></div>
          <div><span className="label">spread</span><span className="mono">{venue.spread_bps?.toFixed(2)} bps</span></div>
        </div>
      ) : (
        <p className="faint" style={{ margin: "8px 0", fontSize: 12 }}>{venue.detail || "waiting for the first quote"}</p>
      )}
      <div style={{ fontSize: 11, color: "var(--text-faint)" }}>
        taker fee <strong className="mono">{venue.taker_fee_bps.toFixed(0)} bps</strong> · quoted {age(venue.quoted_at)}
        {venue.failures > 0 && ` · ${venue.failures} failed polls`}
      </div>
      <div style={{ fontSize: 10.5, color: "var(--text-faint)", marginTop: 3 }} title={venue.fee_source}>
        {venue.fee_source}
      </div>
    </div>
  );
}

function GapTable({ gaps, names }: { gaps: ArbGap[]; names: Record<string, string> }) {
  if (gaps.length === 0) return <Empty message="Fewer than two venues are quoting, so there is no gap to measure." />;
  return (
    <table>
      <thead>
        <tr>
          <th>Buy at</th>
          <th>Sell at</th>
          <th className="num">Gross</th>
          <th className="num">Fees</th>
          <th className="num">Net</th>
          <th className="num">On $1</th>
          <th className="num">On $100</th>
          <th className="num">On $10,000</th>
        </tr>
      </thead>
      <tbody>
        {gaps.map((g) => (
          <tr key={`${g.buy_venue}-${g.sell_venue}`} className={g.clears_costs ? "arb-clears" : ""}>
            <td>{names[g.buy_venue] ?? g.buy_venue} <span className="faint">@ {money(g.buy_ask, 2)}</span></td>
            <td>{names[g.sell_venue] ?? g.sell_venue} <span className="faint">@ {money(g.sell_bid, 2)}</span></td>
            <td className={`num ${g.gross_bps >= 0 ? "" : "faint"}`}>{bps(g.gross_bps, 2)}</td>
            <td className="num neg">-{g.fee_bps.toFixed(0)} bps</td>
            <td className={`num ${g.clears_costs ? "pos" : "neg"}`}><strong>{bps(g.net_bps, 2)}</strong></td>
            <td className={`num ${g.clears_costs ? "pos" : "neg"}`}>{usd(g.net_usd_per_100 / 100, 4)}</td>
            <td className={`num ${g.clears_costs ? "pos" : "neg"}`}>{usd(g.net_usd_per_100, 3)}</td>
            <td className={`num ${g.clears_costs ? "pos" : "neg"}`}>{usd(g.net_usd_per_10k, 2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * The perpetual market's price of leverage. The BIS finds crypto carry averages above
 * 10% a year and that HIGH carry predicts crashes — a crowded long book. Shown as a
 * yield and as a warning, with a year of settlements so "high" means something.
 */
function FundingCard() {
  const [report, setReport] = useState<FundingReport | null>(null);

  useEffect(() => {
    const load = () => api.funding().then(setReport).catch(() => undefined);
    load();
    const id = window.setInterval(() => { if (!document.hidden) load(); }, 60_000);
    return () => window.clearInterval(id);
  }, []);

  const latest = report?.latest ?? null;
  const pct = (v: number | null | undefined, digits = 1) =>
    v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
  const tone = report?.stance === "crowded long" ? "neg" : report?.stance === "crowded short" ? "warn" : "";
  return (
    <Card title="Carry — the perpetual's funding rate, measured against a year of it">
      {!report ? (
        <Empty message="Reading the funding rate…" />
      ) : !latest ? (
        <Empty message={`No funding reading: ${report.health.detail || "the endpoint did not answer"}.`} />
      ) : (
        <>
          <div className="grid cols-4" style={{ gap: 12 }}>
            <Stat label="Funding now" value={`${latest.funding_bps >= 0 ? "+" : ""}${latest.funding_bps.toFixed(2)} bps / 8h`} sub={`${pct(latest.annualised_pct)} annualised`} tone={latest.funding_bps > 0 ? "pos" : latest.funding_bps < 0 ? "neg" : "flat"} />
            <Stat label="Last week" value={pct(report.mean_annualised_pct_7d)} sub={`year mean ${pct(report.mean_annualised_pct_all)}`} />
            <Stat label="Percentile · 1 year" value={report.percentile == null ? "—" : `${report.percentile.toFixed(0)}th`} sub={report.stance} tone={tone as "neg" | "warn" | undefined} />
            <Stat label="Cash-and-carry, net" value={pct(report.carry.net_annualised_pct)} sub={`after ${report.carry.fee_round_trip_bps} bps of fees · upper bound`} tone={(report.carry.net_annualised_pct ?? 0) > 0 ? "pos" : "neg"} />
          </div>
          <p style={{ fontSize: 13, lineHeight: 1.6, marginTop: 14 }}>{report.verdict}</p>
          <p className="footnote" style={{ marginTop: 10 }}>
            Basis (mark over index): {latest.basis_bps == null ? "—" : `${latest.basis_bps >= 0 ? "+" : ""}${latest.basis_bps.toFixed(2)} bps`} ·
            {" "}{report.history_settlements} settlements over {report.history_span_days} days · {report.carry.assumes}.
            Read-only: nothing here places an order. The Advisor sees this reading; the trading pipeline does not act on it.
          </p>
        </>
      )}
    </Card>
  );
}

/**
 * "Earn the spread a hundred times a second." Priced against the book as it is: the
 * spread the venue shows, the maker fee on both legs, the orders per second the venue
 * accepts, and the market's own volume. A calculation, not a simulation — the paper
 * engine cannot model a queue and would overstate every fill.
 */
function SpreadCaptureCard() {
  const [check, setCheck] = useState<SpreadCheck | null>(null);
  const [size, setSize] = useState(0.01);

  useEffect(() => {
    const load = () => api.spreadCheck(size).then(setCheck).catch(() => undefined);
    load();
    const id = window.setInterval(() => { if (!document.hidden) load(); }, 10_000);
    return () => window.clearInterval(id);
  }, [size]);

  const usd4 = (v: number | undefined) => (v == null ? "—" : `${v < 0 ? "-" : ""}$${Math.abs(v).toFixed(4)}`);
  return (
    <Card
      title="Spread capture — the idea, priced on the live book"
      actions={
        <div className="row" style={{ gap: 6 }}>
          {[0.01, 0.1, 1].map((s) => (
            <button key={s} className={`btn small ${size === s ? "primary" : ""}`} onClick={() => setSize(s)}>{s} BTC</button>
          ))}
        </div>
      }
    >
      {!check?.available ? (
        <Empty message={check?.reason ?? "Waiting for the live book…"} />
      ) : (
        <>
          <div className="grid cols-4" style={{ gap: 12 }}>
            <Stat label="Spread now" value={`$${(check.spread_usd ?? 0).toFixed(2)}`} sub={`${(check.spread_bps ?? 0).toFixed(3)} bps · bid ${check.bid_size} / ask ${check.ask_size} BTC`} />
            <Stat label={`Round trip on ${check.size_btc} BTC`} value={usd4(check.net_per_round_trip_usd)} sub={`earns ${usd4(check.gross_per_round_trip_usd)} · pays ${usd4(check.fees_per_round_trip_usd)} in fees`} tone={(check.net_per_round_trip_usd ?? 0) > 0 ? "pos" : "neg"} />
            <Stat label="Spread needed to break even" value={`$${(check.breakeven_spread_usd ?? 0).toFixed(2)}`} sub={`${check.maker_fee_bps_per_leg} bps maker fee per leg`} />
            <Stat label="Venue order limit" value={`${check.max_round_trips_per_s} round trips / s`} sub={`${check.order_limit_per_10s} orders per 10 s · ${(check.order_limit_per_day ?? 0).toLocaleString("en-US")} per day`} />
          </div>
          <p style={{ fontSize: 13, lineHeight: 1.6, marginTop: 14 }}>{check.verdict}</p>
          <p className="footnote" style={{ marginTop: 10 }}>
            The market trades about {check.market_btc_per_s} BTC a second (${(check.market_usd_per_s ?? 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}/s) on the last bar
            {check.share_of_market_at_100_per_s != null ? `; a hundred fills a second at ${check.size_btc} BTC would be the other side of ${(check.share_of_market_at_100_per_s * 100).toFixed(0)}% of it` : ""}.
            {" "}{(check.caveats ?? []).join(" ")}
          </p>
        </>
      )}
    </Card>
  );
}

export function Arbitrage() {
  const [report, setReport] = useState<ArbitrageReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback((force = false) => {
    setLoading(true);
    api.arbitrage(force)
      .then((r) => { setReport(r); setError(""); })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "request failed"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    const id = window.setInterval(() => { if (!document.hidden) load(); }, REFRESH_MS);
    return () => window.clearInterval(id);
  }, [load]);

  const names = useMemo(
    () => Object.fromEntries((report?.venues ?? []).map((v) => [v.venue_id, v.name])),
    [report],
  );

  const stats = report?.stats;
  const hyp = report?.hypothetical;
  const share = stats?.opportunity_share ?? null;
  const best = stats?.best_net_bps ?? null;

  return (
    <>
      <h1>Arbitrage — the viral claim, measured</h1>
      <p className="section-note">
        &ldquo;A bot turned less than $1 into $400,000 by scanning exchanges for small price
        gaps.&rdquo; This page runs that idea against real quotes: the same bitcoin on three
        exchanges, every gap between them recorded, every venue&apos;s taker fee subtracted.
        <strong> Read-only:</strong> no order is placed anywhere, and nothing here reaches
        the trading pipeline. What you see is what was measured.
      </p>

      {error && <div className="banner warn">{error}</div>}

      <div className="cc-hero arb-hero">
        <div className="cc-hero-main">
          <div className="cc-kicker">
            <span className="cc-live"><i /> {report?.running ? "SCANNING" : "IDLE"}</span>
            <span>{report?.instrument ?? "BTC/USDT"} · {report?.venues_ok ?? 0}/{report?.venues.length ?? 3} venues · every {report?.poll_seconds ?? 15}s</span>
          </div>
          <div className={`cc-big ${best != null && best > 0 ? "pos" : "neon"}`}>{bps(best)}</div>
          <div className="cc-sub">
            best gap after fees · {stats?.best_pair ?? "no pair yet"}
            {stats?.best_at ? ` · at ${clock(stats.best_at)}` : ""}
          </div>
        </div>
        <div className="cc-hero-side">
          <Stat label="Fees cleared" value={share == null ? "—" : `${(share * 100).toFixed(1)}%`} sub={`of ${stats?.samples_measured ?? 0} samples over ${span(stats?.span_seconds ?? 0)}`} tone={share ? "pos" : "warn"} />
          <Stat label="Typical best gap" value={bps(stats?.mean_best_net_bps)} sub="mean of the best pair, net" tone={(stats?.mean_best_net_bps ?? -1) > 0 ? "pos" : "neg"} />
          <Stat
            label="Perfect executor, $100"
            value={hyp ? usd(hyp.net_usd, 4) : "—"}
            sub={hyp?.net_usd_per_hour != null ? `${usd(hyp.net_usd_per_hour, 4)} / hour · ${hyp.round_trips} round trips` : `${hyp?.round_trips ?? 0} round trips · upper bound`}
            tone={(hyp?.net_usd ?? 0) > 0 ? "pos" : "flat"}
          />
        </div>
      </div>

      <div className="grid cols-3" style={{ marginTop: 16 }}>
        {(report?.venues ?? []).map((v) => <VenueCard key={v.venue_id} venue={v} />)}
      </div>

      <div style={{ marginTop: 16 }}>
        <Card
          title="Every pair, right now — net of taker fees"
          actions={
            <button className="btn small" disabled={loading} onClick={() => load(true)}>
              {loading ? "Polling…" : "Poll now"}
            </button>
          }
        >
          <GapTable gaps={report?.gaps ?? []} names={names} />
          <p className="footnote" style={{ marginTop: 12 }}>
            Gross is the sell venue&apos;s bid over the buy venue&apos;s ask. Fees are both
            venues&apos; taker rates at the retail tier — the tier a &ldquo;$1 start&rdquo;
            sits in. A row lights up green when the net clears zero; that is the whole trade,
            and the columns to the right say what it is worth at each size.
          </p>
        </Card>
      </div>

      <div style={{ marginTop: 16 }}>
        <Card title="Best net gap over time">
          {(report?.history.length ?? 0) > 1 ? (
            <GapChart points={report?.history ?? []} />
          ) : (
            <Empty message="Collecting samples — the line appears after the second poll." />
          )}
        </Card>
      </div>

      <div style={{ marginTop: 16 }}>
        <FundingCard />
      </div>

      <div style={{ marginTop: 16 }}>
        <SpreadCaptureCard />
      </div>

      <div style={{ marginTop: 16 }}>
        <Card title="Verdict — from the record, not the post">
          <p style={{ marginTop: 0, fontSize: 13.5, lineHeight: 1.6 }}>{report?.verdict ?? "Waiting for the first poll…"}</p>
          <div className="grid cols-2" style={{ gap: 12, marginTop: 8 }}>
            <div className="card" style={{ background: "var(--bg-input)" }}>
              <h2>The arithmetic on one dollar</h2>
              <ul className="arb-list">
                <li>Fees at the retail tier: <span className="mono">{report ? `${report.venues.map((v) => v.taker_fee_bps).sort((a, b) => a - b).slice(0, 2).reduce((a, b) => a + b, 0).toFixed(0)}` : "50"} bps</span> for the cheapest pair of legs — half a cent on $1, before the gap has paid anything.</li>
                <li>The best gap measured here is worth <span className="mono">{best == null ? "—" : usd(best / 10_000, 5)}</span> on one dollar.</li>
                <li>On-chain the same trade pays 25–30 bps of swap fees <em>per leg</em> plus priority fees, and competes with bots that see the same gap in the same block.</li>
                <li>Nothing in a gap of a few basis points compounds a dollar into anything. A claim of $1 → $400,000 needs a 40-million-fold return; the report above is measuring cents.</li>
              </ul>
            </div>
            <div className="card" style={{ background: "var(--bg-input)" }}>
              <h2>What the net number still leaves out</h2>
              <ul className="arb-list">
                {(report?.caveats ?? []).map((c) => <li key={c}>{c}</li>)}
              </ul>
              {hyp && <p className="faint" style={{ fontSize: 11.5, marginBottom: 0 }}>Hypothetical: {hyp.assumes}.</p>}
            </div>
          </div>
        </Card>
      </div>
    </>
  );
}
