"""Microstructure features: computed from what was seen, described, never judged."""

from __future__ import annotations

import math

import pytest

from tia.mm.features import FeatureConfig, FeatureEngine
from tia.mm.order_book import DepthUpdate, LocalOrderBook, snapshot_from_levels
from tia.mm.streams import TradeEvent

T0 = 1_789_754_400_000


def _book() -> LocalOrderBook:
    book = LocalOrderBook("BTC-USD")
    book.begin_sync()
    # Prices rounded like a parsed decimal string would be, so keys match across events.
    bids = [(round(100_000.0 - i * 0.1, 1), float(i + 1)) for i in range(25)]  # deeper is bigger
    asks = [(round(100_000.1 + i * 0.1, 1), 1.0) for i in range(25)]
    assert book.apply_snapshot(snapshot_from_levels(100, bids, asks))
    return book


def _update(uid: int, t: int, bids=(), asks=()) -> DepthUpdate:  # type: ignore[no-untyped-def]
    return DepthUpdate(first_update_id=uid, final_update_id=uid, bids=tuple(bids), asks=tuple(asks), event_time_ms=t - 30, received_at_ms=t)


def _trade(tid: int, t: int, price: float, qty: float, *, buyer_is_maker: bool) -> TradeEvent:
    return TradeEvent(trade_id=tid, price=price, quantity=qty, buyer_is_maker=buyer_is_maker, trade_time_ms=t - 5, event_time_ms=t - 2, received_at_ms=t)


def _feed(engine: FeatureEngine, book: LocalOrderBook, update: DepthUpdate) -> None:
    engine.before_depth(update, book)
    assert book.apply_update(update)
    engine.after_depth(update, book)


# ------------------------------------------------------------------ 1. imbalance, 2. microprice


def test_imbalance_at_every_depth_matches_the_visible_quantities() -> None:
    book, engine = _book(), FeatureEngine()
    fv = engine.compute(book, T0)
    assert fv is not None
    # bids 1..n vs asks n: top1 = (1-1)/(1+1) = 0; top5 = (15-5)/(15+5) = 0.5
    assert fv.imbalance_t1 == pytest.approx(0.0)
    assert fv.imbalance_t5 == pytest.approx(0.5)
    assert fv.imbalance_t10 == pytest.approx((55 - 10) / 65)
    assert fv.imbalance_t20 == pytest.approx((210 - 20) / 230)


def test_microprice_leans_towards_the_heavier_side() -> None:
    book, engine = _book(), FeatureEngine()
    _feed(engine, book, _update(101, T0, bids=[(100_000.0, 3.0)]))  # bid 3x heavier than the ask
    fv = engine.compute(book, T0)
    assert fv is not None
    expected = (100_000.1 * 3.0 + 100_000.0 * 1.0) / 4.0
    assert fv.microprice == pytest.approx(expected)
    assert fv.microprice_minus_mid > 0 and fv.microprice_delta_bps == pytest.approx((expected - fv.mid_price) / fv.mid_price * 1e4)
    assert fv.spread_abs == pytest.approx(0.1) and fv.spread_bps == pytest.approx(0.1 / 100_000.05 * 1e4)


# ------------------------------------------------------------------ 3. order-flow imbalance


def test_ofi_separates_additions_cancellations_and_trades() -> None:
    book, engine = _book(), FeatureEngine(FeatureConfig(ofi_window_ms=10_000))
    _feed(engine, book, _update(101, T0 + 100, bids=[(100_000.0, 2.5)]))  # +1.5 at the best bid
    fv = engine.compute(book, T0 + 100)
    assert fv is not None
    assert fv.bid_additions == pytest.approx(1.5) and fv.bid_cancellations == 0.0
    assert fv.ofi_last == pytest.approx(2.5 - 1.0)  # CKS at an unchanged best price: q_new - q_old

    _feed(engine, book, _update(102, T0 + 200, asks=[(100_000.1, 0.4)]))  # ask shrinks 1.0 -> 0.4, no trades
    fv = engine.compute(book, T0 + 200)
    assert fv is not None
    assert fv.ask_cancellations == pytest.approx(0.6) and fv.ask_additions == 0.0
    assert fv.ofi_last == pytest.approx(-(0.4 - 1.0))  # supply withdrawn at the ask counts as positive OFI

    # A decrease explained by prints at that price is a trade, not a cancellation.
    engine.on_trade(_trade(1, T0 + 250, 100_000.0, 2.0, buyer_is_maker=True))  # seller hits the bid
    _feed(engine, book, _update(103, T0 + 300, bids=[(100_000.0, 0.5)]))  # 2.5 -> 0.5: 2.0 traded, 0 cancelled
    fv = engine.compute(book, T0 + 300)
    assert fv is not None
    assert fv.bid_cancellations == pytest.approx(0.0)
    assert fv.ofi_window == pytest.approx(1.5 + 0.6 + (0.5 - 2.5))
    assert fv.ofi_norm is not None and -1.0 <= fv.ofi_norm <= 1.0

    # Only the best N levels count: a change 20 levels deep is not order flow at the touch.
    _feed(engine, book, _update(104, T0 + 400, bids=[(100_000.0 - 2.0, 50.0)]))
    fv = engine.compute(book, T0 + 400)
    assert fv is not None
    assert fv.bid_additions == pytest.approx(1.5)


# ------------------------------------------------------------------ 4. trade classification and flow


