"""Cross-venue arbitrage — measured against real quotes, with every cost on the table.

A viral post claims a student turned less than one dollar into four hundred thousand by
"scanning decentralised exchanges for small price gaps". The user asked the system to try
what the post describes. This module is the honest version of that attempt: it watches the
same bitcoin on three large exchanges, records every gap between them, subtracts the fees
each venue actually charges, and keeps the numbers — so the answer to "does this work?" is
a measurement rather than a belief.

**What is measured.** Top-of-book quotes (best bid, best ask) for BTC/USDT on Binance,
Coinbase Exchange and Kraken, from their public, keyless REST endpoints. For every ordered
pair of venues the gross gap is *sell venue's bid minus buy venue's ask*, in basis points of
the buy price; the net gap is the gross gap minus both venues' taker fees at the retail tier
(a new account with tiny volume, which is the tier a "$1 start" would sit in).

**What is deliberately not done.** No order is placed anywhere, on any tier. Everything
here reads public data, and nothing here touches the trading pipeline, the paper session,
the learning engine or the real-money gate. The report is informational — it exists to be
looked at, and to make a claim checkable.

**What the net number still leaves out** (each one makes reality worse than the report):
the spread crossed on both legs is already in the quotes, but slippage past the top of the
book is not; moving coins between exchanges costs a withdrawal fee and minutes of
confirmations during which the gap closes; keeping inventory on both venues instead ties
up twice the capital; and on-chain venues add swap fees of 25-30 bps per leg, priority fees,
and bots that see the same gap in the same block. The report says so where it is shown.

Integration status: **REQUIRES VALIDATION** — the venue endpoints could not be reached from
this build environment (egress blocked), so each parser is written against the venues'
documented response shapes and exercised with recorded payloads. Every venue's health is
part of the report: a dead or changed endpoint shows as such instead of as a silent zero.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import httpx

from tia.core.clock import Clock
from tia.core.logging import get_logger

_log = get_logger("data.arbitrage")

#: A ticker response larger than this is not a ticker; refuse rather than parse.
MAX_TICKER_BYTES = 64_000

#: Samples kept in memory: 24 hours at the default 15-second cadence.
DEFAULT_HISTORY = 5_760


# --------------------------------------------------------------------------- venues


@dataclass(frozen=True)
class Quote:
    """One venue's best bid and ask at one instant."""

    venue_id: str
    bid: float
    ask: float
    at: datetime

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread_bps(self) -> float:
        return (self.ask - self.bid) / self.mid * 10_000.0 if self.mid > 0 else 0.0


def _positive(value: Any, name: str) -> float:
    number = float(value)
    if not number > 0:
        raise ValueError(f"{name} must be positive, got {value!r}")
    return number


def parse_binance(payload: Any) -> tuple[float, float]:
    """``GET /api/v3/ticker/bookTicker`` -> ``{"bidPrice": "…", "askPrice": "…"}``."""
    return _positive(payload["bidPrice"], "bid"), _positive(payload["askPrice"], "ask")


def parse_coinbase(payload: Any) -> tuple[float, float]:
    """``GET /products/{id}/ticker`` -> ``{"bid": "…", "ask": "…", "price": …}``."""
    return _positive(payload["bid"], "bid"), _positive(payload["ask"], "ask")


def parse_kraken(payload: Any) -> tuple[float, float]:
    """``GET /0/public/Ticker`` -> ``{"error": [], "result": {PAIR: {"a": [ask, …],
    "b": [bid, …]}}}``. The pair key is whatever Kraken chooses to call it."""
    errors = payload.get("error") or []
    if errors:
        raise ValueError(f"kraken error: {errors[0]}")
    result = payload["result"]
    pair = next(iter(result.values()))
    return _positive(pair["b"][0], "bid"), _positive(pair["a"][0], "ask")


@dataclass(frozen=True)
class Venue:
    """One exchange in the registry. Fees are the venue's published retail taker rate."""

    venue_id: str
    name: str
    url: str
    #: Taker fee at the lowest-volume tier, in basis points. A "$1 start" sits here.
    taker_fee_bps: float
    #: Where the number came from, so a reviewer can check it aged well.
    fee_source: str
    parse: Callable[[Any], tuple[float, float]]


