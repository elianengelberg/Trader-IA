"""Market regime classification — deterministic.

The regime the risk engine and strategies act on is computed here, in code, from
features. The LLM may *describe* a regime in its narrative, and that description is
recorded for evaluation, but it never replaces this classification. A model that decides
"this is a crisis" and thereby unlocks different position sizing would be a model with
authority over risk, which is exactly what the architecture forbids.

Two axes plus two overrides:

* **Direction** — trending up / trending down / ranging, from ADX, DI spread and slope.
* **Volatility** — high / low, from the realized-volatility percentile *for this
  instrument*. An absolute volatility threshold is meaningless across assets.
* **ANOMALOUS** overrides both when the data looks structurally odd.
* **CRISIS** overrides everything when volatility is extreme *and* the move is sharply
  directional — the combination that historically precedes the worst fills.

Hysteresis is applied deliberately: a regime must be confirmed for a minimum number of
bars before it is accepted. Without it, a classifier flickers between states on noise and
every downstream component thrashes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from tia.core.clock import ensure_utc
from tia.domain.enums import MarketRegime
from tia.quant.features import FeatureSet


@dataclass(frozen=True)
class RegimeThresholds:
    """Tunable boundaries. Configuration, not learned parameters."""

    adx_trending: float = 25.0
    adx_strong: float = 40.0
    # Percent change of the fitted line across the 20-bar window. Calibrated so that
    # roughly the quietest half of synthetic bars are treated as non-directional.
    slope_flat: float = 0.20
    high_vol_percentile: float = 0.80
    low_vol_percentile: float = 0.25
    crisis_vol_percentile: float = 0.97
    crisis_abs_return_pct: float = 3.0
    anomaly_zscore: float = 4.0
    confirmation_bars: int = 3


class RegimeAssessment(BaseModel):
    """A classification plus the evidence behind it."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    regime: MarketRegime
    confidence: float = Field(ge=0.0, le=1.0)
    assessed_at: datetime
    volatility_percentile: float = Field(0.5, ge=0.0, le=1.0)
    trend_strength: float = Field(0.0, ge=0.0)
    direction_bias: float = Field(0.0, ge=-1.0, le=1.0)
    evidence: dict[str, float] = Field(default_factory=dict)
    pending_regime: MarketRegime | None = None
    bars_pending: int = 0

    @property
    def is_hostile(self) -> bool:
        return self.regime.is_hostile

    @property
    def favours_trend_following(self) -> bool:
        return self.regime in {MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN}

    @property
    def favours_mean_reversion(self) -> bool:
        return self.regime in {MarketRegime.RANGING, MarketRegime.LOW_VOLATILITY}


@dataclass
class _SymbolState:
    """Per-symbol hysteresis state."""

    current: MarketRegime = MarketRegime.UNKNOWN
    candidate: MarketRegime = MarketRegime.UNKNOWN
    candidate_count: int = 0
    history: list[MarketRegime] = field(default_factory=list)


