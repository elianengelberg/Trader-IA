/**
 * Backtests.
 *
 * The layout enforces the reporting rule: a result is never shown on its own. Every row
 * carries its verdict, and the verdict vocabulary contains nothing that means "good" —
 * the best available outcome is "beat all baselines on this dataset". The baseline
 * comparison is given more visual weight than the headline return, because the return
 * alone is the number that misleads.
 */
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type Backtest } from "../lib/api";
import { Sparkbars } from "../components/charts";
import { Card, Empty, Pill, SimulationFootnote } from "../components/ui";
import { dateTime, signedPct } from "../lib/format";

const VERDICT_TONE: Record<string, string> = {
  beat_all_baselines: "ok",
  mixed: "warn",
  no_edge_demonstrated: "bad",
  insufficient_evidence: "",
};

export function Backtests() {
  const [rows, setRows] = useState<Backtest[]>([]);
  const [selected, setSelected] = useState<Backtest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [symbol, setSymbol] = useState("BTC-USD");
  const [timeframe, setTimeframe] = useState("1h");
  const [bars, setBars] = useState(1200);

  const load = useCallback(() => {
    api.backtests().then(setRows).catch(() => undefined);
  }, []);

  useEffect(load, [load]);

  async function run() {
    setBusy(true);
    setError("");
    try {
      const result = await api.runBacktest({ symbol, timeframe, bars, seed: 20260812 });
      setSelected(result);
      load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Backtests</h1>
      <p className="section-note">
        Run against the committed CSV fixtures, so a result here is reproducible by anyone
        with this repository — no network, no credentials. The backtester is the runtime:
        the same quality gate, features, regime classifier, strategies, risk engine and
        matching engine, driven by historical bars instead of a live feed.
      </p>

      <Card title="Run a backtest">
        {error && <div className="banner error">{error}</div>}
        <div className="row" style={{ alignItems: "flex-end" }}>
          <label className="field">
            Symbol
            <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
              <option value="BTC-USD">BTC-USD</option>
              <option value="ETH-USD">ETH-USD</option>
              <option value="SPX-IDX">SPX-IDX</option>
            </select>
          </label>
          <label className="field">
            Timeframe
            <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
              <option value="1h">1h</option>
              <option value="1m">1m</option>
            </select>
          </label>
          <label className="field">
            Bars
            <input
              type="number"
              value={bars}
              min={200}
              max={5000}
              step={100}
              onChange={(e) => setBars(Number(e.target.value))}
            />
          </label>
          <button className="btn primary" disabled={busy} onClick={run}>
            {busy ? "Running…" : "Run backtest"}
          </button>
        </div>
        <p className="footnote" style={{ marginTop: 12, paddingTop: 8 }}>
          BTC-USD has 1h and 1m fixtures; ETH-USD and SPX-IDX have 1m only. A combination
          without a fixture returns an error rather than silently substituting one.
        </p>
      </Card>

      <div style={{ marginTop: 16 }}>
        <Card title={`Results (${rows.length})`}>
          {rows.length === 0 ? (
            <Empty message="No backtests recorded yet." />
          ) : (
            <div className="scroll">
              <table>
                <thead>
                  <tr>
                    <th>Run</th><th>Dataset</th><th className="num">Bars</th>
                    <th className="num">Return</th><th className="num">Max DD</th>
                    <th className="num">Sharpe</th><th className="num">Trades</th><th>Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.run_id} className="clickable" onClick={() => setSelected(row)}>
                      <td className="faint">{dateTime(row.created_at)}</td>
                      <td>{row.symbols.join(",")} {row.timeframe}</td>
                      <td className="num">{row.bars}</td>
                      <td className={`num ${row.total_return_pct >= 0 ? "pos" : "neg"}`}>
                        {signedPct(row.total_return_pct)}
                      </td>
                      <td className="num warn">{row.max_drawdown_pct.toFixed(2)}%</td>
                      <td className="num">{row.sharpe === null ? "n/a" : row.sharpe.toFixed(2)}</td>
                      <td className="num">{row.trades}</td>
                      <td><Pill value={row.verdict} tone={VERDICT_TONE[row.verdict]} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {selected && (
        <div className="drawer-backdrop" onClick={() => setSelected(null)}>
          <div className="drawer" onClick={(event) => event.stopPropagation()}>
            <header>
              <div>
                <h1 style={{ marginBottom: 2 }}>
                  {selected.symbols.join(", ")} · {selected.timeframe}
                </h1>
                <Pill value={selected.verdict} tone={VERDICT_TONE[selected.verdict]} />
              </div>
              <button className="btn small" onClick={() => setSelected(null)}>Close</button>
            </header>

            <h2>Against the mandatory baselines</h2>
            <Sparkbars
              items={[
                { label: "this configuration", value: selected.total_return_pct, highlight: true },
                ...selected.baselines.map((baseline) => ({
                  label: baseline.name.replace(/_/g, " "),
                  value: baseline.total_return_pct,
                })),
              ]}
            />
            <p className="footnote" style={{ marginTop: 12, paddingTop: 8 }}>
              All six are evaluated on the same bars with the same fees and slippage. The
              random-entry control is matched to this run&rsquo;s trade count and holding
              period, so it pays comparable costs — an unmatched control would prove
              nothing.
            </p>

            <h2>Evidence statement</h2>
            <p style={{ fontSize: 12.5, color: "var(--text-dim)", whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
              {selected.evidence_statement}
            </p>

            {selected.warnings.length > 0 && (
              <>
                <h2>Caveats</h2>
                <ul style={{ fontSize: 12.5, color: "var(--warn)", paddingLeft: 18 }}>
                  {selected.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </>
            )}

            <h2>Baseline detail</h2>
            <table>
              <thead>
                <tr><th>Baseline</th><th className="num">Return</th><th className="num">Max DD</th><th className="num">Trades</th></tr>
              </thead>
              <tbody>
                {selected.baselines.map((baseline) => (
                  <tr key={baseline.name}>
                    <td>{baseline.name.replace(/_/g, " ")}</td>
                    <td className={`num ${baseline.total_return_pct >= 0 ? "pos" : "neg"}`}>
                      {signedPct(baseline.total_return_pct)}
                    </td>
                    <td className="num warn">{baseline.max_drawdown_pct.toFixed(2)}%</td>
                    <td className="num">{baseline.trades}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <SimulationFootnote />
    </>
  );
}
