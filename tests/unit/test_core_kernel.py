"""Core kernel: time, identity, randomness, configuration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tia.core.clock import (
    FrozenClock,
    SimulatedClock,
    SystemClock,
    ensure_utc,
    millis_from_utc,
    utc_from_millis,
)
from tia.core.config import (
    Environment,
    LLMConfig,
    MarketDataConfig,
    RiskLimits,
    Settings,
    TradingMode,
    settings_for_env,
)
from tia.core.errors import NaiveDatetimeError, RiskLimitImmutableError
from tia.core.ids import content_hash, deterministic_id, new_ulid, ulid_from_parts
from tia.core.rng import RngRegistry, derive_seed


class TestClock:
    def test_system_clock_is_utc_aware(self) -> None:
        now = SystemClock().now()
        assert now.tzinfo is not None
        assert now.utcoffset() == timedelta(0)

    def test_ensure_utc_rejects_naive(self) -> None:
        with pytest.raises(NaiveDatetimeError):
            ensure_utc(datetime(2026, 1, 1))

    def test_ensure_utc_converts_other_zones(self) -> None:
        from datetime import timezone

        tokyo = datetime(2026, 1, 1, 9, tzinfo=timezone(timedelta(hours=9)))
        assert ensure_utc(tokyo) == datetime(2026, 1, 1, 0, tzinfo=UTC)

    def test_simulated_clock_advances(self) -> None:
        clock = SimulatedClock(datetime(2026, 1, 1, tzinfo=UTC))
        clock.advance_by(timedelta(minutes=5))
        assert clock.now() == datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
        assert clock.monotonic_ns() == 300_000_000_000

    def test_simulated_clock_refuses_to_move_backwards(self) -> None:
        """Out-of-order replay is a bug, and must fail loudly rather than corrupt state."""
        clock = SimulatedClock(datetime(2026, 1, 2, tzinfo=UTC))
        with pytest.raises(ValueError, match="backwards"):
            clock.advance_to(datetime(2026, 1, 1, tzinfo=UTC))

    def test_millis_roundtrip(self) -> None:
        moment = datetime(2026, 3, 15, 12, 30, 45, tzinfo=UTC)
        assert utc_from_millis(millis_from_utc(moment)) == moment

    def test_frozen_clock_never_moves(self) -> None:
        clock = FrozenClock(datetime(2026, 1, 1, tzinfo=UTC))
        assert clock.now() == clock.now()


class TestIds:
    def test_ulids_sort_by_time(self) -> None:
        clock = SimulatedClock(datetime(2026, 1, 1, tzinfo=UTC))
        first = new_ulid(clock)
        clock.advance_by(timedelta(seconds=1))
        second = new_ulid(clock)
        assert first < second

    def test_deterministic_id_ignores_dict_order(self) -> None:
        a = deterministic_id("x", {"a": 1, "b": 2}, 3.0)
        b = deterministic_id("x", {"b": 2, "a": 1}, 3.0)
        assert a == b

    def test_deterministic_id_differs_on_content(self) -> None:
        assert deterministic_id("x", 1) != deterministic_id("x", 2)

    def test_deterministic_id_prefixed_and_bounded(self) -> None:
        value = deterministic_id("coid", "BTC-USD", length=16)
        assert value.startswith("coid_")
        assert len(value.split("_", 1)[1]) == 16

    def test_float_precision_is_normalised(self) -> None:
        """Quantities equal to twelve significant figures are the same logical order."""
        assert deterministic_id("q", 1.0) == deterministic_id("q", 1.0000000000000002)

    def test_ulid_from_parts_is_reproducible(self) -> None:
        moment = datetime(2026, 1, 1, tzinfo=UTC)
        assert ulid_from_parts(moment, 7) == ulid_from_parts(moment, 7)
        assert ulid_from_parts(moment, 7) != ulid_from_parts(moment, 8)

    def test_content_hash_is_stable(self) -> None:
        assert content_hash({"a": [1, 2]}) == content_hash({"a": [1, 2]})
        assert content_hash({"a": [1, 2]}) != content_hash({"a": [2, 1]})


class TestRng:
    def test_streams_are_independent_and_reproducible(self) -> None:
        a = RngRegistry(42)
        b = RngRegistry(42)
        assert a.get("execution").normal() == b.get("execution").normal()
        # Drawing from one stream must not perturb another.
        c = RngRegistry(42)
        c.get("market").normal()
        assert c.get("execution").normal() == RngRegistry(42).get("execution").normal()

    def test_different_root_seeds_diverge(self) -> None:
        assert RngRegistry(1).get("s").normal() != RngRegistry(2).get("s").normal()

    def test_derive_seed_is_stable(self) -> None:
        assert derive_seed(7, "abc") == derive_seed(7, "abc")
        assert derive_seed(7, "abc") != derive_seed(7, "abd")

    def test_describe_reports_used_streams(self) -> None:
        reg = RngRegistry(5)
        reg.get("a")
        reg.get("b")
        assert sorted(reg.describe()) == ["a", "b"]


class TestRiskLimits:
    def test_limits_are_immutable_at_runtime(self) -> None:
        limits = RiskLimits()
        with pytest.raises(RiskLimitImmutableError):
            limits.max_drawdown_pct = 99.0

    def test_propose_change_does_not_mutate_the_original(self) -> None:
        limits = RiskLimits(max_drawdown_pct=10.0)
        proposed = limits.propose_change(max_drawdown_pct=15.0)
        assert limits.max_drawdown_pct == 10.0
        assert proposed.max_drawdown_pct == 15.0

    def test_daily_loss_must_be_below_max_drawdown(self) -> None:
        with pytest.raises(ValueError, match="daily_loss_limit_pct"):
            RiskLimits(daily_loss_limit_pct=20.0, max_drawdown_pct=10.0)

    def test_net_exposure_cannot_exceed_gross(self) -> None:
        with pytest.raises(ValueError, match="max_net_exposure_pct"):
            RiskLimits(max_gross_exposure_pct=50.0, max_net_exposure_pct=80.0)


class TestSettings:
    def test_every_mode_is_simulation_only(self) -> None:
        """The scope rule, asserted mechanically: no mode may execute real orders."""
        for mode in TradingMode:
            settings = settings_for_env(Environment.DEVELOPMENT, mode=mode)
            assert settings.is_simulation_only

    def test_demo_refuses_a_network_provider(self) -> None:
        with pytest.raises(ValueError, match="synthetic or csv"):
            settings_for_env(Environment.DEMO, market_data=MarketDataConfig(provider="binance"))

    def test_anthropic_provider_requires_a_key(self) -> None:
        with pytest.raises(ValueError, match="requires TIA_ANTHROPIC_API_KEY"):
            settings_for_env(
                Environment.PAPER, llm=LLMConfig(enabled=True, provider="anthropic")
            )

    def test_redacted_output_hides_secrets(self) -> None:
        settings = settings_for_env(Environment.PAPER)
        redacted = settings.redacted()
        assert redacted["security"]["jwt_secret"] == "***"  # noqa: S105
        assert redacted["security"]["webhook_secret"] == "***"  # noqa: S105

    def test_date_suffixed_model_id_is_rejected(self) -> None:
        """A date-suffixed alias is a common copy-paste error that 404s at the API."""
        with pytest.raises(ValueError, match="date-suffixed"):
            LLMConfig(model="claude-opus-5-20260101")

    def test_redis_bus_requires_a_url(self) -> None:
        with pytest.raises(ValueError, match="requires redis_url"):
            Settings(event_bus="redis", redis_url=None)

    def test_strategy_weights_must_cover_enabled_strategies(self) -> None:
        from tia.core.config import StrategyConfig

        with pytest.raises(ValueError, match="missing fusion weights"):
            StrategyConfig(enabled=("trend_following", "unknown_one"))