class RegimeClassifier:
    """Classifies market regime from a feature set, with hysteresis."""

    def __init__(self, thresholds: RegimeThresholds | None = None) -> None:
        self._t = thresholds or RegimeThresholds()
        self._state: dict[str, _SymbolState] = {}

    @property
    def thresholds(self) -> RegimeThresholds:
        return self._t

    def current_regime(self, symbol: str) -> MarketRegime:
        return self._state.get(symbol, _SymbolState()).current

    def reset(self, symbol: str | None = None) -> None:
        if symbol is None:
            self._state.clear()
        else:
            self._state.pop(symbol, None)

    def classify(self, features: FeatureSet, *, now: datetime) -> RegimeAssessment:
        now = ensure_utc(now, field="now")
        symbol = features.symbol
        state = self._state.setdefault(symbol, _SymbolState())

        adx = features.get("adx_14")
        di_spread = features.get("di_spread")
        slope = features.get("trend_slope_20")
        vol_pct = features.get("vol_percentile_100")
        zscore = features.get("zscore_20")
        return_1 = features.get("return_1")
        bb_width = features.get("bb_width_pct")

        evidence = {
            "adx_14": adx,
            "di_spread": di_spread,
            "trend_slope_20": slope,
            "vol_percentile_100": vol_pct,
            "zscore_20": zscore,
            "return_1_pct": return_1,
            "bb_width_pct": bb_width,
        }
        evidence = {k: v for k, v in evidence.items() if math.isfinite(v)}

        # Not enough information to classify is a legitimate answer, and a far better one
        # than a confident guess from three bars of history.
        if not features.complete or not math.isfinite(adx) or not math.isfinite(vol_pct):
            return RegimeAssessment(
                symbol=symbol,
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                assessed_at=now,
                evidence=evidence,
            )

        raw, raw_confidence = self._raw_classification(
            adx=adx,
            di_spread=di_spread,
            slope=slope,
            vol_pct=vol_pct,
            zscore=zscore,
            return_1=return_1,
        )

        confirmed = self._apply_hysteresis(state, raw)

        direction_bias = 0.0
        if math.isfinite(di_spread):
            direction_bias = max(-1.0, min(1.0, di_spread / 50.0))

        return RegimeAssessment(
            symbol=symbol,
            regime=confirmed,
            confidence=raw_confidence if confirmed == raw else raw_confidence * 0.6,
            assessed_at=now,
            volatility_percentile=vol_pct if math.isfinite(vol_pct) else 0.5,
            trend_strength=adx if math.isfinite(adx) else 0.0,
            direction_bias=direction_bias,
            evidence=evidence,
            pending_regime=state.candidate if state.candidate != confirmed else None,
            bars_pending=state.candidate_count if state.candidate != confirmed else 0,
        )

    def _raw_classification(
        self,
        *,
        adx: float,
        di_spread: float,
        slope: float,
        vol_pct: float,
        zscore: float,
        return_1: float,
    ) -> tuple[MarketRegime, float]:
        t = self._t

        # CRISIS: extreme volatility *and* a sharp directional move. Extreme volatility
        # alone is a high-volatility regime, which is tradable with smaller size; the
        # combination is what produces gaps, halts and terrible fills.
        if (
            vol_pct >= t.crisis_vol_percentile
            and math.isfinite(return_1)
            and abs(return_1) >= t.crisis_abs_return_pct
        ):
            return MarketRegime.CRISIS, 0.9

        # ANOMALOUS: the price is far outside its own recent distribution. Not
        # necessarily wrong data — the quality engine handles that — but a state in
        # which historical relationships should not be assumed to hold.
        if math.isfinite(zscore) and abs(zscore) >= t.anomaly_zscore:
            return MarketRegime.ANOMALOUS, 0.75

        trending = adx >= t.adx_trending
        directional = math.isfinite(slope) and abs(slope) >= t.slope_flat

        if trending and directional:
            up = slope > 0 if math.isfinite(slope) else di_spread > 0
            # Confidence scales with how far past the threshold ADX sits, saturating at
            # the "strong trend" level.
            span = max(t.adx_strong - t.adx_trending, 1e-9)
            confidence = 0.55 + 0.4 * min(1.0, (adx - t.adx_trending) / span)
            return (MarketRegime.TRENDING_UP if up else MarketRegime.TRENDING_DOWN), confidence

        if vol_pct >= t.high_vol_percentile:
            return MarketRegime.HIGH_VOLATILITY, 0.6 + 0.3 * (vol_pct - t.high_vol_percentile) / max(
                1.0 - t.high_vol_percentile, 1e-9
            )

        if vol_pct <= t.low_vol_percentile:
            return MarketRegime.LOW_VOLATILITY, 0.6

        return MarketRegime.RANGING, 0.5 + 0.3 * (1.0 - min(1.0, adx / max(t.adx_trending, 1e-9)))

    def _apply_hysteresis(self, state: _SymbolState, raw: MarketRegime) -> MarketRegime:
        """Require ``confirmation_bars`` consecutive observations before switching.

        Hostile regimes are the exception: they are adopted immediately. Waiting three
        bars to acknowledge a crisis in order to avoid flicker is the wrong trade — the
        cost of a false crisis call is a few skipped trades, and the cost of a late one
        is the trades you should have skipped.
        """
        if raw == state.current:
            state.candidate = raw
            state.candidate_count = 0
            return state.current

        if raw.is_hostile:
            state.current = raw
            state.candidate = raw
            state.candidate_count = 0
            state.history.append(raw)
            return raw

        if raw == state.candidate:
            state.candidate_count += 1
        else:
            state.candidate = raw
            state.candidate_count = 1

        if state.candidate_count >= self._t.confirmation_bars:
            state.current = raw
            state.candidate_count = 0
            state.history.append(raw)

        return state.current


__all__ = ["RegimeAssessment", "RegimeClassifier", "RegimeThresholds"]