def test_trade_flow_uses_the_venue_aggressor_flag_over_windows() -> None:
    book, engine = _book(), FeatureEngine()
    engine.on_trade(_trade(1, T0 + 100, 100_000.1, 0.5, buyer_is_maker=False))  # buyer crossed: buy
    engine.on_trade(_trade(2, T0 + 900, 100_000.0, 0.2, buyer_is_maker=True))  # seller crossed: sell
    engine.on_trade(_trade(3, T0 + 4_000, 100_000.1, 1.3, buyer_is_maker=False))
    fv = engine.compute(book, T0 + 4_500)
    assert fv is not None
    one = fv.trade_flow["1s"]
    assert one.trade_count == 1 and one.buy_volume == pytest.approx(1.3) and one.sell_volume == 0.0
    five = fv.trade_flow["5s"]
    assert five.trade_count == 3 and five.buy_volume == pytest.approx(1.8) and five.sell_volume == pytest.approx(0.2)
    assert five.net_aggressive_volume == pytest.approx(1.6) and five.average_trade_size == pytest.approx(2.0 / 3)
    assert five.flow_norm == pytest.approx(1.6 / 2.0)
    assert fv.trade_flow["60s"].trade_count == 3
    # A trade in the future of t is not in the window at t.
    earlier = engine.compute(book, T0 + 500)
    assert earlier is not None and earlier.trade_flow["60s"].trade_count == 1


# ------------------------------------------------------------------ 5. volatility, returns


def test_volatility_and_returns_use_only_observed_history() -> None:
    book, engine = _book(), FeatureEngine()
    fv = engine.compute(book, T0)
    assert fv is not None and fv.vol_bps["5s"] is None and fv.returns_bps["1s"] is None
    # Move the mid without ever crossing: removing the best ask lifts it, removing the
    # best bid lowers it. Alternating signs give the returns a spread.
    steps = [("ask", 100_000.1), ("ask", 100_000.2), ("bid", 100_000.0), ("ask", 100_000.3), ("bid", 99_999.9)]
    for i, (side, price) in enumerate(steps):
        kwargs = {"asks": [(price, 0.0)]} if side == "ask" else {"bids": [(price, 0.0)]}
        _feed(engine, book, _update(101 + i, T0 + 500 * (i + 1), **kwargs))
    fv = engine.compute(book, T0 + 2_600)
    assert fv is not None
    assert fv.vol_bps["5s"] is not None and fv.vol_bps["5s"] > 0
    assert fv.returns_bps["1s"] is not None
    assert fv.returns_bps["5s"] is None  # only 2.5 s of history exist: no 5 s return is invented
    # A constant mid has no samples, so no volatility number: None, not zero by fiat.
    flat_book, flat = _book(), FeatureEngine()
    for i in range(6):
        _feed(flat, flat_book, _update(101 + i, T0 + 200 * (i + 1), bids=[(100_000.0 - 1.0, 5.0 + i)]))
    fv = flat.compute(flat_book, T0 + 1_300)
    assert fv is not None and fv.vol_bps["5s"] is None


# ------------------------------------------------------------------ 6. spread regime


def test_spread_regime_is_unknown_until_enough_samples_then_labelled() -> None:
    book, engine = _book(), FeatureEngine(FeatureConfig(spread_min_samples=20))
    fv = engine.compute(book, T0)
    assert fv is not None and fv.spread_regime == "unknown" and fv.spread_pct is None
    # 30 samples: spread widens over time (asks pulled step by step)
    for i in range(30):
        pulled = min(i, 20)  # never empty the ask side: a one-sided book is not a market
        _feed(engine, book, _update(101 + i, T0 + 100 * (i + 1), asks=[(round(100_000.1 + j * 0.1, 1), 0.0) for j in range(pulled)] if pulled else []))
    fv = engine.compute(book, T0 + 3_100)
    assert fv is not None
    assert fv.spread_regime == "wide" and fv.spread_pct is not None and fv.spread_pct >= 0.75
    # Back to the tightest spread seen: tight.
    _feed(engine, book, _update(131, T0 + 3_200, asks=[(100_000.1, 1.0)]))
    fv = engine.compute(book, T0 + 3_200)
    assert fv is not None and fv.spread_regime == "tight"


# ------------------------------------------------------------------ 19. no look-ahead (prefix)


def test_features_at_t_do_not_change_when_later_events_arrive() -> None:
    def run(n_events: int) -> dict:  # type: ignore[type-arg]
        book, engine = _book(), FeatureEngine()
        snapshot_at_k = None
        uid = 100
        for i in range(n_events):
            t = T0 + 100 * (i + 1)
            if i % 3 == 2:
                engine.on_trade(_trade(i, t, 100_000.1, 0.3, buyer_is_maker=bool(i % 2)))
            else:
                uid += 1
                _feed(engine, book, _update(uid, t, bids=[(round(100_000.0 - (i % 4) * 0.1, 1), 1.0 + i * 0.1)]))
            if i == 9:
                fv = engine.compute(book, t)
                assert fv is not None
                snapshot_at_k = fv.as_dict()
        assert snapshot_at_k is not None
        return snapshot_at_k

    assert run(10) == run(40)


def test_features_are_none_while_the_book_is_not_valid() -> None:
    book, engine = LocalOrderBook("BTC-USD"), FeatureEngine()
    book.begin_sync()
    assert engine.compute(book, T0) is None
    assert math.isfinite(T0)
