"""Cross-venue arbitrage: the arithmetic is right, and failure degrades per venue.

What must hold: a gap is the sell venue's bid over the buy venue's ask, net of both taker
fees; the best gap sorts first; each venue's documented response shape parses and a
malformed one is a recorded failure rather than a fake quote; a dead venue never empties
the report; and the verdict is built from the record, not from the claim being checked.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from tia.core.clock import SimulatedClock
from tia.data.arbitrage import (
    DEFAULT_VENUES,
    CrossVenueMonitor,
    Quote,
    Venue,
    pairwise_gaps,
    parse_binance,
    parse_coinbase,
    parse_kraken,
)

BINANCE = {"symbol": "BTCUSDT", "bidPrice": "60000.00", "bidQty": "1.2", "askPrice": "60001.00", "askQty": "0.8"}
COINBASE = {"ask": "60040.00", "bid": "60030.00", "volume": "1.0", "price": "60035", "time": "2026-08-18T00:00:00Z"}
KRAKEN = {
    "error": [],
    "result": {"XBTUSDT": {"a": ["60020.0", "1", "1.000"], "b": ["60010.0", "1", "1.000"], "c": ["60015", "0.1"]}},
}


def _clock() -> SimulatedClock:
    return SimulatedClock(start=datetime(2026, 8, 18, tzinfo=UTC))


def _at() -> datetime:
    return datetime(2026, 8, 18, tzinfo=UTC)


def _monitor(handler, venues=DEFAULT_VENUES, clock=None) -> CrossVenueMonitor:  # type: ignore[no-untyped-def]
    return CrossVenueMonitor(
        clock=clock or _clock(),
        venues=venues,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _payload_for(url: str) -> dict:  # type: ignore[type-arg]
    if "binance" in url:
        return BINANCE
    if "coinbase" in url:
        return COINBASE
    return KRAKEN


def _all_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=_payload_for(str(request.url)))


# ------------------------------------------------------------------ gap arithmetic


def test_a_gap_is_the_sell_bid_over_the_buy_ask_net_of_both_taker_fees() -> None:
    quotes = [
        Quote("a", bid=100.0, ask=100.1, at=_at()),
        Quote("b", bid=100.6, ask=100.7, at=_at()),
    ]
    gaps = pairwise_gaps(quotes, {"a": 10.0, "b": 40.0})

    best = gaps[0]
    assert (best.buy_venue, best.sell_venue) == ("a", "b")
    # (100.6 - 100.1) / 100.1 = 49.95 bps gross, minus 50 bps of fees.
    assert best.gross_bps == pytest.approx(49.95, abs=0.01)
    assert best.fee_bps == 50.0
    assert best.net_bps == pytest.approx(-0.05, abs=0.01)
    assert best.clears_costs is False
    # The reverse direction buys the dear venue and sells the cheap one: deeply negative.
    worst = gaps[-1]
    assert (worst.buy_venue, worst.sell_venue) == ("b", "a")
    assert worst.gross_bps < -50


def test_the_best_net_gap_sorts_first_and_dollars_follow_the_notional() -> None:
    quotes = [
        Quote("a", bid=100.0, ask=100.0, at=_at()),
        Quote("b", bid=101.0, ask=101.0, at=_at()),
        Quote("c", bid=100.5, ask=100.5, at=_at()),
    ]
    gaps = pairwise_gaps(quotes, {"a": 0.0, "b": 0.0, "c": 0.0})

    assert len(gaps) == 6  # every ordered pair of three venues
    assert [g.net_bps for g in gaps] == sorted((g.net_bps for g in gaps), reverse=True)
    assert (gaps[0].buy_venue, gaps[0].sell_venue) == ("a", "b")
    assert gaps[0].net_bps == pytest.approx(100.0)
    assert gaps[0].net_usd(100.0) == pytest.approx(1.0)
    assert gaps[0].as_dict()["net_usd_per_10k"] == pytest.approx(100.0)


def test_a_single_venue_has_no_gap_to_measure() -> None:
    assert pairwise_gaps([Quote("a", bid=1.0, ask=1.0, at=_at())], {"a": 10.0}) == []


# ------------------------------------------------------------------ parsers


def test_each_venue_parser_reads_its_documented_shape() -> None:
    assert parse_binance(BINANCE) == (60000.0, 60001.0)
    assert parse_coinbase(COINBASE) == (60030.0, 60040.0)
    assert parse_kraken(KRAKEN) == (60010.0, 60020.0)


def test_kraken_reports_its_errors_in_the_body_and_the_parser_refuses_them() -> None:
    with pytest.raises(ValueError, match="EQuery:Unknown asset pair"):
        parse_kraken({"error": ["EQuery:Unknown asset pair"], "result": {}})


def test_a_non_positive_price_is_refused_not_quoted() -> None:
    with pytest.raises(ValueError):
        parse_binance({"bidPrice": "0", "askPrice": "1"})


def test_the_registry_fees_are_documented_and_the_instrument_matches_across_venues() -> None:
    for venue in DEFAULT_VENUES:
        assert venue.taker_fee_bps > 0
        assert venue.fee_source  # a number nobody can check is a number nobody should trust
        assert "USDT" in venue.url  # like for like, or a stablecoin basis masquerades as a gap


# ------------------------------------------------------------------ monitor


async def test_a_poll_quotes_every_venue_and_measures_every_pair() -> None:
    monitor = _monitor(_all_ok)
    sample = await monitor.poll()

    assert sample.venues_quoted == 3
    assert sample.best is not None
    report = monitor.report()
    assert report["venues_ok"] == 3
    assert len(report["gaps"]) == 6
    # Ranked by NET, not gross: Binance->Coinbase has the widest gross gap (4.8 bps) but
    # 70 bps of fees; Binance->Kraken is narrower (1.5 bps) with 50 bps of fees and so
    # loses less. Neither clears costs — which is the finding.
    best = report["gaps"][0]
    assert (best["buy_venue"], best["sell_venue"]) == ("binance", "kraken")
    assert best["gross_bps"] == pytest.approx(1.5, abs=0.01)
    assert best["fee_bps"] == 50.0
    assert best["net_bps"] == pytest.approx(-48.5, abs=0.01)
    widest = next(g for g in report["gaps"] if (g["buy_venue"], g["sell_venue"]) == ("binance", "coinbase"))
    assert widest["gross_bps"] == pytest.approx(4.83, abs=0.01)
    assert widest["fee_bps"] == 70.0
    assert not any(g["clears_costs"] for g in report["gaps"])
    assert report["stats"]["samples"] == 1
    assert report["stats"]["opportunities"] == 0
    await monitor.close()


async def test_a_dead_venue_is_recorded_and_the_others_are_still_compared() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "coinbase" in str(request.url):
            return httpx.Response(503, text="upstream unavailable")
        return httpx.Response(200, json=_payload_for(str(request.url)))

    monitor = _monitor(handler)
    sample = await monitor.poll()

    assert sample.venues_quoted == 2
    report = monitor.report()
    coinbase = next(v for v in report["venues"] if v["venue_id"] == "coinbase")
    assert coinbase["ok"] is False
    assert "503" in coinbase["detail"]
    assert coinbase["failures"] == 1
    assert coinbase["bid"] is None
    assert len(report["gaps"]) == 2  # binance<->kraken both ways
    assert {g["buy_venue"] for g in report["gaps"]} == {"binance", "kraken"}
    await monitor.close()


async def test_a_venue_that_changes_its_shape_fails_loudly_instead_of_quoting_garbage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "kraken" in str(request.url):
            return httpx.Response(200, json={"result": {"XBTUSDT": {"a": ["-1", "1", "1"], "b": ["0", "1", "1"]}}, "error": []})
        return httpx.Response(200, json=_payload_for(str(request.url)))

    monitor = _monitor(handler)
    await monitor.poll()

    kraken = next(v for v in monitor.report()["venues"] if v["venue_id"] == "kraken")
    assert kraken["ok"] is False
    assert "ValueError" in kraken["detail"]
    await monitor.close()


async def test_an_oversized_response_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "binance" in str(request.url):
            return httpx.Response(200, content=b"{" + b" " * 70_000 + b"}")
        return httpx.Response(200, json=_payload_for(str(request.url)))

    monitor = _monitor(handler)
    await monitor.poll()

    binance = next(v for v in monitor.report()["venues"] if v["venue_id"] == "binance")
    assert binance["ok"] is False
    assert "exceeds" in binance["detail"]
    await monitor.close()


async def test_stale_quotes_are_not_compared_with_fresh_ones() -> None:
    """A gap between now and a minute ago is a chart, not an arbitrage."""
    clock = _clock()
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "coinbase" in str(request.url):
            calls["n"] += 1
            if calls["n"] > 1:
                return httpx.Response(500)
        return httpx.Response(200, json=_payload_for(str(request.url)))

    monitor = _monitor(handler, clock=clock)
    first = await monitor.poll()
    assert first.venues_quoted == 3

    clock.advance_by(timedelta(seconds=60))
    second = await monitor.poll()
    assert second.venues_quoted == 2
    assert not any("coinbase" in (g["buy_venue"], g["sell_venue"]) for g in monitor.report()["gaps"])
    await monitor.close()


async def test_the_verdict_and_the_hypothetical_come_from_the_record() -> None:
    """Fee-free venues with a real gap: the report must say the gap cleared and price it."""
    clock = _clock()
    venues = (
        Venue("x", "X", "https://x.test/t", taker_fee_bps=0.0, fee_source="test", parse=parse_binance),
        Venue("y", "Y", "https://y.test/t", taker_fee_bps=0.0, fee_source="test", parse=parse_binance),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if "x.test" in str(request.url):
            return httpx.Response(200, json={"bidPrice": "100", "askPrice": "100"})
        return httpx.Response(200, json={"bidPrice": "101", "askPrice": "101"})

    monitor = _monitor(handler, venues=venues, clock=clock)
    for _ in range(3):
        await monitor.poll()
        clock.advance_by(timedelta(seconds=15))

    report = monitor.report()
    stats = report["stats"]
    assert stats["samples"] == 3
    assert stats["opportunities"] == 3
    assert stats["opportunity_share"] == 1.0
    assert stats["best_net_bps"] == pytest.approx(100.0)
    assert stats["best_pair"] == "buy x / sell y"
    # Three $100 round trips at +100 bps each: three dollars, the most anyone could have made.
    assert report["hypothetical"]["round_trips"] == 3
    assert report["hypothetical"]["net_usd"] == pytest.approx(3.0)
    assert "upper bound" in report["hypothetical"]["assumes"]
    assert "+100.0 bps" in report["verdict"]
    assert "100.0% of samples" in report["verdict"]
    assert len(report["history"]) == 3
    assert report["caveats"]
    await monitor.close()


async def test_with_nothing_measured_the_verdict_says_so_instead_of_guessing() -> None:
    monitor = _monitor(lambda request: httpx.Response(500))
    await monitor.poll()

    report = monitor.report()
    assert report["venues_ok"] == 0
    assert report["gaps"] == []
    assert report["stats"]["best_net_bps"] is None
    assert "No gap measured yet" in report["verdict"]
    await monitor.close()


async def test_the_history_is_bounded_and_downsampled_for_the_chart() -> None:
    clock = _clock()
    monitor = CrossVenueMonitor(
        clock=clock,
        client=httpx.AsyncClient(transport=httpx.MockTransport(_all_ok)),
        history_size=50,
    )
    for _ in range(80):
        await monitor.poll()
        clock.advance_by(timedelta(seconds=15))

    report = monitor.report(history_points=10)
    assert report["stats"]["samples"] == 50
    assert report["polls"] == 80
    assert len(report["history"]) <= 11
    assert report["history"][-1]["at"] == (clock.now() - timedelta(seconds=15)).isoformat()
    await monitor.close()


async def test_the_sampler_runs_in_the_background_and_stops_on_close() -> None:
    import asyncio

    monitor = CrossVenueMonitor(
        clock=_clock(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(_all_ok)),
        poll_seconds=0.01,
    )
    monitor.start()
    monitor.start()  # idempotent
    assert monitor.is_running
    await asyncio.sleep(0.08)
    assert monitor.report()["polls"] >= 2
    await monitor.close()
    assert not monitor.is_running


def test_the_report_is_json_serialisable() -> None:
    monitor = CrossVenueMonitor(clock=_clock(), client=httpx.AsyncClient(transport=httpx.MockTransport(_all_ok)))
    json.dumps(monitor.report())
