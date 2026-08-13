"""Execution provider interface.

The abstraction that would, in principle, let a different execution venue be plugged in.
**Every implementation in this repository is a simulator**, and the scope rule forbids
adding one that is not — see ``docs/ARCHITECTURE.md`` §1. The interface exists so the
rest of the system is written against a contract rather than against a simulator's
internals, not as a staging post for going live.

``ExecutionCapabilities.is_simulated`` is asserted to be ``True`` for every registered
provider by ``tests/unit/test_scope_boundary.py``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict

from tia.domain.orders import Fill, Order, OrderIntent
from tia.domain.portfolio import PortfolioState, Position

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
    """Submit, cancel and query simulated orders."""

    def __init__(self, capabilities: ExecutionCapabilities) -> None:
        if not capabilities.is_simulated:
            # Structural enforcement of the scope rule: a provider claiming to be real
            # cannot be constructed at all.
            raise ValueError(
                "this platform is simulation-only; a non-simulated execution provider "
                "may not be constructed"
            )
        self._capabilities = capabilities

    @property
    def capabilities(self) -> ExecutionCapabilities:
        return self._capabilities

    @property
    def name(self) -> str:
        return self._capabilities.name

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
