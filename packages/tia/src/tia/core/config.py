"""Configuration.

Everything configurable lives here, is externalizable via environment variables, and is
strictly separated by environment. There is no code path that mixes two environments'
settings: ``TIA_ENV`` selects exactly one profile and the API reports it on ``/health`` so
a screenshot from ``demo`` can never be mistaken for one from ``paper``.

Risk limits are frozen models. Mutating one at runtime raises
:class:`~tia.core.errors.RiskLimitImmutableError` — see ADR-0004 and §22 of the
architecture: the system may *propose* limit changes, it may never *apply* them.
"""

from __future__ import annotations

import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from tia.core.errors import ConfigurationError, RiskLimitImmutableError


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    DEMO = "demo"
    PAPER = "paper"
    SHADOW = "shadow"
    BACKTEST = "backtest"


class TradingMode(StrEnum):
    """The only modes that exist. There is deliberately no ``LIVE``."""

    BACKTEST = "backtest"
    PAPER = "paper"
    SHADOW = "shadow"
    RESEARCH = "research"


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- risk


class RiskLimits(FrozenModel):
    """Hard limits. Frozen by construction; see :meth:`propose_change`."""

    max_risk_per_trade_pct: float = Field(0.5, gt=0, le=5, description="% of equity at risk")
    max_position_notional_pct: float = Field(20.0, gt=0, le=100)
    max_gross_exposure_pct: float = Field(100.0, gt=0, le=300)
    max_net_exposure_pct: float = Field(60.0, gt=0, le=300)
    max_concurrent_positions: int = Field(5, ge=1, le=200)
    max_positions_per_cluster: int = Field(2, ge=1, le=50)
    max_cluster_exposure_pct: float = Field(40.0, gt=0, le=200)
    max_correlation_for_new_position: float = Field(0.80, gt=0, le=1.0)
    daily_loss_limit_pct: float = Field(2.0, gt=0, le=50)
    max_drawdown_pct: float = Field(10.0, gt=0, le=90)
    min_data_quality_score: float = Field(0.75, ge=0, le=1)
    min_freshness_score: float = Field(0.70, ge=0, le=1)
    max_spread_bps: float = Field(25.0, gt=0, le=1000)
    min_bar_volume: float = Field(0.0, ge=0)
    max_volatility_percentile: float = Field(0.97, gt=0, le=1)
    min_confidence: float = Field(0.55, ge=0, le=1)
    trade_cooldown_seconds: int = Field(300, ge=0)
    max_trades_per_day: int = Field(20, ge=1)
    max_trades_per_symbol_per_day: int = Field(5, ge=1)

    @model_validator(mode="after")
    def _coherent(self) -> RiskLimits:
        if self.max_net_exposure_pct > self.max_gross_exposure_pct:
            raise ValueError("max_net_exposure_pct cannot exceed max_gross_exposure_pct")
        if self.daily_loss_limit_pct >= self.max_drawdown_pct:
            raise ValueError(
                "daily_loss_limit_pct must be below max_drawdown_pct, otherwise the daily "
                "limit can never fire before the drawdown breaker"
            )
        if self.max_positions_per_cluster > self.max_concurrent_positions:
            raise ValueError("max_positions_per_cluster cannot exceed max_concurrent_positions")
        return self

    def propose_change(self, **changes: Any) -> RiskLimits:
        """Return a *proposed* new limit set without touching this one.

        The proposal must go through backtest -> out-of-sample validation -> shadow test
        -> human approval before it becomes configuration. Nothing in the running system
        may swap the active limits for the result of this call.
        """
        return self.model_copy(update=changes)

    def __setattr__(self, name: str, value: Any) -> None:  # pragma: no cover - guard
        raise RiskLimitImmutableError(
            "risk limits are immutable at runtime; change them through versioned config",
            attribute=name,
        )


# --------------------------------------------------------------------------- execution


