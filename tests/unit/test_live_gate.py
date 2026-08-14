"""The Live Activation Gate.

The gate is the last thing between a simulation and an account with money in it, so these
tests are written from the attacker's side: not "does it work when everything is fine?" but
"what is the cheapest way to get a live provider without the checks passing?"

Four answers the gate has to have:

* Forge a token → refused, the constructor checks an issuer sentinel.
* Skip a check by not reporting it → refused, absence is failure.
* Arm once and run forever → refused, tokens expire and are re-validated per order.
* Arm, then widen a risk limit → refused, the token is bound to a config fingerprint.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tia.core.clock import Clock, FrozenClock, SimulatedClock
from tia.core.config import RiskLimits
from tia.core.errors import LiveActivationError
from tia.execution.provider import ExecutionCapabilities, ExecutionProvider
from tia.live.gate import (
    CHECK_RATIONALE,
    CONFIRMATION_PHRASE,
    MAX_TTL_SECONDS,
    REQUIRED_CHECKS,
    CheckName,
    GateCheck,
    LiveActivationGate,
    LiveActivationToken,
    configuration_fingerprint,
    failing,
    passing,
)

START = datetime(2026, 8, 13, 9, 0, tzinfo=UTC)


def all_passing() -> dict[CheckName, GateCheck]:
    """Every check green. The tests below take things away from this."""
    return {name: passing(name, "verified") for name in REQUIRED_CHECKS}


def gate(clock: Clock | None = None) -> LiveActivationGate:
    return LiveActivationGate(clock or FrozenClock(START), environment="live")


def arm(engine: LiveActivationGate, probes=None, **overrides) -> LiveActivationToken:  # type: ignore[no-untyped-def]
    kwargs = {
        "operator": "elian",
        "confirmation": CONFIRMATION_PHRASE,
        "max_live_capital": 500.0,
        "fingerprint": "fp-1",
    }
    kwargs.update(overrides)
    return engine.arm(probes if probes is not None else all_passing(), **kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- absence


def test_an_unreported_check_fails_rather_than_defaulting_to_pass() -> None:
    """The most dangerous check is the one nobody wired up.

    A gate that treated a missing probe as neutral would arm a system whose reconciliation
    had never run, and would do it without a word.
    """
    report = gate().evaluate({})

    assert not report.passed
    assert len(report.unreported) == len(REQUIRED_CHECKS)
    assert all(not check.passed for check in report.checks)
    assert all(check.detail == "not reported" for check in report.unreported)


@pytest.mark.parametrize("missing", list(REQUIRED_CHECKS))
def test_removing_any_single_check_blocks_activation(missing: CheckName) -> None:
    """Every check is load-bearing. If dropping one still armed the gate, that check was
    decoration."""
    probes = all_passing()
    del probes[missing]

    with pytest.raises(LiveActivationError, match="LIVE REFUSED"):
        arm(gate(), probes)


@pytest.mark.parametrize("failed", list(REQUIRED_CHECKS))
def test_failing_any_single_check_blocks_activation(failed: CheckName) -> None:
    probes = all_passing()
    probes[failed] = failing(failed, "broken", "fix it")

    with pytest.raises(LiveActivationError) as exc:
        arm(gate(), probes)
    assert failed.value in str(exc.value)
    assert "fix it" in str(exc.value)


def test_every_check_carries_a_rationale_an_operator_can_act_on() -> None:
    """"reconciliation_healthy: false" tells nobody what to do next."""
    for name in REQUIRED_CHECKS:
        assert name in CHECK_RATIONALE
        assert len(CHECK_RATIONALE[name]) > 60


def test_a_probe_for_an_unknown_check_is_an_error_not_an_ignored_extra() -> None:
    """Caller and gate disagreeing about what is being checked is itself the bug."""
    probes = all_passing()
    probes["invented_check"] = passing(CheckName.TESTS_PASS, "x")  # type: ignore[index]

    with pytest.raises(ValueError, match="does not know about"):
        gate().evaluate(probes)


# --------------------------------------------------------------------------- forgery


def test_a_token_cannot_be_constructed_outside_the_gate() -> None:
    from tia.live.gate import GateReport

    with pytest.raises(LiveActivationError, match="only be issued by"):
        LiveActivationToken(
            issuer=object(),
            issued_at=START,
            expires_at=START + timedelta(hours=1),
            issued_by="attacker",
            environment="live",
            max_live_capital=1e9,
            configuration_fingerprint="fp-1",
            report=GateReport(checks=(), evaluated_at=START, environment="live"),
        )


def test_there_is_no_boolean_that_means_allowed_to_trade_live() -> None:
    """The gate is only a gate if a token is the *only* evidence of activation.

    A provider constructed with ``is_simulated=False`` and no token must fail, and there
    must be no keyword, flag or setting that substitutes for one.
    """
    live = type(
        "Live",
        (ExecutionProvider,),
        {name: (lambda self, *a, **k: None) for name in ExecutionProvider.__abstractmethods__},
    )

    with pytest.raises(LiveActivationError, match="LiveActivationToken"):
        live(ExecutionCapabilities(name="venue", is_simulated=False))


# --------------------------------------------------------------------------- ceremony


def test_arming_requires_the_exact_confirmation_phrase() -> None:
    for attempt in ("", "si", "yes", CONFIRMATION_PHRASE.lower(), CONFIRMATION_PHRASE[:-1]):
        with pytest.raises(LiveActivationError, match="confirmation phrase"):
            arm(gate(), confirmation=attempt)

    # Surrounding whitespace is forgiven; the phrase itself is not.
    assert arm(gate(), confirmation=f"  {CONFIRMATION_PHRASE}  ")


def test_arming_requires_a_named_operator() -> None:
    """An activation with nobody's name on it is one nobody decided to make."""
    with pytest.raises(LiveActivationError, match="named operator"):
        arm(gate(), operator="   ")


