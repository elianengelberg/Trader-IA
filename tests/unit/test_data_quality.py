"""The data-quality gate.

Each check gets a test that constructs data which *should* trip it, because a check that
has never been observed to fire is indistinguishable from a check that cannot fire.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import START, linear_series, make_candle
from tia.core.config import DataQualityConfig
from tia.data.quality import DataQualityEngine
from tia.domain.enums import DataQualityFlag
from tia.domain.market import Quote

CONFIG = DataQualityConfig(min_history_bars=20)


@pytest.fixture
def engine() -> DataQualityEngine:
    return DataQualityEngine(CONFIG)


def _now_after(candles: list) -> datetime:
    return candles[-1].close_time + timedelta(seconds=30)


class TestHealthySeries:
    def test_clean_series_scores_high_and_is_tradable(self, engine: DataQualityEngine) -> None:
        candles = linear_series(120)
        report = engine.evaluate(
            symbol="BTC-USD", timeframe="1m", candles=candles, now=_now_after(candles)
        )
        assert report.hard_fail is False
        assert report.quality_score >= 0.95
        assert report.freshness_score > 0.8
        assert report.is_tradable(min_quality=0.75, min_freshness=0.70)
        assert report.reason() == "ok"

    def test_every_check_is_recorded_even_when_passing(self, engine: DataQualityEngine) -> None:
        candles = linear_series(120)
        report = engine.evaluate(
            symbol="BTC-USD", timeframe="1m", candles=candles, now=_now_after(candles)
        )
        names = {c.name for c in report.checks}
        assert {
            "feed_connected",
            "sufficient_history",
            "monotonic_sequence",
            "no_duplicate_bars",
            "bar_freshness",
            "price_sanity",
            "volume_sanity",
        } <= names

    def test_report_id_is_deterministic(self, engine: DataQualityEngine) -> None:
        candles = linear_series(120)
        now = _now_after(candles)
        a = engine.evaluate(symbol="BTC-USD", timeframe="1m", candles=candles, now=now)
        b = engine.evaluate(symbol="BTC-USD", timeframe="1m", candles=candles, now=now)
        assert a.report_id == b.report_id


class TestHardFails:
    def test_stale_data_hard_fails(self, engine: DataQualityEngine) -> None:
        candles = linear_series(120)
        late = candles[-1].close_time + timedelta(minutes=30)
        report = engine.evaluate(symbol="BTC-USD", timeframe="1m", candles=candles, now=late)
        assert report.hard_fail is True
        assert DataQualityFlag.STALE in report.flags
        assert report.freshness_score == 0.0
        assert report.is_tradable(0.75, 0.70) is False

    def test_disconnected_feed_hard_fails(self, engine: DataQualityEngine) -> None:
        candles = linear_series(120)
        report = engine.evaluate(
            symbol="BTC-USD",
            timeframe="1m",
            candles=candles,
            now=_now_after(candles),
            feed_connected=False,
        )
        assert report.hard_fail is True
        assert DataQualityFlag.FEED_DISCONNECTED in report.flags
        assert report.quality_score == 0.0

    def test_silent_feed_hard_fails_even_while_nominally_connected(
        self, engine: DataQualityEngine
    ) -> None:
        """The dangerous case: connected, last price plausible, but nothing arriving."""
        candles = linear_series(120)
        now = _now_after(candles)
        report = engine.evaluate(
            symbol="BTC-USD",
            timeframe="1m",
            candles=candles,
            now=now,
            feed_connected=True,
            last_feed_message_at=now - timedelta(minutes=45),
        )
        assert report.hard_fail is True
        assert DataQualityFlag.FEED_DISCONNECTED in report.flags

    def test_out_of_order_bars_hard_fail(self, engine: DataQualityEngine) -> None:
        candles = linear_series(120)
        shuffled = [*candles[:50], candles[60], *candles[50:60], *candles[61:]]
        report = engine.evaluate(
            symbol="BTC-USD", timeframe="1m", candles=shuffled, now=_now_after(candles)
        )
        assert report.hard_fail is True
        assert DataQualityFlag.OUT_OF_ORDER in report.flags

    def test_future_timestamp_hard_fails(self, engine: DataQualityEngine) -> None:
        candles = linear_series(120)
        report = engine.evaluate(
            symbol="BTC-USD",
            timeframe="1m",
            candles=candles,
            now=candles[-1].close_time - timedelta(minutes=10),
        )
        assert report.hard_fail is True
        assert DataQualityFlag.FUTURE_TIMESTAMP in report.flags

    def test_frozen_price_hard_fails(self, engine: DataQualityEngine) -> None:
        """A stuck feed reports a perfectly valid, perfectly unchanging price."""
        frozen = [
            make_candle(open_time=START + timedelta(minutes=i), open_=100.0, close=100.0)
            for i in range(60)
        ]
        report = engine.evaluate(
            symbol="BTC-USD", timeframe="1m", candles=frozen, now=_now_after(frozen)
        )
        assert report.hard_fail is True
        assert DataQualityFlag.STALE in report.flags

    def test_empty_series_hard_fails(self, engine: DataQualityEngine) -> None:
        report = engine.evaluate(
            symbol="BTC-USD", timeframe="1m", candles=[], now=datetime(2026, 1, 5, tzinfo=UTC)
        )
        assert report.hard_fail is True
        assert report.freshness_score == 0.0


class TestSoftDegradation:
    def test_gaps_reduce_the_score(self, engine: DataQualityEngine) -> None:
        candles = linear_series(120)
        gapped = candles[:40] + candles[60:]
        report = engine.evaluate(
            symbol="BTC-USD", timeframe="1m", candles=gapped, now=_now_after(candles)
        )
        assert DataQualityFlag.GAP in report.flags
        assert report.quality_score < 1.0

    def test_duplicates_are_detected(self, engine: DataQualityEngine) -> None:
        candles = linear_series(120)
        duped = [*candles, candles[-1]]
        report = engine.evaluate(
            symbol="BTC-USD", timeframe="1m", candles=duped, now=_now_after(candles)
        )
        assert DataQualityFlag.DUPLICATE in report.flags

    def test_insufficient_history_is_flagged(self, engine: DataQualityEngine) -> None:
        candles = linear_series(5)
        report = engine.evaluate(
            symbol="BTC-USD", timeframe="1m", candles=candles, now=_now_after(candles)
        )
        assert DataQualityFlag.INSUFFICIENT_HISTORY in report.flags
        assert report.quality_score < 1.0

    def test_long_zero_volume_run_is_flagged(self, engine: DataQualityEngine) -> None:
        candles = linear_series(60)
        dead = [c.model_copy(update={"volume": 0.0}) for c in candles]
        report = engine.evaluate(
            symbol="BTC-USD", timeframe="1m", candles=dead, now=_now_after(candles)
        )
        assert DataQualityFlag.INVALID_VOLUME in report.flags

    def test_absolute_spread_breach_is_flagged(self, engine: DataQualityEngine) -> None:
        candles = linear_series(120)
        last = candles[-1]
        wide = Quote(
            symbol="BTC-USD",
            timestamp=last.close_time,
            bid=last.close * 0.98,
            ask=last.close * 1.02,
        )
        report = engine.evaluate(
            symbol="BTC-USD",
            timeframe="1m",
            candles=candles,
            now=_now_after(candles),
            quote=wide,
            max_spread_bps=25.0,
        )
        assert DataQualityFlag.SPREAD_ANOMALY in report.flags
        breach = next(c for c in report.checks if c.name == "spread_absolute")
        assert breach.passed is False
        assert breach.observed is not None and breach.observed > 25.0

    def test_price_jump_is_flagged(self, engine: DataQualityEngine) -> None:
        """A 40% single-bar move on a quiet series is bad data far more often than news."""
        candles = linear_series(120, step=0.01)
        last = candles[-1]
        spike = last.model_copy(
            update={
                "close": last.close * 1.4,
                "high": last.close * 1.41,
            }
        )
        report = engine.evaluate(
            symbol="BTC-USD", timeframe="1m", candles=[*candles[:-1], spike], now=_now_after(candles)
        )
        jump = next(c for c in report.checks if c.name == "price_jump")
        assert jump.passed is False
        assert DataQualityFlag.IMPOSSIBLE_VALUE in report.flags


class TestScoring:
    def test_composite_weights_quality_above_freshness(self) -> None:
        from tia.domain.quality import DataQualityReport

        report = DataQualityReport(
            report_id="r",
            symbol="X",
            timeframe="1m",
            evaluated_at=datetime(2026, 1, 1, tzinfo=UTC),
            quality_score=0.0,
            freshness_score=1.0,
        )
        assert report.composite_score == pytest.approx(0.35)

    def test_reason_lists_failed_checks(self, engine: DataQualityEngine) -> None:
        candles = linear_series(120)
        report = engine.evaluate(
            symbol="BTC-USD",
            timeframe="1m",
            candles=candles,
            now=candles[-1].close_time + timedelta(hours=2),
        )
        assert "bar_freshness" in report.reason()