class ExecutionSimConfig(FrozenModel):
    """Cost and microstructure model for the paper matching engine.

    Defaults are deliberately pessimistic. Optimistic fill assumptions are the single
    easiest way to manufacture a backtest edge that does not exist.
    """

    taker_fee_bps: float = Field(7.5, ge=0, le=200)
    maker_fee_bps: float = Field(2.5, ge=0, le=200)
    base_slippage_bps: float = Field(2.0, ge=0, le=500)
    impact_coefficient: float = Field(
        0.35, ge=0, le=10, description="bps of impact at 100% of bar volume, sqrt-scaled"
    )
    max_participation_rate: float = Field(
        0.10, gt=0, le=1, description="max fraction of a bar's volume we may consume"
    )
    submit_latency_ms: int = Field(120, ge=0, le=60_000)
    ack_latency_ms: int = Field(60, ge=0, le=60_000)
    reject_probability: float = Field(0.01, ge=0, le=0.5)
    partial_fill_probability: float = Field(0.15, ge=0, le=1)
    allow_shorting: bool = True


class DataQualityConfig(FrozenModel):
    max_bar_age_multiplier: float = Field(3.0, gt=1, le=100)
    max_gap_ratio: float = Field(0.02, ge=0, le=1)
    max_spread_zscore: float = Field(4.0, gt=0, le=50)
    min_history_bars: int = Field(60, ge=1)
    hard_fail_quality_score: float = Field(0.40, ge=0, le=1)
    spread_window: int = Field(120, ge=10)


# --------------------------------------------------------------------------- llm


class LLMConfig(FrozenModel):
    """Claude configuration.

    Model ids and parameters verified against the Anthropic API reference bundled with
    this session (see docs/LLM.md). ``claude-opus-5`` is the default; adaptive thinking is
    the only supported thinking mode on this model family and ``budget_tokens`` /
    ``temperature`` are rejected by the API, so neither appears here.
    """

    enabled: bool = False
    provider: Literal["anthropic", "stub"] = "stub"
    model: str = "claude-opus-5"
    max_tokens: int = Field(8000, ge=256, le=128_000)
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    thinking: Literal["adaptive", "disabled"] = "adaptive"
    timeout_seconds: float = Field(60.0, gt=0, le=600)
    max_retries: int = Field(2, ge=0, le=5)

    # Cost governance
    max_calls_per_minute: int = Field(6, ge=1, le=1000)
    max_calls_per_day: int = Field(500, ge=1)
    max_input_tokens_per_day: int = Field(4_000_000, ge=1000)
    max_output_tokens_per_day: int = Field(500_000, ge=1000)
    max_cost_usd_per_day: float = Field(25.0, gt=0)
    input_cost_per_mtok_usd: float = Field(5.0, ge=0)
    output_cost_per_mtok_usd: float = Field(25.0, ge=0)
    circuit_breaker_failures: int = Field(3, ge=1, le=50)
    circuit_breaker_cooldown_seconds: int = Field(300, ge=1)

    # Trigger policy
    assessment_ttl_seconds: int = Field(900, ge=30, le=86_400)
    periodic_review_seconds: int = Field(3600, ge=60)
    macro_surprise_zscore_trigger: float = Field(2.0, gt=0)
    regime_change_triggers: bool = True
    anomaly_triggers: bool = True

    @field_validator("model")
    @classmethod
    def _known_model(cls, v: str) -> str:
        # Guard against date-suffixed ids, which are a common copy-paste error and 404.
        if v.count("-") >= 3 and v.rsplit("-", 1)[-1].isdigit():
            raise ValueError(
                f"{v!r} looks date-suffixed; use the plain alias, e.g. 'claude-opus-5'"
            )
        return v


# --------------------------------------------------------------------------- data


