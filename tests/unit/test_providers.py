"""Market data providers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

import pytest

from tia.core.clock import FrozenClock, SimulatedClock
from tia.core.config import Environment, MarketDataConfig, settings_for_env
from tia.core.errors import DataError
from tia.core.rng import RngRegistry
from tia.data.providers import build_provider
from tia.data.providers.csv_replay import CsvReplayProvider, write_fixture
from tia.data.providers.synthetic import (
    SyntheticMarketDataProvider,
    build_synthetic_history,
)

END = datetime(2026, 1, 6, tzinfo=UTC)


class TestSyntheticProvider:
    async def test_produces_the_requested_number_of_valid_bars(
        self, clock: SimulatedClock, rng: RngRegistry
    ) -> None:
        provider = SyntheticMarketDataProvider(clock, rng)
        candles = await provider.get_candles("BTC-USD", "1m", limit=300)
        assert len(candles) == 300
        assert all(c.high >= max(c.open, c.close) for c in candles)
        assert all(c.low <= min(c.open, c.close) for c in candles)
        assert all(c.volume >= 0 for c in candles)

    async def test_bars_are_contiguous_and_ordered(
        self, clock: SimulatedClock, rng: RngRegistry
    ) -> None:
        provider = SyntheticMarketDataProvider(clock, rng)
        candles = await provider.get_candles("BTC-USD", "5m", limit=100)
        for a, b in pairwise(candles):
            assert b.open_time - a.open_time == timedelta(minutes=5)

    def test_same_seed_reproduces_the_series_exactly(self) -> None:
        """The property the whole experiment-reproducibility story rests on."""
        a = build_synthetic_history("BTC-USD", "1m", 200, seed=99, end=END)
        b = build_synthetic_history("BTC-USD", "1m", 200, seed=99, end=END)
        assert [c.close for c in a] == [c.close for c in b]
        assert [c.volume for c in a] == [c.volume for c in b]

    def test_different_seeds_produce_different_series(self) -> None:
        a = build_synthetic_history("BTC-USD", "1m", 200, seed=1, end=END)
        b = build_synthetic_history("BTC-USD", "1m", 200, seed=2, end=END)
        assert [c.close for c in a] != [c.close for c in b]

    def test_series_actually_moves(self) -> None:
        """A generator that produces a flat line would pass every structural test and be
        useless for evaluating a strategy."""
        candles = build_synthetic_history("BTC-USD", "1m", 500, seed=7, end=END)
        closes = [c.close for c in candles]
        assert len(set(closes)) > 400
        assert max(closes) / min(closes) > 1.001

    def test_unknown_symbols_get_a_deterministic_spec(
        self, clock: SimulatedClock, rng: RngRegistry
    ) -> None:
        provider = SyntheticMarketDataProvider(clock, rng)
        first = provider.spec_for("NEW-SYM")
        second = provider.spec_for("NEW-SYM")
        assert first == second

    async def test_quote_spread_is_positive_and_brackets_the_close(
        self, clock: SimulatedClock, rng: RngRegistry
    ) -> None:
        provider = SyntheticMarketDataProvider(clock, rng)
        quote = await provider.get_quote("BTC-USD")
        assert quote is not None
        assert quote.ask > quote.bid
        assert quote.spread_bps > 0

    def test_capabilities_declare_no_network_and_no_credentials(
        self, clock: SimulatedClock, rng: RngRegistry
    ) -> None:
        caps = SyntheticMarketDataProvider(clock, rng).capabilities
        assert caps.requires_network is False
        assert caps.requires_credentials is False

    async def test_only_closed_bars_are_returned(self, rng: RngRegistry) -> None:
        """Mid-bar, the last returned candle must already have closed."""
        mid_bar = datetime(2026, 1, 6, 12, 0, 30, tzinfo=UTC)
        provider = SyntheticMarketDataProvider(FrozenClock(mid_bar), rng)
        candles = await provider.get_candles("BTC-USD", "1m", limit=10)
        assert candles[-1].close_time <= mid_bar


class TestCsvReplayProvider:
    @pytest.fixture
    def fixture_dir(self, tmp_path: Path) -> Path:
        candles = build_synthetic_history("BTC-USD", "1m", 150, seed=5, end=END)
        write_fixture(tmp_path / "BTC-USD_1m.csv", candles)
        return tmp_path

    async def test_roundtrip_preserves_prices(self, fixture_dir: Path) -> None:
        original = build_synthetic_history("BTC-USD", "1m", 150, seed=5, end=END)
        provider = CsvReplayProvider(fixture_dir)
        loaded = await provider.get_candles("BTC-USD", "1m", limit=500)
        assert len(loaded) == len(original)
        assert loaded[0].open == pytest.approx(original[0].open)
        assert loaded[-1].close == pytest.approx(original[-1].close)

    def test_dataset_hash_is_stable(self, fixture_dir: Path) -> None:
        provider = CsvReplayProvider(fixture_dir)
        assert provider.dataset_hash("BTC-USD", "1m") == provider.dataset_hash("BTC-USD", "1m")

    def test_missing_fixture_raises(self, fixture_dir: Path) -> None:
        provider = CsvReplayProvider(fixture_dir)
        with pytest.raises(DataError, match="no fixture"):
            provider.load("NOPE-USD", "1m")

    def test_missing_columns_are_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "BAD_1m.csv").write_text("open_time,close\n2026-01-01T00:00:00Z,1\n")
        provider = CsvReplayProvider(tmp_path)
        with pytest.raises(DataError, match="missing columns"):
            provider.load("BAD", "1m")

    def test_strict_mode_refuses_a_partially_valid_file(self, tmp_path: Path) -> None:
        """A dataset that silently lost rows produces a study nobody can trust."""
        (tmp_path / "BAD_1m.csv").write_text(
            "open_time,open,high,low,close,volume\n"
            "2026-01-01T00:00:00Z,1,2,0.5,1.5,10\n"
            "2026-01-01T00:01:00Z,1,0.1,5,1.5,10\n"  # high < low
        )
        provider = CsvReplayProvider(tmp_path, strict=True)
        with pytest.raises(DataError, match="invalid rows"):
            provider.load("BAD", "1m")

    def test_lenient_mode_reports_what_it_dropped(self, tmp_path: Path) -> None:
        (tmp_path / "BAD_1m.csv").write_text(
            "open_time,open,high,low,close,volume\n"
            "2026-01-01T00:00:00Z,1,2,0.5,1.5,10\n"
            "2026-01-01T00:01:00Z,1,0.1,5,1.5,10\n"
        )
        provider = CsvReplayProvider(tmp_path, strict=False)
        loaded = provider.load("BAD", "1m")
        assert len(loaded) == 1
        assert len(provider.rejected_rows) == 1
        assert provider.rejected_rows[0][0] == 3  # line number, not index

    def test_epoch_timestamps_are_accepted(self, tmp_path: Path) -> None:
        (tmp_path / "EP_1m.csv").write_text(
            "open_time,open,high,low,close,volume\n"
            "1767225600,1,2,0.5,1.5,10\n"
            "1767225600000,1,2,0.5,1.5,10\n"
        )
        loaded = CsvReplayProvider(tmp_path).load("EP", "1m")
        assert loaded[0].open_time == loaded[1].open_time

    async def test_end_cutoff_excludes_later_bars(self, fixture_dir: Path) -> None:
        provider = CsvReplayProvider(fixture_dir)
        everything = await provider.get_candles("BTC-USD", "1m", limit=1000)
        cutoff = everything[50].close_time
        limited = await provider.get_candles("BTC-USD", "1m", limit=1000, end=cutoff)
        assert len(limited) == 51
        assert limited[-1].close_time <= cutoff


class TestProviderFactory:
    def test_builds_the_configured_provider(
        self, clock: SimulatedClock, rng: RngRegistry
    ) -> None:
        provider = build_provider(MarketDataConfig(provider="synthetic"), clock, rng)
        assert provider.name == "synthetic"

    def test_demo_environment_cannot_select_a_network_provider(self) -> None:
        with pytest.raises(ValueError, match="synthetic or csv"):
            settings_for_env(Environment.DEMO, market_data=MarketDataConfig(provider="binance"))

    def test_binance_provider_declares_itself_unverified(self) -> None:
        """The integration status must be visible at runtime, not only in a doc."""
        from tia.data.providers.binance_public import BinancePublicProvider

        caps = BinancePublicProvider().capabilities
        assert caps.requires_network is True
        assert "REQUIRES VALIDATION" in caps.notes

    def test_binance_symbol_mapping(self) -> None:
        from tia.data.providers.binance_public import BinancePublicProvider

        assert BinancePublicProvider.to_venue_symbol("BTC-USD") == "BTCUSDT"
        assert BinancePublicProvider.to_venue_symbol("ETH-EUR") == "ETHEUR"

    def test_binance_rejects_a_malformed_kline_rather_than_guessing(self) -> None:
        from tia.core.errors import ProviderError
        from tia.data.providers.binance_public import BinancePublicProvider

        provider = BinancePublicProvider()
        with pytest.raises(ProviderError, match="unexpected kline shape"):
            provider._parse_kline([1, 2, 3], "BTC-USD", "1m")
