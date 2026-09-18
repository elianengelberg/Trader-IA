"""Funding and carry — the perpetual market's own price of leverage, measured.

The BIS (Working Paper 1087, "Crypto carry") finds the gap between crypto futures and
spot averages **above 10% a year**, far larger than in any traditional asset, driven not
by interest rates but by retail demand for leveraged upside in booms and by how little
capital stands ready to take the other side. Two consequences matter to a trading system:

* The carry is a *return stream* — long spot, short the perpetual, collect the funding —
  and studies of that trade on centralised venues find modest, stable returns with
  venue, liquidation and settlement risks that the number does not show.
* **High carry predicts crashes.** A crowded long book paying rich funding is a book
  that liquidates in cascades. The same number is a warning as much as a yield.

This module reads Binance's public perpetual endpoints (keyless: the premium index and
the funding-rate history), keeps the record, and reports what it comes to: the current
funding, its annualised rate, where today sits in the last year of readings, the basis
between mark and index, and what a cash-and-carry would net after taker fees on both
legs. It places no order and reaches nothing in the trading pipeline; it informs the
operator and grounds the Advisor. If it ever *acts*, it will be through a gate that can
only refuse, like every other learned influence here.

Integration status: **REQUIRES VALIDATION** — the endpoints could not be reached from
this build environment; parsers follow the documented response shapes and the health
row says so when they fail.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from tia.core.clock import Clock
from tia.core.logging import get_logger

_log = get_logger("data.funding")

PREMIUM_INDEX_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
FUNDING_HISTORY_URL = "https://fapi.binance.com/fapi/v1/fundingRate"

#: Binance settles funding every eight hours: three payments a day.
FUNDINGS_PER_DAY = 3
#: Taker fee on each leg of a cash-and-carry, retail tier, in bps: spot 10 + perp 5,
#: paid twice (open and close both legs). Documented on binance.com/en/fee/schedule.
CARRY_ROUND_TRIP_FEE_BPS = 2 * (10.0 + 5.0)
MAX_BODY_BYTES = 512_000


@dataclass(frozen=True)
class FundingReading:
    at: datetime
    funding_rate: float  # per 8-hour period, as a fraction (0.0001 = 1 bp)
    mark_price: float | None = None
    index_price: float | None = None

    @property
    def annualised_pct(self) -> float:
        return self.funding_rate * FUNDINGS_PER_DAY * 365 * 100.0

    @property
    def basis_bps(self) -> float | None:
        if not self.mark_price or not self.index_price or self.index_price <= 0:
            return None
        return (self.mark_price - self.index_price) / self.index_price * 10_000.0


def parse_premium_index(payload: Any) -> FundingReading:
    """``GET /fapi/v1/premiumIndex`` -> ``{"markPrice", "indexPrice", "lastFundingRate",
    "nextFundingTime", "time"}``."""
    return FundingReading(
        at=datetime.fromtimestamp(int(payload["time"]) / 1000.0, tz=UTC),
        funding_rate=float(payload["lastFundingRate"]),
        mark_price=float(payload["markPrice"]),
        index_price=float(payload["indexPrice"]),
    )


def parse_funding_history(payload: Any) -> list[FundingReading]:
    """``GET /fapi/v1/fundingRate`` -> ``[{"fundingTime", "fundingRate", "markPrice"}, …]``."""
    rows = []
    for row in payload:
        rows.append(
            FundingReading(
                at=datetime.fromtimestamp(int(row["fundingTime"]) / 1000.0, tz=UTC),
                funding_rate=float(row["fundingRate"]),
                mark_price=float(row["markPrice"]) if row.get("markPrice") not in (None, "") else None,
            )
        )
    rows.sort(key=lambda r: r.at)
    return rows


def percentile_of(value: float, population: list[float]) -> float | None:
    """Share of the population at or below ``value``, in percent. None when empty."""
    if not population:
        return None
    return sum(1 for v in population if v <= value) / len(population) * 100.0


@dataclass
class FundingMonitor:
    """Polls the perpetual's funding and basis; keeps a year of settlements for context."""

    clock: Clock
    symbol: str = "BTCUSDT"
    client: httpx.AsyncClient | None = None
    poll_seconds: float = 300.0
    timeout_seconds: float = 6.0
    history_limit: int = 1000

    _latest: FundingReading | None = None
    _history: deque[FundingReading] = field(default_factory=lambda: deque(maxlen=1100))
    _health: dict[str, Any] = field(default_factory=dict)
    _task: asyncio.Task[Any] | None = None
    _polls: int = 0
    _history_loaded: bool = False
    _owns_client: bool = False

    def __post_init__(self) -> None:
        self._health = {"ok": None, "detail": "", "failures": 0, "last_attempt": None}
        if self.client is None:
            self._owns_client = True
            self.client = httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=False,
                headers={"User-Agent": "trader-ia/0.1 (research; read-only)"},
            )

    # ------------------------------------------------------------------ lifecycle

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.is_running:
            return
        self._task = asyncio.get_running_loop().create_task(self._run(), name="funding-monitor")

    async def _run(self) -> None:
        if self._polls:
            await asyncio.sleep(self.poll_seconds)
        while True:
            try:
                await self.poll()
            except Exception as exc:  # pragma: no cover - poll() isolates its own failures
                _log.warning("funding_poll_failed", error=str(exc)[:160])
            await asyncio.sleep(self.poll_seconds)

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        if self._owns_client and self.client is not None:
            await self.client.aclose()

    # ------------------------------------------------------------------ polling

    async def poll(self) -> FundingReading | None:
        """Read the premium index now; load the settlement history on the first call."""
        self._health["last_attempt"] = self.clock.now().isoformat()
        self._polls += 1
        try:
            if self.client is None:  # pragma: no cover - __post_init__ guarantees one
                raise RuntimeError("funding client not initialised")
            if not self._history_loaded:
                response = await self.client.get(
                    FUNDING_HISTORY_URL, params={"symbol": self.symbol, "limit": self.history_limit}
                )
                response.raise_for_status()
                if len(response.content) > MAX_BODY_BYTES:
                    raise ValueError("funding history exceeds size cap")
                for reading in parse_funding_history(response.json()):
                    self._history.append(reading)
                self._history_loaded = True
            response = await self.client.get(PREMIUM_INDEX_URL, params={"symbol": self.symbol})
            response.raise_for_status()
            if len(response.content) > MAX_BODY_BYTES:
                raise ValueError("premium index exceeds size cap")
            reading = parse_premium_index(response.json())
        except Exception as exc:
            self._health["ok"] = False
            self._health["failures"] = int(self._health.get("failures", 0)) + 1
            self._health["detail"] = f"{type(exc).__name__}: {str(exc)[:160]}"
            _log.warning("funding_fetch_failed", error=self._health["detail"])
            return None
        self._health["ok"] = True
        self._health["detail"] = "quoted"
        self._latest = reading
        return reading

    # ------------------------------------------------------------------ reading

    def report(self) -> dict[str, Any]:
        latest = self._latest
        history = list(self._history)
        rates = [r.funding_rate for r in history]
        annualised = [r.annualised_pct for r in history]
        recent_7d = [r for r in history if latest and (latest.at - r.at).days < 7]
        mean_7d = (
            sum(r.annualised_pct for r in recent_7d) / len(recent_7d) if recent_7d else None
        )
        percentile = percentile_of(latest.funding_rate, rates) if latest else None

        # What a cash-and-carry nets over a year at today's funding, after opening and
        # closing both legs at retail taker fees. No slippage, no liquidation, no venue
        # failure — the same "upper bound, not a forecast" the arbitrage page uses.
        carry_net_pct = (
            latest.annualised_pct - CARRY_ROUND_TRIP_FEE_BPS / 100.0 if latest else None
        )

        stance = "unknown"
        if latest is not None and percentile is not None:
            if percentile >= 90:
                stance = "crowded long"
            elif percentile <= 10:
                stance = "crowded short"
            else:
                stance = "balanced"

        return {
            "symbol": self.symbol,
            "as_of": self.clock.now().isoformat(),
            "running": self.is_running,
            "polls": self._polls,
            "health": dict(self._health),
            "latest": (
                {
                    "at": latest.at.isoformat(),
                    "funding_rate": latest.funding_rate,
                    "funding_bps": round(latest.funding_rate * 10_000.0, 4),
                    "annualised_pct": round(latest.annualised_pct, 3),
                    "mark_price": latest.mark_price,
                    "index_price": latest.index_price,
                    "basis_bps": (
                        round(latest.basis_bps, 3) if latest.basis_bps is not None else None
                    ),
                }
                if latest
                else None
            ),
            "history_settlements": len(history),
            "history_span_days": (
                round((history[-1].at - history[0].at).total_seconds() / 86_400.0, 1)
                if len(history) > 1
                else 0.0
            ),
            "mean_annualised_pct_7d": round(mean_7d, 3) if mean_7d is not None else None,
            "mean_annualised_pct_all": (
                round(sum(annualised) / len(annualised), 3) if annualised else None
            ),
            "percentile": round(percentile, 1) if percentile is not None else None,
            "stance": stance,
            "carry": {
                "net_annualised_pct": round(carry_net_pct, 3) if carry_net_pct is not None else None,
                "fee_round_trip_bps": CARRY_ROUND_TRIP_FEE_BPS,
                "assumes": (
                    "long spot, short perpetual, funding held at today's rate for a year, "
                    "both legs opened and closed at retail taker fees; no slippage, no "
                    "liquidation, no venue failure — an upper bound, not a forecast"
                ),
            },
            "history": [
                {"at": r.at.isoformat(), "annualised_pct": round(r.annualised_pct, 3)}
                for r in history[-90:]
            ],
            "verdict": self._verdict(latest, percentile, mean_7d, carry_net_pct),
        }

    @staticmethod
    def _verdict(
        latest: FundingReading | None,
        percentile: float | None,
        mean_7d: float | None,
        carry_net_pct: float | None,
    ) -> str:
        if latest is None:
            return "No funding reading yet — the health row says whether the endpoint answered."
        head = (
            f"Funding is {latest.funding_rate * 10_000:+.2f} bps per 8 hours "
            f"({latest.annualised_pct:+.1f}% annualised)"
        )
        if mean_7d is not None:
            head += f", averaging {mean_7d:+.1f}% over the last week"
        if percentile is not None:
            head += f"; today sits at the {percentile:.0f}th percentile of the last year"
        if carry_net_pct is not None:
            head += (
                f". A cash-and-carry held a year at this rate nets about "
                f"{carry_net_pct:+.1f}% after fees"
            )
        tail = (
            ". The BIS finds high carry predicts crashes: a rich funding rate is a crowded "
            "long book, and crowded books liquidate in cascades — read it as a warning "
            "before reading it as a yield."
            if percentile is not None and percentile >= 90
            else (
                ". Deeply negative funding is a crowded short book; historically that has "
                "resolved in squeezes more often than in further declines, but two or three "
                "episodes are not a rule."
                if percentile is not None and percentile <= 10
                else ". Nothing here is extreme; the perpetual market is not leaning hard either way."
            )
        )
        return head + tail


__all__ = [
    "CARRY_ROUND_TRIP_FEE_BPS",
    "FUNDINGS_PER_DAY",
    "FundingMonitor",
    "FundingReading",
    "parse_funding_history",
    "parse_premium_index",
    "percentile_of",
]