class MarketDataConfig(FrozenModel):
    provider: Literal["synthetic", "csv", "binance"] = "synthetic"
    symbols: tuple[str, ...] = ("BTC-USD", "ETH-USD", "SPX-IDX")
    timeframe: str = "1m"
    history_bars: int = Field(1500, ge=100, le=200_000)
    fixtures_dir: Path = Path("data/fixtures")
    # Only consulted when provider == "binance"; unverified in this environment.
    binance_base_url: str = "https://api.binance.com"
    request_timeout_seconds: float = Field(15.0, gt=0, le=120)


class StrategyConfig(FrozenModel):
    enabled: tuple[str, ...] = ("trend_following", "mean_reversion", "breakout")
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "trend_following": 0.45,
            "mean_reversion": 0.30,
            "breakout": 0.25,
        }
    )
    signal_ttl_seconds: int = Field(300, ge=10, le=86_400)
    min_agreement: float = Field(
        0.0, ge=0, le=1, description="minimum |net score| before a direction is proposed"
    )

    @model_validator(mode="after")
    def _weights_cover_enabled(self) -> StrategyConfig:
        missing = set(self.enabled) - set(self.weights)
        if missing:
            raise ValueError(f"missing fusion weights for enabled strategies: {sorted(missing)}")
        total = sum(self.weights[name] for name in self.enabled)
        if total <= 0:
            raise ValueError("sum of enabled strategy weights must be positive")
        return self


class SecurityConfig(FrozenModel):
    jwt_secret: SecretStr = SecretStr("change-me-in-any-real-deployment")
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = Field(3600, ge=60, le=86_400)
    api_rate_limit_per_minute: int = Field(240, ge=1)
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)
    webhook_enabled: bool = False
    webhook_secret: SecretStr = SecretStr("")
    webhook_replay_window_seconds: int = Field(300, ge=10, le=3600)
    webhook_ip_allowlist: tuple[str, ...] = (
        # Publicly reported TradingView webhook senders. Could not be verified against
        # the primary source in this environment (tradingview.com is egress-blocked),
        # which is one reason the webhook gateway is disabled by default.
        "52.89.214.238",
        "34.212.75.30",
        "54.218.53.128",
        "52.32.178.7",
    )
    max_webhook_body_bytes: int = Field(16_384, ge=256, le=1_048_576)


class ObservabilityConfig(FrozenModel):
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
    metrics_enabled: bool = True
    tracing_enabled: bool = False


# --------------------------------------------------------------------------- root


