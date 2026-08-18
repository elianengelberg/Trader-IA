import { useCallback, useEffect, useState } from "react";
import { api, type Candle, type Market, type OrderBook } from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { useStreamEvent } from "../lib/stream";
import { PriceChart } from "../components/charts";
import { Card, Empty, Pill, SimulationFootnote, Stat } from "../components/ui";
import { money, signedPct } from "../lib/format";

/**
 * The timeframes offered, in Binance's own vocabulary. `1m` is served from the running
 * session's live buffer (real-time, updated on every stream tick); the longer frames are
 * fetched on demand from Binance's public klines endpoint. `limit` is how many bars to
 * pull for each — enough to fill the viewport without asking the venue for a decade of
 * monthly candles.
 */
const TIMEFRAMES = [
  { id: "1m", label: "1m", limit: 240 },
  { id: "30m", label: "30m", limit: 336 },
  { id: "1h", label: "1H", limit: 336 },
  { id: "1d", label: "1D", limit: 365 },
  { id: "1w", label: "1W", limit: 260 },
  { id: "1M", label: "1M", limit: 120 },
] as const;

type TimeframeId = (typeof TIMEFRAMES)[number]["id"];

/** The buys and sells, laddered the way Binance shows them: asks above, bids below. */
function OrderBookLadder({ book, levels = 12 }: { book: OrderBook; levels?: number }) {
  const asks = book.asks.slice(0, levels);
  const bids = book.bids.slice(0, levels);
  const bestAsk = asks[0]?.[0] ?? 0;
  const bestBid = bids[0]?.[0] ?? 0;
  const mid = bestAsk && bestBid ? (bestAsk + bestBid) / 2 : bestAsk || bestBid;
  const spread = bestAsk && bestBid ? bestAsk - bestBid : 0;
  const spreadBps = mid ? (spread / mid) * 10000 : 0;

  // Cumulative size outward from the touch, so the depth bars read as a wall of resting
  // liquidity rather than a per-level blip. Each side is scaled to its own deepest level.
  let running = 0;
  const askRows = asks.map(([p, q]) => ({ p, q, cum: (running += q) }));
  const askMax = askRows.length ? askRows[askRows.length - 1].cum : 1;
  running = 0;
  const bidRows = bids.map(([p, q]) => ({ p, q, cum: (running += q) }));
  const bidMax = bidRows.length ? bidRows[bidRows.length - 1].cum : 1;

  return (
    <div className="orderbook">
      <div className="ob-head">
        <span>Price (USDT)</span>
        <span>Size</span>
      </div>
      <div className="ob-asks">
        {[...askRows].reverse().map((r) => (
          <div className="ob-row ask" key={`a-${r.p}`}>
            <div className="ob-depth ask" style={{ width: `${(r.cum / askMax) * 100}%` }} />
            <span className="ob-price">{money(r.p)}</span>
            <span className="ob-size">{r.q.toFixed(4)}</span>
          </div>
        ))}
      </div>
      <div className="ob-spread">
        <span className="ob-mid">{money(mid)}</span>
        <span className="ob-spread-val">
          spread {spread.toFixed(2)} · {spreadBps.toFixed(1)} bps
        </span>
      </div>
      <div className="ob-bids">
        {bidRows.map((r) => (
          <div className="ob-row bid" key={`b-${r.p}`}>
            <div className="ob-depth bid" style={{ width: `${(r.cum / bidMax) * 100}%` }} />
            <span className="ob-price">{money(r.p)}</span>
            <span className="ob-size">{r.q.toFixed(4)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Markets({ subscribe }: { subscribe: Subscribe }) {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [timeframe, setTimeframe] = useState<TimeframeId>("1m");
  const [book, setBook] = useState<OrderBook | null>(null);
  const [chartError, setChartError] = useState("");
  const [bookError, setBookError] = useState("");
  const [symbol, setSymbol] = useState<string>("");
  const [liveData, setLiveData] = useState(false);
  const [expanded, setExpanded] = useState(false);

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

  // The candle source depends on the frame. `1m` comes from the session's live buffer —
  // the exact bars it is trading on, refreshed by the stream — so it needs no venue call.
  // Every longer frame is a real Binance kline pull, made once when the frame or symbol
  // changes.
  const loadChart = useCallback(() => {
    if (!symbol) return;
    setChartError("");
    const frame = TIMEFRAMES.find((t) => t.id === timeframe)!;
    const source =
      timeframe === "1m"
        ? api.candles(symbol, 240)
        : api.marketHistory(symbol, timeframe, frame.limit);
    source
      .then(setCandles)
      .catch(() => {
        setCandles([]);
        if (timeframe !== "1m") {
          setChartError("Could not load candles from the venue right now.");
        }
      });
  }, [symbol, timeframe]);

  useEffect(loadChart, [loadChart]);

  // The order book is genuinely live: poll the public depth endpoint a few times a minute.
  useEffect(() => {
    if (!symbol) return;
    let active = true;
    const poll = () =>
      api.orderBook(symbol, 20)
        .then((b) => {
          if (!active) return;
          setBook(b);
          setBookError(b.available === false ? b.reason || "Order book unavailable." : "");
        })
        .catch(() => {
          if (active) setBookError("Order book unavailable right now.");
        });
    poll();
    const id = window.setInterval(poll, 2500);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, [symbol]);

  // Prices move on every bar; on the 1-minute frame the live buffer is refetched (a few
  // kilobytes) rather than appended, since it is capped server-side. Longer frames don't
  // move bar-to-bar, so they are left as loaded until the operator switches.
  useStreamEvent(subscribe, "portfolio.updated", () => {
    api.markets().then(setMarkets).catch(() => undefined);
    if (symbol && timeframe === "1m") {
      api.candles(symbol, 240).then(setCandles).catch(() => undefined);
    }
  });

  // Escape leaves the fullscreen view — never trap the operator behind an overlay.
  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setExpanded(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  const selected = markets.find((m) => m.symbol === symbol);
  const frameLabel = TIMEFRAMES.find((t) => t.id === timeframe)?.label ?? timeframe;
  const overlayHeight =
    typeof window !== "undefined" ? Math.max(360, window.innerHeight - 210) : 560;

  const timeframeButtons = (
    <div className="row" style={{ gap: 4 }}>
      {TIMEFRAMES.map((t) => (
        <button
          key={t.id}
          className={`btn small ${timeframe === t.id ? "primary" : ""}`}
          onClick={() => setTimeframe(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );

  const chartBody = (height: number) =>
    candles.length > 1 ? (
      <PriceChart key={`${symbol}-${timeframe}`} candles={candles} height={height} />
    ) : chartError ? (
      <Empty message={chartError} />
    ) : (
      <Empty
        message={timeframe === "1m" ? "Collecting bars…" : "Loading candles from Binance…"}
      />
    );

  const orderBookPanel = (
    <div className="ob-panel">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <strong style={{ fontSize: 12 }}>Order book — buys &amp; sells</strong>
        <span style={{ fontSize: 11, color: "var(--text-faint)" }}>live · Binance</span>
      </div>
      {book && (book.bids.length > 0 || book.asks.length > 0) ? (
        <OrderBookLadder book={book} />
      ) : (
        <Empty message={bookError || "Loading order book…"} />
      )}
    </div>
  );

  return (
    <>
      <h1>Markets</h1>
      <p className="section-note">
        {liveData ? (
          <>
            <strong>Real Binance market data</strong> — the live price the 24/7 paper
            session is trading on. The 1-minute frame streams from the venue; longer frames
            and the order book are pulled straight from Binance. Fills are still simulated;
            the price, the candles, and the book are real.
          </>
        ) : (
          <>
            The 1-minute chart shows synthetic, seeded data from the demo run; the order
            book and longer timeframes are real Binance data. Start the 24/7 paper session
            in the Live Trading tab to trade on the real 1-minute feed.
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
            title={`${symbol} · ${frameLabel} candles`}
            actions={
              <div className="row" style={{ gap: 8 }}>
                {timeframeButtons}
                <button className="btn small" onClick={() => setExpanded(true)}>
                  ⤢ Fullscreen
                </button>
              </div>
            }
          >
            <div className="markets-chart">
              <div>{chartBody(360)}</div>
              {orderBookPanel}
            </div>
          </Card>
        </>
      )}

      {expanded && (
        <div className="chart-overlay">
          <div className="chart-overlay-head">
            <div className="row" style={{ gap: 14 }}>
              <strong style={{ fontSize: 16 }}>{symbol}</strong>
              {selected && (
                <span
                  className="mono"
                  style={{
                    fontSize: 15,
                    color: selected.change_pct >= 0 ? "var(--pos)" : "var(--neg)",
                  }}
                >
                  {money(selected.price)} · {signedPct(selected.change_pct, 3)}
                </span>
              )}
              {timeframeButtons}
            </div>
            <button className="btn small" onClick={() => setExpanded(false)}>
              ✕ Close
            </button>
          </div>
          <div className="chart-overlay-body">
            <div>{chartBody(overlayHeight)}</div>
            {orderBookPanel}
          </div>
        </div>
      )}

      <SimulationFootnote />
    </>
  );
}
