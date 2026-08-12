"""Risk decision contracts.

Every risk decision records *every* check it ran, not only the one that failed. That is
what makes a rejection auditable months later ("which limit was binding, and by how
much?") and what lets the dashboard show why a trade did not happen.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tia.core.clock import ensure_utc
from tia.domain.enums import RiskVerdict


class RiskCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    passed: bool
    observed: float | None = None
    limit: float | None = None
    action: str = ""
    detail: str = ""

    def describe(self) -> str:
        if self.passed:
            return f"{self.name}: ok"
        obs = f"{self.observed:.6g}" if self.observed is not None else "?"
        lim = f"{self.limit:.6g}" if self.limit is not None else "?"
        suffix = f" -> {self.action}" if self.action else ""
        return f"{self.name}: {obs} vs limit {lim}{suffix}"


class PositionSizing(BaseModel):
    """How the approved quantity was derived. Recorded so sizing is reproducible."""

    model_config = ConfigDict(frozen=True)

    method: str = "atr_risk_budget"
    equity: float
    risk_budget_currency: float
    stop_distance: float
    raw_quantity: float
    quantity_after_limits: float
    notional: float
    limiting_constraint: str = ""


class RiskDecision(BaseModel):
    """The deterministic gate. Nothing downstream may override it."""

    model_config = ConfigDict(frozen=True)

    decision_id: str
    signal_id: str
    symbol: str
    verdict: RiskVerdict
    approved_quantity: float = Field(0.0, ge=0.0)
    requested_quantity: float = Field(0.0, ge=0.0)
    decided_at: datetime
    checks: tuple[RiskCheck, ...] = ()
    sizing: PositionSizing | None = None
    reasons: tuple[str, ...] = ()
    stop_price: float | None = None
    target_price: float | None = None
    correlation_id: str = ""

    @field_validator("decided_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="decided_at")

    @model_validator(mode="after")
    def _coherent(self) -> RiskDecision:
        if self.verdict.allows_execution and self.approved_quantity <= 0:
            raise ValueError(f"verdict {self.verdict} requires a positive approved_quantity")
        if not self.verdict.allows_execution and self.approved_quantity != 0:
            raise ValueError(f"verdict {self.verdict} must approve zero quantity")
        if self.approved_quantity > self.requested_quantity + 1e-9:
            # The engine may only shrink. An engine that could grow a request would be a
            # second, unreviewed sizing model.
            raise ValueError("risk engine may never approve more than was requested")
        return self

    @property
    def allows_execution(self) -> bool:
        return self.verdict.allows_execution

    def failed_checks(self) -> tuple[RiskCheck, ...]:
        return tuple(c for c in self.checks if not c.passed)

    def primary_reason(self) -> str:
        if self.reasons:
            return self.reasons[0]
        failed = self.failed_checks()
        return failed[0].describe() if failed else "approved"


__all__ = ["PositionSizing", "RiskCheck", "RiskDecision"]
