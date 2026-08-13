"""The strategy library.

Three deliberately simple, well-understood strategies. Simplicity is the point: the
platform's purpose is to *measure* whether a decision process has an edge, and a
strategy nobody can reason about produces a result nobody can interpret. Each one also
covers a different regime, so the fusion layer has something to actually arbitrate.

A rule shared by all of them: **no strategy acts on a single indicator.** Each requires
at least two independent confirmations before proposing a direction. One indicator
crossing a threshold is noise roughly as often as it is signal.
"""

from __future__ import annotations

import math

from tia.domain.enums import Direction, MarketRegime
from tia.domain.signals import Evidence, StrategyOpinion
from tia.quant.features import FeatureSet
from tia.regime.classifier import RegimeAssessment
from tia.strategy.base import Strategy


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


class TrendFollowingStrategy(Strategy):
    """EMA structure + ADX + DI agreement, with an ATR-based stop.

    Requires three confirmations: the fast EMA on the correct side of the slow, ADX above
    the trending threshold, and the directional index agreeing with the EMA structure.
    """

    strategy_id = "trend_following"
    version = "1.1.0"
    preferred_regimes = frozenset({MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN})

    def __init__(
        self,
        *,
        adx_threshold: float = 22.0,
        atr_stop_multiple: float = 2.0,
        target_multiple: float = 3.0,
        min_atr_pct: float = 0.02,
    ) -> None:
        self._adx_threshold = adx_threshold
        self._atr_stop_multiple = atr_stop_multiple
        self._target_multiple = target_multiple
        self._min_atr_pct = min_atr_pct

    def evaluate(self, features: FeatureSet, regime: RegimeAssessment) -> StrategyOpinion:
        required = ("close", "ema_12", "ema_26", "ema_50", "adx_14", "di_spread", "atr_14", "atr_pct")
        if not features.has_all(*required):
            return self._no_trade(features, "insufficient features for trend evaluation")

        close = features.require("close")
        ema_fast = features.require("ema_12")
        ema_slow = features.require("ema_26")
        ema_trend = features.require("ema_50")
        adx = features.require("adx_14")
        di_spread = features.require("di_spread")
        atr = features.require("atr_14")
        atr_pct = features.require("atr_pct")

        # An ATR near zero means a stop distance near zero, which means an unbounded
        # position size. Refuse rather than divide by something tiny.
        if atr <= 0 or atr_pct < self._min_atr_pct:
            return self._no_trade(
                features, f"volatility too low to define a stop (atr_pct={atr_pct:.4f})"
            )

        if adx < self._adx_threshold:
            return self._no_trade(
                features, f"no trend: ADX {adx:.1f} below {self._adx_threshold:.1f}",
                metrics={"adx_14": adx},
            )

        bullish = ema_fast > ema_slow and close > ema_trend and di_spread > 0
        bearish = ema_fast < ema_slow and close < ema_trend and di_spread < 0

        if not (bullish or bearish):
            return self._no_trade(
                features, "trend present but EMA structure and DI disagree",
                metrics={"adx_14": adx, "di_spread": di_spread},
            )

        direction = Direction.LONG if bullish else Direction.SHORT

        # Strength combines trend quality (ADX) and directional conviction (DI spread),
        # each normalized and capped so neither can dominate on its own.
        adx_component = _clamp01((adx - self._adx_threshold) / 25.0)
        di_component = _clamp01(abs(di_spread) / 40.0)
        separation = abs(ema_fast - ema_slow) / close * 100.0
        separation_component = _clamp01(separation / (atr_pct * 1.5)) if atr_pct > 0 else 0.0
        strength = _clamp01(0.45 * adx_component + 0.35 * di_component + 0.20 * separation_component)

        stop_distance = atr * self._atr_stop_multiple
        if direction is Direction.LONG:
            stop = close - stop_distance
            target = close + atr * self._target_multiple
        else:
            stop = close + stop_distance
            target = close - atr * self._target_multiple

        if stop <= 0:
            return self._no_trade(features, "computed stop is non-positive")

        return StrategyOpinion(
            strategy_id=self.strategy_id,
            strategy_version=self.version,
            symbol=features.symbol,
            direction=direction,
            strength=strength,
            entry_reference=close,
            stop_reference=stop,
            target_reference=target,
            evidence=(
                Evidence(claim=f"ADX {adx:.1f} indicates a trending market", weight=0.35),
                Evidence(
                    claim=f"EMA12 {'above' if bullish else 'below'} EMA26 and price "
                    f"{'above' if bullish else 'below'} EMA50",
                    weight=0.35,
                ),
                Evidence(claim=f"DI spread {di_spread:+.1f} confirms direction", weight=0.30),
            ),
            invalidation_conditions=(
                f"close crosses back through EMA50 ({ema_trend:.2f})",
                f"ADX falls below {self._adx_threshold:.0f}",
                f"price reaches the stop at {stop:.2f}",
            ),
            metrics={
                "adx_14": adx,
                "di_spread": di_spread,
                "atr_14": atr,
                "ema_separation_pct": separation,
                "regime_confidence": regime.confidence,
            },
        )


