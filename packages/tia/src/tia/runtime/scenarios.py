"""Demo scenarios — reproducible market conditions, each proving one thing.

A demo that only shows the happy path proves nothing. Each scenario below is designed to
exercise a specific part of the system, *including the parts that are supposed to refuse*:
a data-failure scenario whose correct outcome is that no trades happen at all is as much a
demonstration as one that produces a winning trade.

Every scenario is seeded. The same scenario id and seed produce the same bars, the same
decisions and the same P&L on any machine — which is what makes "it worked on the demo" a
statement anyone can check.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

import numpy as np

from tia.core.clock import ensure_utc
from tia.core.rng import derive_seed
from tia.domain.instruments import Timeframe
from tia.domain.market import Candle


class ScenarioId(StrEnum):
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"
    HIGH_VOLATILITY = "high_volatility"
    NEWS_SHOCK = "news_shock"
    RISK_TRIGGER = "risk_trigger"
    DATA_FAILURE = "data_failure"
    LLM_FAILURE = "llm_failure"
    MIXED = "mixed"


@dataclass(frozen=True)
class Segment:
    """One stretch of market behaviour."""

    bars: int
    drift: float = 0.0
    volatility: float = 4.0e-4
    mean_reversion: float = 0.0
    jump_probability: float = 0.0
    jump_scale: float = 0.0
    volume_scale: float = 1.0
    label: str = ""


@dataclass(frozen=True)
class Scenario:
    """A named market condition plus the faults injected while it runs."""

    id: ScenarioId
    title: str
    demonstrates: str
    segments: tuple[Segment, ...]
    #: Fraction of bars deliberately corrupted (stale repeats, zero volume, gaps).
    data_corruption_rate: float = 0.0
    #: Fraction of LLM calls that fail. Proves the pipeline survives losing the model.
    llm_failure_rate: float = 0.0
    #: Bars at which a news item is injected, and its tone.
    news_at: tuple[tuple[int, str], ...] = ()
    #: Overrides applied to the risk limits, to force a specific gate to bind.
    risk_overrides: dict[str, float] = field(default_factory=dict)
    expected_outcome: str = ""

    @property
    def total_bars(self) -> int:
        return sum(segment.bars for segment in self.segments)


#: The catalogue. Ordered so a reader working down the list sees the system's behaviour
#: broaden from "it trades" to "it correctly refuses to".
SCENARIOS: dict[ScenarioId, Scenario] = {
    ScenarioId.TREND_UP: Scenario(
        id=ScenarioId.TREND_UP,
        title="Sustained uptrend",
        demonstrates=(
            "The trend-following strategy finds setups, the regime classifier reports "
            "trending_up, and orders reach fills."
        ),
        segments=(
            Segment(bars=140, drift=0.0, volatility=3.0e-4, label="base"),
            Segment(bars=360, drift=9.0e-5, volatility=3.6e-4, label="trend"),
        ),
        expected_outcome="long entries, few or no shorts",
    ),
    ScenarioId.TREND_DOWN: Scenario(
        id=ScenarioId.TREND_DOWN,
        title="Sustained downtrend",
        demonstrates="The same machinery on the short side, including short-sale checks.",
        segments=(
            Segment(bars=140, drift=0.0, volatility=3.0e-4, label="base"),
            Segment(bars=360, drift=-8.5e-5, volatility=4.2e-4, label="decline"),
        ),
        expected_outcome="short entries dominate",
    ),
    ScenarioId.RANGE: Scenario(
        id=ScenarioId.RANGE,
        title="Range-bound market",
        demonstrates=(
            "Mean reversion becomes the applicable strategy and trend following is "
            "correctly excluded by regime."
        ),
        segments=(
            Segment(bars=140, drift=0.0, volatility=2.8e-4, label="base"),
            Segment(
                bars=360, drift=0.0, volatility=2.6e-4, mean_reversion=0.06, label="range"
            ),
        ),
        expected_outcome="mean-reversion entries, regime reported as ranging",
    ),
    ScenarioId.HIGH_VOLATILITY: Scenario(
        id=ScenarioId.HIGH_VOLATILITY,
        title="Volatility spike",
        demonstrates=(
            "Position sizing shrinks as volatility rises, and the volatility-percentile "
            "gate starts refusing trades outright."
        ),
        segments=(
            Segment(bars=140, drift=0.0, volatility=3.0e-4, label="calm"),
            Segment(
                bars=200,
                drift=0.0,
                volatility=1.8e-3,
                jump_probability=0.02,
                jump_scale=7.0e-3,
                volume_scale=2.5,
                label="spike",
            ),
            Segment(bars=160, drift=0.0, volatility=6.0e-4, label="decay"),
        ),
        expected_outcome="smaller sizes, then refusals as the vol gate binds",
    ),
    ScenarioId.NEWS_SHOCK: Scenario(
        id=ScenarioId.NEWS_SHOCK,
        title="News shock",
        demonstrates=(
            "A gap plus news items flowing into the context layer. The model can raise "
            "caution; it still cannot create or enlarge a position."
        ),
        segments=(
            Segment(bars=150, drift=2.0e-5, volatility=3.0e-4, label="pre-news"),
            Segment(
                bars=40,
                drift=-6.0e-4,
                volatility=2.4e-3,
                jump_probability=0.15,
                jump_scale=9.0e-3,
                volume_scale=4.0,
                label="shock",
            ),
            Segment(bars=210, drift=1.0e-5, volatility=8.0e-4, label="aftermath"),
        ),
        news_at=((150, "bearish"), (152, "bearish"), (160, "neutral"), (200, "bullish")),
        expected_outcome="context modifier goes negative around the shock",
    ),
    ScenarioId.RISK_TRIGGER: Scenario(
        id=ScenarioId.RISK_TRIGGER,
        title="Risk limits bind",
        demonstrates=(
            "The Risk Engine's veto, demonstrated by tightening limits until it refuses "
            "trades the strategies wanted to take."
        ),
        segments=(
            Segment(bars=140, drift=0.0, volatility=3.0e-4, label="base"),
            Segment(bars=200, drift=-1.2e-4, volatility=9.0e-4, label="drawdown"),
            Segment(bars=160, drift=0.0, volatility=5.0e-4, label="recovery"),
        ),
        risk_overrides={
            "max_risk_per_trade_pct": 0.1,
            "daily_loss_limit_pct": 0.5,
            "max_drawdown_pct": 1.5,
            "max_trades_per_day": 4,
        },
        expected_outcome="rejections attributed to named risk checks; possible safe mode",
    ),
    ScenarioId.DATA_FAILURE: Scenario(
        id=ScenarioId.DATA_FAILURE,
        title="Degraded market data",
        demonstrates=(
            "The data-quality gate refusing to trade on bad input. The correct outcome "
            "is *fewer or no trades* — a scenario that produces nothing is passing."
        ),
        segments=(
            Segment(bars=140, drift=0.0, volatility=3.0e-4, label="clean"),
            Segment(bars=360, drift=2.0e-5, volatility=4.0e-4, label="degraded"),
        ),
        data_corruption_rate=0.35,
        expected_outcome="bars skipped on quality; NO_TRADE dominates",
    ),
    ScenarioId.LLM_FAILURE: Scenario(
        id=ScenarioId.LLM_FAILURE,
        title="Context layer unavailable",
        demonstrates=(
            "Losing the language model entirely. The deterministic pipeline continues "
            "unchanged, which is the whole point of the asymmetry rule."
        ),
        segments=(
            Segment(bars=140, drift=0.0, volatility=3.0e-4, label="base"),
            Segment(bars=360, drift=6.0e-5, volatility=3.8e-4, label="trend"),
        ),
        llm_failure_rate=1.0,
        expected_outcome="every assessment neutral; trading continues normally",
    ),
    ScenarioId.MIXED: Scenario(
        id=ScenarioId.MIXED,
        title="Mixed regimes",
        demonstrates="Regime transitions and hysteresis over a longer sample.",
        segments=(
            Segment(bars=120, drift=0.0, volatility=3.0e-4, label="base"),
            Segment(bars=150, drift=8.0e-5, volatility=3.5e-4, label="up"),
            Segment(bars=150, drift=0.0, volatility=2.8e-4, mean_reversion=0.05, label="range"),
            Segment(bars=120, drift=-7.0e-5, volatility=7.0e-4, label="down"),
            Segment(bars=120, drift=0.0, volatility=1.4e-3, jump_probability=0.01,
                    jump_scale=5.0e-3, label="turbulent"),
        ),
        expected_outcome="several regime changes; strategy mix shifts with them",
    ),
}


def generate_series(
    scenario: Scenario,
    *,
    symbol: str,
    timeframe: str,
    start: datetime,
    seed: int,
    start_price: float = 50_000.0,
    base_volume: float = 400.0,
) -> list[Candle]:
    """Build the scenario's full bar series.

    Generated up front rather than streamed, so the whole run is decided the moment the
    seed is fixed. A generator that produced bars lazily from a live RNG would make a
    replay impossible to reproduce exactly, which is the property the demo depends on.
    """
    tf = Timeframe.parse(timeframe)
    rng = np.random.default_rng(derive_seed(seed, f"scenario:{scenario.id.value}:{symbol}"))
    moment = ensure_utc(start)

    candles: list[Candle] = []
    price = start_price
    anchor = start_price
    index = 0

    for segment in scenario.segments:
        for _ in range(segment.bars):
            shock = float(rng.normal(0.0, segment.volatility))
            reversion = (
                segment.mean_reversion * math.log(anchor / price)
                if segment.mean_reversion > 0
                else 0.0
            )
            jump = 0.0
            if segment.jump_probability > 0 and rng.random() < segment.jump_probability:
                jump = float(rng.normal(0.0, segment.jump_scale))

            log_return = segment.drift + reversion + shock + jump
            open_price = price
            close_price = max(1e-6, price * math.exp(log_return))

            wick = abs(float(rng.normal(0.0, segment.volatility))) * 0.8
            high = max(open_price, close_price) * (1.0 + wick)
            low = min(open_price, close_price) * (1.0 - wick)

            activity = 1.0 + 1.5 * abs(log_return) / max(segment.volatility, 1e-9)
            volume = max(
                1.0,
                float(rng.gamma(2.0, base_volume * segment.volume_scale * activity / 2.0)),
            )

            open_time = moment + tf.delta * index
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open_time=open_time,
                    close_time=open_time + tf.delta,
                    open=round(open_price, 8),
                    high=round(high, 8),
                    low=round(low, 8),
                    close=round(close_price, 8),
                    volume=round(volume, 8),
                    trade_count=max(1, int(volume / 8)),
                    provider="scenario",
                )
            )
            price = close_price
            anchor = anchor * 0.998 + close_price * 0.002
            index += 1

    if scenario.data_corruption_rate > 0:
        candles = _corrupt(candles, scenario, seed)
    return candles


def _corrupt(candles: list[Candle], scenario: Scenario, seed: int) -> list[Candle]:
    """Inject realistic data faults, as **runs** rather than isolated bars.

    This is the shape the fault actually takes, and it matters: a stuck feed repeats the
    same price for many bars, a dead venue reports zero volume for a stretch, and a bad
    tick arrives as a spike that reverts. Corrupting single scattered bars — the obvious
    first implementation — produced a series the quality gate correctly ignored, because
    one frozen bar in a moving market is not evidence of a broken feed. The scenario then
    claimed to demonstrate the gate while demonstrating nothing.

    The gate's thresholds were left alone. Loosening a quality check so a demo looks
    livelier is the wrong direction entirely.
    """
    rng = np.random.default_rng(derive_seed(seed, f"corrupt:{scenario.id.value}"))
    # The warm-up stretch is left clean so the run can reach a decision at all; a feed
    # broken from bar zero demonstrates only that the system refuses to start.
    protected = min(140, len(candles) // 3)
    out = list(candles)
    index = protected

    while index < len(out) - 25:
        if rng.random() >= scenario.data_corruption_rate:
            index += 1
            continue

        kind = int(rng.integers(0, 3))
        if kind == 0:
            # A stuck feed: the same close repeated long enough to be unmistakable. The
            # frozen-price check looks at the last 20 bars and needs them identical.
            length = int(rng.integers(22, 30))
            frozen = out[index - 1].close
            for offset in range(length):
                position = index + offset
                if position >= len(out):
                    break
                bar = out[position]
                out[position] = bar.model_copy(
                    update={
                        "open": frozen,
                        "high": frozen,
                        "low": frozen,
                        "close": frozen,
                        "volume": max(1.0, bar.volume * 0.02),
                    }
                )
            index += length
        elif kind == 1:
            # A dead venue: zero volume for long enough that it cannot be a quiet market.
            length = int(rng.integers(8, 18))
            for offset in range(length):
                position = index + offset
                if position >= len(out):
                    break
                out[position] = out[position].model_copy(
                    update={"volume": 0.0, "trade_count": 0}
                )
            index += length
        else:
            # A bad tick: a spike far outside the recent distribution, reverting next bar.
            bar = out[index]
            direction = 1.0 if rng.random() < 0.5 else -1.0
            close = max(1e-6, bar.close * (1.0 + direction * 0.22))
            out[index] = bar.model_copy(
                update={
                    "close": close,
                    "high": max(bar.high, close) * 1.001,
                    "low": min(bar.low, close) * 0.999,
                }
            )
            index += 1

    return out


def scenario_catalogue() -> list[dict[str, object]]:
    """Serialisable list for the dashboard's scenario picker."""
    return [
        {
            "id": s.id.value,
            "title": s.title,
            "demonstrates": s.demonstrates,
            "expected_outcome": s.expected_outcome,
            "bars": s.total_bars,
            "injects_data_faults": s.data_corruption_rate > 0,
            "injects_llm_failure": s.llm_failure_rate > 0,
            "tightens_risk_limits": bool(s.risk_overrides),
            "news_items": len(s.news_at),
        }
        for s in SCENARIOS.values()
    ]


