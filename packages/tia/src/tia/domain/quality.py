"""Data quality contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tia.core.clock import ensure_utc
from tia.domain.enums import DataQualityFlag


class QualityCheck(BaseModel):
    """One executed check, recorded whether it passed or not.

    Failures are useless without the observed value: "spread anomaly" is not actionable,
    "spread 84 bps against a 25 bps limit" is.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    passed: bool
    hard_fail: bool = False
    flag: DataQualityFlag | None = None
    observed: float | None = None
    limit: float | None = None
    detail: str = ""

    def describe(self) -> str:
        if self.passed:
            return f"{self.name}: ok"
        parts = [f"{self.name}: FAILED"]
        if self.observed is not None:
            parts.append(f"observed={self.observed:.6g}")
        if self.limit is not None:
            parts.append(f"limit={self.limit:.6g}")
        if self.detail:
            parts.append(self.detail)
        return " ".join(parts)


class DataQualityReport(BaseModel):
    """Verdict on one bar (or one symbol's current view).

    Two scores rather than one, because they fail for different reasons and demand
    different responses: bad *quality* means the data is wrong, bad *freshness* means the
    data is late. Both gate trading; only the second is fixed by waiting.
    """

    model_config = ConfigDict(frozen=True)

    report_id: str
    symbol: str
    timeframe: str
    evaluated_at: datetime
    quality_score: float = Field(ge=0.0, le=1.0)
    freshness_score: float = Field(ge=0.0, le=1.0)
    hard_fail: bool = False
    flags: tuple[DataQualityFlag, ...] = ()
    checks: tuple[QualityCheck, ...] = ()
    bars_evaluated: int = 0

    @field_validator("evaluated_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="evaluated_at")

    @property
    def composite_score(self) -> float:
        """Weighted toward quality: stale-but-correct data is less dangerous than fresh-but-wrong."""
        return 0.65 * self.quality_score + 0.35 * self.freshness_score

    def is_tradable(self, min_quality: float, min_freshness: float) -> bool:
        return (
            not self.hard_fail
            and self.quality_score >= min_quality
            and self.freshness_score >= min_freshness
        )

    def failed_checks(self) -> tuple[QualityCheck, ...]:
        return tuple(c for c in self.checks if not c.passed)

    def reason(self) -> str:
        failures = self.failed_checks()
        if not failures:
            return "ok"
        return "; ".join(c.describe() for c in failures[:5])


__all__ = ["DataQualityReport", "QualityCheck"]