class MeanReversionStrategy(Strategy):
    """Bollinger extension + RSI extreme + a non-trending regime.

    Deliberately conservative: mean reversion applied inside a strong trend is the
    fastest way to lose money in a systematic backtest, so this refuses to act when ADX
    says a trend is present, regardless of how stretched the price looks.
    """

    strategy_id = "mean_reversion"
    version = "1.1.0"
    preferred_regimes = frozenset({MarketRegime.RANGING, MarketRegime.LOW_VOLATILITY})

    def __init__(
        self,
        *,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        percent_b_low: float = 0.05,
        percent_b_high: float = 0.95,
        max_adx: float = 25.0,
        atr_stop_multiple: float = 1.5,
    ) -> None:
        self._rsi_low = rsi_oversold
        self._rsi_high = rsi_overbought
        self._pb_low = percent_b_low
        self._pb_high = percent_b_high
        self._max_adx = max_adx
        self._atr_stop_multiple = atr_stop_multiple

    def evaluate(self, features: FeatureSet, regime: RegimeAssessment) -> StrategyOpinion:
        required = ("close", "rsi_14", "bb_percent_b", "bb_middle", "adx_14", "atr_14", "zscore_20")
        if not features.has_all(*required):
            return self._no_trade(features, "insufficient features for mean-reversion evaluation")

        close = features.require("close")
        rsi = features.require("rsi_14")
        percent_b = features.require("bb_percent_b")
        middle = features.require("bb_middle")
        adx = features.require("adx_14")
        atr = features.require("atr_14")
        zscore = features.require("zscore_20")

        if adx > self._max_adx:
            return self._no_trade(
                features,
                f"trend present (ADX {adx:.1f}); fading a trend is not this strategy's job",
                metrics={"adx_14": adx},
            )

        if atr <= 0:
            return self._no_trade(features, "zero ATR; stop distance undefined")

        oversold = rsi <= self._rsi_low and percent_b <= self._pb_low and zscore < -1.0
        overbought = rsi >= self._rsi_high and percent_b >= self._pb_high and zscore > 1.0

        if not (oversold or overbought):
            return self._no_trade(
                features,
                f"not extended (RSI {rsi:.1f}, %B {percent_b:.2f})",
                metrics={"rsi_14": rsi, "bb_percent_b": percent_b},
            )

        direction = Direction.LONG if oversold else Direction.SHORT

        rsi_component = _clamp01(
            (self._rsi_low - rsi) / self._rsi_low
            if oversold
            else (rsi - self._rsi_high) / max(100.0 - self._rsi_high, 1e-9)
        )
        band_component = _clamp01(
            (self._pb_low - percent_b) / max(self._pb_low, 1e-9)
            if oversold
            else (percent_b - self._pb_high) / max(1.0 - self._pb_high, 1e-9)
        )
        z_component = _clamp01((abs(zscore) - 1.0) / 2.0)
        strength = _clamp01(0.4 * rsi_component + 0.35 * band_component + 0.25 * z_component)

        stop_distance = atr * self._atr_stop_multiple
        if direction is Direction.LONG:
            stop, target = close - stop_distance, middle
        else:
            stop, target = close + stop_distance, middle

        if stop <= 0:
            return self._no_trade(features, "computed stop is non-positive")

        # The target is the band middle. If price is already past it, the trade is over
        # before it starts.
        if (direction is Direction.LONG and target <= close) or (
            direction is Direction.SHORT and target >= close
        ):
            return self._no_trade(features, "mean-reversion target already reached")

        return StrategyOpinion(
            strategy_id=self.strategy_id,
            strategy_version=self.version,
            symbol=features.symbol,
            direction=direction,
            strength=strength,
            entry_reference=close,
            stop_reference=stop,
            target_reference=target,
            evidence=(
                Evidence(claim=f"RSI {rsi:.1f} is {'oversold' if oversold else 'overbought'}", weight=0.35),
                Evidence(claim=f"Bollinger %B {percent_b:.2f} at the band edge", weight=0.35),
                Evidence(claim=f"z-score {zscore:+.2f} away from the mean", weight=0.30),
            ),
            invalidation_conditions=(
                f"price reaches the stop at {stop:.2f}",
                f"ADX rises above {self._max_adx:.0f}, indicating a trend has started",
                "price fails to revert within the signal TTL",
            ),
            metrics={
                "rsi_14": rsi,
                "bb_percent_b": percent_b,
                "zscore_20": zscore,
                "adx_14": adx,
                "regime_confidence": regime.confidence,
            },
        )


