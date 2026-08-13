import { useCallback, useEffect, useState } from "react";
import { api, type Candle, type Market } from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { useStreamEvent } from "../lib/stream";
import { PriceChart } from "../components/charts";
import { Card, Empty, Pill, SimulationFootnote, Stat } from "../components/ui";
import { money, signedPct } from "../lib/format";

export function Markets({ subscribe }: { subscribe: Subscribe }) {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [symbol, setSymbol] = useState<string>("");

  const load = useCallback(() => {
    api.markets().then((rows) => {
      setMarkets(rows);
      if (!symbol && rows.length > 0) setSymbol(rows[0].symbol);
    }).catch(() => undefined);
  }, [symbol]);

  useEffect(load, [load]);

  useEffect(() => {
    if (!symbol) return;
    api.candles(symbol, 260).then(setCandles).catch(() => undefined);
  }, [symbol]);

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
        Synthetic, seeded market data. The same scenario and seed produce the same bars on
        any machine, which is what makes a demo run reproducible rather than anecdotal.
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

          <Card title={`${symbol} · price`}>
            {candles.length > 1 ? <PriceChart candles={candles} height={340} /> : <Empty message="Collecting bars…" />}
          </Card>
        </>
      )}
      <SimulationFootnote />
    </>
  );
}
