import { useCallback, useEffect, useState } from "react";
import { api, type Position, type RuntimeSnapshot } from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { useStreamEvent } from "../lib/stream";
import { EquityChart } from "../components/charts";
import { Card, Empty, MoneyStat, Pill, SimulationFootnote, Stat } from "../components/ui";
import { dateTime, money, qty, signedMoney } from "../lib/format";

export function Portfolio({ subscribe }: { subscribe: Subscribe }) {
  const [snapshot, setSnapshot] = useState<RuntimeSnapshot | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [curve, setCurve] = useState<{ at: string; equity: number; drawdown_pct: number }[]>([]);

  const load = useCallback(() => {
    api.portfolio().then((p) => {
      setSnapshot(p);
      setPositions(p.positions ?? []);
      setCurve(p.equity_curve ?? []);
    }).catch(() => undefined);
  }, []);

  useEffect(load, [load]);
  useStreamEvent(subscribe, "portfolio.updated", (data) => {
    setCurve((previous) => [...previous.slice(-1400), data as { at: string; equity: number; drawdown_pct: number }]);
  });
  useStreamEvent(subscribe, "order.fill_simulated", load);

  const capital = snapshot?.capital;

  return (
    <>
      <h1>Portfolio</h1>
      <p className="section-note">
        Every figure below is simulated capital. Cash can exceed equity when a short is
        open — the proceeds are credited while the obligation is carried in the position.
      </p>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="card"><MoneyStat label="Starting capital" value={capital?.starting ?? 0} /></div>
        <div className="card"><MoneyStat label="Current equity" value={capital?.equity ?? 0} /></div>
        <div className="card"><MoneyStat label="Available cash" value={capital?.cash ?? 0} /></div>
        <div className="card"><MoneyStat label="Invested" value={capital?.invested ?? 0} /></div>
        <div className="card"><MoneyStat label="Unrealised P&L" value={capital?.unrealized_pnl ?? 0} signed /></div>
        <div className="card"><MoneyStat label="Realised P&L" value={capital?.realized_pnl ?? 0} signed /></div>
        <div className="card"><MoneyStat label="Fees paid" value={capital?.fees_paid ?? 0} /></div>
        <div className="card">
          <Stat label="Max drawdown" value={`${(capital?.max_drawdown_pct ?? 0).toFixed(2)}%`}
            tone={(capital?.max_drawdown_pct ?? 0) > 5 ? "warn" : "flat"} />
        </div>
      </div>

      <Card title="Equity and drawdown">
        {curve.length > 1 ? <EquityChart points={curve} height={260} /> : <Empty message="No equity history yet." />}
      </Card>

      <div style={{ marginTop: 16 }}>
        <Card title={`Positions (${positions.length})`}>
          {positions.length === 0 ? (
            <Empty message="Flat." />
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Symbol</th><th>Side</th><th className="num">Qty</th>
                  <th className="num">Entry</th><th className="num">Last</th>
                  <th className="num">Notional</th><th className="num">Unrealised</th>
                  <th className="num">Realised</th><th>Opened</th>
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
                    <td className="num">{money(position.notional)}</td>
                    <td className={`num ${position.unrealized_pnl >= 0 ? "pos" : "neg"}`}>{signedMoney(position.unrealized_pnl)}</td>
                    <td className={`num ${position.realized_pnl >= 0 ? "pos" : "neg"}`}>{signedMoney(position.realized_pnl)}</td>
                    <td className="faint">{position.opened_at ? dateTime(position.opened_at) : "—"}</td>
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
