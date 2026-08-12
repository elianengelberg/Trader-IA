"""Synthetic market data — the zero-config demo feed.

This is the only provider that is guaranteed to work anywhere: no credentials, no
network, fully deterministic given a seed. It is what makes ``docker compose up`` a real
demonstration rather than a screenshot.

The generator is a **regime-switching process**, not a plain random walk, because a plain
random walk makes every trend strategy look identically useless and every mean-reversion
strategy look identically brilliant. The Markov chain over {trending up, trending down,
ranging, high-volatility} produces the alternation that makes regime detection and
strategy selection meaningful to test.

What is modelled: drift and volatility per regime, volatility clustering, fat tails via
occasional jump shocks, volume correlated with realised range, and a spread that widens
with volatility.

**What this is not.** It has no order-book dynamics, no market impact from our own
orders, no venue microstructure and no real-world causality. A strategy that works here
has demonstrated that the *plumbing* works, and nothing whatsoever about the market.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from tia.core.clock import Clock, ensure_utc
from tia.core.rng import RngRegistry, derive_seed
from tia.data.providers.base import MarketDataProvider, ProviderCapabilities
from tia.domain.instruments import Timeframe
from tia.domain.market import Candle, Quote


@dataclass(frozen=True)
class RegimeSpec:
    """Per-regime parameters, expressed per bar."""

    name: str
    drift: float
    volatility: float
    mean_reversion: float = 0.0
    jump_probability: float = 0.0
    jump_scale: float = 0.0


# Parameters are per 1-minute bar and calibrated so the annualized volatility lands in a
# plausible range (~55% for the crypto scale factor, ~18% for the index one) rather than
# whatever a random walk happens to produce. Drifts are deliberately mild: a synthetic
# feed with a strong permanent uptrend would make a long-only trend follower look
# profitable for reasons that have nothing to do with skill.
REGIMES: tuple[RegimeSpec, ...] = (
    RegimeSpec("trending_up", drift=6.0e-5, volatility=4.6e-4, jump_probability=0.001, jump_scale=1.8e-3),
    RegimeSpec("trending_down", drift=-5.5e-5, volatility=5.4e-4, jump_probability=0.002, jump_scale=2.4e-3),
    RegimeSpec("ranging", drift=0.0, volatility=3.2e-4, mean_reversion=0.045),
    RegimeSpec("high_volatility", drift=0.0, volatility=1.5e-3, jump_probability=0.010, jump_scale=6.0e-3),
)

# Row i = current regime, column j = next. Diagonal-heavy so regimes persist long enough
# for a strategy to actually act within one.
TRANSITION_MATRIX = np.array(
    [
        [0.9880, 0.0025, 0.0075, 0.0020],
        [0.0025, 0.9860, 0.0085, 0.0030],
        [0.0060, 0.0055, 0.9840, 0.0045],
        [0.0090, 0.0090, 0.0170, 0.9650],
    ]
)


@dataclass(frozen=True)
class SymbolSpec:
    symbol: str
    start_price: float
    volatility_scale: float = 1.0
    base_volume: float = 1_000.0
    base_spread_bps: float = 3.0


DEFAULT_SYMBOL_SPECS: dict[str, SymbolSpec] = {
    "BTC-USD": SymbolSpec("BTC-USD", 62_000.0, volatility_scale=1.35, base_volume=180.0, base_spread_bps=2.5),
    "ETH-USD": SymbolSpec("ETH-USD", 3_100.0, volatility_scale=1.55, base_volume=1_400.0, base_spread_bps=3.5),
    "SPX-IDX": SymbolSpec("SPX-IDX", 5_400.0, volatility_scale=0.45, base_volume=9_000.0, base_spread_bps=1.2),
}


class SyntheticMarketDataProvider(MarketDataProvider):
    """Deterministic regime-switching candle generator.

    Two identical seeds produce byte-identical series, which is what lets an experiment
    record reproduce a result exactly rather than approximately.
    """

    def __init__(
        self,
        clock: Clock,
        rng: RngRegistry,
        *,
        symbol_specs: dict[str, SymbolSpec] | None = None,
    ) -> None:
        super().__init__(
            ProviderCapabilities(
                name="synthetic",
                quotes=True,
                trades=False,
                candles=True,
                order_book=False,
                historical=True,
                streaming=True,
                requires_credentials=False,
                requires_network=False,
                max_history_bars=200_000,
                notes="Deterministic simulation. Contains no real market information.",
            )
        )
        self._clock = clock
        self._rng = rng
        self._specs = symbol_specs or dict(DEFAULT_SYMBOL_SPECS)
        self._series_cache: dict[tuple[str, str, int, int], list[Candle]] = {}

    def spec_for(self, symbol: str) -> SymbolSpec:
        spec = self._specs.get(symbol)
        if spec is None:
            # Unknown symbols get a deterministic pseudo-spec derived from the name, so
            # adding a symbol to config never requires touching this file.
            seed = sum(ord(c) for c in symbol)
            spec = SymbolSpec(
                symbol=symbol,
                start_price=50.0 + (seed % 500),
                volatility_scale=0.8 + (seed % 7) / 10.0,
                base_volume=500.0 + (seed % 2000),
            )
            self._specs[symbol] = spec
        return spec

    def _generate(
        self, symbol: str, timeframe: str, count: int, end: datetime
    ) -> list[Candle]:
        """Generate ``count`` closed bars ending at ``end`` (exclusive of a forming bar)."""
        tf = Timeframe.parse(timeframe)
        spec = self.spec_for(symbol)

        # The cache key includes the end timestamp so a later call extends rather than
        # regenerates — and so repeated calls in one bar return identical data.
        key = (symbol, timeframe, count, int(end.timestamp()))
        cached = self._series_cache.get(key)
        if cached is not None:
            return cached

        # A dedicated stream per (symbol, timeframe, count, end) so the same request
        # always yields the same series regardless of call order elsewhere in the
        # process. derive_seed hashes with BLAKE2s rather than the builtin hash(),
        # which is randomized per interpreter run and would silently break
        # reproducibility across processes.
        rng = np.random.default_rng(
            derive_seed(
                self._rng.root_seed, f"synthetic:{symbol}:{timeframe}:{count}:{int(end.timestamp())}"
            )
        )

        # Warm up so the series does not start in an artificial "just initialised" state.
        warmup = min(240, count // 2 + 20)
        total = count + warmup

        regime_idx = int(rng.integers(0, len(REGIMES)))
        price = spec.start_price
        anchor_price = spec.start_price

        rows: list[tuple[int, float, float, float, float, float, str]] = []
        for i in range(total):
            regime = REGIMES[regime_idx]
            vol = regime.volatility * spec.volatility_scale
            shock = float(rng.normal(0.0, vol))

            reversion = 0.0
            if regime.mean_reversion > 0:
                reversion = regime.mean_reversion * math.log(anchor_price / price)

            jump = 0.0
            if regime.jump_probability > 0 and rng.random() < regime.jump_probability:
                jump = float(rng.normal(0.0, regime.jump_scale * spec.volatility_scale))
                jump *= 1.0 if rng.random() < 0.5 else -1.0

            log_return = regime.drift + reversion + shock + jump
            open_price = price
            close_price = max(1e-9, price * math.exp(log_return))

            # Intrabar extremes: a fraction of the bar's own volatility, always
            # consistent with open/close so the OHLC invariant can never be violated.
            wick = abs(float(rng.normal(0.0, vol))) * 0.85
            high = max(open_price, close_price) * (1.0 + wick)
            low = min(open_price, close_price) * (1.0 - wick)

            # Volume responds to realised movement — quiet bars are thin, violent bars
            # are heavy, which is what makes liquidity checks meaningful.
            activity = 1.0 + 9.0 * abs(log_return) / max(vol, 1e-9) * 0.15
            volume = max(0.0, float(rng.gamma(shape=2.0, scale=spec.base_volume * activity / 2.0)))

            rows.append((i, open_price, high, low, close_price, volume, regime.name))

            price = close_price
            anchor_price = anchor_price * 0.999 + close_price * 0.001
            regime_idx = int(rng.choice(len(REGIMES), p=TRANSITION_MATRIX[regime_idx]))

        candles: list[Candle] = []
        first_open = end - tf.delta * count
        for offset, (_, o, h, low_, c, v, _regime) in enumerate(rows[warmup:]):
            open_time = first_open + tf.delta * offset
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open_time=open_time,
                    close_time=open_time + tf.delta,
                    open=round(o, 8),
                    high=round(h, 8),
                    low=round(low_, 8),
                    close=round(c, 8),
                    volume=round(v, 8),
                    trade_count=int(max(1, v / 10)),
                    provider=self.name,
                )
            )

        if len(self._series_cache) > 64:
            self._series_cache.clear()
        self._series_cache[key] = candles
        return candles

    async def get_candles(
        self, symbol: str, timeframe: str, *, limit: int = 500, end: datetime | None = None
    ) -> list[Candle]:
        tf = Timeframe.parse(timeframe)
        now = ensure_utc(end) if end is not None else self._clock.now()
        # Floor to the last *closed* bar boundary.
        boundary = tf.floor(now)
        candles = self._generate(symbol, timeframe, limit, boundary)
        self._record_success(boundary)
        return candles

    async def get_quote(self, symbol: str) -> Quote | None:
        candles = await self.get_candles(symbol, "1m", limit=30)
        if not candles:
            return None
        last = candles[-1]
        recent = candles[-20:]
        realized = float(np.std([c.close / c.open - 1.0 for c in recent])) if len(recent) > 2 else 0.001
        spec = self.spec_for(symbol)
        # Spread widens with realised volatility — the relationship every liquidity
        # check assumes, made explicit here so those checks have something to detect.
        spread_bps = spec.base_spread_bps * (1.0 + 60.0 * realized)
        half = last.close * spread_bps / 20_000.0
        return Quote(
            symbol=symbol,
            timestamp=last.close_time,
            bid=round(last.close - half, 8),
            ask=round(last.close + half, 8),
            bid_size=round(last.volume * 0.05, 8),
            ask_size=round(last.volume * 0.05, 8),
            provider=self.name,
        )

    def iter_candles(
        self, symbol: str, timeframe: str, *, count: int, start: datetime
    ) -> Iterator[Candle]:
        """Synchronous generator used by the backtester to drive a replay."""
        tf = Timeframe.parse(timeframe)
        end = ensure_utc(start) + tf.delta * count
        yield from self._generate(symbol, timeframe, count, end)


def build_synthetic_history(
    symbol: str,
    timeframe: str,
    bars: int,
    *,
    seed: int,
    end: datetime,
    spec: SymbolSpec | None = None,
) -> list[Candle]:
    """Standalone helper for fixtures and tests — no clock required."""
    from tia.core.clock import FrozenClock

    provider = SyntheticMarketDataProvider(
        FrozenClock(end),
        RngRegistry(seed),
        symbol_specs={symbol: spec} if spec else None,
    )
    return provider._generate(symbol, timeframe, bars, end)


__all__ = [
    "DEFAULT_SYMBOL_SPECS",
    "REGIMES",
    "TRANSITION_MATRIX",
    "RegimeSpec",
    "SymbolSpec",
    "SyntheticMarketDataProvider",
    "build_synthetic_history",
]
