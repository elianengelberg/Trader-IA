"""Signals, agent findings and the LLM context contract.

The single most important type here is :class:`ContextAssessment`. Its
``context_modifier`` is clamped to ``[-1, 0]`` on construction, which is the mechanical
enforcement of the asymmetry rule: **the language model can only reduce risk-taking.**
A hallucination, a poisoned news article, or a prompt injection can therefore cost us
trades we would have taken — never a trade we would not have taken, and never a larger one.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tia.core.clock import ensure_utc
from tia.domain.enums import AgentKind, Direction, FindingSource, MarketRegime


class Evidence(BaseModel):
    """One citable observation supporting or contradicting a thesis."""

    model_config = ConfigDict(frozen=True)

    claim: str = Field(min_length=1, max_length=600)
    source_ref: str = Field(default="", max_length=300)
    observed_at: datetime | None = None
    weight: float = Field(0.5, ge=0.0, le=1.0)

    @field_validator("observed_at")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        return ensure_utc(v, field="observed_at") if v is not None else None


class AgentFinding(BaseModel):
    """Output of one agent.

    ``score`` is a signed conviction in ``[-1, 1]``: positive is bullish, negative is
    bearish, zero is neutral. ``confidence`` is how sure the agent is *about its own
    score*, which is a different question and kept separate on purpose.
    """

    model_config = ConfigDict(frozen=True)

    agent: AgentKind
    source: FindingSource
    symbol: str
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(default="", max_length=2000)
    supporting: tuple[Evidence, ...] = ()
    contradicting: tuple[Evidence, ...] = ()
    metrics: dict[str, float] = Field(default_factory=dict)
    produced_at: datetime

    @field_validator("produced_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="produced_at")

    @property
    def direction(self) -> Direction:
        if self.score > 0.05:
            return Direction.LONG
        if self.score < -0.05:
            return Direction.SHORT
        return Direction.HOLD


class StrategyOpinion(BaseModel):
    """One strategy's view, before fusion."""

    model_config = ConfigDict(frozen=True)

    strategy_id: str
    strategy_version: str
    symbol: str
    direction: Direction
    strength: float = Field(ge=0.0, le=1.0)
    entry_reference: float = Field(gt=0)
    stop_reference: float | None = None
    target_reference: float | None = None
    evidence: tuple[Evidence, ...] = ()
    invalidation_conditions: tuple[str, ...] = ()
    metrics: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _stop_on_correct_side(self) -> StrategyOpinion:
        if self.stop_reference is None or not self.direction.is_actionable:
            return self
        if self.direction is Direction.LONG and self.stop_reference >= self.entry_reference:
            raise ValueError("long stop must sit below the entry reference")
        if self.direction is Direction.SHORT and self.stop_reference <= self.entry_reference:
            raise ValueError("short stop must sit above the entry reference")
        return self


