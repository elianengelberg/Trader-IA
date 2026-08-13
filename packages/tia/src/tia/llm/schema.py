"""The structured-output contract the model must satisfy.

This is the narrowest interface the language model is given, and its narrowness is the
point. The model returns a JSON object matching :class:`ContextResponse` and nothing else:
no free text is parsed, no field is inferred from prose, and no value it can return
authorises a trade.

The pipeline is fixed and one-directional:

    Claude → structured output → schema validation → business-rule validation
           → ContextAssessment (modifier clamped to [-1, 0]) → fusion → Risk Engine

Three properties hold by construction rather than by review:

1. **The response cannot express a trade.** There is no quantity field, no price field,
   no order type, no leverage. The largest thing the model can say is "I am concerned",
   and the only mechanical effect of concern is a smaller position or none.
2. **Out-of-range values are neutralised, not trusted.** A `caution` of 999 becomes the
   maximum caution; a NaN becomes zero. Nothing out of range is passed through.
3. **Every response carries an explicit expiry.** An assessment that outlives its market
   is worse than no assessment, so the TTL is applied at construction and checked again
   at use.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tia.core.clock import ensure_utc
from tia.core.ids import deterministic_id
from tia.domain.enums import Direction, MarketRegime
from tia.domain.signals import ContextAssessment, DataQualityAnnotation, Evidence

_LEANING_TO_DIRECTION: dict[str, Direction] = {
    "long": Direction.LONG,
    "short": Direction.SHORT,
    "neutral": Direction.NO_TRADE,
}

_REGIME_VIEW: dict[str, MarketRegime] = {
    "trending_up": MarketRegime.TRENDING_UP,
    "trending_down": MarketRegime.TRENDING_DOWN,
    "ranging": MarketRegime.RANGING,
    "high_volatility": MarketRegime.HIGH_VOLATILITY,
    "low_volatility": MarketRegime.LOW_VOLATILITY,
    "crisis": MarketRegime.CRISIS,
    "unknown": MarketRegime.UNKNOWN,
}

#: Bumped whenever the prompt or this schema changes in a way that alters model
#: behaviour, so an assessment can always be traced to the exact contract that produced it.
PROMPT_VERSION = "ctx-2026.08.1"


class EvidenceItem(BaseModel):
    """One observation the model is citing.

    ``source_ref`` must name something the system actually gave the model. It is checked
    against the supplied references by the business-rule validator, because an
    unattributable claim is the shape a hallucination takes.
    """

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=3, max_length=600)
    source_ref: str = Field(default="", max_length=300)
    weight: float = Field(default=0.5, ge=0.0, le=1.0)


class ContextResponse(BaseModel):
    """Exactly what the model is allowed to return.

    ``extra="forbid"``: an unexpected key is a contract violation, not something to ignore.
    A model that invents a ``quantity`` field must fail loudly here rather than have the
    field silently dropped and the rest of the response trusted.
    """

    model_config = ConfigDict(extra="forbid")

    #: How concerned the model is, 0 (no concern) to 1 (maximum concern). Deliberately
    #: named for concern rather than conviction: there is no field for enthusiasm,
    #: because enthusiasm has no channel through which to act.
    caution: float = Field(ge=0.0, le=1.0)

    #: A hard stop. Reserved for conditions where trading is inadvisable regardless of
    #: what the deterministic strategies think.
    veto: bool = False

    #: Reported for calibration and evaluation only. The fusion layer never reads it to
    #: choose a direction — see ``tia/strategy/fusion.py``.
    leaning: Literal["long", "short", "neutral"] = "neutral"

    #: How sure the model is about its own assessment. Recorded, never amplifying.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    regime_view: Literal[
        "trending_up",
        "trending_down",
        "ranging",
        "high_volatility",
        "low_volatility",
        "crisis",
        "unknown",
    ] = "unknown"

    thesis: str = Field(min_length=1, max_length=4000)
    supporting: list[EvidenceItem] = Field(default_factory=list, max_length=12)
    contradicting: list[EvidenceItem] = Field(default_factory=list, max_length=12)
    invalidation_conditions: list[str] = Field(default_factory=list, max_length=8)
    relevant_events: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("caution", "confidence", mode="before")
    @classmethod
    def _neutralise_nonfinite(cls, v: Any) -> Any:
        """NaN and infinity become the safe end of the range rather than an exception.

        A model that emits `NaN` for caution has told us nothing; treating that as
        maximum caution would let a malformed response stop trading, and treating it as
        an error would discard an otherwise-usable assessment. Zero — no influence — is
        the honest reading.
        """
        try:
            number = float(v)
        except (TypeError, ValueError):
            return v
        if number != number or number in (float("inf"), float("-inf")):
            return 0.0
        return number

    def to_assessment(
        self,
        *,
        symbol: str,
        now: datetime,
        ttl_seconds: int,
        data_quality: DataQualityAnnotation,
        model_id: str,
        call_id: str,
        source_timestamps: tuple[datetime, ...] = (),
    ) -> ContextAssessment:
        """Convert to the domain type, applying the asymmetry rule.

        ``caution`` maps to ``context_modifier = -caution``. This is the only place the
        conversion happens, and :meth:`ContextAssessment.clamp_modifier` re-clamps it, so
        a future edit here cannot produce a positive modifier even by accident.
        """
        moment = ensure_utc(now)
        modifier = ContextAssessment.clamp_modifier(-abs(self.caution))
        return ContextAssessment(
            assessment_id=deterministic_id("ctx", symbol, call_id, moment),
            symbol=symbol,
            created_at=moment,
            expires_at=moment + timedelta(seconds=ttl_seconds),
            decision=_LEANING_TO_DIRECTION[self.leaning],
            confidence=self.confidence,
            context_modifier=modifier,
            veto=self.veto,
            thesis=self.thesis,
            supporting_evidence=tuple(
                Evidence(claim=e.claim, source_ref=e.source_ref, weight=e.weight)
                for e in self.supporting
            ),
            contradicting_evidence=tuple(
                Evidence(claim=e.claim, source_ref=e.source_ref, weight=e.weight)
                for e in self.contradicting
            ),
            market_regime=_REGIME_VIEW[self.regime_view],
            relevant_events=tuple(self.relevant_events),
            invalidation_conditions=tuple(self.invalidation_conditions),
            source_timestamps=source_timestamps,
            data_quality=data_quality,
            model_id=model_id,
            prompt_version=PROMPT_VERSION,
            llm_call_id=call_id,
        )


def response_json_schema() -> dict[str, Any]:
    """The JSON Schema handed to the model as a tool definition.

    Generated from the Pydantic model rather than written by hand, so the schema the
    model is shown and the schema the response is validated against can never drift
    apart — a drift that shows up as a model "misbehaving" when it is in fact obeying an
    older contract.
    """
    return ContextResponse.model_json_schema()


__all__ = [
    "PROMPT_VERSION",
    "ContextResponse",
    "EvidenceItem",
    "response_json_schema",
]
