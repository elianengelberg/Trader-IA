"""The context service — the whole slow loop, in one place.

Prompt → provider → schema validation → business-rule validation → clamped assessment.

Every failure along that chain converges on the same outcome: a **neutral assessment**,
which has zero modifier and no veto and therefore no effect on anything. The deterministic
pipeline neither knows nor cares whether the language model answered. That is what makes
the model safe to depend on: nothing depends on it.

The prompt builder is here too, and it is deliberately mechanical. It emits a
machine-readable JSON block plus a short human-readable framing, and it emits **only**
market state — no credentials, no configuration, no account identifiers, no keys. There is
no code path from a secret to a prompt, and a test asserts it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from tia.core.clock import Clock, ensure_utc
from tia.core.config import LLMConfig
from tia.core.errors import LLMError, LLMSchemaError, LLMUnavailableError
from tia.core.logging import get_logger
from tia.domain.market import MacroEvent, NewsItem
from tia.domain.quality import DataQualityReport
from tia.domain.signals import ContextAssessment, DataQualityAnnotation
from tia.llm.governance import LLMGovernor, RefusalReason
from tia.llm.provider import LLMProvider, LLMUsage, call_id_for
from tia.llm.schema import PROMPT_VERSION
from tia.llm.validation import validate_response
from tia.quant.features import FeatureSet
from tia.regime.classifier import RegimeAssessment

_log = get_logger("llm.context")

#: Features handed to the model. A short, fixed list rather than the whole feature set:
#: a prompt that grows with every new feature becomes expensive and unstable, and most
#: features are not the kind of thing a language model can usefully reason about.
PROMPT_FEATURES = (
    "atr_pct",
    "vol_percentile_100",
    "rsi_14",
    "adx_14",
    "return_1",
    "return_20",
    "ema_fast_above_slow",
    "bb_width_pct",
    "channel_position",
    "volume_zscore",
)


@dataclass
class ContextRequest:
    """Everything the slow loop is allowed to see."""

    symbol: str
    features: FeatureSet
    regime: RegimeAssessment
    quality: DataQualityReport | None = None
    news: tuple[NewsItem, ...] = ()
    macro: tuple[MacroEvent, ...] = ()
    equity: float = 0.0
    drawdown_pct: float = 0.0
    spread_bps: float = 0.0
    open_position_qty: float = 0.0


@dataclass
class ContextOutcome:
    """The assessment plus how it was reached. The dashboard shows both."""

    assessment: ContextAssessment
    used: bool
    reason: str = ""
    usage: LLMUsage | None = None
    refusal: RefusalReason = RefusalReason.NONE
    warnings: tuple[str, ...] = field(default=())
    prompt_chars: int = 0

    @property
    def is_neutral(self) -> bool:
        return self.assessment.context_modifier == 0.0 and not self.assessment.veto


class ContextService:
    """Produces a `ContextAssessment` for a market state, or a neutral one."""

    def __init__(
        self,
        provider: LLMProvider,
        governor: LLMGovernor,
        clock: Clock,
        config: LLMConfig,
        *,
        known_symbols: frozenset[str],
    ) -> None:
        self._provider = provider
        self._governor = governor
        self._clock = clock
        self._config = config
        self._known_symbols = known_symbols
        self.assessments = 0
        self.neutral_assessments = 0
        self.rejections = 0

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @property
    def governor(self) -> LLMGovernor:
        return self._governor

    async def assess(self, request: ContextRequest) -> ContextOutcome:
        """Run the slow loop once. Never raises."""
        now = self._clock.now()
        ttl = self._config.assessment_ttl_seconds

        allowed, refusal = self._governor.may_call(now=now)
        if not allowed:
            return self._neutral(request.symbol, now, ttl, refusal.value, refusal=refusal)

        prompt, source_refs, stamps = build_prompt(request, now=now)
        call_id = call_id_for(request.symbol, now)

        try:
            result = await self._provider.assess(prompt, call_id=call_id)
        except LLMUnavailableError as exc:
            self._governor.record_failure(now=now, error=str(exc))
            return self._neutral(
                request.symbol, now, ttl, f"provider unavailable: {exc.message}"
            )
        except LLMSchemaError as exc:
            # A schema violation is a failure of the model, not of the network, but it
            # counts against the breaker for the same reason: a model that cannot satisfy
            # its contract should be called less, not more.
            self._governor.record_failure(now=now, error=str(exc))
            self.rejections += 1
            return self._neutral(
                request.symbol, now, ttl, f"schema violation: {exc.message}"
            )
        except LLMError as exc:
            self._governor.record_failure(now=now, error=str(exc))
            return self._neutral(request.symbol, now, ttl, f"llm error: {exc.message}")
        except Exception as exc:
            # The last-resort catch, and it earns its place: a provider raising something
            # this module does not know about — a pydantic ValidationError, a bug in a
            # third-party SDK — must not reach the trading loop. The docstring promises
            # this method never raises, and a promise that holds only for anticipated
            # exceptions is not one.
            _log.exception("llm_provider_raised_unexpectedly", symbol=request.symbol)
            self._governor.record_failure(now=now, error=str(exc))
            return self._neutral(
                request.symbol, now, ttl, f"provider raised {type(exc).__name__}"
            )

        self._governor.record_success(result.usage, now=now)

        verdict = validate_response(
            result.response,
            symbol=request.symbol,
            known_symbols=self._known_symbols,
            allowed_source_refs=source_refs,
            now=now,
            input_timestamps=stamps,
        )
        if not verdict.ok:
            self.rejections += 1
            return self._neutral(
                request.symbol, now, ttl, verdict.reason, usage=result.usage
            )

        quality = request.quality
        assessment = result.response.to_assessment(
            symbol=request.symbol,
            now=now,
            ttl_seconds=ttl,
            data_quality=DataQualityAnnotation(
                score=quality.quality_score if quality else 1.0,
                freshness=quality.freshness_score if quality else 1.0,
                notes="" if quality else "no quality report supplied",
            ),
            model_id=result.usage.model or self._provider.name,
            call_id=call_id,
            source_timestamps=stamps,
        )
        self.assessments += 1

        # Belt and braces: the domain type clamps on construction, but assert the
        # invariant here too so a future refactor of either side cannot break it silently.
        if assessment.context_modifier > 0.0:  # pragma: no cover - unreachable by design
            raise LLMError(
                "context modifier escaped the veto/dampen channel",
                modifier=assessment.context_modifier,
            )

        return ContextOutcome(
            assessment=assessment,
            used=True,
            usage=result.usage,
            warnings=verdict.warnings,
            prompt_chars=len(prompt),
        )

    def _neutral(
        self,
        symbol: str,
        now: datetime,
        ttl: int,
        reason: str,
        *,
        usage: LLMUsage | None = None,
        refusal: RefusalReason = RefusalReason.NONE,
    ) -> ContextOutcome:
        self.neutral_assessments += 1
        return ContextOutcome(
            assessment=ContextAssessment.neutral(
                symbol=symbol, now=now, ttl_seconds=ttl, reason=reason
            ),
            used=False,
            reason=reason,
            usage=usage,
            refusal=refusal,
        )


def build_prompt(
    request: ContextRequest, *, now: datetime
) -> tuple[str, frozenset[str], tuple[datetime, ...]]:
    """Build the prompt and the set of references the model is allowed to cite.

    Returns ``(prompt, allowed_source_refs, input_timestamps)``. The reference set is
    produced *here*, from the same data that goes into the prompt, so the attribution
    check downstream compares against exactly what the model was shown.

    Contains only market state. No API key, no database URL, no account identifier, no
    configuration value, and no secret of any kind is reachable from this function — it
    receives a :class:`ContextRequest` and nothing else.
    """
    moment = ensure_utc(now)
    features = request.features
    quality = request.quality

    payload: dict[str, Any] = {
        "symbol": request.symbol,
        "as_of": moment.isoformat(),
        "bar_close_time": features.bar_close_time.isoformat(),
        "timeframe": features.timeframe,
        "regime_view": request.regime.regime.value,
        "regime_confidence": round(request.regime.confidence, 4),
        "data_quality": round(quality.quality_score, 4) if quality else 1.0,
        "data_freshness": round(quality.freshness_score, 4) if quality else 1.0,
        "drawdown_pct": round(request.drawdown_pct, 4),
        "spread_bps": round(request.spread_bps, 4),
        "open_position_qty": round(request.open_position_qty, 8),
        "features": {
            name: round(features.get(name), 6)
            for name in PROMPT_FEATURES
            if features.get(name) == features.get(name)  # drop NaN
        },
    }
    payload["vol_percentile"] = payload["features"].get("vol_percentile_100", 0.0)
    payload["trend_score"] = _trend_score(features)

    refs: set[str] = set()
    stamps: list[datetime] = [features.bar_close_time]

    if request.news:
        payload["news"] = []
        for item in request.news[:10]:
            ref = f"news:{item.news_id}"
            refs.add(ref)
            stamps.append(item.published_at)
            payload["news"].append(
                {
                    "ref": ref,
                    "headline": item.headline,
                    "source": item.source,
                    "published_at": item.published_at.isoformat(),
                    "symbols": list(item.symbols),
                }
            )

    if request.macro:
        payload["macro"] = []
        for event in request.macro[:10]:
            ref = f"macro:{event.macro_id}"
            refs.add(ref)
            stamps.append(event.released_at)
            payload["macro"].append(
                {
                    "ref": ref,
                    "indicator": event.indicator,
                    "region": event.region,
                    "released_at": event.released_at.isoformat(),
                    "actual": event.actual,
                    "consensus": event.consensus,
                    "surprise": event.surprise,
                }
            )

    ref = f"bar:{request.symbol}:{features.bar_close_time.isoformat()}"
    refs.add(ref)
    payload["market_ref"] = ref

    if quality is not None:
        qref = f"quality:{request.symbol}"
        refs.add(qref)
        payload["quality_ref"] = qref
        payload["quality_flags"] = [flag.value for flag in quality.flags]

    prompt = (
        f"Assess the market context for {request.symbol} as of {moment.isoformat()}.\n\n"
        "The deterministic strategies have already formed a view. Your assessment can "
        "only reduce or veto the resulting position; it cannot create or enlarge one.\n\n"
        "Cite only the references listed below. Available references: "
        + ", ".join(sorted(refs))
        + "\n\n```json\n"
        + json.dumps(payload, indent=2, sort_keys=True, default=str)
        + "\n```\n\n"
        f"Respond by calling the assessment tool. Contract version {PROMPT_VERSION}."
    )
    return (prompt, frozenset(refs), tuple(stamps))


def _trend_score(features: FeatureSet) -> float:
    """A single signed number summarising trend, for the mock provider's leaning.

    Not used by the real provider — Claude gets the underlying features and forms its own
    view — but the mock needs something to vary with, and deriving it from the same
    features keeps the two providers driven by identical information.
    """
    above = features.get("ema_fast_above_slow", 0.0)
    momentum = features.get("return_20", 0.0)
    if above != above or momentum != momentum:
        return 0.0
    return max(-1.0, min(1.0, (above - 0.5) * 2.0 * 0.5 + max(-1.0, min(1.0, momentum / 5.0)) * 0.5))


__all__ = [
    "PROMPT_FEATURES",
    "ContextOutcome",
    "ContextRequest",
    "ContextService",
    "build_prompt",
]