class BreakoutStrategy(Strategy):
    """Donchian breakout confirmed by volume and volatility expansion.

    A breakout on thin volume is usually noise. Requiring a volume confirmation is what
    separates this from a strategy that buys every new high.
    """

    strategy_id = "breakout"
    version = "1.1.0"
    preferred_regimes = frozenset(
        {MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN, MarketRegime.HIGH_VOLATILITY}
    )

    def __init__(
        self,
        *,
        min_volume_ratio: float = 1.3,
        atr_stop_multiple: float = 2.0,
        target_multiple: float = 3.0,
    ) -> None:
        self._min_volume_ratio = min_volume_ratio
        self._atr_stop_multiple = atr_stop_multiple
        self._target_multiple = target_multiple

    def evaluate(self, features: FeatureSet, regime: RegimeAssessment) -> StrategyOpinion:
        required = (
            "close",
            "breakout_up",
            "breakout_down",
            "donchian_upper_20",
            "donchian_lower_20",
            "volume_ratio",
            "atr_14",
        )
        if not features.has_all(*required):
            return self._no_trade(features, "insufficient features for breakout evaluation")

        close = features.require("close")
        up = features.require("breakout_up") > 0.5
        down = features.require("breakout_down") > 0.5
        volume_ratio = features.require("volume_ratio")
        atr = features.require("atr_14")
        upper = features.require("donchian_upper_20")
        lower = features.require("donchian_lower_20")

        if not (up or down):
            return self._no_trade(features, "price inside the prior 20-bar range")

        if atr <= 0:
            return self._no_trade(features, "zero ATR; stop distance undefined")

        if volume_ratio < self._min_volume_ratio:
            return self._no_trade(
                features,
                f"breakout on thin volume (ratio {volume_ratio:.2f} < {self._min_volume_ratio:.2f})",
                metrics={"volume_ratio": volume_ratio},
            )

        direction = Direction.LONG if up else Direction.SHORT
        reference = upper if up else lower
        extension = abs(close - reference) / atr if atr > 0 else 0.0

        volume_component = _clamp01((volume_ratio - self._min_volume_ratio) / 2.0)
        extension_component = _clamp01(extension / 1.5)
        bb_width = features.get("bb_width_pct")
        expansion_component = _clamp01(bb_width / 5.0) if math.isfinite(bb_width) else 0.3
        strength = _clamp01(
            0.40 * volume_component + 0.35 * extension_component + 0.25 * expansion_component
        )

        stop_distance = atr * self._atr_stop_multiple
        if direction is Direction.LONG:
            # The stop sits below the level that was broken — if price falls back inside
            # the range, the breakout thesis is simply wrong.
            stop = min(close - stop_distance, reference - atr * 0.25)
            target = close + atr * self._target_multiple
        else:
            stop = max(close + stop_distance, reference + atr * 0.25)
            target = close - atr * self._target_multiple

        if stop <= 0 or target <= 0:
            return self._no_trade(features, "computed stop or target is non-positive")

        return StrategyOpinion(
            strategy_id=self.strategy_id,
            strategy_version=self.version,
            symbol=features.symbol,
            direction=direction,
            strength=strength,
            entry_reference=close,
            stop_reference=stop,
            target_reference=target,
            evidence=(
                Evidence(
                    claim=f"close {close:.2f} broke the prior 20-bar "
                    f"{'high' if up else 'low'} at {reference:.2f}",
                    weight=0.40,
                ),
                Evidence(claim=f"volume {volume_ratio:.2f}x its 20-bar average", weight=0.35),
                Evidence(claim=f"extension {extension:.2f} ATR beyond the level", weight=0.25),
            ),
            invalidation_conditions=(
                f"close returns inside the range (through {reference:.2f})",
                f"price reaches the stop at {stop:.2f}",
                "volume fails to sustain above average",
            ),
            metrics={
                "volume_ratio": volume_ratio,
                "extension_atr": extension,
                "atr_14": atr,
                "regime_confidence": regime.confidence,
            },
        )


STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    TrendFollowingStrategy.strategy_id: TrendFollowingStrategy,
    MeanReversionStrategy.strategy_id: MeanReversionStrategy,
    BreakoutStrategy.strategy_id: BreakoutStrategy,
}


def build_strategies(names: tuple[str, ...]) -> list[Strategy]:
    """Instantiate strategies by id, failing loudly on an unknown name."""
    from tia.core.errors import ConfigurationError

    out: list[Strategy] = []
    for name in names:
        cls = STRATEGY_REGISTRY.get(name)
        if cls is None:
            raise ConfigurationError(
                f"unknown strategy {name!r}", known=sorted(STRATEGY_REGISTRY)
            )
        out.append(cls())
    return out


__all__ = [
    "STRATEGY_REGISTRY",
    "BreakoutStrategy",
    "MeanReversionStrategy",
    "TrendFollowingStrategy",
    "build_strategies",
]
