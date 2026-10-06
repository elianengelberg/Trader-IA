"""The reconciliation's tick carries the time it happens, not the time the reconciliation
started: the venue's REST reads take hundreds of milliseconds, and a tick stamped at the
start fed the engine, and its mid series, timestamps older than events already processed
(107 such samples in the 2026-10-05 Testnet run on 5ac604e, each equal to a reconciliation's
start). Fake venue, simulated clock: the REST delay is the clock advancing while the venue
answers."""

from __future__ import annotations

from datetime import timedelta

from tests.unit.mm.test_mm_live_service import _live, _teardown


async def _slow_venue(live, delay_ms: int) -> None:  # type: ignore[no-untyped-def]
    original = live.venue.get_orders

    async def slow(**kw):  # type: ignore[no-untyped-def]
        snapshot = await original(**kw)
        live.clock.advance_by(timedelta(milliseconds=delay_ms))  # the venue takes its time to answer
        return snapshot

    live.venue.get_orders = slow  # type: ignore[method-assign]


async def test_the_reconciliation_tick_is_stamped_after_the_venue_answered_and_the_mid_series_stays_monotone() -> None:
    live = await _live()
    service, engine = live.service, live.service.engine
    await service.start_live()
    await live.until_resting()
    await _slow_venue(live, 600)
    before = len(engine.mid_samples)
    started = live.clock.timestamp_ms()
    report = await service.reconcile()
    assert report.ok and not report.critical
    assert len(engine.mid_samples) > before  # the tick showed the tracker a mid
    t_tick = engine.mid_samples[-1][0]
    assert t_tick >= started + 600, (t_tick - started)  # stamped after the REST delay, not at the start
    assert service.execution.venue_balances_at_ms >= started + 600  # the balances too
    stamps = [sample[0] for sample in engine.mid_samples]
    assert stamps == sorted(stamps)  # no sample older than one already processed
    await _teardown(live)


async def test_without_a_fresh_stamp_the_series_would_have_inverted(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The regression, demonstrated: feed the engine a tick with the reconciliation's start
    time after a 600 ms REST delay and the series inverts. This is what the harness's
    inversion check reports; the service no longer does it."""
    live = await _live()
    engine = live.service.engine
    await live.service.start_live()
    await live.until_resting()
    stale_t = live.clock.timestamp_ms()
    live.clock.advance_by(timedelta(milliseconds=600))
    await live.feed(1)
    engine.on_event("tick", None, stale_t)  # the old behaviour, by hand
    stamps = [sample[0] for sample in engine.mid_samples]
    assert stamps != sorted(stamps) and stamps[-1] == stale_t
    await _teardown(live)