def get_scenario(scenario_id: str | ScenarioId) -> Scenario:
    try:
        key = ScenarioId(scenario_id)
    except ValueError as exc:
        raise ValueError(
            f"unknown scenario {scenario_id!r}; available: "
            + ", ".join(s.value for s in ScenarioId)
        ) from exc
    return SCENARIOS[key]


def scenario_news(
    scenario: Scenario, *, symbol: str, candles: list[Candle], seed: int
) -> dict[int, tuple[str, str, str]]:
    """Map bar index → (headline, sentiment, impact) for the scenario's injected news."""
    rng = np.random.default_rng(derive_seed(seed, f"news:{scenario.id.value}"))
    templates = {
        "bearish": [
            "Regulator opens inquiry into {sym} derivatives venues",
            "Large holder moves {sym} to exchanges, supply overhang feared",
            "Liquidity thins across {sym} order books",
        ],
        "bullish": [
            "Institutional allocation to {sym} reported at multi-quarter high",
            "{sym} network activity reaches new high",
            "Major venue adds {sym} settlement support",
        ],
        "neutral": [
            "{sym} volumes in line with the trailing average",
            "Analysts split on {sym} positioning into month end",
        ],
    }
    out: dict[int, tuple[str, str, str]] = {}
    for index, tone in scenario.news_at:
        if index >= len(candles):
            continue
        pool = templates.get(tone, templates["neutral"])
        headline = pool[int(rng.integers(0, len(pool)))].format(sym=symbol.split("-")[0])
        impact = "high" if tone != "neutral" else "low"
        out[index] = (headline, tone, impact)
    return out


def bar_offset(start: datetime, timeframe: str, index: int) -> datetime:
    return ensure_utc(start) + Timeframe.parse(timeframe).delta * index


__all__ = [
    "SCENARIOS",
    "Scenario",
    "ScenarioId",
    "Segment",
    "bar_offset",
    "generate_series",
    "get_scenario",
    "scenario_catalogue",
    "scenario_news",
]
