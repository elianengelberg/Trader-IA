"""What ``engine_version`` 1.1.0 promises, checked at the venue (a guard against a false label).

``ENGINE_VERSION`` is a label written by hand next to the code it describes: 1.1.0 means
"order hygiene D1-D3". Nothing ties the label to the behaviour. The provenance change can
be applied, or reverted, without the order-hygiene change, and the engine then records
1.1.0 on results it produced without D1-D3 — while every provenance test still passes.

This module ties them from the outside. Each test runs the real engine over the fixtures
with a paper venue that only *records* what reaches it (and, per scenario, rejects the
first close of every position or lets closes fill only at once), reads the version the
engine wrote on its own result and, when that version claims D1-D3, holds the venue's
record to what D1-D3 mean:

* D1 — a retried close or stop is a new order. Nothing the venue already rejected or
  cancelled is sent again under the same id, and a time stop whose first close is
  rejected still closes within a few bars.
* D2 — the stop in the book follows the leg. It moves, only ever tighter, with no change
  of size, and a working stop is never replaced by an identical one.
* D3 — once a close is sent nothing is added to the position, an entry never fills into
  a position after the one it opened has closed, and a held position is never left with
  neither a working stop nor a working close.

Deliberately not used: the engine's counters (``order_hygiene``), its private state, its
fingerprint, the D1-D3 tests and any trade count. The checks see only orders, fills and
positions at the venue. An engine that carries the label and even the interface of 1.1.0
without the behaviour fails here, and nothing ties the checks to how this engine implements
the rules. What they do assume is the venue contract of today: closes are reduce-only
market orders and stops are stop orders. A version below 1.1.0, or none, claims nothing
and is not held to it; a version that is not a dotted number fails rather than escape.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

import pytest

import tia.backtest.engine as engine_module
from tia.backtest import BacktestConfig, BacktestEngine
from tia.core.config import ExecutionSimConfig
from tia.data.providers.csv_replay import CsvReplayProvider
from tia.domain.enums import OrderState, OrderType, Side
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.domain.market import Candle
from tia.execution.paper import PaperExecutionProvider
from tia.execution.state_machine import transition

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"
SERIES: list[Candle] = asyncio.run(
    CsvReplayProvider(FIXTURES).get_candles("BTC-USD", "1h", limit=700)
)

#: The first version whose label promises D1-D3. Every later version keeps the promise.
ORDER_HYGIENE_SINCE = (1, 1, 0)
TIME_STOP_BARS = 6
#: Seen from the venue, a position whose time-stop close goes through at once is held for
#: ``TIME_STOP_BARS`` bars; a rejected first close, asked for again on the next bar, adds
#: one. Three bars of slack leave two of margin.
TIME_STOP_SLACK = 3
#: Bars a held position may spend with neither a working stop nor a working close. The
#: engine places or re-places the stop on the bar that needs it, so the venue should never
#: see a gap; one bar of margin, no more.
MAX_BARS_UNCOVERED = 1


# --------------------------------------------------------------------------- the venue


@dataclass(frozen=True)
class Sent:
    """One submission, as the venue saw it."""

    bar: int
    order_id: str
    order_type: OrderType
    side: Side
    reduce_only: bool
    quantity: float
    stop_price: float | None
    held: float  # the signed position when it arrived
    new: bool  # False: the venue handed back an order it already had (same client id)
    was_dead: bool  # ... and that order was already rejected, cancelled or expired
    episode: int = 0  # the position (counted at the venue) held when it arrived
    seq: int = 0  # order of arrival among submissions and cancels


@dataclass(frozen=True)
class Cancelled:
    bar: int
    order_id: str
    order_type: OrderType
    remaining: float
    stop_price: float | None
    was_open: bool
    seq: int = 0


@dataclass(frozen=True)
class Working:
    order_id: str
    order_type: OrderType
    side: Side
    reduce_only: bool
    remaining: float
    stop_price: float | None


@dataclass(frozen=True)
class Look:
    """The venue at the start of a bar, as the engine left it after the previous one."""

    bar: int
    held: float
    working: tuple[Working, ...]


@dataclass(frozen=True)
class Filled:
    bar: int
    order_id: str
    order_type: OrderType
    reduce_only: bool
    before: float
    after: float
    episode: int  # which position (counted at the venue) this fill belongs to


@dataclass
class Record:
    sent: list[Sent]
    looks: list[Look]
    fills: list[Filled]
    cancels: list[Cancelled] = field(default_factory=list)
    closes_rejected: int = 0
    closes_expired_with_position: int = 0


def _held(provider: PaperExecutionProvider, symbol: str) -> float:
    position = provider.portfolio.positions.get(symbol)
    return 0.0 if position is None or position.is_flat else float(position.quantity)


class _Venue(PaperExecutionProvider):
    """The paper venue, unchanged except that it writes down what reaches it. Per scenario
    it also rejects the first close of every position, or lets closes fill only at once."""

    last: ClassVar[_Venue | None] = None
    reject_first_close: ClassVar[bool] = False
    closes_are_ioc: ClassVar[bool] = False

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        _Venue.last = self
        self.bar = -1
        self.episode = 0
        self.record = Record(sent=[], looks=[], fills=[])
        self.seq = 0
        self._close_rejected_this_episode = False

    async def submit_order(self, intent):  # type: ignore[no-untyped-def]
        before = {o.order_id: o.state for o in await self.get_orders()}
        held = _held(self, intent.symbol)
        order = await super().submit_order(intent)
        new = order.order_id not in before
        self.record.sent.append(Sent(
            bar=self.bar, order_id=order.order_id, order_type=intent.order_type, side=intent.side,
            reduce_only=bool(intent.reduce_only), quantity=float(intent.quantity),
            stop_price=None if intent.stop_price is None else float(intent.stop_price), held=held,
            new=new, was_dead=not new and before[order.order_id].is_terminal, episode=self.episode,
            seq=self._next(),
        ))
        return order

    async def cancel_order(self, order_id):  # type: ignore[no-untyped-def]
        order = await self.get_order(order_id)
        if order is not None:
            self.record.cancels.append(Cancelled(
                bar=self.bar, order_id=order.order_id, order_type=order.order_type,
                remaining=float(order.quantity - order.filled_quantity),
                stop_price=None if order.stop_price is None else float(order.stop_price),
                was_open=order.state.is_open, seq=self._next(),
            ))
        return await super().cancel_order(order_id)

    def _next(self) -> int:
        self.seq += 1
        return self.seq

    def _should_reject(self, order):  # type: ignore[no-untyped-def]
        if (self.reject_first_close and order.reduce_only and order.order_type is OrderType.MARKET
                and not self._close_rejected_this_episode):
            self._close_rejected_this_episode = True
            self.record.closes_rejected += 1
            return True
        return super()._should_reject(order)

    def _try_fill(self, order, candle):  # type: ignore[no-untyped-def]
        before = _held(self, order.symbol)
        fill = super()._try_fill(order, candle)
        after = _held(self, order.symbol)
        if fill is not None:
            if before == 0.0 and after != 0.0:
                self.episode += 1
                self._close_rejected_this_episode = False
            self.record.fills.append(Filled(
                bar=self.bar, order_id=order.order_id, order_type=order.order_type,
                reduce_only=bool(order.reduce_only), before=before, after=after, episode=self.episode,
            ))
        if (self.closes_are_ioc and order.reduce_only and order.order_type is OrderType.MARKET
                and not order.state.is_terminal):
            transition(order, OrderState.EXPIRED, at=candle.close_time, reason="immediate-or-cancel: the rest expired")
            if after != 0.0:
                self.record.closes_expired_with_position += 1
        return fill

    def on_bar(self, candle):  # type: ignore[no-untyped-def]
        self.bar += 1
        working = tuple(
            Working(o.order_id, o.order_type, o.side, bool(o.reduce_only),
                    float(o.quantity - o.filled_quantity), None if o.stop_price is None else float(o.stop_price))
            for o in asyncio.run(self.get_orders(open_only=True)) if o.symbol == candle.symbol
        )
        self.record.looks.append(Look(bar=self.bar, held=_held(self, candle.symbol), working=working))
        return super().on_bar(candle)


# --------------------------------------------------------------------- the checks (venue only)


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(abs(a), abs(b), 1.0)


def _protects(held: float, order: Working) -> bool:
    """An order working against the position: a stop or a close on the opposite side."""
    against = Side.SELL if held > 0 else Side.BUY
    return order.side is against and (order.order_type is OrderType.STOP or order.reduce_only)


def dead_orders_sent_again(record: Record) -> list[str]:
    """D1: a retry suppressed as a duplicate of an order that was already dead."""
    return [f"bar {s.bar}: {s.order_type.value} {s.order_id} sent again after it was dead"
            for s in record.sent if s.was_dead]


def uncovered_streaks(record: Record, limit: int = MAX_BARS_UNCOVERED) -> list[str]:
    """D1 and D3: a held position with neither a working stop nor a working close."""
    found, streak = [], 0
    for look in record.looks:
        if look.held != 0.0 and not any(_protects(look.held, w) for w in look.working):
            streak += 1
            if streak > limit:
                found.append(f"bar {look.bar}: {look.held} held, uncovered for {streak} bars")
        else:
            streak = 0
    return found


def positions_held_too_long(record: Record, limit: int) -> list[str]:
    """D1 for exits: with a time stop, no position outlives it by more than the slack."""
    found, opened = [], None
    for look in record.looks:
        if look.held != 0.0 and opened is None:
            opened = look.bar
        elif look.held == 0.0:
            opened = None
        if opened is not None and look.bar - opened > limit:
            found.append(f"bar {look.bar}: position open since bar {opened}")
            opened = None  # one report per position
    return found


def stop_moves(record: Record) -> tuple[int, list[str]]:
    """D2: the stops one position got, in order. How many moved at the same size, which
    loosened, and which replaced a working stop of the same size and level (churn). A
    stop cancelled to make way for a close and put back when the close was rejected is
    not churn: the close is what moved it."""
    moved, wrong = 0, []
    closes_at = {s.bar for s in record.sent if s.reduce_only and s.order_type is OrderType.MARKET}
    last: dict[int, Sent] = {}
    for sent in record.sent:
        if sent.order_type is not OrderType.STOP or not sent.new or sent.held == 0.0 or sent.stop_price is None:
            continue
        previous = last.get(sent.episode)
        last[sent.episode] = sent
        if previous is None or previous.stop_price is None:
            continue
        if not _same(previous.stop_price, sent.stop_price):
            long = sent.held > 0
            if (sent.stop_price < previous.stop_price) if long else (sent.stop_price > previous.stop_price):
                wrong.append(f"bar {sent.bar}: stop loosened from {previous.stop_price} to {sent.stop_price}")
            if _same(previous.quantity, sent.quantity):
                moved += 1
        elif sent.bar not in closes_at and any(
            c.bar == sent.bar and c.seq < sent.seq and c.order_id != sent.order_id and c.was_open
            and c.order_type is OrderType.STOP and c.stop_price is not None
            and _same(c.stop_price, sent.stop_price) and _same(c.remaining, sent.quantity)
            for c in record.cancels
        ):
            wrong.append(f"bar {sent.bar}: a working stop replaced at the same size and level {sent.stop_price}")
    return moved, wrong


def growth_after_close(record: Record) -> list[str]:
    """D3: once a close is sent for a position, nothing adds to it."""
    found, asked_at = [], None
    # On a bar the venue matches first (fills) and the engine acts after (submissions).
    events = sorted([(f.bar, 0, f) for f in record.fills] + [(s.bar, 1, s) for s in record.sent],
                    key=lambda e: (e[0], e[1]))
    size = None
    for _bar, kind, event in events:
        if kind == 1:
            if event.reduce_only and event.order_type is OrderType.MARKET and event.held != 0.0 and size is None:
                size = abs(event.held)
                asked_at = event.bar
        else:
            if event.after == 0.0:
                size = None
            elif size is not None and abs(event.after) > size * (1 + 1e-9) + 1e-12:
                found.append(f"bar {event.bar}: grew from {size} to {abs(event.after)} after the close at bar {asked_at}")
    return found


def entries_filling_a_later_position(record: Record) -> list[str]:
    """D3 when flat: an entry whose earlier fills opened a position that has since closed
    never fills again into another one."""
    first_episode: dict[str, int] = {}
    found = []
    for fill in record.fills:
        if fill.reduce_only or fill.order_type is OrderType.STOP:
            continue
        seen = first_episode.setdefault(fill.order_id, fill.episode)
        if fill.episode != seen:
            found.append(f"bar {fill.bar}: entry {fill.order_id} of position {seen} filled into position {fill.episode}")
    return found


def closes_without_reduce_only(record: Record) -> list[str]:
    """Kept from before 1.1.0 and not weakened by it: a market order against the position
    is a close, and a close is reduce-only."""
    return [f"bar {s.bar}: market {s.side.value} against {s.held} without reduce_only"
            for s in record.sent
            if s.order_type is OrderType.MARKET and s.held != 0.0
            and (s.side is Side.SELL) == (s.held > 0) and not s.reduce_only]


# ----------------------------------------------------------------------- running and gating


def _declared(raw: object) -> tuple[int, ...] | None:
    if raw is None:
        return None
    try:
        return tuple(int(part) for part in str(raw).split("."))
    except ValueError:
        raise AssertionError(f"engine_version {raw!r} is not a dotted number: no promise can be read from it") from None


def _run(monkeypatch: pytest.MonkeyPatch, *, reject_first_close: bool = False, closes_are_ioc: bool = False,
         reject: float = 0.0, partial: float = 0.0, **config: object) -> Record:
    monkeypatch.setattr(engine_module, "PaperExecutionProvider", _Venue)
    monkeypatch.setattr(_Venue, "reject_first_close", reject_first_close)
    monkeypatch.setattr(_Venue, "closes_are_ioc", closes_are_ioc)
    monkeypatch.setattr(_Venue, "last", None)
    engine = BacktestEngine(
        BacktestConfig(
            dataset="fixtures", timeframe="1h", warmup_bars=120,
            execution=ExecutionSimConfig(reject_probability=reject, partial_fill_probability=partial),
            **config,
        ),
        DEFAULT_UNIVERSE,
    )
    result = engine.run(SERIES)
    venue = _Venue.last
    # Fail closed: if the engine stopped building its venue through this name, the checks
    # below would see nothing and pass for nothing.
    assert venue is not None and venue.record.looks, "the engine did not run on the recording venue"
    assert len(venue.record.looks) == len(SERIES)
    version = _declared(getattr(result.conditions, "engine_version", None))
    if version is None or version < ORDER_HYGIENE_SINCE:
        pytest.skip(f"the engine records version {version}: it does not claim D1-D3")
    return venue.record


def test_a_rejected_close_is_sent_again_as_a_new_order_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    """D1, exits: the venue rejects the first close of every position."""
    record = _run(monkeypatch, reject_first_close=True, max_holding_bars=TIME_STOP_BARS)
    assert record.closes_rejected, "the scenario must reject closes"
    assert not dead_orders_sent_again(record), dead_orders_sent_again(record)[:3]
    late = positions_held_too_long(record, TIME_STOP_BARS + TIME_STOP_SLACK)
    assert not late, late[:3]
    assert not uncovered_streaks(record), uncovered_streaks(record)[:3]


def test_the_stop_in_the_book_follows_the_leg(monkeypatch: pytest.MonkeyPatch) -> None:
    """D2: break-even and trailing move the stop in the book, only ever tighter, and a
    working stop is not replaced by an identical one."""
    record = _run(monkeypatch)
    moved, wrong = stop_moves(record)
    assert moved, "no stop in the book ever moved at the same size: break-even and trailing stayed on paper"
    assert not wrong, wrong[:3]
    assert not dead_orders_sent_again(record), dead_orders_sent_again(record)[:3]
    assert not uncovered_streaks(record), uncovered_streaks(record)[:3]


def test_partial_fills_never_add_to_a_closing_position_or_reopen_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """D3, on the close and when flat: most fills partial, entries resting in part."""
    record = _run(monkeypatch, partial=0.9)
    assert any(f.after != 0.0 and not f.reduce_only and f.order_type is not OrderType.STOP for f in record.fills)
    for check in (growth_after_close, entries_filling_a_later_position, dead_orders_sent_again,
                  closes_without_reduce_only, uncovered_streaks):
        assert not check(record), (check.__name__, check(record)[:3])


def test_a_close_that_ends_with_position_left_is_followed_by_another(monkeypatch: pytest.MonkeyPatch) -> None:
    """D3 safety net: closes are immediate-or-cancel, so most end with position left. The
    position is never left with neither a stop nor a close working."""
    record = _run(monkeypatch, closes_are_ioc=True, partial=0.9, max_holding_bars=TIME_STOP_BARS)
    for check in (uncovered_streaks, growth_after_close, dead_orders_sent_again, closes_without_reduce_only):
        assert not check(record), (check.__name__, check(record)[:3])
    assert record.closes_expired_with_position, "the scenario must end closes with position left"


def test_rejections_partials_and_limit_entries_together(monkeypatch: pytest.MonkeyPatch) -> None:
    """D1-D3 at once, as a venue has them: a third of all orders rejected, most fills
    partial, limit entries that expire, the first close of every position rejected."""
    record = _run(monkeypatch, reject_first_close=True, reject=0.3, partial=0.6, entry_order_type="limit",
                  max_holding_bars=TIME_STOP_BARS)
    for check in (dead_orders_sent_again, growth_after_close, entries_filling_a_later_position,
                  closes_without_reduce_only):
        assert not check(record), (check.__name__, check(record)[:3])


# ------------------------------------------------------- the checks against hand-made records


def _look(bar: int, held: float, *working: Working) -> Look:
    return Look(bar=bar, held=held, working=tuple(working))


_STOP = Working("s", OrderType.STOP, Side.SELL, False, 1.0, 90.0)
_CLOSE = Working("c", OrderType.MARKET, Side.SELL, True, 1.0, None)
_ENTRY = Working("e", OrderType.LIMIT, Side.BUY, False, 1.0, None)


def _sent(bar: int, order_type: OrderType = OrderType.STOP, *, held: float = 1.0, stop: float | None = 90.0,
          new: bool = True, dead: bool = False, side: Side = Side.SELL, reduce_only: bool = False,
          quantity: float = 1.0, order_id: str = "o", seq: int = 0) -> Sent:
    return Sent(bar, order_id, order_type, side, reduce_only, quantity, stop, held, new, dead, seq=seq)


def test_the_checks_pass_a_clean_record_and_catch_each_defect() -> None:
    """Each check, on a record built by hand: silent on the clean one, loud on the defect
    it is for. Without this a check that can never fail would pass every engine."""
    clean = Record(
        sent=[_sent(1, order_id="s1"), _sent(3, stop=95.0, order_id="s2"),
              _sent(5, OrderType.MARKET, stop=None, reduce_only=True, order_id="c1")],
        looks=[_look(0, 0.0), _look(1, 1.0, _STOP), _look(2, 1.0, _STOP), _look(3, 1.0, _STOP),
               _look(4, 1.0, _CLOSE), _look(5, 0.0)],
        fills=[Filled(0, "e1", OrderType.MARKET, False, 0.0, 1.0, 1), Filled(5, "c1", OrderType.MARKET, True, 1.0, 0.0, 1)],
    )
    assert not dead_orders_sent_again(clean)
    assert not uncovered_streaks(clean)
    assert not positions_held_too_long(clean, 10)
    assert stop_moves(clean) == (1, [])
    assert not growth_after_close(clean)
    assert not entries_filling_a_later_position(clean)
    assert not closes_without_reduce_only(clean)

    assert dead_orders_sent_again(Record(sent=[_sent(2, new=False, dead=True)], looks=[], fills=[]))
    assert uncovered_streaks(Record(sent=[], looks=[_look(b, 1.0) for b in range(3)], fills=[]))
    assert uncovered_streaks(Record(sent=[], looks=[_look(b, 1.0, _ENTRY) for b in range(3)], fills=[]))
    assert positions_held_too_long(Record(sent=[], looks=[_look(b, 1.0, _STOP) for b in range(12)], fills=[]), 10)
    assert stop_moves(Record(sent=[_sent(1, order_id="a")], looks=[], fills=[]))[0] == 0
    assert stop_moves(Record(sent=[_sent(1, order_id="a"), _sent(2, stop=80.0, order_id="b")], looks=[], fills=[]))[1]
    churn = Record(sent=[_sent(1, order_id="a", seq=1), _sent(2, order_id="b", seq=3)], looks=[], fills=[],
                   cancels=[Cancelled(2, "a", OrderType.STOP, 1.0, 90.0, True, seq=2)])
    assert stop_moves(churn)[1]
    put_back = Record(sent=[_sent(1, order_id="a", seq=1), _sent(2, OrderType.MARKET, stop=None, reduce_only=True, seq=3),
                            _sent(2, order_id="b", seq=4)], looks=[], fills=[],
                      cancels=[Cancelled(2, "a", OrderType.STOP, 1.0, 90.0, True, seq=2)])
    assert stop_moves(put_back) == (0, [])
    run_ends = Record(sent=[_sent(1, order_id="a", seq=1), _sent(2, order_id="b", seq=3)], looks=[], fills=[],
                      cancels=[Cancelled(2, "a", OrderType.STOP, 1.0, 90.0, True, seq=2),
                               Cancelled(2, "b", OrderType.STOP, 1.0, 90.0, True, seq=4)])
    assert stop_moves(run_ends)[1] == stop_moves(churn)[1]  # the cancel after it is not what replaced it
    assert growth_after_close(Record(
        sent=[_sent(3, OrderType.MARKET, stop=None, reduce_only=True)], looks=[],
        fills=[Filled(4, "e", OrderType.LIMIT, False, 1.0, 1.5, 1)]))
    assert entries_filling_a_later_position(Record(sent=[], looks=[], fills=[
        Filled(1, "e", OrderType.LIMIT, False, 0.0, 0.5, 1), Filled(9, "e", OrderType.LIMIT, False, 0.0, 0.5, 2)]))
    assert closes_without_reduce_only(Record(sent=[_sent(3, OrderType.MARKET, stop=None)], looks=[], fills=[]))


def test_a_version_that_is_not_a_number_cannot_escape_the_guard() -> None:
    assert _declared(None) is None
    assert _declared("1.1.0") == (1, 1, 0) >= ORDER_HYGIENE_SINCE
    assert _declared("1.2.0") >= ORDER_HYGIENE_SINCE  # a later version keeps the promise
    assert _declared("1.0.9") < ORDER_HYGIENE_SINCE
    with pytest.raises(AssertionError):
        _declared("1.1.0-rc1")
