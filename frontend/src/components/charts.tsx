/**
 * Charts, on lightweight-charts (Apache-2.0).
 *
 * Two of them, and no more: an equity line and a price candlestick. A dashboard that
 * renders eight charts nobody reads costs more attention than it returns.
 *
 * Both handle the case the demo hits constantly — data arriving a point at a time — by
 * calling `update()` for appends and `setData()` only when the series is replaced. Calling
 * `setData()` on every tick would reset the viewport and make the chart unreadable while
 * it is live.
 */
import { useEffect, useRef } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";

const THEME = {
  layout: { background: { color: "transparent" }, textColor: "#8b98ad", fontSize: 11 },
  grid: { vertLines: { color: "#161c27" }, horzLines: { color: "#161c27" } },
  rightPriceScale: { borderColor: "#1f2836" },
  timeScale: { borderColor: "#1f2836", timeVisible: true, secondsVisible: false },
  crosshair: { mode: 0 as const },
};

const toTime = (iso: string): UTCTimestamp =>
  Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;

/** Duplicate or out-of-order timestamps make lightweight-charts throw; drop them. */
function monotonic<T extends { time: UTCTimestamp }>(points: T[]): T[] {
  const out: T[] = [];
  let last = -Infinity;
  for (const point of points) {
    if (point.time > last) {
      out.push(point);
      last = point.time;
    }
  }
  return out;
}

export function EquityChart({
  points,
  height = 220,
}: {
  points: { at: string; equity: number }[];
  height?: number;
}) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Area"> | null>(null);

  useEffect(() => {
    if (!container.current) return;
    const instance = createChart(container.current, {
      ...THEME,
      height,
      width: container.current.clientWidth,
    });
    series.current = instance.addAreaSeries({
      lineColor: "#4c8dff",
      topColor: "rgba(76, 141, 255, 0.28)",
      bottomColor: "rgba(76, 141, 255, 0.02)",
      lineWidth: 2,
      priceLineVisible: false,
    });
    chart.current = instance;

    const observer = new ResizeObserver(([entry]) =>
      instance.applyOptions({ width: entry.contentRect.width }),
    );
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      instance.remove();
      chart.current = null;
      series.current = null;
    };
  }, [height]);

  useEffect(() => {
    if (!series.current) return;
    const data = monotonic(
      points.map((p) => ({ time: toTime(p.at), value: p.equity })),
    );
    series.current.setData(data);
  }, [points]);

  return <div ref={container} className="chart" />;
}

export function PriceChart({
  candles,
  height = 300,
}: {
  candles: { time: string; open: number; high: number; low: number; close: number }[];
  height?: number;
}) {
  const container = useRef<HTMLDivElement>(null);
  const series = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (!container.current) return;
    const instance = createChart(container.current, {
      ...THEME,
      height,
      width: container.current.clientWidth,
    });
    series.current = instance.addCandlestickSeries({
      upColor: "#34d399",
      downColor: "#f87171",
      borderUpColor: "#34d399",
      borderDownColor: "#f87171",
      wickUpColor: "#1d7d5f",
      wickDownColor: "#8f3d3d",
    });

    const observer = new ResizeObserver(([entry]) =>
      instance.applyOptions({ width: entry.contentRect.width }),
    );
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      instance.remove();
      series.current = null;
    };
  }, [height]);

  useEffect(() => {
    if (!series.current) return;
    series.current.setData(
      monotonic(
        candles.map((c) => ({
          time: toTime(c.time),
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        })),
      ),
    );
  }, [candles]);

  return <div ref={container} className="chart" />;
}

/** A tiny inline bar chart for baseline comparisons — no library, no axes, no legend. */
export function Sparkbars({
  items,
}: {
  items: { label: string; value: number; highlight?: boolean }[];
}) {
  const max = Math.max(...items.map((i) => Math.abs(i.value)), 0.0001);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
      {items.map((item) => {
        const width = (Math.abs(item.value) / max) * 50;
        const positive = item.value >= 0;
        return (
          <div key={item.label} style={{ display: "grid", gridTemplateColumns: "150px 1fr 70px", gap: 10, alignItems: "center" }}>
            <span style={{ fontSize: 12, color: item.highlight ? "var(--text)" : "var(--text-dim)", fontWeight: item.highlight ? 600 : 400 }}>
              {item.label}
            </span>
            <div style={{ display: "flex", height: 12, alignItems: "center" }}>
              <div style={{ width: "50%", display: "flex", justifyContent: "flex-end" }}>
                {!positive && (
                  <div style={{ width: `${width * 2}%`, height: 10, background: "var(--neg)", borderRadius: "3px 0 0 3px", opacity: item.highlight ? 1 : 0.55 }} />
                )}
              </div>
              <div style={{ width: 1, height: 14, background: "var(--border-strong)" }} />
              <div style={{ width: "50%" }}>
                {positive && (
                  <div style={{ width: `${width * 2}%`, height: 10, background: "var(--pos)", borderRadius: "0 3px 3px 0", opacity: item.highlight ? 1 : 0.55 }} />
                )}
              </div>
            </div>
            <span className="mono num" style={{ fontSize: 12, color: positive ? "var(--pos)" : "var(--neg)" }}>
              {item.value >= 0 ? "+" : ""}
              {item.value.toFixed(2)}%
            </span>
          </div>
        );
      })}
    </div>
  );
}
