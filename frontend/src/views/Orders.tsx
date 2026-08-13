import { useCallback, useEffect, useState } from "react";
import { api, type Fill, type Order } from "../lib/api";
import type { Subscribe } from "../lib/stream";
import { useStreamEvent } from "../lib/stream";
import { Card, Empty, Pill, SimulationFootnote } from "../components/ui";
import { dateTime, money, qty } from "../lib/format";

export function Orders({ subscribe }: { subscribe: Subscribe }) {
  const [orders, setOrders] = useState<Order[]>([]);
  const [fills, setFills] = useState<Fill[]>([]);

  const load = useCallback(() => {
    api.orders(150).then(setOrders).catch(() => undefined);
    api.fills(150).then(setFills).catch(() => undefined);
  }, []);

  useEffect(load, [load]);
  useStreamEvent(subscribe, "order.state_changed", load);
  useStreamEvent(subscribe, "order.fill_simulated", load);

  return (
    <>
      <h1>Orders &amp; fills</h1>
      <p className="section-note">
        Simulated executions from a bar-based matching engine. Market orders fill at the
        next bar&rsquo;s open plus adverse slippage, never at the price that triggered them;
        limit orders require the price to trade through, not merely touch. There is no order
        book, and our own orders have no effect on the price.
      </p>

      <Card title={`Orders (${orders.length})`}>
        {orders.length === 0 ? (
          <Empty message="No orders yet." />
        ) : (
          <div className="scroll tall">
            <table>
              <thead>
                <tr>
                  <th>Created</th><th>Symbol</th><th>Side</th><th>Type</th>
                  <th className="num">Qty</th><th className="num">Filled</th>
                  <th className="num">Avg price</th><th className="num">Fees</th>
                  <th>State</th><th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr key={order.order_id + order.updated_at}>
                    <td className="faint">{dateTime(order.created_at)}</td>
                    <td>{order.symbol}</td>
                    <td className={order.side === "buy" ? "pos" : "neg"}>{order.side}</td>
                    <td className="faint">{order.order_type}</td>
                    <td className="num">{qty(order.quantity)}</td>
                    <td className="num">{qty(order.filled_quantity)}</td>
                    <td className="num">{order.average_fill_price ? money(order.average_fill_price) : "—"}</td>
                    <td className="num faint">{money(order.fees_paid)}</td>
                    <td><Pill value={order.state} /></td>
                    <td className="faint" style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {order.reject_reason || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div style={{ marginTop: 16 }}>
        <Card title={`Fills (${fills.length})`}>
          {fills.length === 0 ? (
            <Empty message="No fills yet." />
          ) : (
            <div className="scroll">
              <table>
                <thead>
                  <tr>
                    <th>Time</th><th>Symbol</th><th>Side</th>
                    <th className="num">Qty</th><th className="num">Price</th>
                    <th className="num">Fee</th><th className="num">Slippage (bps)</th><th>Liquidity</th>
                  </tr>
                </thead>
                <tbody>
                  {fills.map((fill) => (
                    <tr key={fill.fill_id}>
                      <td className="faint">{dateTime(fill.filled_at)}</td>
                      <td>{fill.symbol}</td>
                      <td className={fill.side === "buy" ? "pos" : "neg"}>{fill.side}</td>
                      <td className="num">{qty(fill.quantity)}</td>
                      <td className="num">{money(fill.price)}</td>
                      <td className="num faint">{money(fill.fee)}</td>
                      <td className="num warn">{fill.slippage_bps.toFixed(2)}</td>
                      <td className="faint">{fill.liquidity}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
      <SimulationFootnote />
    </>
  );
}
