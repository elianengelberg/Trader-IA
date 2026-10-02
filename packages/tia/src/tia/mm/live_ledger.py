"""The live maker's ledger: real balances in, confirmed venue fills and venue fees only.

It is the paper ledger's arithmetic with three differences, each of them a fact about real
money rather than a modelling choice:

* **It starts from the account**, not from a configured number. ``seed`` reads the quote
  balance and the base balance the venue reports at start. The base held *before* the run
  is a baseline, not inventory: the maker's inventory is what its own fills accumulate on
  top of it, and its P&L is only what those fills earn or lose.
* **It books the venue's fee.** A fill carries the commission the venue charged and the
  asset it charged it in. In the quote asset it is booked as is; in the base asset it is
  valued at the fill price (and the base the account kept is reduced accordingly); in a
  third asset it cannot be booked honestly, so the modelled maker fee is applied and the
  case is counted and shown.
* **Binance wins.** ``reconcile_balances`` compares what the ledger expects the account to
  hold with what the venue says it holds. A difference beyond a tolerance is a discrepancy:
  it is counted, recorded with both figures, and the venue's figures are adopted. The
  service that called it decides what the discrepancy means for quoting (nothing good).

It is never restored from a saved state: a restart rebuilds it from the venue.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from tia.mm.costs import MarketMakerCostModel
from tia.mm.ledger import MarketMakerLedger

BOOKED_FEE_STATUSES = ("venue", "converted_from_base")


class LiveLedger(MarketMakerLedger):
    mode = "live"

    def __init__(self, cost_model: MarketMakerCostModel | None = None, *, keep_history: int = 20_000) -> None:
        super().__init__(0.0, cost_model, keep_history=keep_history)
        self.seeded = False
        self.seeded_at_ms: int | None = None
        self.baseline_base_btc = 0.0
        self.venue_quote_usd: float | None = None
        self.venue_base_btc: float | None = None
        self.venue_base_locked_btc: float | None = None
        self.fees_venue_usd = 0.0
        self.fees_converted_usd = 0.0
        self.fees_assumed_usd = 0.0
        self.base_fees_btc = 0.0
        self.fills_unconverted = 0
        self.fills_by_liquidity = {"maker": 0, "taker": 0}
        self.reconciliations = 0
        self.discrepancies = 0
        self.last_reconciliation: dict[str, Any] | None = None
        self.adjustments: deque[dict[str, Any]] = deque(maxlen=200)

    # ------------------------------------------------------------------ seeding

    def seed(self, *, quote_usd: float, base_btc: float, base_locked_btc: float, mark_price: float, t_ms: int) -> None:
        """Start from the account as the venue reports it. May be called once per run."""
        if self.seeded:
            raise ValueError("the live ledger is seeded once per run; a restart rebuilds it from the venue")
        s = self.state
        s.starting_equity_usd = quote_usd
        s.cash_usd = quote_usd
        s.inventory_btc = 0.0
        s.average_cost = 0.0
        s.peak_equity_usd = quote_usd
        s.day_start_equity_usd = quote_usd
        s.mark_price = mark_price
        s.mark_bid = s.mark_ask = mark_price
        s.last_mark_ms = t_ms
        self.baseline_base_btc = base_btc + base_locked_btc
        self.venue_quote_usd, self.venue_base_btc, self.venue_base_locked_btc = quote_usd, base_btc, base_locked_btc
        self.seeded = True
        self.seeded_at_ms = t_ms

    def balances(self) -> tuple[float | None, float | None]:
        """(quote available for bids, base available for asks), for the risk authorizer."""
        if not self.seeded:
            return None, None
        return self.state.cash_usd, self.baseline_base_btc + self.state.inventory_btc - self.base_fees_btc

    # ------------------------------------------------------------------ fills

    def apply_fill(self, fill: Any, *, fee_scenario: str | None = None) -> dict[str, float]:
        notional = fill.quantity * fill.price
        status = str(getattr(fill, "fee_status", "") or "")
        if status in BOOKED_FEE_STATUSES:
            fee = float(getattr(fill, "fee_usd", 0.0) or 0.0)
            if status == "venue":
                self.fees_venue_usd += fee
            else:
                self.fees_converted_usd += fee
                self.base_fees_btc += float(getattr(fill, "fee", 0.0) or 0.0)
        else:
            fee = self.costs.maker_fee_usd(notional, fee_scenario)
            self.fees_assumed_usd += fee
            self.fills_unconverted += 1
        liquidity = str(getattr(fill, "liquidity", "maker") or "maker")
        self.fills_by_liquidity[liquidity] = self.fills_by_liquidity.get(liquidity, 0) + 1
        booked = self._book(fill, fee=fee)
        booked["fee_status"] = status or "assumed"  # type: ignore[assignment]
        return booked

    # ------------------------------------------------------------------ reconciliation

    def expected_balances(self) -> tuple[float, float]:
        """What the account should hold if every booked fill is the whole story: fees the
        venue took in base (or in a third asset) were booked here against cash, so the
        quote expectation adds them back and the base expectation removes the base fees."""
        s = self.state
        quote = s.cash_usd + self.fees_converted_usd + self.fees_assumed_usd
        base = self.baseline_base_btc + s.inventory_btc - self.base_fees_btc
        return quote, base

    def reconcile_balances(
        self,
        *,
        quote_usd: float,
        base_btc: float,
        base_locked_btc: float,
        t_ms: int,
        quote_tolerance_usd: float,
        base_tolerance_btc: float,
    ) -> dict[str, Any]:
        expected_quote, expected_base = self.expected_balances()
        actual_base = base_btc + base_locked_btc
        dq, db = quote_usd - expected_quote, actual_base - expected_base
        ok = abs(dq) <= quote_tolerance_usd and abs(db) <= base_tolerance_btc
        self.reconciliations += 1
        self.venue_quote_usd, self.venue_base_btc, self.venue_base_locked_btc = quote_usd, base_btc, base_locked_btc
        result = {
            "t_ms": t_ms,
            "ok": ok,
            "expected_quote_usd": round(expected_quote, 6),
            "venue_quote_usd": quote_usd,
            "quote_delta_usd": round(dq, 6),
            "quote_tolerance_usd": quote_tolerance_usd,
            "expected_base_btc": round(expected_base, 8),
            "venue_base_btc": actual_base,
            "base_delta_btc": round(db, 8),
            "base_tolerance_btc": base_tolerance_btc,
            "adopted": False,
        }
        if not ok:
            # The venue is the fact. Adopt its figures, keep the record of the difference.
            self.discrepancies += 1
            s = self.state
            s.cash_usd = quote_usd - self.fees_converted_usd - self.fees_assumed_usd
            new_inventory = actual_base - self.baseline_base_btc + self.base_fees_btc
            if abs(new_inventory) < 1e-12:
                new_inventory, s.average_cost = 0.0, 0.0
            elif s.inventory_btc == 0.0 or (s.inventory_btc > 0) != (new_inventory > 0):
                s.average_cost = s.mark_price or s.average_cost
            s.inventory_btc = new_inventory
            result["adopted"] = True
            self.adjustments.append({**result, "note": "venue wins: balances adopted; the cost of the adjusted inventory is the mark"})
        self.last_reconciliation = result
        return result

    # ------------------------------------------------------------------ reading

    def snapshot(self) -> dict[str, Any]:
        base = super().snapshot()
        s = self.state
        held = self.baseline_base_btc + s.inventory_btc - self.base_fees_btc
        return {
            **base,
            "mode": "live",
            "seeded": self.seeded,
            "seeded_at_ms": self.seeded_at_ms,
            "baseline_base_btc": round(self.baseline_base_btc, 8),
            "base_held_btc": round(held, 8),
            "account_equity_usd": round(s.cash_usd + held * (s.mark_price or 0.0), 6),
            "venue_quote_usd": self.venue_quote_usd,
            "venue_base_btc": self.venue_base_btc,
            "venue_base_locked_btc": self.venue_base_locked_btc,
            "fees_venue_usd": round(self.fees_venue_usd, 6),
            "fees_converted_usd": round(self.fees_converted_usd, 6),
            "fees_assumed_usd": round(self.fees_assumed_usd, 6),
            "base_fees_btc": round(self.base_fees_btc, 8),
            "fills_unconverted_fee": self.fills_unconverted,
            "fills_by_liquidity": dict(self.fills_by_liquidity),
            "reconciliations": self.reconciliations,
            "discrepancies": self.discrepancies,
            "last_reconciliation": self.last_reconciliation,
            "adjustments": list(self.adjustments)[-5:],
            "note": "starting equity is the quote balance at seed; inventory and P&L are this maker's fills only; the base held before the run is a baseline, not inventory",
        }

    def export(self) -> dict[str, Any]:
        return {
            **super().export(),
            "mode": "live",
            "baseline_base_btc": self.baseline_base_btc,
            "base_fees_btc": self.base_fees_btc,
            "fees_venue_usd": self.fees_venue_usd,
            "fees_converted_usd": self.fees_converted_usd,
            "fees_assumed_usd": self.fees_assumed_usd,
            "reconciliations": self.reconciliations,
            "discrepancies": self.discrepancies,
        }

    @classmethod
    def restore(cls, payload: dict[str, Any], cost_model: MarketMakerCostModel | None = None) -> MarketMakerLedger:  # noqa: ARG003 - contract
        raise ValueError("a live ledger is rebuilt from the venue at start, never restored from a saved state")


__all__ = ["BOOKED_FEE_STATUSES", "LiveLedger"]
