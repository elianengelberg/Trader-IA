/**
 * The capital page: where the money came from, and what the strategy did with it.
 *
 * The two columns are the point. CAPITAL FLOW is money the user moved; TRADING
 * PERFORMANCE is money the strategy made or lost. A page that mixed them would show a
 * deposit as a great trading day — the flattering error this whole ledger exists to
 * prevent — so they are laid out as separate cards and never summed into one number
 * except as equity, which is labelled as the sum it is.
 */
import { useCallback, useEffect, useState } from "react";
import { api, type CapitalView as CapitalData } from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { useStreamEvent } from "../lib/stream";
import { Card, Empty, MoneyStat, PctStat, Pill, SimulationFootnote, Stat } from "../components/ui";

export function CapitalView({ subscribe }: { subscribe: Subscribe }) {
  const [data, setData] = useState<CapitalData | null>(null);

  const load = useCallback(() => {
    api.capital().then(setData).catch(() => undefined);
  }, []);

  useEffect(load, [load]);
  useStreamEvent(subscribe, "portfolio.updated", load);
  useStreamEvent(subscribe, "trade.closed", load);

  if (!data) {
    return (
      <>
        <h1>Capital</h1>
        <Card>
          <Empty message="Loading…" />
        </Card>
      </>
    );
  }

  return (
    <>
      <h1>Capital</h1>
      <p className="section-note">{data.explanation}</p>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="card">
          <MoneyStat label="Equity" value={data.equity} sub="allocated + realised + unrealised" />
        </div>
        <div className="card">
          <PctStat label="Return on contributed" value={data.return_pct}
            sub="never inflated by a deposit" />
        </div>
        <div className="card">
          <MoneyStat label="Cash" value={data.cash} sub={`invested ${data.invested.toFixed(2)}`} />
        </div>
        <div className="card">
          <Stat label="Max drawdown" value={`${data.max_drawdown_pct.toFixed(2)}%`}
            sub={`peak equity ${data.peak_equity.toFixed(2)}`} />
        </div>
      </div>

      <div className="grid cols-2">
        <Card title="Capital flow — the user's money movements">
          <div className="grid cols-2">
            <MoneyStat label="Deposits" value={data.deposits} />
            <MoneyStat label="Withdrawals" value={data.withdrawals} />
            <MoneyStat label="Net contributed" value={data.net_contributed}
              sub="the denominator of any honest return" />
            <Stat label="Unknown changes" value="0"
              sub="an unexplained move above 10% of the ceiling halts trading" />
          </div>
          <p className="footnote">
            Nothing in this column is performance. A deposit raises the balance and the
            denominator together; recording it as profit is the mistake this table refuses
            to make.
          </p>
        </Card>

        <Card title="Trading performance — the strategy's doing">
          <div className="grid cols-2">
            <MoneyStat label="Realised P&L" value={data.realized_pnl} signed />
            <MoneyStat label="Unrealised P&L" value={data.unrealized_pnl} signed />
            <MoneyStat label="Fees paid" value={data.fees_paid} />
            <MoneyStat label="Trading P&L" value={data.trading_pnl} signed
              sub="realised + unrealised" />
          </div>
          <p className="footnote">
            Only this column may be called performance, and it is measured against
            contributed capital — see the return figure above.
          </p>
        </Card>
      </div>

      <Card title="Live capital">
        <div className="row" style={{ gap: 16, alignItems: "center", marginBottom: 8 }}>
          <Pill value={data.live.enabled ? "enabled" : "disabled"}
            tone={data.live.enabled ? "warn" : ""} />
          <span className="mono">
            ceiling: {data.live.max_live_capital > 0
              ? data.live.max_live_capital.toLocaleString()
              : "not set"}
          </span>
          <span className="mono">allocated: {data.live.allocated.toLocaleString()}</span>
        </div>
        <p className="footnote">{data.live.note}</p>
      </Card>

      <SimulationFootnote />
    </>
  );
}