#: The registry. Three venues that publish keyless tickers and fee schedules. The instrument
#: is BTC/USDT on all three so the comparison is like for like — a USD pair on one side and a
#: USDT pair on the other would show a stablecoin basis of a few bps as if it were a gap.
DEFAULT_VENUES: tuple[Venue, ...] = (
    Venue(
        "binance", "Binance",
        "https://api.binance.com/api/v3/ticker/bookTicker?symbol=BTCUSDT",
        taker_fee_bps=10.0,
        fee_source="binance.com/en/fee/schedule — spot, regular user, taker 0.10%",
        parse=parse_binance,
    ),
    Venue(
        "coinbase", "Coinbase Exchange",
        "https://api.exchange.coinbase.com/products/BTC-USDT/ticker",
        taker_fee_bps=60.0,
        fee_source="coinbase.com/advanced-fees — Advanced Trade, under $1k/30d, taker 0.60%",
        parse=parse_coinbase,
    ),
    Venue(
        "kraken", "Kraken",
        "https://api.kraken.com/0/public/Ticker?pair=XBTUSDT",
        taker_fee_bps=40.0,
        fee_source="kraken.com/features/fee-schedule — spot, under $10k/30d, taker 0.40%",
        parse=parse_kraken,
    ),
)


# --------------------------------------------------------------------------- gap maths


@dataclass(frozen=True)
class Gap:
    """Buy at one venue's ask, sell at another's bid, fees subtracted. Pure arithmetic."""

    buy_venue: str
    sell_venue: str
    buy_ask: float
    sell_bid: float
    gross_bps: float
    fee_bps: float
    net_bps: float

    @property
    def clears_costs(self) -> bool:
        return self.net_bps > 0

    def net_usd(self, notional_usd: float) -> float:
        """What the round trip nets on a position of this size, before anything not
        in the quotes (slippage, transfer, capital tied up on both sides)."""
        return notional_usd * self.net_bps / 10_000.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "buy_venue": self.buy_venue,
            "sell_venue": self.sell_venue,
            "buy_ask": self.buy_ask,
            "sell_bid": self.sell_bid,
            "gross_bps": round(self.gross_bps, 3),
            "fee_bps": round(self.fee_bps, 3),
            "net_bps": round(self.net_bps, 3),
            "clears_costs": self.clears_costs,
            "net_usd_per_100": round(self.net_usd(100.0), 4),
            "net_usd_per_10k": round(self.net_usd(10_000.0), 2),
        }


def pairwise_gaps(quotes: Sequence[Quote], fees_bps: Mapping[str, float]) -> list[Gap]:
    """Every ordered (buy here, sell there) pair, best net first.

    Gross is measured in basis points of the buy price — the money at risk. Fees are the
    taker rate on both legs because an arbitrage that waits for a maker fill is not an
    arbitrage; the gap is gone before the order is.
    """
    gaps: list[Gap] = []
    for buy in quotes:
        for sell in quotes:
            if buy.venue_id == sell.venue_id or buy.ask <= 0:
                continue
            gross = (sell.bid - buy.ask) / buy.ask * 10_000.0
            fee = float(fees_bps.get(buy.venue_id, 0.0)) + float(fees_bps.get(sell.venue_id, 0.0))
            gaps.append(
                Gap(
                    buy_venue=buy.venue_id,
                    sell_venue=sell.venue_id,
                    buy_ask=buy.ask,
                    sell_bid=sell.bid,
                    gross_bps=gross,
                    fee_bps=fee,
                    net_bps=gross - fee,
                )
            )
    gaps.sort(key=lambda g: g.net_bps, reverse=True)
    return gaps


# --------------------------------------------------------------------------- service


@dataclass
class _VenueHealth:
    venue: Venue
    ok: bool | None = None  # None until first attempted
    detail: str = ""
    last_attempt: datetime | None = None
    last_quote: Quote | None = None
    failures: int = 0

    def as_dict(self) -> dict[str, Any]:
        quote = self.last_quote
        return {
            "venue_id": self.venue.venue_id,
            "name": self.venue.name,
            "url": self.venue.url,
            "taker_fee_bps": self.venue.taker_fee_bps,
            "fee_source": self.venue.fee_source,
            "ok": self.ok,
            "detail": self.detail,
            "failures": self.failures,
            "last_attempt": self.last_attempt.isoformat() if self.last_attempt else None,
            "bid": quote.bid if quote else None,
            "ask": quote.ask if quote else None,
            "mid": round(quote.mid, 2) if quote else None,
            "spread_bps": round(quote.spread_bps, 3) if quote else None,
            "quoted_at": quote.at.isoformat() if quote else None,
        }


@dataclass(frozen=True)
class Sample:
    """One poll: which venues answered and the best gap between the ones that did."""

    at: datetime
    venues_quoted: int
    best: Gap | None

    @property
    def best_net_bps(self) -> float | None:
        return self.best.net_bps if self.best else None

    @property
    def best_gross_bps(self) -> float | None:
        return self.best.gross_bps if self.best else None


