"""Request-weight budgeting for the Binance REST API.

Binance meters requests by *weight*, not by count, over rolling windows, and the
enforcement escalates: HTTP 429 means back off, HTTP 418 means the IP has been banned for
minutes to days because it kept going after the 429. The second one is the operational
disaster — a live session that cannot reach the venue still has positions — so the point
of this module is to make 429 rare and 418 unreachable.

**REQUIRES VALIDATION.** The default limit (6,000 weight per minute) and the per-endpoint
weights below are documented values, transcribed here without ever having been confirmed
against the live API — this environment cannot reach any Binance host. The real,
current limits are in the ``rateLimits`` field of ``/api/v3/exchangeInfo``, and
``scripts/validate_binance.py`` reads them; feed those numbers in at construction rather
than trusting these constants.

Two behaviours, deliberately conservative:

* **Pacing before the fact.** ``acquire()`` is awaited before every request. Above 80% of
  budget it starts inserting delays sized to the window's remaining time; at 100% it waits
  for headroom. Nothing in this system is latency-critical enough to justify entering the
  venue's penalty regime.
* **Obedience after the fact.** A 429 arms a cooldown (from ``Retry-After`` when present);
  a 418 arms a much longer one. During cooldown every ``acquire()`` waits. There is no
  retry-storm code path because there is no unpaced retry at all.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from tia.core.clock import Clock
from tia.core.logging import get_logger

_log = get_logger("data.binance.budget")

#: Documented default: 6,000 request weight per rolling minute per IP. REQUIRES
#: VALIDATION against exchangeInfo's rateLimits at runtime.
DEFAULT_WEIGHT_PER_MINUTE = 6_000

#: Documented weights for the endpoints this system uses. Anything not listed costs
#: DEFAULT_ENDPOINT_WEIGHT, which over-counts rather than under-counts. REQUIRES
#: VALIDATION.
ENDPOINT_WEIGHTS: dict[str, int] = {
    "/api/v3/ping": 1,
    "/api/v3/time": 1,
    "/api/v3/klines": 2,
    "/api/v3/ticker/bookTicker": 2,
    "/api/v3/exchangeInfo": 20,
    "/api/v3/order": 1,
    "/api/v3/openOrders": 6,
    "/api/v3/account": 20,
    "/api/v3/myTrades": 20,
    "/sapi/v1/account/apiRestrictions": 1,
}

DEFAULT_ENDPOINT_WEIGHT = 10

#: Start pacing at this fraction of the budget. 0.8 leaves a fifth of the window as the
#: safety margin that absorbs the requests already in flight.
PACING_THRESHOLD = 0.8

#: Cooldowns. The 418 figure is deliberately long: the venue just said it was about to
#: ban this IP, and the only winning move is to stop entirely.
COOLDOWN_ON_429_SECONDS = 30.0
COOLDOWN_ON_418_SECONDS = 300.0


class BinanceRequestBudget:
    """Tracks weight spent in a rolling window and paces callers to stay inside it."""

    def __init__(
        self,
        clock: Clock,
        *,
        weight_per_minute: int = DEFAULT_WEIGHT_PER_MINUTE,
        window_seconds: float = 60.0,
    ) -> None:
        if weight_per_minute <= 0 or window_seconds <= 0:
            raise ValueError("budget parameters must be positive")
        self._clock = clock
        self._limit = weight_per_minute
        self._window = window_seconds
        #: (monotonic_seconds, weight) pairs inside the current window.
        self._spent: deque[tuple[float, int]] = deque()
        self._cooldown_until = 0.0
        self._delays = 0
        self._denied_bursts = 0

    # ------------------------------------------------------------------ accounting

    def _now(self) -> float:
        return self._clock.monotonic_ns() / 1e9

    def _prune(self, now: float) -> None:
        while self._spent and now - self._spent[0][0] > self._window:
            self._spent.popleft()

    def used(self) -> int:
        self._prune(self._now())
        return sum(weight for _, weight in self._spent)

    def remaining(self) -> int:
        return max(0, self._limit - self.used())

    @staticmethod
    def weight_of(path: str) -> int:
        return ENDPOINT_WEIGHTS.get(path, DEFAULT_ENDPOINT_WEIGHT)

    # ------------------------------------------------------------------ pacing

    async def acquire(self, path: str) -> None:
        """Wait until spending this endpoint's weight is within budget, then record it.

        The wait is computed, not polled: when over the pacing threshold the delay is the
        time until enough of the window's oldest spend expires, so a burst spreads itself
        across the window instead of slamming into the limit's far side.
        """
        weight = self.weight_of(path)
        now = self._now()

        if now < self._cooldown_until:
            wait = self._cooldown_until - now
            _log.warning("budget_cooldown_wait", path=path, seconds=round(wait, 2))
            await asyncio.sleep(wait)
            now = self._now()

        self._prune(now)
        used = sum(w for _, w in self._spent)

        if used + weight > self._limit:
            # Fully spent: wait for the oldest entries to age out of the window.
            self._denied_bursts += 1
            wait = self._time_until_headroom(now, weight)
            _log.warning("budget_exhausted_wait", path=path, seconds=round(wait, 2))
            await asyncio.sleep(wait)
            now = self._now()
            self._prune(now)
        elif used + weight > self._limit * PACING_THRESHOLD:
            # Nearing the limit: insert a small, proportional delay.
            fraction_over = (used + weight - self._limit * PACING_THRESHOLD) / (
                self._limit * (1.0 - PACING_THRESHOLD)
            )
            delay = min(2.0, max(0.05, fraction_over * 2.0))
            self._delays += 1
            await asyncio.sleep(delay)
            now = self._now()

        self._spent.append((now, weight))

    def _time_until_headroom(self, now: float, needed: int) -> float:
        freed = 0
        for stamp, weight in self._spent:
            freed += weight
            if self.used() - freed + needed <= self._limit:
                return max(0.05, self._window - (now - stamp) + 0.05)
        return self._window

    # ------------------------------------------------------------------ enforcement

    def note_rate_limited(self, *, status_code: int, retry_after_seconds: float | None) -> None:
        """The venue said stop. Believe it, with a margin."""
        now = self._now()
        if status_code == 418:
            cooldown = max(retry_after_seconds or 0.0, COOLDOWN_ON_418_SECONDS)
        else:
            cooldown = max(retry_after_seconds or 0.0, COOLDOWN_ON_429_SECONDS)
        self._cooldown_until = max(self._cooldown_until, now + cooldown)
        _log.warning(
            "budget_venue_rate_limited", status=status_code, cooldown_seconds=cooldown
        )

    @property
    def in_cooldown(self) -> bool:
        return self._now() < self._cooldown_until

    def snapshot(self) -> dict[str, Any]:
        return {
            "limit_per_window": self._limit,
            "window_seconds": self._window,
            "used": self.used(),
            "remaining": self.remaining(),
            "in_cooldown": self.in_cooldown,
            "paced_requests": self._delays,
            "exhausted_waits": self._denied_bursts,
            "weights_source": "documented defaults — REQUIRES VALIDATION via exchangeInfo",
        }


__all__ = [
    "DEFAULT_WEIGHT_PER_MINUTE",
    "ENDPOINT_WEIGHTS",
    "BinanceRequestBudget",
]