class DataQualityAnnotation(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: float = Field(ge=0.0, le=1.0)
    freshness: float = Field(ge=0.0, le=1.0)
    notes: str = Field(default="", max_length=1000)


class ContextAssessment(BaseModel):
    """The LLM's contribution — advisory, expiring, and strictly non-amplifying.

    ``decision`` is recorded for evaluation and calibration only. The fusion layer reads
    ``context_modifier`` and ``veto``; it never reads ``decision`` to choose a direction.
    """

    model_config = ConfigDict(frozen=True)

    assessment_id: str
    symbol: str
    created_at: datetime
    expires_at: datetime

    decision: Direction = Direction.NO_TRADE
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    context_modifier: float = Field(0.0, le=0.0, ge=-1.0)
    veto: bool = False

    thesis: str = Field(default="", max_length=4000)
    supporting_evidence: tuple[Evidence, ...] = ()
    contradicting_evidence: tuple[Evidence, ...] = ()
    market_regime: MarketRegime = MarketRegime.UNKNOWN
    relevant_events: tuple[str, ...] = ()
    invalidation_conditions: tuple[str, ...] = ()
    source_timestamps: tuple[datetime, ...] = ()
    data_quality: DataQualityAnnotation

    strategy_id: str = ""
    model_id: str = ""
    prompt_version: str = ""
    llm_call_id: str = ""

    @field_validator("created_at", "expires_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="assessment time")

    @model_validator(mode="after")
    def _validity(self) -> ContextAssessment:
        if self.expires_at <= self.created_at:
            raise ValueError("assessment expires_at must be after created_at")
        return self

    def is_valid_at(self, moment: datetime) -> bool:
        return ensure_utc(moment) < self.expires_at

    @staticmethod
    def clamp_modifier(raw: float) -> float:
        """Clamp any model-supplied modifier into the veto/dampen channel.

        Applied at the boundary so that an out-of-range value from the model is
        neutralised rather than rejected — a model that returns ``+0.9`` gets ``0.0``
        (no effect), not an exception that would fail the whole assessment.
        """
        if raw != raw:  # NaN
            return 0.0
        return max(-1.0, min(0.0, float(raw)))

    @classmethod
    def neutral(
        cls, *, symbol: str, now: datetime, ttl_seconds: int = 900, reason: str = "unavailable"
    ) -> ContextAssessment:
        """The assessment used when the slow loop has nothing to say.

        Neutral means *no influence*: modifier 0, no veto. The fast loop is unaffected.
        """
        now = ensure_utc(now)
        return cls(
            assessment_id=f"ctx_neutral_{int(now.timestamp())}",
            symbol=symbol,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            context_modifier=0.0,
            veto=False,
            thesis=f"No LLM context available ({reason}); proceeding on deterministic signals only.",
            data_quality=DataQualityAnnotation(score=1.0, freshness=1.0, notes=reason),
        )


class SignalCandidate(BaseModel):
    """A proposal. Never an instruction.

    A candidate becomes an order intent only after the Risk Engine approves it, and only
    while it is unexpired. ``snapshot_id`` ties it to exactly the market view that
    produced it, so the decision can be replayed.
    """

    model_config = ConfigDict(frozen=True)

    signal_id: str
    symbol: str
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    base_confidence: float = Field(ge=0.0, le=1.0)

    created_at: datetime
    expires_at: datetime
    market_snapshot_id: str

    entry_reference: float = Field(gt=0)
    stop_reference: float | None = None
    target_reference: float | None = None

    strategy_id: str
    strategy_version: str
    model_version: str = ""
    prompt_version: str = ""
    feature_version: str = ""

    regime: MarketRegime = MarketRegime.UNKNOWN
    data_quality_score: float = Field(1.0, ge=0.0, le=1.0)
    data_freshness_score: float = Field(1.0, ge=0.0, le=1.0)

    opinions: tuple[StrategyOpinion, ...] = ()
    findings: tuple[AgentFinding, ...] = ()
    context_assessment_id: str | None = None
    context_modifier_applied: float = 0.0

    why_enter: tuple[str, ...] = ()
    why_not_enter: tuple[str, ...] = ()
    supporting_factors: tuple[Evidence, ...] = ()
    contradicting_factors: tuple[Evidence, ...] = ()
    invalidation_conditions: tuple[str, ...] = ()

    correlation_id: str = ""

    @field_validator("created_at", "expires_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="signal time")

    @model_validator(mode="after")
    def _coherent(self) -> SignalCandidate:
        if self.expires_at <= self.created_at:
            raise ValueError("signal expires_at must be after created_at")
        if self.confidence > self.base_confidence + 1e-9:
            # Defence in depth: even if fusion had a bug, an amplified signal cannot exist.
            raise ValueError(
                "final confidence exceeds base confidence; context may only dampen, never amplify"
            )
        return self

    def is_expired_at(self, moment: datetime) -> bool:
        return ensure_utc(moment) >= self.expires_at

    @property
    def is_actionable(self) -> bool:
        return self.direction.is_actionable

    def ttl_seconds(self) -> float:
        return (self.expires_at - self.created_at).total_seconds()


__all__ = [
    "AgentFinding",
    "ContextAssessment",
    "DataQualityAnnotation",
    "Evidence",
    "SignalCandidate",
    "StrategyOpinion",
]
