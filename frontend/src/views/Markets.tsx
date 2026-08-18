import { useCallback, useEffect, useState } from "react";
import { api, type Candle, type Market } from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { useStreamEvent } from "../lib/stream";
import { PriceChart } from "../components/charts";
import { Card, Empty, Pill, SimulationFootnote, Stat } from "../components/ui";
import { money, signedPct } from "../lib/format";

type ChartRange = "live" | "history";

export function Markets({ subscribe }: { subscribe: Subscribe }) {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [history, setHistory] = useState<Candle[]>([]);
  const [range, setRange] = useState<ChartRange>("live");
  const [historyError, setHistoryError] = useState("");
  const [symbol, setSymbol] = useState<string>("");
  const [liveData, setLiveData] = useState(false);

  const load = useCallback(() => {
    api.markets().then((rows) => {
      setMarkets(rows);
      if (!symbol && rows.length > 0) setSymbol(rows[0].symbol);
    }).catch(() => undefined);
    // Are we showing the real paper-live feed, or the synthetic demo?
    api.liveSnapshot()
      .then((s) => setLiveData(Boolean(s.active) && s.mode === "paper-live"))
      .catch(() => setLiveData(false));
  }, [symbol]);

  useEffect(load, [load]);

  useEffect(() => {
    if (!symbol) return;
    api.candles(symbol, 260).then(setCandles).catch(() => undefined);
  }, [symbol]);

  // One year of real daily candles from Binance, fetched on demand when the operator
  // switches the chart to the history range.
  useEffect(() => {
    if (!symbol || range !== "history") return;
    setHistoryError("");
    api.marketHistory(symbol, "1d", 365)
      .then(setHistory)
      .catch(() => setHistoryError("Could not load history from the venue right now."));
  }, [symbol, range]);

  // Prices move on every bar; the candle series is refetched rather than appended because
  // the buffer is capped server-side and a refetch of 260 bars is a few kilobytes.
  useStreamEvent(subscribe, "portfolio.updated", () => {
    api.markets().then(setMarkets).catch(() => undefined);
    if (symbol) api.candles(symbol, 260).then(setCandles).catch(() => undefined);
  });

  return (
    <>
      <h1>Markets</h1>
      <p className="section-note">
        {liveData ? (
          <>
            <strong>Real Binance market data</strong> — the live price the 24/7 paper
            session is trading on, 1-minute bars, straight from the venue. Fills are still
            simulated; the price and the chart are real.
          </>
        ) : (
          <>
            Synthetic, seeded market data (demo run). Start the 24/7 paper session in the
            Live Trading tab to see real Binance prices here instead.
          </>
        )}
      </p>

      {markets.length === 0 ? (
        <Card><Empty message="No market data. Start a run." /></Card>
      ) : (
        <>
          <div className="grid cols-3" style={{ marginBottom: 16 }}>
            {markets.map((market) => (
              <div
                key={market.symbol}
                className="card"
                style={{
                  cursor: "pointer",
                  borderColor: market.symbol === symbol ? "var(--accent)" : undefined,
                }}
                onClick={() => setSymbol(market.symbol)}
              >
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
                  <strong>{market.symbol}</strong>
                  <Pill value={market.regime} />
                </div>
                <Stat
                  label="Last price"
                  value={money(market.price)}
                  tone={market.change_pct >= 0 ? "pos" : "neg"}
                  sub={`${signedPct(market.change_pct, 3)} · vol ${money(market.volume, 0)}`}
                />
              </div>
            ))}
          </div>

          <Card
            title={`${symbol} · price`}
            actions={
              <div className="row" style={{ gap: 6 }}>
                <button
                  className={`btn small ${range === "live" ? "" : "ghost"}`}
                  onClick={() => setRange("live")}
                >
                  Live · 1m
                </button>
                <button
                  className={`btn small ${range === "history" ? "" : "ghost"}`}
                  onClick={() => setRange("history")}
                >
                  1 year · daily
                </button>
              </div>
            }
          >
            {range === "live" ? (
              candles.length > 1 ? (
                <PriceChart candles={candles} height={340} />
              ) : (
                <Empty message="Collecting bars…" />
              )
            ) : historyError ? (
              <Empty message={historyError} />
            ) : history.length > 1 ? (
              <PriceChart candles={history} height={340} />
            ) : (
              <Empty message="Loading a year of daily bars from Binance…" />
            )}
          </Card>
        </>
      )}
      <SimulationFootnote />
    </>
  );
}
