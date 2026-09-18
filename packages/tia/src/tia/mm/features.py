"""Microstructure features: descriptions of the book and the tape at time ``t``.

Every number here is computed from events received at or before ``t`` — the engine
never holds the tape, it is fed one event at a time in arrival order — and every
number is a **description, not a signal**. Whether imbalance, microprice, order-flow
imbalance or trade flow predict anything is measured downstream, against markouts,
and never assumed.

What is computed, and from what:

* **Imbalance** at 1/5/10/20 levels — from the local book's visible quantities.
* **Microprice** — size-weighted mid at the top of book.
* **Order-flow imbalance (OFI)** — from the real depth diffs, the Cont-Kukanov-Stoikov
  event at the best levels, summed over a window and normalised by depth; plus, over
  the best N levels, quantity **added** and quantity **cancelled** per side, where a
  decrease is a cancellation only for the part not explained by trades printed at that
  price since the previous diff.
* **Trade flow** — the venue's own aggressor flag (``buyer_is_maker``), never inferred
  and never from the future, aggregated over 1/5/15/30/60 s windows.
* **Short-term volatility** — standard deviation of log mid changes over 1/5/15/30/60 s
  of observed history, in bps.
* **Spread** — absolute, bps, percentile over a rolling window, and a regime label.
* **Recent movement** — mid returns over 1/5/30 s.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from tia.mm.order_book import DepthUpdate, LocalOrderBook
from tia.mm.streams import TradeEvent

FLOW_WINDOWS_MS: dict[str, int] = {"1s": 1_000, "5s": 5_000, "15s": 15_000, "30s": 30_000, "60s": 60_000}
VOL_WINDOWS_MS: dict[str, int] = dict(FLOW_WINDOWS_MS)
RETURN_WINDOWS_MS: dict[str, int] = {"1s": 1_000, "5s": 5_000, "30s": 30_000}


@dataclass(frozen=True)
class FeatureConfig:
    ofi_levels: int = 5  # additions/cancellations are counted this deep
    ofi_window_ms: int = 1_000
    spread_window_ms: int = 30 * 60_000
    spread_min_samples: int = 60
    spread_tight_pct: float = 0.25
    spread_wide_pct: float = 0.75
    vol_min_returns: int = 3
    history_ms: int = 60_000  # the longest window any feature needs


@dataclass(frozen=True)
class TradeFlowWindow:
    window: str
    buy_volume: float
    sell_volume: float
    net_aggressive_volume: float
    trade_count: int
    average_trade_size: float
    flow_norm: float | None  # net / (buy + sell) in [-1, 1]

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class FeatureVector:
    t_ms: int
    update_id: int
    best_bid: float
    best_ask: float
    best_bid_size: float
    best_ask_size: float
    mid_price: float
    microprice: float
    microprice_minus_mid: float
    microprice_delta_bps: float
    imbalance_t1: float | None
    imbalance_t5: float | None
    imbalance_t10: float | None
    imbalance_t20: float | None
    spread_abs: float
    spread_bps: float
    spread_pct: float | None
    spread_regime: str
    ofi_last: float
    ofi_window: float
    ofi_norm: float | None
    bid_additions: float
    bid_cancellations: float
    ask_additions: float
    ask_cancellations: float
    trade_flow: dict[str, TradeFlowWindow]
    vol_bps: dict[str, float | None]
    returns_bps: dict[str, float | None]
    data_age_ms: int
    contributions: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        out = dict(self.__dict__)
        out["trade_flow"] = {k: v.as_dict() for k, v in self.trade_flow.items()}
        return out


class FeatureEngine:
    """Fed one event at a time; asked for a :class:`FeatureVector` at any ``t``."""

    def __init__(self, config: FeatureConfig | None = None) -> None:
        self.config = config or FeatureConfig()
        self._prev_top: tuple[float, float, float, float] | None = None  # bid, bid_qty, ask, ask_qty
        self._touched: dict[tuple[str, float], float] = {}  # (side, price) -> qty before the diff
        self._traded_at: dict[float, float] = {}  # price -> qty traded since the previous diff
        self._ofi: deque[tuple[int, float]] = deque()
        self._depth_samples: deque[tuple[int, float]] = deque()  # (t, top-5 depth both sides)
        self._flow: deque[tuple[int, float, float, str]] = deque()  # (t, side_sign, qty, price)
        self._mids: deque[tuple[int, float]] = deque()  # (t, log mid), on every mid change
        self._last_mid: float | None = None
        self._spreads: deque[tuple[int, float]] = deque()
        self._adds: deque[tuple[int, float, float]] = deque()  # (t, bid_add, ask_add)
        self._cancels: deque[tuple[int, float, float]] = deque()
        self._last_event_ms: int | None = None
        self.depth_events = 0
        self.trade_events = 0

    # ------------------------------------------------------------------ inputs

    def before_depth(self, update: DepthUpdate, book: LocalOrderBook) -> None:
        """Called with the book **as it is before** the diff is applied."""
        self._touched.clear()
        if not book.is_valid:
            self._prev_top = None
            return
        bid, ask = book.best_bid(), book.best_ask()
        if bid is None or ask is None:
            self._prev_top = None
            return
        self._prev_top = (bid[0], bid[1], ask[0], ask[1])
        top_bids, top_asks = book.top(self.config.ofi_levels)
        band_bid = top_bids[-1][0] if top_bids else bid[0]
        band_ask = top_asks[-1][0] if top_asks else ask[0]
        for price, _ in update.bids:
            if price >= band_bid:
                self._touched[("bid", price)] = book.quantity_at("bid", price)
        for price, _ in update.asks:
            if price <= band_ask:
                self._touched[("ask", price)] = book.quantity_at("ask", price)

    def after_depth(self, update: DepthUpdate, book: LocalOrderBook) -> None:
        """Called with the book **after** the diff is applied; computes OFI and flows."""
        t = update.received_at_ms
        self._last_event_ms = t
        self.depth_events += 1
        bid, ask = book.best_bid(), book.best_ask()
        if self._prev_top is not None and bid is not None and ask is not None:
            pb, qb, pa, qa = self._prev_top
            # Cont-Kukanov-Stoikov: demand at the bid up, supply at the ask down.
            e = 0.0
            e += bid[1] if bid[0] >= pb else 0.0
            e -= qb if bid[0] <= pb else 0.0
            e -= ask[1] if ask[0] <= pa else 0.0
            e += qa if ask[0] >= pa else 0.0
            self._ofi.append((t, e))
            depth_b, depth_a = book.depth(5)
            self._depth_samples.append((t, depth_b + depth_a))
        bid_add = bid_cancel = ask_add = ask_cancel = 0.0
        for (side, price), before in self._touched.items():
            after = book.quantity_at(side, price)
            delta = after - before
            if delta > 0:
                if side == "bid":
                    bid_add += delta
                else:
                    ask_add += delta
            elif delta < 0:
                unexplained = max(0.0, -delta - self._traded_at.get(price, 0.0))
                if side == "bid":
                    bid_cancel += unexplained
                else:
                    ask_cancel += unexplained
        self._adds.append((t, bid_add, ask_add))
        self._cancels.append((t, bid_cancel, ask_cancel))
        self._traded_at.clear()
        self._touched.clear()
        mid, spread_bps = book.mid, book.spread_bps
        if mid is not None and spread_bps is not None:
            if mid != self._last_mid:
                self._mids.append((t, math.log(mid)))
                self._last_mid = mid
            self._spreads.append((t, spread_bps))
        self._trim(t)

    def on_trade(self, trade: TradeEvent) -> None:
        t = trade.received_at_ms
        self._last_event_ms = t
        self.trade_events += 1
        sign = -1.0 if trade.buyer_is_maker else 1.0  # buyer is maker => seller crossed
        self._flow.append((t, sign, trade.quantity, trade.price))
        self._traded_at[trade.price] = self._traded_at.get(trade.price, 0.0) + trade.quantity
        self._trim(t)

    def _trim(self, t: int) -> None:
        horizon = t - self.config.history_ms
        for dq in (self._ofi, self._flow, self._mids, self._adds, self._cancels, self._depth_samples):
            while dq and dq[0][0] < horizon:
                dq.popleft()
        spread_horizon = t - self.config.spread_window_ms
        while self._spreads and self._spreads[0][0] < spread_horizon:
            self._spreads.popleft()

    # ------------------------------------------------------------------ output

    def compute(self, book: LocalOrderBook, t_ms: int) -> FeatureVector | None:
        """The features at ``t_ms``; None while the book cannot be trusted."""
        if not book.is_valid:
            return None
        bid, ask = book.best_bid(), book.best_ask()
        mid, micro = book.mid, book.microprice(1)
        spread, spread_bps = book.spread, book.spread_bps
        if bid is None or ask is None or mid is None or micro is None or spread is None or spread_bps is None:
            return None
        cfg = self.config

        ofi_last = self._ofi[-1][1] if self._ofi else 0.0
        ofi_window = sum(e for ts, e in self._ofi if ts > t_ms - cfg.ofi_window_ms)
        depths = [d for ts, d in self._depth_samples if ts > t_ms - cfg.ofi_window_ms]
        mean_depth = sum(depths) / len(depths) if depths else 0.0
        ofi_norm = max(-1.0, min(1.0, ofi_window / mean_depth)) if mean_depth > 0 else None

        adds = [(b, a) for ts, b, a in self._adds if ts > t_ms - cfg.ofi_window_ms]
        cancels = [(b, a) for ts, b, a in self._cancels if ts > t_ms - cfg.ofi_window_ms]

        spread_samples = [s for _, s in self._spreads]
        spread_pct: float | None = None
        regime = "unknown"
        if len(spread_samples) >= cfg.spread_min_samples:
            spread_pct = sum(1 for s in spread_samples if s <= spread_bps) / len(spread_samples)
            ordered = sorted(spread_samples)
            tight = ordered[int(cfg.spread_tight_pct * (len(ordered) - 1))]
            wide = ordered[int(cfg.spread_wide_pct * (len(ordered) - 1))]
            regime = "tight" if spread_bps <= tight else ("wide" if spread_bps >= wide else "normal")

        return FeatureVector(
            t_ms=t_ms,
            update_id=book.update_id,
            best_bid=bid[0],
            best_ask=ask[0],
            best_bid_size=bid[1],
            best_ask_size=ask[1],
            mid_price=mid,
            microprice=micro,
            microprice_minus_mid=micro - mid,
            microprice_delta_bps=(micro - mid) / mid * 10_000.0,
            imbalance_t1=book.imbalance(1),
            imbalance_t5=book.imbalance(5),
            imbalance_t10=book.imbalance(10),
            imbalance_t20=book.imbalance(20),
            spread_abs=spread,
            spread_bps=spread_bps,
            spread_pct=spread_pct,
            spread_regime=regime,
            ofi_last=ofi_last,
            ofi_window=ofi_window,
            ofi_norm=ofi_norm,
            bid_additions=sum(b for b, _ in adds),
            bid_cancellations=sum(b for b, _ in cancels),
            ask_additions=sum(a for _, a in adds),
            ask_cancellations=sum(a for _, a in cancels),
            trade_flow={name: self._flow_window(name, ms, t_ms) for name, ms in FLOW_WINDOWS_MS.items()},
            vol_bps={name: self._vol(ms, t_ms) for name, ms in VOL_WINDOWS_MS.items()},
            returns_bps={name: self._return(ms, t_ms) for name, ms in RETURN_WINDOWS_MS.items()},
            data_age_ms=max(0, t_ms - (self._last_event_ms or t_ms)),
        )

    def _flow_window(self, name: str, window_ms: int, t_ms: int) -> TradeFlowWindow:
        rows = [(sign, qty) for ts, sign, qty, _ in self._flow if ts > t_ms - window_ms and ts <= t_ms]
        buy = sum(q for s, q in rows if s > 0)
        sell = sum(q for s, q in rows if s < 0)
        count = len(rows)
        total = buy + sell
        return TradeFlowWindow(
            window=name,
            buy_volume=buy,
            sell_volume=sell,
            net_aggressive_volume=buy - sell,
            trade_count=count,
            average_trade_size=total / count if count else 0.0,
            flow_norm=(buy - sell) / total if total > 0 else None,
        )

    def _vol(self, window_ms: int, t_ms: int) -> float | None:
        logs = [lm for ts, lm in self._mids if ts > t_ms - window_ms and ts <= t_ms]
        if len(logs) < self.config.vol_min_returns + 1:
            return None
        rets = [b - a for a, b in pairwise(logs)]
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1) if len(rets) > 1 else 0.0
        return math.sqrt(var) * 10_000.0

    def _return(self, window_ms: int, t_ms: int) -> float | None:
        if self._last_mid is None:
            return None
        past = None
        for ts, lm in self._mids:
            if ts <= t_ms - window_ms:
                past = lm
            else:
                break
        if past is None:
            return None
        return (math.log(self._last_mid) - past) * 10_000.0


__all__ = [
    "FLOW_WINDOWS_MS",
    "RETURN_WINDOWS_MS",
    "VOL_WINDOWS_MS",
    "FeatureConfig",
    "FeatureEngine",
    "FeatureVector",
    "TradeFlowWindow",
]
