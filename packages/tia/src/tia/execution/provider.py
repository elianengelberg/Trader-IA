"""Execution provider interface.

One contract, two kinds of implementation, and a gate between them.

Simulated providers — the paper matching engine and the backtest engine — are constructible
by anyone, at any time, with no ceremony. They spend nothing.

A provider that reaches a real venue is different in exactly one way that matters: it can
lose the user's money. So it cannot be constructed by declaring itself live. It requires a
:class:`~tia.live.gate.LiveActivationToken`, which only
:meth:`~tia.live.gate.LiveActivationGate.arm` can mint, and only when every check in
:data:`~tia.live.gate.REQUIRED_CHECKS` has passed within that same call.

This replaced an earlier, blunter rule — the base constructor used to refuse *any*
non-simulated provider outright, which was correct while the platform was research-only.
The property that mattered about that rule is preserved: **there is no code path that
produces a live provider by accident**. What changed is that the deliberate path now
exists, is auditable, and expires. ``tests/unit/test_scope_boundary.py`` asserts the
replacement rather than the original.

The token is re-checked on every order rather than once at construction — see
:meth:`ExecutionProvider.assert_may_trade` — because a provider built an hour ago holds a
token that may since have expired or been voided by a configuration change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from tia.core.errors import LiveActivationError
from tia.domain.orders import Fill, Order, OrderIntent
from tia.domain.portfolio import PortfolioState, Position

if TYPE_CHECKING:  # pragma: no cover - typing only
    from tia.core.clock import Clock
    from tia.live.gate import LiveActivationToken

#: Sentinel limit meaning "every trade" for :meth:`ExecutionProvider.state_snapshot`.
#: A reconciliation that silently compared a truncated trade list would report a
#: fill-count divergence on every run once the history exceeded the page size.
_ALL_TRADES = 2**62


class ExecutionCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    is_simulated: bool = True
    supports_limit_orders: bool = True
    supports_stop_orders: bool = True
    supports_partial_fills: bool = True
    supports_cancellation: bool = True
    models_slippage: bool = True
    models_fees: bool = True
    models_latency: bool = True
    notes: str = ""


class ExecutionProvider(ABC):
    """Submit, cancel and query orders — simulated by default, live only through the gate."""

    def __init__(
        self,
        capabilities: ExecutionCapabilities,
        *,
        activation: LiveActivationToken | None = None,
        clock: Clock | None = None,
    ) -> None:
        if not capabilities.is_simulated:
            if activation is None:
                raise LiveActivationError(
                    f"{capabilities.name!r} declares itself non-simulated, so it may only be "
                    "constructed with a LiveActivationToken from LiveActivationGate.arm(). "
                    "There is no flag, setting or environment variable that substitutes for "
                    "one: the gate has to actually pass."
                )
            if clock is None:
                raise LiveActivationError(
                    "a live execution provider requires a Clock, because its activation "
                    "expires and something has to be able to tell that it has"
                )
            activation.assert_usable(now=clock.now())

        self._capabilities = capabilities
        self._activation = activation
        self._clock = clock

    @property
    def capabilities(self) -> ExecutionCapabilities:
        return self._capabilities

    @property
    def name(self) -> str:
        return self._capabilities.name

    @property
    def is_live(self) -> bool:
        """True when this provider reaches a venue that holds real money."""
        return not self._capabilities.is_simulated

    @property
    def activation(self) -> LiveActivationToken | None:
        return self._activation

    def assert_may_trade(self, *, fingerprint: str | None = None) -> None:
        """Gate every live order. A no-op for simulators.

        Called immediately before submission rather than at construction, so an expired
        activation stops the *next* order instead of being noticed at the next restart.
        Passing ``fingerprint`` also voids the token if risk limits or the capital policy
        have changed since it was issued.
        """
        if self._capabilities.is_simulated:
            return
        if self._activation is None or self._clock is None:  # pragma: no cover - guarded above
            raise LiveActivationError("live provider lost its activation; refusing to trade")
        self._activation.assert_usable(now=self._clock.now(), fingerprint=fingerprint)

    @abstractmethod
    async def submit_order(self, intent: OrderIntent) -> Order:
        """Submit an intent. Idempotent on ``client_order_id``.

        A second submission of the same ``client_order_id`` must return the *existing*
        order rather than creating a second one — that is what makes a retry safe.
        """

    @abstractmethod
    async def cancel_order(self, order_id: str) -> Order: ...

    @abstractmethod
    async def get_order(self, order_id: str) -> Order | None: ...

    @abstractmethod
    async def get_orders(self, *, open_only: bool = False) -> list[Order]: ...

    @abstractmethod
    async def get_positions(self) -> dict[str, Position]: ...

    @abstractmethod
    async def get_balance(self) -> float: ...

    @abstractmethod
    async def get_trades(self, *, limit: int = 100) -> list[Fill]: ...

    @abstractmethod
    async def get_pnl(self) -> dict[str, float]: ...

    @abstractmethod
    async def get_portfolio(self) -> PortfolioState: ...

    async def state_snapshot(self) -> dict[str, Any]:
        """The provider's own picture of the account, for reconciliation.

        Built from the public query methods rather than from an implementation's
        internals, so a provider whose snapshot disagrees with its own API is itself
        caught by the comparison. Implementations may override this only to make it
        cheaper, never to make it disagree.
        """
        orders = await self.get_orders()
        positions = await self.get_positions()
        balance = await self.get_balance()
        trades = await self.get_trades(limit=_ALL_TRADES)
        return {
            "orders": {o.order_id: o.state.value for o in orders},
            "positions": {s: p.quantity for s, p in positions.items() if not p.is_flat},
            "balance": balance,
            "fill_count": len(trades),
        }

    async def close(self) -> None:  # pragma: no cover - default no-op
        return None


__all__ = ["ExecutionCapabilities", "ExecutionProvider"]
