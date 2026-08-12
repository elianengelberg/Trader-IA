"""The data-quality engine — the first gate, and the one that says NO_TRADE most often.

Nothing computes a feature, let alone a signal, from data that has not passed here. The
engine answers two separate questions, because they fail for different reasons and demand
different responses:

``quality_score``    is the data *correct*?  (gaps, ordering, impossible values, anomalies)
``freshness_score``  is the data *current*?  (age of the last bar, feed liveness)

Stale-but-correct data is recoverable by waiting. Fresh-but-wrong data is not recoverable
at all, which is why quality carries the heavier weight in the composite.

Design commitments:

* **Hard fails are absolute.** No score, however high elsewhere, rescues a bar whose high
  is below its low or whose timestamp is in the future.
* **Every check is recorded**, passed or failed, with the observed value and the limit.
  "Spread anomaly" is not actionable; "spread 84 bps against a 25 bps limit" is.
* **Silence is a failure.** A feed that has stopped sending is treated as a fault, not as
  an absence of news. This is the check that catches the most dangerous real-world
  condition: a dead feed whose last price still looks perfectly reasonable.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from itertools import pairwise

import numpy as np

from tia.core.clock import ensure_utc
from tia.core.config import DataQualityConfig
from tia.core.ids import deterministic_id
from tia.domain.enums import DataQualityFlag
from tia.domain.instruments import Timeframe
from tia.domain.market import Candle, Quote
from tia.domain.quality import DataQualityReport, QualityCheck

# Weight per flag when reducing the quality score. Hard fails zero the score outright, so
# these govern only the graduated degradation of soft problems.
_PENALTIES: dict[DataQualityFlag, float] = {
    DataQualityFlag.GAP: 0.30,
    DataQualityFlag.DUPLICATE: 0.15,
    DataQualityFlag.SPREAD_ANOMALY: 0.25,
    DataQualityFlag.INSUFFICIENT_HISTORY: 0.35,
    DataQualityFlag.INVALID_VOLUME: 0.20,
    DataQualityFlag.IMPOSSIBLE_VALUE: 0.50,
}

# Tolerance for clock skew between us and a venue before a "future" bar is a hard fail.
SKEW_TOLERANCE = timedelta(seconds=5)

_HARD_FAIL_FLAGS = frozenset(
    {
        DataQualityFlag.OUT_OF_ORDER,
        DataQualityFlag.INVALID_OHLC,
        DataQualityFlag.FUTURE_TIMESTAMP,
        DataQualityFlag.FEED_DISCONNECTED,
        DataQualityFlag.STALE,
    }
)


class DataQualityEngine:
    """Evaluates a candle series and, optionally, the current quote."""

    def __init__(self, config: DataQualityConfig | None = None) -> None:
        self._config = config or DataQualityConfig()

    @property
    def config(self) -> DataQualityConfig:
        return self._config

    def evaluate(
        self,
        *,
        symbol: str,
        timeframe: str,
        candles: list[Candle],
        now: datetime,
        quote: Quote | None = None,
        max_spread_bps: float | None = None,
        feed_connected: bool = True,
        last_feed_message_at: datetime | None = None,
    ) -> DataQualityReport:
        now = ensure_utc(now, field="now")
        tf = Timeframe.parse(timeframe)
        checks: list[QualityCheck] = []
        flags: set[DataQualityFlag] = set()

        self._check_feed(checks, flags, feed_connected, last_feed_message_at, now, tf)
        self._check_history(checks, flags, candles)

        if candles:
            self._check_ordering(checks, flags, candles)
            self._check_duplicates(checks, flags, candles)
            self._check_gaps(checks, flags, candles, tf)
            self._check_freshness_bar(checks, flags, candles[-1], now, tf)
            self._check_future(checks, flags, candles[-1], now)
            self._check_values(checks, flags, candles)
            self._check_volume(checks, flags, candles)
            self._check_frozen(checks, flags, candles)
            self._check_jumps(checks, flags, candles)

        if quote is not None:
            self._check_spread(checks, flags, quote, candles, max_spread_bps)

        hard_fail = any(c.hard_fail for c in checks if not c.passed)
        quality = self._quality_score(flags, hard_fail)
        freshness = self._freshness_score(candles, now, tf, feed_connected)

        if quality < self._config.hard_fail_quality_score:
            hard_fail = True

        return DataQualityReport(
            report_id=deterministic_id(
                "dq", symbol, timeframe, int(now.timestamp()), len(candles), sorted(f.value for f in flags)
            ),
            symbol=symbol,
            timeframe=timeframe,
            evaluated_at=now,
            quality_score=round(quality, 6),
            freshness_score=round(freshness, 6),
            hard_fail=hard_fail,
            flags=tuple(sorted(flags, key=lambda f: f.value)),
            checks=tuple(checks),
            bars_evaluated=len(candles),
        )

    # ------------------------------------------------------------------ checks

    def _check_feed(
        self,
        checks: list[QualityCheck],
        flags: set[DataQualityFlag],
        connected: bool,
        last_message_at: datetime | None,
        now: datetime,
        tf: Timeframe,
    ) -> None:
        if not connected:
            flags.add(DataQualityFlag.FEED_DISCONNECTED)
            checks.append(
                QualityCheck(
                    name="feed_connected",
                    passed=False,
                    hard_fail=True,
                    flag=DataQualityFlag.FEED_DISCONNECTED,
                    detail="provider reports disconnected",
                )
            )
            return

        checks.append(QualityCheck(name="feed_connected", passed=True))

        if last_message_at is not None:
            silence = (now - ensure_utc(last_message_at)).total_seconds()
            limit = tf.seconds * self._config.max_bar_age_multiplier
            ok = silence <= limit
            if not ok:
                flags.add(DataQualityFlag.FEED_DISCONNECTED)
            checks.append(
                QualityCheck(
                    name="feed_liveness",
                    passed=ok,
                    hard_fail=True,
                    flag=None if ok else DataQualityFlag.FEED_DISCONNECTED,
                    observed=silence,
                    limit=limit,
                    detail="" if ok else "feed silent for longer than the tolerated window",
                )
            )

    def _check_history(
        self, checks: list[QualityCheck], flags: set[DataQualityFlag], candles: list[Candle]
    ) -> None:
        required = self._config.min_history_bars
        ok = len(candles) >= required
        if not ok:
            flags.add(DataQualityFlag.INSUFFICIENT_HISTORY)
        checks.append(
            QualityCheck(
                name="sufficient_history",
                passed=ok,
                hard_fail=len(candles) == 0,
                flag=None if ok else DataQualityFlag.INSUFFICIENT_HISTORY,
                observed=float(len(candles)),
                limit=float(required),
                detail="" if ok else "not enough history to compute stable indicators",
            )
        )

    def _check_ordering(
        self, checks: list[QualityCheck], flags: set[DataQualityFlag], candles: list[Candle]
    ) -> None:
        violations = sum(
            1 for a, b in pairwise(candles) if b.open_time < a.open_time
        )
        ok = violations == 0
        if not ok:
            flags.add(DataQualityFlag.OUT_OF_ORDER)
        checks.append(
            QualityCheck(
                name="monotonic_sequence",
                passed=ok,
                hard_fail=True,
                flag=None if ok else DataQualityFlag.OUT_OF_ORDER,
                observed=float(violations),
                limit=0.0,
                detail="" if ok else "bars arrived out of chronological order",
            )
        )

    def _check_duplicates(
        self, checks: list[QualityCheck], flags: set[DataQualityFlag], candles: list[Candle]
    ) -> None:
        seen = {c.open_time for c in candles}
        duplicates = len(candles) - len(seen)
        ok = duplicates == 0
        if not ok:
            flags.add(DataQualityFlag.DUPLICATE)
        checks.append(
            QualityCheck(
                name="no_duplicate_bars",
                passed=ok,
                flag=None if ok else DataQualityFlag.DUPLICATE,
                observed=float(duplicates),
                limit=0.0,
            )
        )

    def _check_gaps(
        self,
        checks: list[QualityCheck],
        flags: set[DataQualityFlag],
        candles: list[Candle],
        tf: Timeframe,
    ) -> None:
        if len(candles) < 2:
            return
        expected = tf.seconds
        missing = 0
        for a, b in pairwise(candles):
            delta = (b.open_time - a.open_time).total_seconds()
            if delta > expected:
                missing += round(delta / expected) - 1
        total_expected = len(candles) + missing
        ratio = missing / total_expected if total_expected else 0.0
        ok = ratio <= self._config.max_gap_ratio
        if not ok:
            flags.add(DataQualityFlag.GAP)
        checks.append(
            QualityCheck(
                name="gap_ratio",
                passed=ok,
                flag=None if ok else DataQualityFlag.GAP,
                observed=ratio,
                limit=self._config.max_gap_ratio,
                detail=f"{missing} missing bars",
            )
        )

    def _check_freshness_bar(
        self,
        checks: list[QualityCheck],
        flags: set[DataQualityFlag],
        last: Candle,
        now: datetime,
        tf: Timeframe,
    ) -> None:
        age = (now - last.close_time).total_seconds()
        limit = tf.seconds * self._config.max_bar_age_multiplier
        ok = age <= limit
        if not ok:
            flags.add(DataQualityFlag.STALE)
        checks.append(
            QualityCheck(
                name="bar_freshness",
                passed=ok,
                hard_fail=True,
                flag=None if ok else DataQualityFlag.STALE,
                observed=age,
                limit=limit,
                detail="" if ok else f"last bar closed {age:.0f}s ago",
            )
        )

    def _check_future(
        self, checks: list[QualityCheck], flags: set[DataQualityFlag], last: Candle, now: datetime
    ) -> None:
        # A small tolerance absorbs ordinary clock skew between us and the venue; beyond
        # that, a bar from the future means the clock or the parser is wrong, and either
        # way the data cannot be trusted.
        ok = last.close_time <= now.replace(microsecond=0).replace(tzinfo=now.tzinfo) + SKEW_TOLERANCE
        if not ok:
            flags.add(DataQualityFlag.FUTURE_TIMESTAMP)
        checks.append(
            QualityCheck(
                name="no_future_timestamps",
                passed=ok,
                hard_fail=True,
                flag=None if ok else DataQualityFlag.FUTURE_TIMESTAMP,
                observed=(last.close_time - now).total_seconds(),
                limit=SKEW_TOLERANCE.total_seconds(),
            )
        )

    def _check_values(
        self, checks: list[QualityCheck], flags: set[DataQualityFlag], candles: list[Candle]
    ) -> None:
        bad = 0
        for c in candles:
            values = (c.open, c.high, c.low, c.close)
            if any(not math.isfinite(v) or v <= 0 for v in values) or c.high < c.low or c.high < max(c.open, c.close) or c.low > min(c.open, c.close):
                bad += 1
        ok = bad == 0
        if not ok:
            flags.add(DataQualityFlag.IMPOSSIBLE_VALUE)
            flags.add(DataQualityFlag.INVALID_OHLC)
        checks.append(
            QualityCheck(
                name="price_sanity",
                passed=ok,
                hard_fail=True,
                flag=None if ok else DataQualityFlag.IMPOSSIBLE_VALUE,
                observed=float(bad),
                limit=0.0,
                detail="" if ok else "non-finite, non-positive or OHLC-inconsistent prices",
            )
        )

    def _check_volume(
        self, checks: list[QualityCheck], flags: set[DataQualityFlag], candles: list[Candle]
    ) -> None:
        bad = sum(1 for c in candles if not math.isfinite(c.volume) or c.volume < 0)
        zero_run = 0
        longest_zero_run = 0
        for c in candles:
            zero_run = zero_run + 1 if c.volume == 0 else 0
            longest_zero_run = max(longest_zero_run, zero_run)
        # A long run of exactly-zero volume is a dead feed, not a quiet market.
        suspicious = longest_zero_run >= max(5, len(candles) // 10)
        ok = bad == 0 and not suspicious
        if not ok:
            flags.add(DataQualityFlag.INVALID_VOLUME)
        checks.append(
            QualityCheck(
                name="volume_sanity",
                passed=ok,
                flag=None if ok else DataQualityFlag.INVALID_VOLUME,
                observed=float(bad or longest_zero_run),
                limit=0.0,
                detail="" if ok else f"{bad} invalid, longest zero-volume run {longest_zero_run}",
            )
        )

    def _check_frozen(
        self, checks: list[QualityCheck], flags: set[DataQualityFlag], candles: list[Candle]
    ) -> None:
        """A price that has not moved at all for many bars is usually a stuck feed."""
        window = candles[-20:]
        if len(window) < 10:
            return
        distinct = len({round(c.close, 10) for c in window})
        ok = distinct > 1
        if not ok:
            flags.add(DataQualityFlag.STALE)
        checks.append(
            QualityCheck(
                name="price_not_frozen",
                passed=ok,
                hard_fail=True,
                flag=None if ok else DataQualityFlag.STALE,
                observed=float(distinct),
                limit=1.0,
                detail="" if ok else "identical close across the recent window",
            )
        )

    def _check_jumps(
        self, checks: list[QualityCheck], flags: set[DataQualityFlag], candles: list[Candle]
    ) -> None:
        """Flag a bar-to-bar move so extreme it is more likely bad data than a real move."""
        if len(candles) < 20:
            return
        closes = np.array([c.close for c in candles], dtype=float)
        returns = np.diff(np.log(closes))
        if returns.size < 10:
            return
        sigma = float(np.std(returns[:-1])) or 1e-9
        last_move = abs(float(returns[-1])) / sigma
        limit = 12.0
        ok = last_move <= limit
        if not ok:
            flags.add(DataQualityFlag.IMPOSSIBLE_VALUE)
        checks.append(
            QualityCheck(
                name="price_jump",
                passed=ok,
                flag=None if ok else DataQualityFlag.IMPOSSIBLE_VALUE,
                observed=last_move,
                limit=limit,
                detail="" if ok else "last move is implausibly large relative to recent volatility",
            )
        )

    def _check_spread(
        self,
        checks: list[QualityCheck],
        flags: set[DataQualityFlag],
        quote: Quote,
        candles: list[Candle],
        max_spread_bps: float | None,
    ) -> None:
        spread_bps = quote.spread_bps
        if max_spread_bps is not None:
            ok_abs = spread_bps <= max_spread_bps
            if not ok_abs:
                flags.add(DataQualityFlag.SPREAD_ANOMALY)
            checks.append(
                QualityCheck(
                    name="spread_absolute",
                    passed=ok_abs,
                    flag=None if ok_abs else DataQualityFlag.SPREAD_ANOMALY,
                    observed=spread_bps,
                    limit=max_spread_bps,
                )
            )

        # A relative check as well: a spread can be within the absolute cap and still be
        # four standard deviations wider than this instrument's own normal.
        window = candles[-self._config.spread_window :]
        if len(window) >= 20:
            proxy = np.array(
                [(c.high - c.low) / c.close * 10_000.0 for c in window if c.close > 0], dtype=float
            )
            if proxy.size >= 20:
                mu = float(np.mean(proxy))
                sd = float(np.std(proxy)) or 1e-9
                z = (spread_bps - mu) / sd
                ok_rel = z <= self._config.max_spread_zscore
                if not ok_rel:
                    flags.add(DataQualityFlag.SPREAD_ANOMALY)
                checks.append(
                    QualityCheck(
                        name="spread_zscore",
                        passed=ok_rel,
                        flag=None if ok_rel else DataQualityFlag.SPREAD_ANOMALY,
                        observed=z,
                        limit=self._config.max_spread_zscore,
                    )
                )

    # ------------------------------------------------------------------ scoring

    def _quality_score(self, flags: set[DataQualityFlag], hard_fail: bool) -> float:
        if hard_fail or flags & _HARD_FAIL_FLAGS:
            return 0.0
        score = 1.0
        for flag in flags:
            score -= _PENALTIES.get(flag, 0.10)
        return max(0.0, min(1.0, score))

    def _freshness_score(
        self, candles: list[Candle], now: datetime, tf: Timeframe, feed_connected: bool
    ) -> float:
        if not feed_connected or not candles:
            return 0.0
        age = (now - candles[-1].close_time).total_seconds()
        if age <= 0:
            return 1.0
        limit = tf.seconds * self._config.max_bar_age_multiplier
        if age >= limit:
            return 0.0
        # Linear decay across the tolerated window: a bar one interval old is still good,
        # one about to breach the limit is nearly worthless.
        return max(0.0, min(1.0, 1.0 - (age / limit) ** 1.5))

__all__ = ["SKEW_TOLERANCE", "DataQualityEngine"]
