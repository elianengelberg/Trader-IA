"""The market-maker engine: one event at a time, in this order and never another.

    DATA VALIDITY  ->  GLOBAL SAFETY GATE  ->  RISK CONTROLLER  ->  QUOTING  ->  PAPER EXECUTION

The engine owns its own local book (mirroring the venue's sync procedure from the
snapshots and diffs it is fed), the feature engine, the fair-value engine, the markout
tracker and toxicity engine, the inventory manager, the spread engine, the maker's own
risk controller, the quoting engine, the paper execution simulator and the maker's own
ledger. It is fed the same kinds of events live and in replay — snapshot, depth,
trade, book, disconnect — with the receive time as the only clock, so a replay of the
tape is the live run, exactly.

Every decision, quote, cancel and fill is written to an explainable journal with the
features, fair value, inventory and reason at that moment; a result is appended later
as its own row referring back, never rewritten into the decision. The journal hashes,
so two runs over the same tape and configuration must agree byte for byte.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from tia.mm.adverse_selection import FillObservation, MarkoutTracker, RegimeConfig, regimes_of
from tia.mm.costs import MarketMakerCostConfig, MarketMakerCostModel
from tia.mm.fair_value import FairValueConfig, FairValueEngine
from tia.mm.features import FeatureConfig, FeatureEngine, FeatureVector
from tia.mm.inventory import InventoryConfig, InventoryManager
from tia.mm.latency_model import LatencyScenario
from tia.mm.ledger import MarketMakerLedger
from tia.mm.order_book import DepthSnapshot, DepthUpdate, LocalOrderBook
from tia.mm.quoting import AdaptiveQuotingEngine, QuoteDecision, QuotingConfig
from tia.mm.risk import MarketMakerRiskController, MarketMakerRiskLimits
from tia.mm.safety import GlobalTradingSafetyGate, SafetyStatus
from tia.mm.sim import PaperMarketMakerExecution, SimulatedFill, SimulatedOrder
from tia.mm.spread import SpreadConfig, SpreadEngine
from tia.mm.streams import TradeEvent
from tia.mm.toxicity import ToxicityConfig, ToxicityEngine


@dataclass(frozen=True)
class MarketMakerConfig:
    symbol: str = "BTC-USD"
    starting_equity_usd: float = 10_000.0
    fee_scenario: str = "assumed"
    max_data_age_ms: int = 2_000
    requote_interval_ms: int = 500
    requote_threshold_bps: float = 0.5
    features: FeatureConfig = field(default_factory=FeatureConfig)
    fair_value: FairValueConfig = field(default_factory=FairValueConfig)
    spread: SpreadConfig = field(default_factory=SpreadConfig)
    inventory: InventoryConfig = field(default_factory=InventoryConfig)
    quoting: QuotingConfig = field(default_factory=QuotingConfig)
    limits: MarketMakerRiskLimits = field(default_factory=MarketMakerRiskLimits)
    costs: MarketMakerCostConfig = field(default_factory=MarketMakerCostConfig)
    toxicity: ToxicityConfig = field(default_factory=ToxicityConfig)
    regimes: RegimeConfig = field(default_factory=RegimeConfig)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in self.__dict__.items():
            out[key] = dict(value.__dict__) if hasattr(value, "__dict__") and not isinstance(value, (int, float, str)) else value
        return out

    @property
    def config_id(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:12]


class MarketMakerEngine:
    def __init__(
        self,
        config: MarketMakerConfig,
        *,
        latency: LatencyScenario,
        gate: GlobalTradingSafetyGate,
        journal_sink: Callable[[dict[str, Any]], None] | None = None,
        journal_keep: int = 5_000,
    ) -> None:
        self.config = config
        self.latency = latency
        self.gate = gate
        self.book = LocalOrderBook(symbol=config.symbol)
        self.features = FeatureEngine(config.features)
        self.fair_value = FairValueEngine(config.fair_value)
        self.markouts = MarkoutTracker()
        self.toxicity = ToxicityEngine(config.toxicity)
        self.inventory = InventoryManager(config.inventory)
        self.spread = SpreadEngine(config.spread)
        self.controller = MarketMakerRiskController(config.limits)
        self.quoting = AdaptiveQuotingEngine(config.quoting)
        self.execution = PaperMarketMakerExecution(latency)
        self.costs = MarketMakerCostModel(config.costs)
        self.ledger = MarketMakerLedger(config.starting_equity_usd, self.costs)
        self._journal_sink = journal_sink
        self.journal: deque[dict[str, Any]] = deque(maxlen=journal_keep)
        self._hasher = hashlib.sha256()
        self.journal_rows = 0
        self.events = 0
        self.decisions = 0
        self.quotes = 0
        self.requotes = 0
        self.cancels = 0
        self.no_quote_reasons: dict[str, int] = {}
        self.gate_blocks = 0
        self.data_blocks = 0
        self.unresolved_events = 0
        self.holds = 0  # resting quotes kept through a pacing denial, each one journaled
        self.hold_cancels = 0  # pacing denial while the quote had to move: cancelled, not replaced
        self._last_decision_ms: int | None = None
        self._last_event_ms: int | None = None
        self._last_features: FeatureVector | None = None
        self.last_decision: QuoteDecision | None = None
        self.last_gate: SafetyStatus | None = None
        self.last_block_reason = ""
        self._active: list[SimulatedOrder] = []
        self._order_regimes: dict[str, dict[str, str]] = {}

    # ------------------------------------------------------------------ journal

    def _write(self, row: dict[str, Any]) -> None:
        self.journal.append(row)
        self.journal_rows += 1
        line = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
        self._hasher.update(line.encode())
        self._hasher.update(b"\n")
        if self._journal_sink is not None:
            self._journal_sink(row)

    def journal_hash(self) -> str:
        return self._hasher.hexdigest()

    # ------------------------------------------------------------------ events

    def on_event(self, kind: str, event: Any, t_ms: int) -> None:
        self.events += 1
        if kind in ("snapshot", "checkpoint"):
            snapshot = event if isinstance(event, DepthSnapshot) else DepthSnapshot(int(event["id"]), tuple(tuple(x) for x in event["b"]), tuple(tuple(x) for x in event["a"]))
            # A snapshot is authoritative whatever the book held: adopt it as the live sync did.
            self.book.begin_sync()
            self.book.apply_snapshot(snapshot, received_at_ms=t_ms)
            self._last_event_ms = t_ms
        elif kind == "depth" and isinstance(event, DepthUpdate):
            self.features.before_depth(event, self.book)
            self.book.apply_update(event)
            self.features.after_depth(event, self.book)
            self._last_event_ms = t_ms
        elif kind == "trade" and isinstance(event, TradeEvent):
            self.features.on_trade(event)
            self._last_event_ms = t_ms
        elif kind == "disconnect":
            self.book.invalidate("stream disconnected")
            self._block(t_ms, "data", "stream disconnected")
            return
        # Paper execution advances on every event, before any new decision.
        for fill in self.execution.on_event(kind, event, self.book, t_ms):
            self._on_fill(fill, t_ms)
        self._note_unresolved(t_ms)
        if self.book.is_valid:
            bid, ask, mid = self.book.best_bid(), self.book.best_ask(), self.book.mid
            if bid is not None and ask is not None and mid is not None:
                self.ledger.mark(t_ms, bid=bid[0], ask=ask[0])
                for markout in self.markouts.on_mid(t_ms, mid):
                    if not markout.observation.shadow:
                        # Only confirmed fills teach toxicity and cost the ledger.
                        self.toxicity.observe(markout)
                        adverse = markout.adverse_bps_1s or 0.0
                        self.ledger.record_adverse_selection(adverse / 10_000.0 * markout.observation.price * markout.observation.quantity)
                    self._write({"t": t_ms, "kind": "markout", **markout.as_dict()})
        self._maybe_decide(t_ms)

    def _note_unresolved(self, t_ms: int) -> None:
        """An order whose optimistic-but-not-conservative quantity grew: written down as
        UNRESOLVED with its context, and shadowed in the markout tracker so the cases the
        simulator refuses to book can be compared with the ones it books."""
        for order, grew in self.execution.last_unresolved:
            if grew <= 1e-12 or order.queue is None:
                continue
            self.unresolved_events += 1
            regimes = self._order_regimes.get(order.order_id, {})
            mid = self.book.mid
            row = {
                "t": t_ms,
                "kind": "unresolved",
                "order_id": order.order_id,
                "side": order.side,
                "price": order.price,
                "quantity": grew,
                "mid": mid,
                "queue_ahead_conservative": order.queue.ahead_conservative,
                "queue_ahead_optimistic": order.queue.ahead_optimistic,
                "inventory_btc": self.ledger.state.inventory_btc,
                "regimes": regimes,
                "note": "would fill only if cancellations were ahead of us: not booked",
            }
            self._write(row)
            if mid is not None:
                self.markouts.register(FillObservation(f"shadow-{order.order_id}-{self.unresolved_events}", t_ms, order.side, order.price, grew, mid, regimes, shadow=True))

    def _on_fill(self, fill: SimulatedFill, t_ms: int) -> None:
        booked = self.ledger.apply_fill(fill, fee_scenario=self.config.fee_scenario)
        regimes = self._order_regimes.get(fill.order_id, {})
        self.markouts.register(FillObservation(fill.fill_id, fill.t_ms, fill.side, fill.price, fill.quantity, fill.mid_at_fill or fill.price, regimes))
        self._write({"t": t_ms, "kind": "fill", **fill.as_dict(), **booked, "inventory_btc": self.ledger.state.inventory_btc, "regimes": regimes})

    # ------------------------------------------------------------------ the hierarchy

    def _block(self, t_ms: int, layer: str, reason: str) -> None:
        cancelled = self.execution.cancel_all(t_ms, reason=f"{layer}: {reason}")
        self.cancels += cancelled
        self._active = []
        if layer == "gate":
            self.gate_blocks += 1
        elif layer == "data":
            self.data_blocks += 1
        if reason != self.last_block_reason or cancelled:
            self._write({"t": t_ms, "kind": "block", "layer": layer, "reason": reason, "cancelled": cancelled})
        self.last_block_reason = reason
        self.last_decision = None

    def _maybe_decide(self, t_ms: int) -> None:
        if self._last_decision_ms is not None and t_ms - self._last_decision_ms < self.config.requote_interval_ms:
            return
        self._last_decision_ms = t_ms
        self.decisions += 1
        # 1. Data validity.
        age = t_ms - self._last_event_ms if self._last_event_ms is not None else None
        if not self.book.is_valid:
            self._block(t_ms, "data", f"book {self.book.state.value}: {self.book.last_invalid_reason or 'not synced'}")
            return
        if age is None or age > self.config.max_data_age_ms:
            self._block(t_ms, "data", f"last event {age} ms ago, over {self.config.max_data_age_ms}")
            return
        # 2. Global safety gate — read-only, consulted before the maker's own controller.
        status = self.gate.status(t_ms)
        self.last_gate = status
        if not status.allows_quoting:
            self._block(t_ms, "gate", f"{status.state.value}: {status.reason}")
            return
        self.last_block_reason = ""
        # 3. The maker's own risk controller.
        allowance = self.controller.allowance(self.ledger.view(), t_ms)
        # 4. Quoting.
        features = self.features.compute(self.book, t_ms)
        if features is None:
            self._block(t_ms, "data", "no features")
            return
        self._last_features = features
        fv = self.fair_value.estimate(features)
        inventory = self.inventory.assess(self.ledger.state.inventory_btc)
        regimes_bid = regimes_of(features, "buy", self.config.regimes)
        regimes_ask = regimes_of(features, "sell", self.config.regimes)
        toxicity = max((self.toxicity.reading(regimes_bid), self.toxicity.reading(regimes_ask)), key=lambda r: r.score or 0.0)
        expected_adverse = toxicity.adverse_mean_bps or 0.0
        spread = self.spread.target(features, fee_bps=self.costs.maker_fee_bps, expected_adverse_bps=expected_adverse, toxicity_widen_bps=toxicity.widen_bps)
        active = [o for o in self._active if o.state in ("pending_arrival", "resting")]
        if not allowance.allowed and allowance.hold_only and active:
            # Pacing denial (quote rate / minimum interval) with quotes resting. Nothing new
            # may be placed; what may be held is decided by re-evaluating the quote as if
            # pacing allowed it: still within the requote threshold -> HOLD, journaled with
            # the reason; moved (fair value, inventory, toxicity, spread, a side no longer
            # allowed) -> cancelled normally, and not replaced. Every hard rule above still
            # applies: the gate was consulted first and a hard denial never reaches here.
            probe = replace(allowance, allowed=True)
            desired = self.quoting.decide(features=features, fair_value=fv, inventory=inventory, spread=spread, toxicity=toxicity, allowance=probe, latency=self.latency, t_ms=t_ms)
            row = {
                "t": t_ms,
                "kind": "decision",
                "fair_value": fv.fair_value,
                "fair_value_offset_bps": fv.fair_value_offset_bps,
                "fair_value_confidence": fv.fair_value_confidence,
                "bid": desired.bid_price,
                "ask": desired.ask_price,
                "bid_size": desired.bid_size,
                "ask_size": desired.ask_size,
                "half_spread_bps": desired.half_spread_bps,
                "spread_binding": spread.binding,
                "inventory_btc": inventory.inventory_btc,
                "inventory_adjustment_bps": inventory.inventory_adjustment_bps,
                "toxicity": toxicity.as_dict(),
                "allowance": allowance.as_dict(),
                "features": self._feature_summary(features),
                "regimes": regimes_bid,
                "gate": status.state.value,
                "resting_orders": [o.order_id for o in active],
            }
            if desired.is_quote and not self._moved(desired):
                self.holds += 1
                row["decision"] = "hold"
                row["reason"] = f"held through pacing denial ({allowance.reason}): resting quotes still within {self.config.requote_threshold_bps} bps of the desired ones"
                self._write(row)
                return
            cancelled = self.execution.cancel_all(t_ms, reason=f"pacing denial while a requote was due ({allowance.reason})")
            self.cancels += cancelled
            self.hold_cancels += 1
            self._active = []
            row["decision"] = "no_quote"
            row["reason"] = f"requote due but pacing denied ({allowance.reason}): {'quotes moved' if desired.is_quote else desired.quote_reason}; cancelled, not replaced"
            row["cancelled"] = cancelled
            self._write(row)
            return
        decision = self.quoting.decide(features=features, fair_value=fv, inventory=inventory, spread=spread, toxicity=toxicity, allowance=allowance, latency=self.latency, t_ms=t_ms)
        self.last_decision = decision
        row = {
            "t": t_ms,
            "kind": "decision",
            "decision": "quote" if decision.is_quote else "no_quote",
            "fair_value": fv.fair_value,
            "fair_value_offset_bps": fv.fair_value_offset_bps,
            "fair_value_confidence": fv.fair_value_confidence,
            "fair_value_components_bps": fv.components_bps,
            "bid": decision.bid_price,
            "ask": decision.ask_price,
            "bid_size": decision.bid_size,
            "ask_size": decision.ask_size,
            "half_spread_bps": decision.half_spread_bps,
            "spread_binding": spread.binding,
            "inventory_btc": inventory.inventory_btc,
            "inventory_adjustment_bps": inventory.inventory_adjustment_bps,
            "toxicity": toxicity.as_dict(),
            "allowance": allowance.as_dict(),
            "features": self._feature_summary(features),
            "regimes": regimes_bid,
            "reason": decision.quote_reason,
            "gate": status.state.value,
        }
        # 5. Paper execution.
        if not decision.is_quote:
            self.no_quote_reasons[decision.quote_reason.split(":")[0]] = self.no_quote_reasons.get(decision.quote_reason.split(":")[0], 0) + 1
            cancelled = self.execution.cancel_all(t_ms, reason=decision.quote_reason)
            self.cancels += cancelled
            self._active = []
            row["cancelled"] = cancelled
            self._write(row)
            return
        if self._active and not self._moved(decision):
            row["decision"] = "hold"
            row["reason"] = "quotes unchanged within the requote threshold"
            self._write(row)
            return
        if self._active:
            self.cancels += self.execution.cancel_all(t_ms, reason="requote")
            self.requotes += 1
        placed = self.execution.place(decision, t_ms)
        for order in placed:
            self._order_regimes[order.order_id] = regimes_bid if order.side == "buy" else regimes_ask
        if len(self._order_regimes) > 4_000:  # regimes are needed while an order lives; prune the oldest
            for stale in list(self._order_regimes)[:2_000]:
                if stale not in self.execution.orders:
                    del self._order_regimes[stale]
        self._active = placed
        self.controller.record_quote(t_ms)
        self.quotes += 1
        row["orders"] = [o.order_id for o in placed]
        self._write(row)

    def _moved(self, decision: QuoteDecision) -> bool:
        threshold = self.config.requote_threshold_bps
        active = {o.side: o for o in self._active if o.state in ("pending_arrival", "resting")}
        if not active:
            return True
        for side, price, size in (("buy", decision.bid_price, decision.bid_size), ("sell", decision.ask_price, decision.ask_size)):
            order = active.get(side)
            if (order is None) != (price is None):
                return True
            if order is not None and price is not None and (abs(price - order.price) / order.price * 10_000.0 > threshold or abs(size - order.quantity) > 1e-9):
                return True
        return False

    @staticmethod
    def _feature_summary(features: FeatureVector) -> dict[str, Any]:
        flow = features.trade_flow.get("5s")
        return {
            "mid": features.mid_price,
            "microprice": features.microprice,
            "microprice_delta_bps": round(features.microprice_delta_bps, 4),
            "imbalance_t1": features.imbalance_t1,
            "imbalance_t5": features.imbalance_t5,
            "imbalance_t10": features.imbalance_t10,
            "imbalance_t20": features.imbalance_t20,
            "spread_bps": round(features.spread_bps, 4),
            "spread_regime": features.spread_regime,
            "ofi_norm": features.ofi_norm,
            "flow_norm_5s": flow.flow_norm if flow else None,
            "vol_5s_bps": features.vol_bps.get("5s"),
            "data_age_ms": features.data_age_ms,
        }

    # ------------------------------------------------------------------ reading

    def snapshot(self) -> dict[str, Any]:
        return {
            "symbol": self.config.symbol,
            "config_id": self.config.config_id,
            "latency": self.latency.as_dict(),
            "events": self.events,
            "decisions": self.decisions,
            "quotes": self.quotes,
            "requotes": self.requotes,
            "cancels": self.cancels,
            "gate_blocks": self.gate_blocks,
            "data_blocks": self.data_blocks,
            "unresolved_events": self.unresolved_events,
            "holds": self.holds,
            "hold_cancels": self.hold_cancels,
            "no_quote_reasons": dict(self.no_quote_reasons),
            "gate": self.last_gate.as_dict() if self.last_gate else None,
            "last_block_reason": self.last_block_reason,
            "book": {"state": self.book.state.value, "valid": self.book.is_valid, "update_id": self.book.update_id, "best_bid": self.book.best_bid(), "best_ask": self.book.best_ask(), "spread_bps": self.book.spread_bps},
            "features": self._feature_summary(self._last_features) if self._last_features else None,
            "last_decision": self.last_decision.as_dict() if self.last_decision else None,
            "active_orders": [o.as_dict() for o in self._active if o.state in ("pending_arrival", "resting")],
            "execution": self.execution.stats(),
            "ledger": self.ledger.snapshot(),
            "controller": self.controller.as_dict(),
            "markouts": self.markouts.summary(),
            "toxicity": self.toxicity.as_dict(),
            "journal_rows": self.journal_rows,
            "journal_hash": self.journal_hash(),
        }


__all__ = ["MarketMakerConfig", "MarketMakerEngine"]
