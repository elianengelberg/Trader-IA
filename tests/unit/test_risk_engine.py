"""The Risk Engine.

The engine holds absolute veto, so the tests are written adversarially: they try to get
a position approved that should not be, try to get one *grown*, and try to slip a signal
past a limit. The three structural properties — may only shrink, records every check,
cannot be overridden — get dedicated coverage.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tia.core.clock import SimulatedClock
from tia.core.config import RiskLimits
from tia.core.errors import RiskLimitImmutableError
from tia.domain.enums import Direction, MarketRegime, RiskVerdict, SystemMode
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.domain.portfolio import PortfolioState
from tia.domain.quality import DataQualityReport
from tia.domain.signals import SignalCandidate
from tia.risk.engine import RiskEngine, RiskState
from tia.risk.sizing import MIN_STOP_DISTANCE_PCT, compute_size, implied_risk

NOW = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
EQUITY = 100_000.0


def signal(
    *,
    direction: Direction = Direction.LONG,
    confidence: float = 0.8,
    entry: float = 60_000.0,
    stop: float | None = 58_000.0,
    symbol: str = "BTC-USD",
    created_at: datetime = NOW,
    ttl_seconds: int = 300,
    quality_score: float = 1.0,
) -> SignalCandidate:
    return SignalCandidate(
        signal_id=f"sig_test_{symbol}_{direction.value}",
        symbol=symbol,
        direction=direction,
        confidence=confidence,
        base_confidence=confidence,
        created_at=created_at,
        expires_at=created_at + timedelta(seconds=ttl_seconds),
        market_snapshot_id="snap_test",
        entry_reference=entry,
        stop_reference=stop,
        target_reference=entry * 1.05 if direction is Direction.LONG else entry * 0.95,
        strategy_id="trend_following",
        strategy_version="1.0.0",
        regime=MarketRegime.TRENDING_UP,
        data_quality_score=quality_score,
        data_freshness_score=quality_score,
    )


def quality(score: float = 1.0, hard_fail: bool = False) -> DataQualityReport:
    return DataQualityReport(
        report_id="dq",
        symbol="BTC-USD",
        timeframe="1m",
        evaluated_at=NOW,
        quality_score=score,
        freshness_score=score,
        hard_fail=hard_fail,
    )


@pytest.fixture
def engine() -> RiskEngine:
    return RiskEngine(RiskLimits(), DEFAULT_UNIVERSE, SimulatedClock(NOW))


@pytest.fixture
def portfolio() -> PortfolioState:
    return PortfolioState.initial(EQUITY)


class TestApproval:
    def test_a_clean_signal_is_approved(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        decision = engine.evaluate(signal=signal(), portfolio=portfolio, quality=quality(), now=NOW)
        assert decision.verdict is RiskVerdict.APPROVED
        assert decision.approved_quantity > 0
        assert decision.sizing is not None

    def test_risk_taken_matches_the_configured_budget(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        """The property the whole sizing method exists for: a loss costs ~0.5% of equity
        regardless of the instrument's price."""
        sig = signal(entry=60_000.0, stop=58_000.0)
        decision = engine.evaluate(signal=sig, portfolio=portfolio, quality=quality(), now=NOW)
        risk = implied_risk(decision.approved_quantity, sig.entry_reference, sig.stop_reference)
        expected = EQUITY * RiskLimits().max_risk_per_trade_pct / 100.0
        assert risk == pytest.approx(expected, rel=0.01)

    def test_every_check_is_recorded_even_on_approval(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        decision = engine.evaluate(signal=signal(), portfolio=portfolio, quality=quality(), now=NOW)
        names = {c.name for c in decision.checks}
        assert {
            "system_mode",
            "signal_actionable",
            "signal_ttl",
            "data_quality_score",
            "min_confidence",
            "max_drawdown_breaker",
            "daily_loss_limit",
            "position_sizing",
            "max_gross_exposure",
        } <= names

    def test_short_signals_are_approved_for_shortable_instruments(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        decision = engine.evaluate(
            signal=signal(direction=Direction.SHORT, entry=60_000.0, stop=62_000.0),
            portfolio=portfolio,
            quality=quality(),
            now=NOW,
        )
        assert decision.verdict is RiskVerdict.APPROVED


class TestVetoes:
    def test_no_trade_signal_is_never_sized(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        decision = engine.evaluate(
            signal=signal(direction=Direction.NO_TRADE), portfolio=portfolio, now=NOW
        )
        assert decision.verdict is RiskVerdict.NO_TRADE
        assert decision.approved_quantity == 0

    def test_expired_signal_is_refused(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        """Acting on an expired signal is acting on a market that has already moved."""
        old = signal(created_at=NOW - timedelta(hours=1))
        decision = engine.evaluate(signal=old, portfolio=portfolio, quality=quality(), now=NOW)
        assert decision.verdict is RiskVerdict.NO_TRADE
        assert "expired" in decision.primary_reason()

    def test_data_quality_hard_fail_vetoes(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        decision = engine.evaluate(
            signal=signal(), portfolio=portfolio, quality=quality(0.99, hard_fail=True), now=NOW
        )
        assert decision.verdict is RiskVerdict.NO_TRADE

    def test_low_data_quality_vetoes(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        decision = engine.evaluate(
            signal=signal(), portfolio=portfolio, quality=quality(0.5), now=NOW
        )
        assert decision.verdict is RiskVerdict.NO_TRADE

    def test_low_confidence_is_rejected(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        decision = engine.evaluate(
            signal=signal(confidence=0.1), portfolio=portfolio, quality=quality(), now=NOW
        )
        assert decision.verdict is RiskVerdict.REJECTED
        assert "confidence" in decision.primary_reason()

    def test_signal_without_a_stop_cannot_be_sized(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        """A position with no invalidation level has undefined risk."""
        decision = engine.evaluate(
            signal=signal(stop=None), portfolio=portfolio, quality=quality(), now=NOW
        )
        assert decision.verdict is RiskVerdict.REJECTED
        assert decision.sizing is not None
        assert decision.sizing.limiting_constraint == "no_stop_defined"

    def test_stop_too_close_is_refused(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        """A stop one tick away implies a position many times the account."""
        decision = engine.evaluate(
            signal=signal(entry=60_000.0, stop=59_999.0), portfolio=portfolio, quality=quality(), now=NOW
        )
        assert decision.verdict is RiskVerdict.REJECTED
        assert decision.sizing is not None
        assert decision.sizing.limiting_constraint == "stop_too_close"

    def test_unknown_instrument_is_rejected(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        decision = engine.evaluate(
            signal=signal(symbol="NOPE-USD"), portfolio=portfolio, quality=quality(), now=NOW
        )
        assert decision.verdict is RiskVerdict.REJECTED
        assert "unknown instrument" in decision.primary_reason()

    def test_wide_spread_is_rejected(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        decision = engine.evaluate(
            signal=signal(), portfolio=portfolio, quality=quality(), spread_bps=500.0, now=NOW
        )
        assert decision.verdict is RiskVerdict.REJECTED
        assert "spread" in decision.primary_reason()


class TestCircuitBreakers:
    def test_drawdown_breach_halts_the_system_not_just_the_signal(
        self, engine: RiskEngine
    ) -> None:
        """A drawdown breach is a system condition. The next signal must not be evaluated
        as though nothing happened."""
        portfolio = PortfolioState.initial(EQUITY)
        portfolio.peak_equity = 200_000.0  # a 50% drawdown from peak

        first = engine.evaluate(signal=signal(), portfolio=portfolio, quality=quality(), now=NOW)
        assert first.verdict is RiskVerdict.NO_TRADE
        assert engine.state.mode is SystemMode.SAFE_MODE

        healthy = PortfolioState.initial(EQUITY)
        second = engine.evaluate(signal=signal(), portfolio=healthy, quality=quality(), now=NOW)
        assert second.verdict is RiskVerdict.NO_TRADE
        assert "halted" in second.primary_reason()

    def test_daily_loss_limit_blocks_new_risk(self, engine: RiskEngine) -> None:
        portfolio = PortfolioState.initial(EQUITY)
        portfolio.day_start_equity = 110_000.0  # ~9% down on the day
        decision = engine.evaluate(
            signal=signal(), portfolio=portfolio, quality=quality(), now=NOW
        )
        assert decision.verdict is RiskVerdict.NO_TRADE
        assert "daily loss" in decision.primary_reason()

    def test_kill_switch_blocks_everything(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        engine.engage_kill_switch("operator intervention")
        decision = engine.evaluate(signal=signal(), portfolio=portfolio, quality=quality(), now=NOW)
        assert decision.verdict is RiskVerdict.NO_TRADE
        assert "operator intervention" in decision.primary_reason()

    def test_resume_requires_naming_an_approver(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        engine.engage_kill_switch("test")
        engine.resume(approved_by="operator@example.com")
        assert engine.state.mode is SystemMode.NORMAL
        decision = engine.evaluate(signal=signal(), portfolio=portfolio, quality=quality(), now=NOW)
        assert decision.verdict is RiskVerdict.APPROVED


class TestFrequencyLimits:
    def test_cooldown_blocks_a_rapid_second_trade(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        engine.record_execution("BTC-USD", NOW)
        decision = engine.evaluate(
            signal=signal(created_at=NOW + timedelta(seconds=10)),
            portfolio=portfolio,
            quality=quality(),
            now=NOW + timedelta(seconds=10),
        )
        assert decision.verdict is RiskVerdict.REJECTED
        assert "cooldown" in decision.primary_reason()

    def test_daily_trade_cap_is_enforced(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        limits = RiskLimits(max_trades_per_day=2, trade_cooldown_seconds=0)
        capped = RiskEngine(limits, DEFAULT_UNIVERSE, SimulatedClock(NOW))
        capped.record_execution("BTC-USD", NOW)
        capped.record_execution("ETH-USD", NOW)
        decision = capped.evaluate(
            signal=signal(), portfolio=portfolio, quality=quality(), now=NOW
        )
        assert decision.verdict is RiskVerdict.REJECTED
        assert "daily trade count" in decision.primary_reason()

    def test_counters_reset_on_a_new_day(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        limits = RiskLimits(max_trades_per_day=1, trade_cooldown_seconds=0)
        capped = RiskEngine(limits, DEFAULT_UNIVERSE, SimulatedClock(NOW))
        capped.record_execution("BTC-USD", NOW)
        tomorrow = NOW + timedelta(days=1)
        decision = capped.evaluate(
            signal=signal(created_at=tomorrow), portfolio=portfolio, quality=quality(), now=tomorrow
        )
        assert decision.verdict is RiskVerdict.APPROVED


class TestPortfolioLimits:
    def test_gross_exposure_limit_reduces_rather_than_rejects(self) -> None:
        limits = RiskLimits(max_gross_exposure_pct=10.0, max_net_exposure_pct=10.0)
        engine = RiskEngine(limits, DEFAULT_UNIVERSE, SimulatedClock(NOW))
        portfolio = PortfolioState.initial(EQUITY)
        decision = engine.evaluate(
            signal=signal(), portfolio=portfolio, quality=quality(), now=NOW
        )
        assert decision.verdict is RiskVerdict.REDUCED_SIZE
        assert decision.approved_quantity * 60_000.0 <= EQUITY * 0.10 + 1

    def test_concurrent_position_limit_blocks_a_new_symbol(self) -> None:
        limits = RiskLimits(max_concurrent_positions=1, max_positions_per_cluster=1)
        engine = RiskEngine(limits, DEFAULT_UNIVERSE, SimulatedClock(NOW))
        portfolio = PortfolioState.initial(EQUITY)
        existing = portfolio.position("ETH-USD")
        existing.quantity = 1.0
        existing.average_price = 3_000.0
        existing.last_price = 3_000.0

        decision = engine.evaluate(
            signal=signal(), portfolio=portfolio, quality=quality(), now=NOW
        )
        assert decision.verdict is RiskVerdict.REJECTED
        assert "concurrent positions" in decision.primary_reason()

    def test_cluster_position_limit_blocks_a_correlated_symbol(self) -> None:
        """BTC and ETH share a correlation cluster in the default universe."""
        limits = RiskLimits(max_positions_per_cluster=1, max_concurrent_positions=10)
        engine = RiskEngine(limits, DEFAULT_UNIVERSE, SimulatedClock(NOW))
        portfolio = PortfolioState.initial(EQUITY)
        eth = portfolio.position("ETH-USD")
        eth.quantity = 1.0
        eth.average_price = 3_000.0
        eth.last_price = 3_000.0

        decision = engine.evaluate(
            signal=signal(), portfolio=portfolio, quality=quality(), now=NOW
        )
        assert decision.verdict is RiskVerdict.REJECTED
        assert "cluster" in decision.primary_reason()

    def test_measured_correlation_blocks_a_new_position(self) -> None:
        """Cluster membership is static; measured correlation catches instruments that
        have started moving together regardless of how they were labelled."""
        limits = RiskLimits(
            max_correlation_for_new_position=0.5,
            max_positions_per_cluster=10,
            max_concurrent_positions=10,
        )
        engine = RiskEngine(limits, DEFAULT_UNIVERSE, SimulatedClock(NOW))
        portfolio = PortfolioState.initial(EQUITY)
        spx = portfolio.position("SPX-IDX")
        spx.quantity = 1.0
        spx.average_price = 5_400.0
        spx.last_price = 5_400.0

        decision = engine.evaluate(
            signal=signal(),
            portfolio=portfolio,
            quality=quality(),
            correlations={("BTC-USD", "SPX-IDX"): 0.95},
            now=NOW,
        )
        assert decision.verdict is RiskVerdict.REJECTED
        assert "correlation" in decision.primary_reason()


class TestTheEngineMayOnlyShrink:
    def test_approved_never_exceeds_requested(
        self, engine: RiskEngine, portfolio: PortfolioState
    ) -> None:
        decision = engine.evaluate(signal=signal(), portfolio=portfolio, quality=quality(), now=NOW)
        assert decision.sizing is not None
        assert decision.approved_quantity <= decision.sizing.raw_quantity + 1e-9

    def test_the_domain_model_rejects_an_engine_that_grew_a_position(self) -> None:
        """Defence in depth: even a buggy engine cannot emit an inflated decision."""
        from tia.domain.risk import RiskDecision

        with pytest.raises(ValueError, match="never approve more than was requested"):
            RiskDecision(
                decision_id="rd",
                signal_id="sig",
                symbol="BTC-USD",
                verdict=RiskVerdict.APPROVED,
                approved_quantity=10.0,
                requested_quantity=1.0,
                decided_at=NOW,
            )

    def test_limits_cannot_be_mutated_at_runtime(self, engine: RiskEngine) -> None:
        with pytest.raises(RiskLimitImmutableError):
            engine.limits.max_risk_per_trade_pct = 100.0

    @settings(max_examples=200, deadline=None)
    @given(
        confidence=st.floats(min_value=0.0, max_value=1.0),
        entry=st.floats(min_value=1.0, max_value=100_000.0),
        stop_frac=st.floats(min_value=0.001, max_value=0.5),
        equity=st.floats(min_value=1_000.0, max_value=10_000_000.0),
        direction=st.sampled_from([Direction.LONG, Direction.SHORT]),
    )
    def test_never_approves_more_risk_than_the_budget(
        self,
        confidence: float,
        entry: float,
        stop_frac: float,
        equity: float,
        direction: Direction,
    ) -> None:
        """Property: across any signal, an approved position's risk at the stop never
        exceeds the configured risk budget."""
        limits = RiskLimits()
        engine = RiskEngine(limits, DEFAULT_UNIVERSE, SimulatedClock(NOW))
        portfolio = PortfolioState.initial(equity)
        stop = entry * (1 - stop_frac) if direction is Direction.LONG else entry * (1 + stop_frac)

        decision = engine.evaluate(
            signal=signal(direction=direction, confidence=confidence, entry=entry, stop=stop),
            portfolio=portfolio,
            quality=quality(),
            now=NOW,
        )
        if decision.allows_execution:
            risk = implied_risk(decision.approved_quantity, entry, stop)
            budget = equity * limits.max_risk_per_trade_pct / 100.0
            assert risk <= budget * 1.001


class TestSizing:
    def test_stop_on_the_wrong_side_is_refused(self) -> None:
        result = compute_size(
            equity=EQUITY,
            entry_price=100.0,
            stop_price=110.0,  # above entry, for a long
            direction=Direction.LONG,
            instrument=DEFAULT_UNIVERSE.require("BTC-USD"),
            risk_per_trade_pct=0.5,
            max_position_notional_pct=20.0,
            available_capital=EQUITY,
        )
        assert result.quantity_after_limits == 0.0
        assert result.limiting_constraint == "stop_above_entry_for_long"

    def test_minimum_stop_distance_bounds_the_quantity(self) -> None:
        result = compute_size(
            equity=EQUITY,
            entry_price=100.0,
            stop_price=100.0 * (1 - MIN_STOP_DISTANCE_PCT / 200.0),  # half the minimum
            direction=Direction.LONG,
            instrument=DEFAULT_UNIVERSE.require("BTC-USD"),
            risk_per_trade_pct=0.5,
            max_position_notional_pct=20.0,
            available_capital=EQUITY,
        )
        assert result.limiting_constraint == "stop_too_close"

    def test_available_capital_caps_the_position(self) -> None:
        result = compute_size(
            equity=EQUITY,
            entry_price=100.0,
            stop_price=99.0,
            direction=Direction.LONG,
            instrument=DEFAULT_UNIVERSE.require("BTC-USD"),
            risk_per_trade_pct=5.0,
            max_position_notional_pct=100.0,
            available_capital=1_000.0,
        )
        assert result.notional <= 1_000.0
        assert result.limiting_constraint == "available_capital"

    def test_non_positive_equity_is_a_bug_not_a_market_condition(self) -> None:
        from tia.core.errors import RiskError

        with pytest.raises(RiskError, match="non-positive"):
            compute_size(
                equity=0.0,
                entry_price=100.0,
                stop_price=99.0,
                direction=Direction.LONG,
                instrument=DEFAULT_UNIVERSE.require("BTC-USD"),
                risk_per_trade_pct=0.5,
                max_position_notional_pct=20.0,
                available_capital=0.0,
            )


class TestRiskState:
    def test_state_rolls_over_at_midnight(self) -> None:
        state = RiskState()
        state.record_trade("BTC-USD", NOW)
        assert state.trades_today == 1
        state.roll_day(NOW + timedelta(days=1))
        assert state.trades_today == 0
        assert state.trades_today_by_symbol == {}
