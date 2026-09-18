"""The market maker's own ledger: a $10,000 paper account that shares nothing.

Inventory at average cost; realised P&L when inventory is reduced; unrealised marked
at the mid **and** at the conservative side (bid for a long, ask for a short) so the
optimistic mark never stands alone; fees, adverse-selection attribution and slippage
kept apart; equity, peak, drawdown and the day's start for the risk controller.

Separate from the session's ledger, the paper account, the track record and any real
capital by construction: this class knows none of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from tia.mm.costs import MarketMakerCostModel
from tia.mm.risk import LedgerView
from tia.mm.sim import SimulatedFill


@dataclass
class LedgerState:
    starting_equity_usd: float
    cash_usd: float
    inventory_btc: float = 0.0
    average_cost: float = 0.0
    realised_pnl_usd: float = 0.0  # gross of fees: spread capture realised
    fees_usd: float = 0.0
    adverse_selection_usd: float = 0.0  # attribution from resolved 1 s markouts, informational
    slippage_usd: float = 0.0  # unwinds by taker
    fills: int = 0
    buy_volume_btc: float = 0.0
    sell_volume_btc: float = 0.0
    mark_price: float | None = None
    mark_bid: float | None = None
    mark_ask: float | None = None
    peak_equity_usd: float = 0.0
    day: str = ""
    day_start_equity_usd: float = 0.0
    max_inventory_btc: float = 0.0
    inventory_since_ms: int | None = None
    inventory_ms_total: int = 0
    last_mark_ms: int | None = None
    history: list[tuple[int, float]] = field(default_factory=list)


class MarketMakerLedger:
    def __init__(self, starting_equity_usd: float, cost_model: MarketMakerCostModel | None = None, *, keep_history: int = 20_000) -> None:
        self.costs = cost_model or MarketMakerCostModel()
        self.state = LedgerState(starting_equity_usd=starting_equity_usd, cash_usd=starting_equity_usd, peak_equity_usd=starting_equity_usd, day_start_equity_usd=starting_equity_usd)
        self._keep_history = keep_history

    # ------------------------------------------------------------------ fills

    def apply_fill(self, fill: SimulatedFill, *, fee_scenario: str | None = None) -> dict[str, float]:
        s = self.state
        notional = fill.quantity * fill.price
        fee = self.costs.maker_fee_usd(notional, fee_scenario)
        realised = 0.0
        signed = fill.quantity if fill.side == "buy" else -fill.quantity
        if s.inventory_btc == 0.0 or (s.inventory_btc > 0) == (signed > 0):
            # Adding to (or opening) a position: average cost moves.
            total = abs(s.inventory_btc) + fill.quantity
            s.average_cost = (abs(s.inventory_btc) * s.average_cost + fill.quantity * fill.price) / total
            s.inventory_btc += signed
        else:
            # Reducing: realise on the reduced part, then flip if it went through zero.
            reduced = min(abs(s.inventory_btc), fill.quantity)
            direction = 1.0 if s.inventory_btc > 0 else -1.0
            realised = reduced * (fill.price - s.average_cost) * direction
            leftover = fill.quantity - reduced
            s.inventory_btc += signed
            if abs(s.inventory_btc) < 1e-12:
                s.inventory_btc = 0.0
                s.average_cost = 0.0
            elif leftover > 0:
                s.average_cost = fill.price
        s.cash_usd += -notional - fee if fill.side == "buy" else notional - fee
        s.realised_pnl_usd += realised
        s.fees_usd += fee
        s.fills += 1
        if fill.side == "buy":
            s.buy_volume_btc += fill.quantity
        else:
            s.sell_volume_btc += fill.quantity
        s.max_inventory_btc = max(s.max_inventory_btc, abs(s.inventory_btc))
        if s.inventory_btc != 0.0 and s.inventory_since_ms is None:
            s.inventory_since_ms = fill.t_ms
        elif s.inventory_btc == 0.0 and s.inventory_since_ms is not None:
            s.inventory_ms_total += fill.t_ms - s.inventory_since_ms
            s.inventory_since_ms = None
        return {"notional_usd": notional, "fee_usd": fee, "realised_usd": realised}

    def record_adverse_selection(self, usd: float) -> None:
        self.state.adverse_selection_usd += max(0.0, usd)

    def record_slippage(self, usd: float) -> None:
        self.state.slippage_usd += max(0.0, usd)

    # ------------------------------------------------------------------ marks

    def mark(self, t_ms: int, *, bid: float, ask: float) -> None:
        s = self.state
        s.mark_bid, s.mark_ask = bid, ask
        s.mark_price = (bid + ask) / 2.0
        s.last_mark_ms = t_ms
        day = datetime.fromtimestamp(t_ms / 1000.0, tz=UTC).date().isoformat()
        if day != s.day:
            s.day = day
            s.day_start_equity_usd = self.equity_usd
        s.peak_equity_usd = max(s.peak_equity_usd, self.equity_usd)
        s.history.append((t_ms, round(self.equity_usd, 4)))
        if len(s.history) > self._keep_history:
            del s.history[: len(s.history) - self._keep_history]

    # ------------------------------------------------------------------ reading

    def _unrealised(self, price: float | None) -> float:
        s = self.state
        if price is None or s.inventory_btc == 0.0:
            return 0.0
        return s.inventory_btc * (price - s.average_cost)

    @property
    def unrealised_mid_usd(self) -> float:
        return self._unrealised(self.state.mark_price)

    @property
    def unrealised_conservative_usd(self) -> float:
        s = self.state
        side = s.mark_bid if s.inventory_btc > 0 else s.mark_ask
        return self._unrealised(side)

    @property
    def equity_usd(self) -> float:
        s = self.state
        mark = s.mark_price if s.mark_price is not None else s.average_cost
        return s.cash_usd + s.inventory_btc * mark

    @property
    def equity_conservative_usd(self) -> float:
        s = self.state
        side = s.mark_bid if s.inventory_btc > 0 else s.mark_ask
        mark = side if side is not None else s.average_cost
        return s.cash_usd + s.inventory_btc * mark

    @property
    def net_pnl_usd(self) -> float:
        return self.equity_usd - self.state.starting_equity_usd

    @property
    def drawdown_pct(self) -> float:
        s = self.state
        return (s.peak_equity_usd - self.equity_usd) / s.peak_equity_usd * 100.0 if s.peak_equity_usd > 0 else 0.0

    def view(self) -> LedgerView:
        s = self.state
        return LedgerView(s.inventory_btc, self.equity_usd, s.day_start_equity_usd, s.peak_equity_usd, s.mark_price or s.average_cost or 0.0)

    def snapshot(self) -> dict[str, Any]:
        s = self.state
        inventory_ms = s.inventory_ms_total + ((s.last_mark_ms - s.inventory_since_ms) if s.inventory_since_ms is not None and s.last_mark_ms else 0)
        return {
            "starting_equity_usd": s.starting_equity_usd,
            "cash_usd": round(s.cash_usd, 6),
            "inventory_btc": round(s.inventory_btc, 8),
            "average_cost": round(s.average_cost, 4),
            "mark_price": s.mark_price,
            "equity_usd": round(self.equity_usd, 6),
            "equity_conservative_usd": round(self.equity_conservative_usd, 6),
            "gross_pnl_usd": round(s.realised_pnl_usd + self.unrealised_mid_usd, 6),
            "realised_pnl_usd": round(s.realised_pnl_usd, 6),
            "unrealised_mid_usd": round(self.unrealised_mid_usd, 6),
            "unrealised_conservative_usd": round(self.unrealised_conservative_usd, 6),
            "fees_usd": round(s.fees_usd, 6),
            "adverse_selection_usd": round(s.adverse_selection_usd, 6),
            "slippage_usd": round(s.slippage_usd, 6),
            "net_pnl_usd": round(self.net_pnl_usd, 6),
            "net_pnl_conservative_usd": round(self.equity_conservative_usd - s.starting_equity_usd, 6),
            "peak_equity_usd": round(s.peak_equity_usd, 6),
            "drawdown_pct": round(self.drawdown_pct, 4),
            "day": s.day,
            "day_start_equity_usd": round(s.day_start_equity_usd, 6),
            "daily_pnl_usd": round(self.equity_usd - s.day_start_equity_usd, 6),
            "fills": s.fills,
            "buy_volume_btc": round(s.buy_volume_btc, 8),
            "sell_volume_btc": round(s.sell_volume_btc, 8),
            "max_inventory_btc": round(s.max_inventory_btc, 8),
            "inventory_duration_s": round(inventory_ms / 1000.0, 1),
            "cost_model": self.costs.as_dict(),
            "note": "net = equity - starting equity; fees already deducted from cash; adverse selection and slippage are attributions, shown apart, not deducted twice",
        }

    # ------------------------------------------------------------------ persistence

    def export(self) -> dict[str, Any]:
        s = self.state
        return {k: v for k, v in s.__dict__.items() if k != "history"}

    @classmethod
    def restore(cls, payload: dict[str, Any], cost_model: MarketMakerCostModel | None = None) -> MarketMakerLedger:
        ledger = cls(float(payload["starting_equity_usd"]), cost_model)
        for key, value in payload.items():
            if hasattr(ledger.state, key) and key != "history":
                setattr(ledger.state, key, value)
        return ledger


__all__ = ["LedgerState", "MarketMakerLedger"]