class Settings(BaseSettings):
    """Root settings object. Construct via :func:`get_settings`."""

    model_config = SettingsConfigDict(
        env_prefix="TIA_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    env: Environment = Environment.DEMO
    mode: TradingMode = TradingMode.PAPER
    app_name: str = "trader-ia"
    version: str = "0.1.0"

    seed: int = Field(20260812, ge=0, description="root seed for every derived RNG stream")
    initial_capital: float = Field(100_000.0, gt=0)
    base_currency: str = "USD"

    database_url: str = "sqlite+aiosqlite:///./data/runtime/tia.db"
    redis_url: str | None = None
    event_bus: Literal["memory", "redis"] = "memory"

    anthropic_api_key: SecretStr | None = None

    risk: RiskLimits = Field(default_factory=RiskLimits)
    execution: ExecutionSimConfig = Field(default_factory=ExecutionSimConfig)
    data_quality: DataQualityConfig = Field(default_factory=DataQualityConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    market_data: MarketDataConfig = Field(default_factory=MarketDataConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    @model_validator(mode="after")
    def _environment_invariants(self) -> Settings:
        # The zero-config demo must never depend on a credential or an external host.
        if self.env is Environment.DEMO:
            if self.market_data.provider not in ("synthetic", "csv"):
                raise ValueError(
                    "demo environment must use the synthetic or csv provider so it runs "
                    "with no credentials and no network"
                )
            if self.llm.enabled and self.llm.provider != "stub" and self.anthropic_api_key is None:
                raise ValueError("llm enabled in demo without an API key; use provider='stub'")
        if self.llm.enabled and self.llm.provider == "anthropic" and self.anthropic_api_key is None:
            raise ValueError(
                "llm.provider='anthropic' requires TIA_ANTHROPIC_API_KEY; "
                "set llm.provider='stub' to run without credentials"
            )
        if self.event_bus == "redis" and not self.redis_url:
            raise ValueError("event_bus='redis' requires redis_url")
        if self.mode is TradingMode.BACKTEST and self.env is Environment.PAPER:
            raise ValueError("backtest mode cannot run under the paper environment profile")
        return self

    @property
    def is_simulation_only(self) -> bool:
        """Always true. Kept as an explicit, testable assertion of the scope rule."""
        return self.mode in {
            TradingMode.BACKTEST,
            TradingMode.PAPER,
            TradingMode.SHADOW,
            TradingMode.RESEARCH,
        }

    def redacted(self) -> dict[str, Any]:
        """Config safe to log or return from the API: no secret ever leaves here."""
        data = self.model_dump(mode="json")
        for key in ("anthropic_api_key",):
            if data.get(key) is not None:
                data[key] = "***"
        data["security"]["jwt_secret"] = "***"  # noqa: S105 - redaction marker
        data["security"]["webhook_secret"] = "***"  # noqa: S105 - redaction marker
        if "://" in str(data.get("database_url", "")) and "@" in str(data["database_url"]):
            scheme, _, rest = str(data["database_url"]).partition("://")
            data["database_url"] = f"{scheme}://***@{rest.rsplit('@', 1)[-1]}"
        return data


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, resolved once."""
    try:
        return Settings()
    except Exception as exc:  # pragma: no cover - surfaced as a clean startup failure
        raise ConfigurationError(f"invalid configuration: {exc}") from exc


def reset_settings_cache() -> None:
    """Test helper: force the next :func:`get_settings` to re-read the environment."""
    get_settings.cache_clear()


def settings_for_env(env: Environment, **overrides: Any) -> Settings:
    """Build a Settings instance for a specific environment without touching os.environ."""
    presets: dict[Environment, dict[str, Any]] = {
        Environment.DEMO: {
            "mode": TradingMode.PAPER,
            "market_data": MarketDataConfig(provider="synthetic"),
            "llm": LLMConfig(enabled=True, provider="stub"),
            "database_url": "sqlite+aiosqlite:///./data/runtime/demo.db",
        },
        Environment.TESTING: {
            "mode": TradingMode.BACKTEST,
            "market_data": MarketDataConfig(provider="synthetic", history_bars=400),
            "llm": LLMConfig(enabled=True, provider="stub"),
            "database_url": "sqlite+aiosqlite:///:memory:",
            "observability": ObservabilityConfig(log_level="WARNING", metrics_enabled=False),
        },
        Environment.BACKTEST: {
            "mode": TradingMode.BACKTEST,
            "llm": LLMConfig(enabled=False, provider="stub"),
        },
        Environment.SHADOW: {"mode": TradingMode.SHADOW},
        Environment.PAPER: {"mode": TradingMode.PAPER},
        Environment.DEVELOPMENT: {"mode": TradingMode.RESEARCH},
    }
    payload: dict[str, Any] = {"env": env, **presets.get(env, {}), **overrides}
    return Settings(**payload)


def current_env() -> Environment:
    raw = os.environ.get("TIA_ENV", Environment.DEMO.value)
    try:
        return Environment(raw)
    except ValueError as exc:
        raise ConfigurationError(f"unknown TIA_ENV {raw!r}") from exc


__all__ = [
    "DataQualityConfig",
    "Environment",
    "ExecutionSimConfig",
    "LLMConfig",
    "MarketDataConfig",
    "ObservabilityConfig",
    "RiskLimits",
    "SecurityConfig",
    "Settings",
    "StrategyConfig",
    "TradingMode",
    "current_env",
    "get_settings",
    "reset_settings_cache",
    "settings_for_env",
]