@dataclass
class CrossVenueMonitor:
    """Polls the venues, keeps the gaps, and tells you what they came to.

    Failure is a first-class outcome: a venue that is down, rate-limiting, or has changed
    its response shape is recorded as such and skipped — the gaps between the venues that
    did answer are still measured, and no failure here can reach the trading loop because
    nothing here is on the trading loop.
    """

    clock: Clock
    venues: tuple[Venue, ...] = DEFAULT_VENUES
    client: httpx.AsyncClient | None = None
    poll_seconds: float = 15.0
    timeout_seconds: float = 6.0
    history_size: int = DEFAULT_HISTORY
    #: A quote older than this is not compared: a gap between now and a minute ago is
    #: a chart, not an arbitrage.
    max_quote_age_seconds: float = 20.0

    _health: dict[str, _VenueHealth] = field(default_factory=dict)
    _history: deque[Sample] = field(default_factory=deque)
    _gaps: list[Gap] = field(default_factory=list)
    _task: asyncio.Task[Any] | None = None
    _started_at: datetime | None = None
    _polls: int = 0
    _owns_client: bool = False

    def __post_init__(self) -> None:
        self._health = {v.venue_id: _VenueHealth(venue=v) for v in self.venues}
        self._history = deque(maxlen=self.history_size)
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
        """Begin sampling in the background. Idempotent."""
        if self.is_running:
            return
        self._started_at = self._started_at or self.clock.now()
        self._task = asyncio.get_running_loop().create_task(self._run(), name="arbitrage-monitor")

    async def _run(self) -> None:
        if self._polls:  # the caller already polled inline; the cadence starts from there
            await asyncio.sleep(self.poll_seconds)
        while True:
            try:
                await self.poll()
            except Exception as exc:  # pragma: no cover - poll() isolates its own failures
                _log.warning("arbitrage_poll_failed", error=str(exc)[:160])
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

    async def poll(self) -> Sample:
        """Fetch every venue at once, measure the gaps between those that answered."""
        if self._started_at is None:
            self._started_at = self.clock.now()
        await asyncio.gather(
            *(self._fetch_venue(v) for v in self.venues),
            return_exceptions=True,  # belt and braces; _fetch_venue already catches
        )
        now = self.clock.now()
        fresh = [
            h.last_quote
            for h in self._health.values()
            if h.last_quote is not None
            and (now - h.last_quote.at) <= timedelta(seconds=self.max_quote_age_seconds)
        ]
        fees = {v.venue_id: v.taker_fee_bps for v in self.venues}
        self._gaps = pairwise_gaps(fresh, fees)
        sample = Sample(at=now, venues_quoted=len(fresh), best=self._gaps[0] if self._gaps else None)
        self._history.append(sample)
        self._polls += 1
        return sample

    async def _fetch_venue(self, venue: Venue) -> None:
        health = self._health[venue.venue_id]
        health.last_attempt = self.clock.now()
        try:
            if self.client is None:  # pragma: no cover - __post_init__ guarantees one
                raise RuntimeError("arbitrage client not initialised")
            response = await self.client.get(venue.url)
            response.raise_for_status()
            if len(response.content) > MAX_TICKER_BYTES:
                raise ValueError(f"ticker exceeds {MAX_TICKER_BYTES} bytes")
            bid, ask = venue.parse(response.json())
            if ask < bid:
                raise ValueError(f"crossed book: bid {bid} > ask {ask}")
        except Exception as exc:  # each venue degrades independently
            health.ok = False
            health.failures += 1
            health.detail = f"{type(exc).__name__}: {str(exc)[:160]}"
            _log.warning("arbitrage_venue_failed", venue=venue.venue_id, error=health.detail)
            return
        health.ok = True
        health.detail = "quoted"
        health.last_quote = Quote(venue_id=venue.venue_id, bid=bid, ask=ask, at=self.clock.now())

    # ------------------------------------------------------------------ reading

    @staticmethod
    def _downsample(samples: Iterable[Sample], limit: int) -> list[dict[str, Any]]:
        rows = [s for s in samples if s.best is not None]
        if len(rows) > limit:
            step = -(-len(rows) // limit)
            rows = rows[::step] + ([rows[-1]] if (len(rows) - 1) % step else [])
        return [
            {
                "at": s.at.isoformat(),
                "net_bps": round(s.best_net_bps or 0.0, 3),
                "gross_bps": round(s.best_gross_bps or 0.0, 3),
            }
            for s in rows
        ]

    def report(self, *, history_points: int = 240) -> dict[str, Any]:
        """Everything measured so far, with the arithmetic the viral claim leaves out."""
        now = self.clock.now()
        samples = list(self._history)
        measured = [s for s in samples if s.best is not None]
        positive = [s for s in measured if (s.best_net_bps or 0.0) > 0]
        best = max(measured, key=lambda s: s.best_net_bps or 0.0, default=None)
        mean_net = (
            sum(s.best_net_bps or 0.0 for s in measured) / len(measured) if measured else None
        )
        span_seconds = (
            (samples[-1].at - samples[0].at).total_seconds() if len(samples) > 1 else 0.0
        )

        # The upper bound of the strategy: one $100 round trip on every sample whose best
        # gap cleared fees, filled instantly at the top of both books, with inventory
        # already sitting on both venues. Reality can only be worse than this number.
        hypothetical_notional = 100.0
        hypothetical_usd = sum((s.best.net_usd(hypothetical_notional) for s in positive if s.best), 0.0)
        per_hour = hypothetical_usd / (span_seconds / 3600.0) if span_seconds >= 600 else None

        return {
            "instrument": "BTC/USDT",
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "as_of": now.isoformat(),
            "running": self.is_running,
            "poll_seconds": self.poll_seconds,
            "polls": self._polls,
            "venues": [h.as_dict() for h in self._health.values()],
            "venues_ok": sum(1 for h in self._health.values() if h.ok),
            "gaps": [g.as_dict() for g in self._gaps],
            "stats": {
                "samples": len(samples),
                "samples_measured": len(measured),
                "span_seconds": round(span_seconds, 1),
                "opportunities": len(positive),
                "opportunity_share": (len(positive) / len(measured)) if measured else None,
                "best_net_bps": round(best.best_net_bps or 0.0, 3) if best else None,
                "best_gross_bps": round(best.best_gross_bps or 0.0, 3) if best else None,
                "best_at": best.at.isoformat() if best else None,
                "best_pair": (
                    f"buy {best.best.buy_venue} / sell {best.best.sell_venue}"
                    if best and best.best
                    else None
                ),
                "mean_best_net_bps": round(mean_net, 3) if mean_net is not None else None,
            },
            "hypothetical": {
                "notional_usd": hypothetical_notional,
                "round_trips": len(positive),
                "net_usd": round(hypothetical_usd, 4),
                "net_usd_per_hour": round(per_hour, 4) if per_hour is not None else None,
                "assumes": (
                    "inventory already on both venues, instant fills at the top of both "
                    "books, no slippage, no transfers — an upper bound, not a forecast"
                ),
            },
            "history": self._downsample(samples, history_points),
            "verdict": self._verdict(measured, positive, best, mean_net, span_seconds),
            "caveats": [
                "Top-of-book only: any size beyond the first level pays more than the quote.",
                "Moving coins between venues costs a withdrawal fee and minutes of "
                "confirmations; the gap does not wait.",
                "Holding inventory on every venue instead ties up capital on all of them "
                "for a return measured in basis points.",
                "On-chain venues add 25-30 bps of swap fees per leg, priority fees, and "
                "bots that see the same gap in the same block.",
            ],
        }

    @staticmethod
    def _verdict(
        measured: list[Sample],
        positive: list[Sample],
        best: Sample | None,
        mean_net: float | None,
        span_seconds: float,
    ) -> str:
        if not measured:
            return (
                "No gap measured yet — fewer than two venues have answered. The per-venue "
                "rows above say which ones and why."
            )
        hours = span_seconds / 3600.0
        window = f"{hours:.1f} hours" if hours >= 1 else f"{span_seconds / 60:.0f} minutes"
        best_net = best.best_net_bps or 0.0 if best else 0.0
        share = len(positive) / len(measured)
        head = (
            f"Over {window} and {len(measured)} samples, the best gap after taker fees was "
            f"{best_net:+.1f} bps ({best_net / 100:+.3f} dollars per $100), and fees were "
            f"cleared in {share * 100:.1f}% of samples"
        )
        if mean_net is not None:
            head += f"; the typical best gap was {mean_net:+.1f} bps net"
        if share == 0:
            tail = (
                ". Every gap seen was smaller than the fees to take it. On one dollar that "
                "is a loss of a fraction of a cent per attempt, not a path to anything."
            )
        elif best_net < 5:
            tail = (
                ". The gaps that did clear fees were worth cents per hundred dollars and "
                "assume instant fills on both venues with capital already parked on each. "
                "That is the whole trade; nothing in it compounds one dollar into anything."
            )
        else:
            tail = (
                ". Gaps this size exist for seconds and are contested by bots with capital "
                "on every venue; the report's hypothetical is the most a perfect executor "
                "could have made, and it is dollars, not fortunes."
            )
        return head + tail