def test_arming_requires_a_deliberate_capital_ceiling() -> None:
    with pytest.raises(LiveActivationError, match="max_live_capital"):
        arm(gate(), max_live_capital=0.0)


def test_a_successful_arming_records_who_when_and_against_what() -> None:
    token = arm(gate())

    assert token.issued_by == "elian"
    assert token.issued_at == START
    assert token.max_live_capital == 500.0
    assert token.report.passed
    assert "secret" not in str(token.as_dict()).lower()


# --------------------------------------------------------------------------- expiry


def test_a_token_expires_and_the_expiry_is_enforced_per_order() -> None:
    """A gate that passed at nine says nothing about eleven.

    Checked on every order rather than once at construction, so an expiry stops the *next*
    order instead of being noticed at the next restart.
    """
    clock = SimulatedClock(START)
    token = arm(gate(clock))

    token.assert_usable(now=clock.now())

    clock.advance_by(timedelta(seconds=3599))
    token.assert_usable(now=clock.now())

    clock.advance_by(timedelta(seconds=2))
    with pytest.raises(LiveActivationError, match="expired"):
        token.assert_usable(now=clock.now())


def test_the_ttl_cannot_be_widened_past_the_ceiling() -> None:
    """A configurable expiry that can be set to a year is not an expiry."""
    engine = LiveActivationGate(FrozenClock(START), environment="live", ttl_seconds=10**9)
    assert engine.ttl_seconds == MAX_TTL_SECONDS


def test_a_live_provider_refuses_to_trade_once_its_activation_expires() -> None:
    clock = SimulatedClock(START)
    token = arm(gate(clock))
    live = type(
        "Live",
        (ExecutionProvider,),
        {name: (lambda self, *a, **k: None) for name in ExecutionProvider.__abstractmethods__},
    )
    provider = live(
        ExecutionCapabilities(name="venue", is_simulated=False), activation=token, clock=clock
    )

    provider.assert_may_trade()
    clock.advance_by(timedelta(hours=2))
    with pytest.raises(LiveActivationError, match="expired"):
        provider.assert_may_trade()


def test_a_live_provider_cannot_be_built_with_an_already_expired_token() -> None:
    clock = SimulatedClock(START)
    token = arm(gate(clock))
    clock.advance_by(timedelta(hours=2))

    live = type(
        "Live",
        (ExecutionProvider,),
        {name: (lambda self, *a, **k: None) for name in ExecutionProvider.__abstractmethods__},
    )
    with pytest.raises(LiveActivationError, match="expired"):
        live(
            ExecutionCapabilities(name="venue", is_simulated=False),
            activation=token,
            clock=clock,
        )


# --------------------------------------------------------------------------- fingerprint


def test_changing_a_risk_limit_after_arming_voids_the_token() -> None:
    """§17: nothing in the running system may raise a limit and then trade on it.

    The token carries a fingerprint of the limits the gate checked. If the active limits
    stop matching — by *any* mechanism, including one nobody anticipated — the token is
    dead. This is the structural half of "the system may propose limit changes and may
    never apply them".
    """
    limits = RiskLimits()
    before = configuration_fingerprint(limits)
    token = arm(gate(), fingerprint=before)

    token.assert_usable(now=START, fingerprint=before)

    widened = limits.propose_change(max_risk_per_trade_pct=5.0)
    after = configuration_fingerprint(widened)
    assert after != before

    with pytest.raises(LiveActivationError, match="changed after this activation"):
        token.assert_usable(now=START, fingerprint=after)


def test_the_fingerprint_is_stable_and_order_independent() -> None:
    """A fingerprint that changed on a dict reordering would void tokens at random, and a
    safety mechanism that fires at random gets disabled."""
    limits = RiskLimits()
    assert configuration_fingerprint(limits) == configuration_fingerprint(limits)
    assert configuration_fingerprint({"a": 1, "b": 2}) == configuration_fingerprint(
        {"b": 2, "a": 1}
    )
    assert configuration_fingerprint(limits, {"cap": 500.0}) != configuration_fingerprint(
        limits, {"cap": 501.0}
    )


# --------------------------------------------------------------------------- reporting


def test_the_report_serialises_without_secrets_and_explains_itself() -> None:
    probes = all_passing()
    probes[CheckName.FEES_VERIFIED_AT_SOURCE] = failing(
        CheckName.FEES_VERIFIED_AT_SOURCE,
        "fee schedule is a configured default",
        "read the fee tier from the account",
    )
    report = gate().evaluate(probes)
    payload = report.as_dict()

    assert payload["passed"] is False
    assert payload["failed"] == 1
    assert "LIVE REFUSED" in payload["explanation"]
    assert "read the fee tier" in payload["explanation"]


def test_a_passing_report_does_not_claim_the_strategy_is_profitable() -> None:
    """§63/§76: the gate checks machinery, not edge. Saying otherwise here would put a
    profitability claim in front of the user at the exact moment they are deciding."""
    explanation = gate().evaluate(all_passing()).explain()

    assert "known state" in explanation
    assert "does not mean the strategy is profitable" in explanation
