"""Cost governance and the circuit breaker.

Two independent failure modes get controlled here, and they are different problems:

* **Spend.** A loop that calls a model once per bar on three symbols at one-minute bars
  is 4,320 calls a day. Rate, daily call count, token volume and dollar cost are each
  capped, and the *first* limit to bind stops the calls.
* **Failure.** A provider that is timing out should be asked less often, not more. After
  N consecutive failures the breaker opens and every request is refused locally until a
  cooldown elapses — which also protects against a retry storm turning one outage into a
  bill.

Refusal is never an error the caller must handle specially. A refused call means "no
context this bar", and no context means the deterministic pipeline runs unmodified. That
is the whole point of the asymmetry rule: losing the language model costs nothing except
the caution it might have added.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from tia.core.clock import Clock, ensure_utc
from tia.core.config import LLMConfig
from tia.core.logging import get_logger
from tia.llm.provider import LLMUsage

_log = get_logger("llm.governance")


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class RefusalReason(StrEnum):
    """Why a call was not made. Each is a counter worth graphing separately."""

    NONE = "none"
    DISABLED = "disabled"
    RATE_LIMIT = "rate_limit"
    DAILY_CALLS = "daily_calls"
    DAILY_INPUT_TOKENS = "daily_input_tokens"
    DAILY_OUTPUT_TOKENS = "daily_output_tokens"
    DAILY_COST = "daily_cost"
    CIRCUIT_OPEN = "circuit_open"


@dataclass
class BudgetSnapshot:
    """Everything the dashboard needs to show what the model is costing."""

    day: str = ""
    calls_today: int = 0
    input_tokens_today: int = 0
    output_tokens_today: int = 0
    cost_usd_today: float = 0.0
    calls_last_minute: int = 0
    breaker: BreakerState = BreakerState.CLOSED
    consecutive_failures: int = 0
    breaker_opened_at: datetime | None = None
    last_refusal: RefusalReason = RefusalReason.NONE

    def as_dict(self) -> dict[str, object]:
        return {
            "day": self.day,
            "calls_today": self.calls_today,
            "input_tokens_today": self.input_tokens_today,
            "output_tokens_today": self.output_tokens_today,
            "cost_usd_today": round(self.cost_usd_today, 4),
            "calls_last_minute": self.calls_last_minute,
            "breaker": self.breaker.value,
            "consecutive_failures": self.consecutive_failures,
            "last_refusal": self.last_refusal.value,
        }


@dataclass
class _Window:
    """Timestamps of recent calls, for the per-minute rate limit."""

    stamps: deque[datetime] = field(default_factory=deque)

    def prune(self, now: datetime) -> None:
        cutoff = now - timedelta(seconds=60)
        while self.stamps and self.stamps[0] < cutoff:
            self.stamps.popleft()


class LLMGovernor:
    """Decides whether a call may be made, and records what it cost.

    Deliberately stateful and deliberately not an LLM: the component that limits the
    language model's spend must not itself depend on the language model.
    """

    def __init__(self, config: LLMConfig, clock: Clock) -> None:
        self._config = config
        self._clock = clock
        self._window = _Window()
        self._snapshot = BudgetSnapshot(day=clock.now().date().isoformat())

    @property
    def config(self) -> LLMConfig:
        return self._config

    def snapshot(self) -> BudgetSnapshot:
        self._roll_day(self._clock.now())
        self._window.prune(self._clock.now())
        self._snapshot.calls_last_minute = len(self._window.stamps)
        return self._snapshot

    # ------------------------------------------------------------------ decisions

    def may_call(self, *, now: datetime | None = None) -> tuple[bool, RefusalReason]:
        """Whether a call is permitted right now, and if not, which limit bound."""
        moment = ensure_utc(now) if now else self._clock.now()
        self._roll_day(moment)
        state = self._snapshot

        if not self._config.enabled:
            return self._refuse(RefusalReason.DISABLED)

        if state.breaker is BreakerState.OPEN:
            opened = state.breaker_opened_at
            cooldown = timedelta(seconds=self._config.circuit_breaker_cooldown_seconds)
            if opened is not None and moment - opened < cooldown:
                return self._refuse(RefusalReason.CIRCUIT_OPEN)
            # One probe is allowed through; a success closes the breaker, a failure
            # re-opens it for another cooldown.
            state.breaker = BreakerState.HALF_OPEN
            _log.info("llm_breaker_half_open", cooldown_seconds=cooldown.total_seconds())

        if state.calls_today >= self._config.max_calls_per_day:
            return self._refuse(RefusalReason.DAILY_CALLS)
        if state.input_tokens_today >= self._config.max_input_tokens_per_day:
            return self._refuse(RefusalReason.DAILY_INPUT_TOKENS)
        if state.output_tokens_today >= self._config.max_output_tokens_per_day:
            return self._refuse(RefusalReason.DAILY_OUTPUT_TOKENS)
        if state.cost_usd_today >= self._config.max_cost_usd_per_day:
            return self._refuse(RefusalReason.DAILY_COST)

        self._window.prune(moment)
        if len(self._window.stamps) >= self._config.max_calls_per_minute:
            return self._refuse(RefusalReason.RATE_LIMIT)

        state.last_refusal = RefusalReason.NONE
        return (True, RefusalReason.NONE)

    def _refuse(self, reason: RefusalReason) -> tuple[bool, RefusalReason]:
        self._snapshot.last_refusal = reason
        return (False, reason)

    # ------------------------------------------------------------------ recording

    def record_success(self, usage: LLMUsage, *, now: datetime | None = None) -> None:
        moment = ensure_utc(now) if now else self._clock.now()
        self._roll_day(moment)
        state = self._snapshot

        state.calls_today += 1
        state.input_tokens_today += usage.input_tokens
        state.output_tokens_today += usage.output_tokens
        state.cost_usd_today += usage.cost_usd(self._config)
        self._window.stamps.append(moment)

        if state.breaker is not BreakerState.CLOSED:
            _log.info("llm_breaker_closed", after_failures=state.consecutive_failures)
        state.breaker = BreakerState.CLOSED
        state.consecutive_failures = 0
        state.breaker_opened_at = None

    def record_failure(self, *, now: datetime | None = None, error: str = "") -> None:
        """A failure counts against the breaker but not against the spend budget.

        A call that failed may still have cost tokens, but no provider reliably reports
        usage on failure — counting an unknown as zero understates spend, and counting it
        as a full call overstates it. Understating is the safer error here because the
        breaker stops the calls long before the difference matters.
        """
        moment = ensure_utc(now) if now else self._clock.now()
        self._roll_day(moment)
        state = self._snapshot
        state.consecutive_failures += 1

        if state.consecutive_failures >= self._config.circuit_breaker_failures:
            if state.breaker is not BreakerState.OPEN:
                _log.error(
                    "llm_breaker_opened",
                    consecutive_failures=state.consecutive_failures,
                    error=error[:300],
                )
            state.breaker = BreakerState.OPEN
            state.breaker_opened_at = moment

    def _roll_day(self, moment: datetime) -> None:
        day = moment.date().isoformat()
        if day == self._snapshot.day:
            return
        _log.info(
            "llm_budget_rolled",
            previous_day=self._snapshot.day,
            calls=self._snapshot.calls_today,
            cost_usd=round(self._snapshot.cost_usd_today, 4),
        )
        breaker = self._snapshot.breaker
        failures = self._snapshot.consecutive_failures
        opened_at = self._snapshot.breaker_opened_at
        self._snapshot = BudgetSnapshot(
            day=day,
            breaker=breaker,
            consecutive_failures=failures,
            breaker_opened_at=opened_at,
        )
        self._window.stamps.clear()


__all__ = [
    "BreakerState",
    "BudgetSnapshot",
    "LLMGovernor",
    "RefusalReason",
]
