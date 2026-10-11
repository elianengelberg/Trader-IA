"""The spread gate reads a book or refuses; it never reads a constant as one (Phase 1.5).

A quoting feed that shows a fresh quote inside the limit lets the entry through and
prices the costs off it; a quote over the session's gate is refused at the ``spread``
stage; a quote over the risk engine's hard limit is refused by the risk engine even with
the gate off; and a quoting feed with no quote — absent, stale, failed, invalid — has
the entry refused with the reason, with no order and no position. A feed that cannot
quote at all keeps the configured constant, labelled as such.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from tests.integration.test_live_runtime import (
    QuotingMarketData,
    _seed_every_bucket,
    build_runtime_paper_with,
)
from tia.core.config import Environment, LiveConfig, RiskLimits, settings_for_env


def _events(runtime, kind: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    seen: list[dict[str, Any]] = []
    previous = runtime._on_event

    def capture(event: dict[str, Any]) -> None:
        if event.get("type") == kind:
            seen.append(event.get("data", {}))
        previous(event)

    runtime._on_event = capture
    return seen


async def _drive(runtime, market, bars: int = 150) -> None:  # type: ignore[no-untyped-def]
    _seed_every_bucket(runtime)
    for _ in range(bars):
        market.advance()
        await runtime._cycle_once()
        if runtime.counters["orders"] > 0:
            return


async def test_a_fresh_quote_inside_the_limit_lets_the_entry_through_and_is_the_source() -> None:
    runtime, _execution, market = build_runtime_paper_with(quoting=True, max_spread_bps=10.0)
    market.spread_bps = 2.0
    await runtime.start()
    try:
        await _drive(runtime, market, bars=300)
        assert runtime.counters["orders"] > 0
        assert runtime.counters["spread_unverifiable"] == 0 and runtime.counters["spread_rejected"] == 0
        view = runtime.snapshot()["market"]
        assert view["spread_source"] == "venue top of book" and view["quote_state"] == "ok"
        assert view["quote"]["spread_bps"] == pytest.approx(2.0, rel=1e-3)
    finally:
        await runtime.stop()


async def test_a_quote_over_the_sessions_gate_is_refused_at_the_spread_stage() -> None:
    runtime, execution, market = build_runtime_paper_with(quoting=True, max_spread_bps=10.0)
    market.spread_bps = 15.0  # over the gate (10), under the risk engine's ceiling (25)
    refusals = _events(runtime, "live.no_trade")
    await runtime.start()
    try:
        await _drive(runtime, market)
        assert runtime.counters["orders"] == 0
        assert runtime.counters["spread_rejected"] > 0 and runtime.counters["spread_unverifiable"] == 0
        assert any("spread gate" in str(r.get("reason", "")) for r in refusals)
        assert await execution.get_positions() == {}
    finally:
        await runtime.stop()


async def test_a_quote_over_the_risk_engines_ceiling_is_refused_even_with_the_gate_off() -> None:
    """``RiskLimits.max_spread_bps`` is a hard limit on the *observed* spread: the risk
    engine now receives the quote, so the limit binds whether or not the session's own
    gate is on. Before Phase 1.5 nothing passed it the spread and it never bound."""
    runtime, execution, market = build_runtime_paper_with(quoting=True, max_spread_bps=0.0)
    market.spread_bps = 30.0  # over RiskLimits.max_spread_bps (25)
    refusals = _events(runtime, "live.no_trade")
    await runtime.start()
    try:
        await _drive(runtime, market)
        assert runtime.counters["orders"] == 0
        assert runtime.counters["spread_rejected"] == 0, "the session gate is off"
        assert runtime.counters["risk_rejected"] > 0
        assert any("spread" in str(r.get("reason", "")) and "exceeds" in str(r.get("reason", "")) for r in refusals)
        assert await execution.get_positions() == {}
    finally:
        await runtime.stop()


class _NoBook(QuotingMarketData):
    async def get_quote(self, symbol: str):  # type: ignore[no-untyped-def]
        return None


class _Dead(QuotingMarketData):
    async def get_quote(self, symbol: str):  # type: ignore[no-untyped-def]
        raise ConnectionError("bookTicker unreachable")


class _Crossed(QuotingMarketData):
    """A duck-typed quote with a zero bid: data that is not a book."""

    async def get_quote(self, symbol: str):  # type: ignore[no-untyped-def]
        return SimpleNamespace(bid=0.0, ask=1.0, bid_size=1.0, ask_size=1.0, timestamp=None)


class _Old(QuotingMarketData):
    """A provider that keeps serving a quote stamped ten minutes ago."""

    async def get_quote(self, symbol: str):  # type: ignore[no-untyped-def]
        quote = await super().get_quote(symbol)
        return quote.model_copy(update={"timestamp": self._clock.now() - timedelta(minutes=10)})


class _Ahead(QuotingMarketData):
    """A provider whose clock runs ten minutes ahead of the session's: a book from the
    future is a clock fault, not a fresh quote (Phase 1.6)."""

    async def get_quote(self, symbol: str):  # type: ignore[no-untyped-def]
        quote = await super().get_quote(symbol)
        return quote.model_copy(update={"timestamp": self._clock.now() + timedelta(minutes=10)})


class _SlightlyAhead(QuotingMarketData):
    """A provider one second ahead: inside the skew two clocks are allowed, so fresh."""

    async def get_quote(self, symbol: str):  # type: ignore[no-untyped-def]
        quote = await super().get_quote(symbol)
        return quote.model_copy(update={"timestamp": self._clock.now() + timedelta(seconds=1)})


@pytest.mark.parametrize(
    ("feed", "state"),
    [(_NoBook, "absent"), (_Dead, "unavailable"), (_Crossed, "invalid"), (_Old, "stale"), (_Ahead, "invalid")],
)
async def test_a_quoting_feed_without_a_verifiable_quote_has_the_entry_refused(feed, state) -> None:  # type: ignore[no-untyped-def]
    runtime, execution, market = build_runtime_paper_with(quoting=True, max_spread_bps=10.0)
    feed_market = feed(market._candles, market._clock)
    feed_market.cursor = market.cursor
    runtime._market_data = feed_market
    refusals = _events(runtime, "live.no_trade")
    await runtime.start()
    try:
        await _drive(runtime, feed_market)
        assert runtime.counters["orders"] == 0
        assert runtime.counters["spread_unverifiable"] > 0
        assert runtime.counters["spread_rejected"] == 0
        assert any(f"no verifiable quote ({state})" in str(r.get("reason", "")) for r in refusals), refusals[-1:]
        view = runtime.snapshot()["market"]
        assert view["quote_state"] == state and view["spread_source"] == "configured constant"
        assert await execution.get_positions() == {}
    finally:
        await runtime.stop()


async def test_a_quote_stamped_within_the_allowed_skew_ahead_of_us_is_fresh() -> None:
    runtime, _execution, market = build_runtime_paper_with(quoting=True, max_spread_bps=10.0)
    feed_market = _SlightlyAhead(market._candles, market._clock)
    feed_market.cursor = market.cursor
    feed_market.spread_bps = 2.0
    runtime._market_data = feed_market
    await runtime.start()
    try:
        await _drive(runtime, feed_market, bars=300)
        assert runtime.counters["orders"] > 0
        assert runtime.counters["spread_unverifiable"] == 0
        view = runtime.snapshot()["market"]
        assert view["quote_state"] == "ok" and view["spread_source"] == "venue top of book"
    finally:
        await runtime.stop()


async def test_with_the_gate_active_a_spread_over_the_risk_engines_ceiling_sends_nothing() -> None:
    """Gate on (10 bps) and a book at 30 bps, over the risk engine's own ceiling (25):
    the risk engine sees the observed spread first and refuses; no order is built, no
    position opens, and the session gate — which would also have refused — is never the
    one that did. The two limits are both in force; the ceiling binds first."""
    runtime, execution, market = build_runtime_paper_with(quoting=True, max_spread_bps=10.0)
    market.spread_bps = 30.0
    refusals = _events(runtime, "live.no_trade")
    await runtime.start()
    try:
        await _drive(runtime, market)
        assert runtime.counters["orders"] == 0 and execution.submissions == 0
        assert runtime.counters["risk_rejected"] > 0
        assert runtime.counters["spread_rejected"] == 0 and runtime.counters["spread_unverifiable"] == 0
        assert any("spread" in str(r.get("reason", "")) and "exceeds" in str(r.get("reason", "")) for r in refusals)
        assert await execution.get_positions() == {}
        assert runtime._open_trade is None
        view = runtime.snapshot()["market"]
        assert view["quote_state"] == "ok" and view["quote"]["spread_bps"] == pytest.approx(30.0, rel=1e-3)
    finally:
        await runtime.stop()


async def test_a_feed_that_cannot_quote_keeps_the_constant_labelled_and_is_not_refused() -> None:
    """A replay or a fake has no book to show: the constant stands for the costs and the
    snapshot says so (``unsupported``); nothing pretends it was observed."""
    runtime, _execution, market = build_runtime_paper_with(max_spread_bps=10.0)
    await runtime.start()
    try:
        await _drive(runtime, market, bars=300)
        assert runtime.counters["orders"] > 0
        assert runtime.counters["spread_unverifiable"] == 0
        view = runtime.snapshot()["market"]
        assert view["quote"] is None and view["quote_state"] == "unsupported"
        assert view["spread_source"] == "configured constant"
    finally:
        await runtime.stop()


async def test_with_the_gate_off_a_missing_quote_does_not_refuse() -> None:
    runtime, _execution, market = build_runtime_paper_with(quoting=True, max_spread_bps=0.0)
    feed_market = _NoBook(market._candles, market._clock)
    feed_market.cursor = market.cursor
    runtime._market_data = feed_market
    await runtime.start()
    try:
        await _drive(runtime, feed_market, bars=300)
        assert runtime.counters["orders"] > 0
        assert runtime.counters["spread_unverifiable"] == 0
    finally:
        await runtime.stop()


def test_the_session_gate_may_not_be_looser_than_the_risk_engines_limit() -> None:
    """Two limits, one relation: the session's gate binds first, the risk engine's limit
    is the ceiling; a gate above the ceiling would never bind and is refused as config."""
    base = settings_for_env(Environment.TESTING)
    data = base.model_dump()
    with pytest.raises(ValueError, match="must not exceed"):
        type(base).model_validate(
            {**data, "live": LiveConfig(max_spread_bps=30.0), "risk": RiskLimits(max_spread_bps=25.0)}
        )
    # Off (0) is not "looser": it disables the gate and leaves the ceiling in force.
    off = type(base).model_validate(
        {**data, "live": LiveConfig(max_spread_bps=0.0), "risk": RiskLimits(max_spread_bps=25.0)}
    )
    assert off.live.max_spread_bps == 0.0 and off.risk.max_spread_bps == 25.0
    tight = type(base).model_validate(
        {**data, "live": LiveConfig(max_spread_bps=10.0), "risk": RiskLimits(max_spread_bps=25.0)}
    )
    assert tight.live.max_spread_bps == 10.0
