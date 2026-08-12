"""Market data providers and the factory that selects one from configuration."""

from __future__ import annotations

from tia.core.clock import Clock
from tia.core.config import MarketDataConfig
from tia.core.errors import ConfigurationError
from tia.core.rng import RngRegistry
from tia.data.providers.base import MarketDataProvider, ProviderCapabilities, ProviderHealth
from tia.data.providers.csv_replay import CsvReplayProvider, write_fixture
from tia.data.providers.synthetic import SyntheticMarketDataProvider, build_synthetic_history


def build_provider(
    config: MarketDataConfig, clock: Clock, rng: RngRegistry
) -> MarketDataProvider:
    """Instantiate the configured provider.

    The network-dependent provider is imported lazily so that a deployment which never
    uses it does not pay for the import — and so that a missing optional dependency
    surfaces only when that provider is actually selected.
    """
    if config.provider == "synthetic":
        return SyntheticMarketDataProvider(clock, rng)
    if config.provider == "csv":
        return CsvReplayProvider(config.fixtures_dir)
    if config.provider == "binance":
        from tia.data.providers.binance_public import BinancePublicProvider

        return BinancePublicProvider(
            base_url=config.binance_base_url, timeout_seconds=config.request_timeout_seconds
        )
    raise ConfigurationError(f"unknown market data provider {config.provider!r}")


__all__ = [
    "CsvReplayProvider",
    "MarketDataProvider",
    "ProviderCapabilities",
    "ProviderHealth",
    "SyntheticMarketDataProvider",
    "build_provider",
    "build_synthetic_history",
    "write_fixture",
]
