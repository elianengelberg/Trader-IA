/**
 * The Trade Journal — every closed round trip the system has on record.
 *
 * Training simulations, demo runs and the 24/7 session all land here, newest first,
 * each with what the system expected, what it got, and what that was worth at the size
 * the trade actually carried. The filters are the point: "how do longs do in ranging
 * markets?" is a strip of totals, not a scroll. The totals are computed over the whole
 * filtered set on the server, so they mean what they say regardless of the page shown.
 */
import { useCallback, useEffect, useState } from "react";
import { api, type JournalFilters, type JournalPage, type SetupRow } from "../lib/api";
import { Card, Empty, Pill, SimulationFootnote, Stat } from "../components/ui";
import { dateTime, money, signedMoney } from "../lib/format";

const REGIMES = ["trending_up", "trending_down", "ranging", "high_volatility", "low_volatility"];
const PAGE = 50;

const SOURCE_TONE: Record<string, string> = { live: "ok", sim: "", paper: "info" };
const SOURCE_LABEL: Record<string, string> = {
  live: "24/7 session",
  sim: "training",
  paper: "demo",
};

export function Journal() {
  const [page, setPage] = useState<JournalPage | null>(null);
  const [setups, setSetups] = useState<SetupRow[]>([]);
  const [filters, setFilters] = useState<JournalFilters>({ limit: PAGE, offset: 0 });
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api.journal(filters).then(setPage).catch(() => undefined).finally(() => setLoading(false));
    api.journalSetups(filters.source).then(setSetups).catch(() => undefined);
  }, [filters]);

  useEffect(load, [load]);
  // New trades close on their own — the session and any running trainer both write
  // here — so the first page keeps itself current. Deeper pages are history and stay put.
  useEffect(() => {
    if ((filters.offset ?? 0) > 0) return;
    const id = window.setInterval(() => {
      if (!document.hidden) load();
    }, 30_000);
    return () => window.clearInterval(id);
  }, [filters.offset, load]);

  const set = (patch: Partial<JournalFilters>) =>
    setFilters((previous) => ({ ...previous, ...patch, offset: 0 }));

  const summary = page?.summary;
  const total = page?.total ?? 0;
  const offset = filters.offset ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + PAGE, total);

  const select = (
    label: string,
    value: string | undefined,
    options: [string, string][],
    onChange: (value: string) => void,
  ) => (
    <label className="field" style={{ minWidth: 150 }}>
      {label}
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
        <option value="">All</option>
        {options.map(([id, text]) => (
          <option key={id} value={id}>{text}</option>
        ))}
      </select>
    </label>
  );

  return (
    <>
      <h1>Trade Journal</h1>
      <p className="section-note">
        Every round trip the system has ever closed, newest first — training simulations,
        demo runs and the 24/7 session alike. Each row is what the system{" "}
        <em>expected</em> against what it <em>got</em>, in dollars at the size the trade
        actually carried. Filter to a setup and the totals answer for that setup: this is
        the record every next decision can be checked against.
      </p>

      <Card>
        <div className="row" style={{ gap: 14, flexWrap: "wrap", alignItems: "flex-end" }}>
          {select("Source", filters.source, [
            ["live", "24/7 session"], ["sim", "Training"], ["paper", "Demo"],
          ], (v) => set({ source: v || undefined }))}
          {select("Regime", filters.regime, REGIMES.map((r) => [r, r.replace("_", " ")]),
            (v) => set({ regime: v || undefined }))}
          {select("Direction", filters.direction, [["long", "Long"], ["short", "Short"]],
            (v) => set({ direction: v || undefined }))}
          {select("Outcome", filters.outcome, [["win", "Won"], ["loss", "Lost"]],
            (v) => set({ outcome: v || undefined }))}
          <button
            className="btn small"
            onClick={() => setFilters({ limit: PAGE, offset: 0 })}
            disabled={!filters.source && !filters.regime && !filters.direction && !filters.outcome}
          >
            Clear filters
          </button>
        </div>
      </Card>

      {summary && (
        <div className="grid cols-4" style={{ margin: "16px 0" }}>
          <div className="card">
            <Stat label="Trades in this view" value={summary.trades.toLocaleString("en-US")}
              sub={`${summary.wins.toLocaleString("en-US")} won`} />
          </div>
          <div className="card">
            <Stat label="Win rate" value={`${(summary.win_rate * 100).toFixed(0)}%`}
              tone={summary.win_rate >= 0.5 ? "pos" : summary.trades ? "neg" : "flat"}
              sub="of the filtered set, not the page" />
          </div>
          <div className="card">
            <Stat label="Net result" value={`${signedMoney(summary.pnl_usd)}`}
              tone={summary.pnl_usd > 0 ? "pos" : summary.pnl_usd < 0 ? "neg" : "flat"}
              sub="simulated dollars, at each trade's own size" />
          </div>
          <div className="card">
            <Stat label="Mean per trade" value={`${signedMoney(summary.mean_trade_usd)}`}
              tone={summary.mean_trade_usd > 0 ? "pos" : summary.mean_trade_usd < 0 ? "neg" : "flat"}
              sub="net of fees" />
          </div>
        </div>
      )}

      {setups.length > 0 && (
        <Card title="By setup — where the record is good and where it is not">
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>Setup</th>
                  <th className="num">Trades</th>
                  <th className="num">Win rate</th>
                  <th className="num">Net</th>
                  <th className="num">Mean / trade</th>
                </tr>
              </thead>
              <tbody>
                {setups.map((row) => (
                  <tr key={`${row.regime}|${row.direction}`}>
                    <td className="mono">
                      <span className={row.direction === "long" ? "pos" : "neg"}>{row.direction}</span>
                      {" · "}{row.regime.replace("_", " ")}
                    </td>
                    <td className="num mono">{row.trades.toLocaleString("en-US")}</td>
                    <td className={`num mono ${row.win_rate >= 0.5 ? "pos" : ""}`}>
                      {(row.win_rate * 100).toFixed(0)}%
                    </td>
                    <td className={`num mono ${row.pnl_usd > 0 ? "pos" : "neg"}`}>
                      {signedMoney(row.pnl_usd)}
                    </td>
                    <td className={`num mono ${row.mean_trade_usd > 0 ? "pos" : "neg"}`}>
                      {signedMoney(row.mean_trade_usd)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="footnote">
            Best net result first, over the selected source. A setup that is green here is
            one the expected-value engine can already price; a red one with many trades is
            evidence of where <em>not</em> to be — which is also learning.
          </p>
        </Card>
      )}

      <Card
        title={`Closed round trips ${total ? `· ${from.toLocaleString("en-US")}–${to.toLocaleString("en-US")} of ${total.toLocaleString("en-US")}` : ""}`}
        actions={
          <div className="row" style={{ gap: 8 }}>
            <button className="btn small" disabled={offset === 0 || loading}
              onClick={() => setFilters((f) => ({ ...f, offset: Math.max(0, (f.offset ?? 0) - PAGE) }))}>
              ← Newer
            </button>
            <button className="btn small" disabled={offset + PAGE >= total || loading}
              onClick={() => setFilters((f) => ({ ...f, offset: (f.offset ?? 0) + PAGE }))}>
              Older →
            </button>
          </div>
        }
      >
        {!page ? (
          <Empty message="Loading…" />
        ) : page.rows.length === 0 ? (
          <Empty message={page.error ?? "No closed trades match these filters yet."} />
        ) : (
          <div className="scroll tall">
            <table>
              <thead>
                <tr>
                  <th>Closed</th>
                  <th>Source</th>
                  <th>Setup</th>
                  <th className="num">Conf.</th>
                  <th className="num">Entry → Exit</th>
                  <th className="num">Size</th>
                  <th className="num">Expected</th>
                  <th className="num">Got</th>
                  <th className="num">Fees</th>
                  <th>Exit</th>
                </tr>
              </thead>
              <tbody>
                {page.rows.map((row) => (
                  <tr key={row.outcome_id}>
                    <td className="mono faint" style={{ whiteSpace: "nowrap" }}>
                      {dateTime(row.closed_at ?? "")}
                    </td>
                    <td>
                      <Pill value={SOURCE_LABEL[row.source] ?? row.source} tone={SOURCE_TONE[row.source] ?? ""} />
                      {row.exploratory && (
                        <span style={{ marginLeft: 6 }}>
                          <Pill value="exploration" tone="info" />
                        </span>
                      )}
                    </td>
                    <td className="mono">
                      <span className={row.direction === "long" ? "pos" : "neg"}>{row.direction}</span>
                      {" · "}{row.regime.replace("_", " ")}
                    </td>
                    <td className="num mono">{row.confidence.toFixed(2)}</td>
                    <td className="num mono faint" style={{ whiteSpace: "nowrap" }}>
                      {money(row.entry_price, 0)} → {money(row.exit_price, 0)}
                    </td>
                    <td className="num mono">${money(row.notional_usd, 0)}</td>
                    <td className="num mono faint">{signedMoney(row.expected_usd)}</td>
                    <td className={`num mono ${row.is_win ? "pos" : "neg"}`}>
                      {signedMoney(row.net_usd)}
                    </td>
                    <td className="num mono faint">
                      {money((row.fees_bps / 10_000) * row.notional_usd)}
                    </td>
                    <td className="faint" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
                      {row.exit_reason ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="footnote">
          &ldquo;Expected&rdquo; is the net edge the system priced at entry; an exploration
          trade&apos;s expectation is just its cost, because it was taken to find out.
          &ldquo;Got&rdquo; is the realised result net of the fees actually paid on both
          legs. Training rows come from thousands of independent simulations and are
          evidence, never a track record — only 24/7-session rows count toward the
          real-money gate.
        </p>
      </Card>
      <SimulationFootnote />
    </>
  );
}
