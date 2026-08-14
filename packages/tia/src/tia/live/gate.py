"""The Live Activation Gate.

This module is the boundary between "a simulation that might be right" and "an account
with real money in it". Everything else in the system can be wrong and cost nothing; past
this line, being wrong costs the user money.

The gate exists because the interesting failure is not a component that is broken — a
broken component announces itself. It is a component that is *unknown*: the reconciliation
that has not run yet, the fee schedule nobody checked, the strategy whose edge was measured
on eleven trades. Each of those looks exactly like health from the inside.

So the rule here is **absence is failure**. :data:`REQUIRED_CHECKS` names every condition
that must hold. A check that reports nothing is not neutral and does not default to pass —
it fails as ``not reported``, with the same force as a check that failed outright. Adding a
required check therefore breaks activation until someone wires up a probe for it, which is
the correct direction for that failure to point.

Three further properties, each chosen because the obvious design lacks it:

**The token cannot be forged.** :class:`LiveActivationToken` refuses construction outside
this module. There is no boolean anywhere that means "we are allowed to trade live" — the
only evidence is an object that the gate alone can mint, and minting requires every check
to have passed within the same call.

**The token expires.** A gate that passed at nine o'clock says nothing about eleven. Health
decays, connections drop, and a system that armed itself once and ran for a week on that
decision is a system that stopped checking. Tokens carry a TTL and the execution path
re-validates on every use.

**The token is bound to the configuration it was issued against.** The token carries a
fingerprint of the active risk limits and capital policy. If either changes after arming —
by any mechanism, including a mechanism nobody anticipated — the fingerprint no longer
matches and the token is dead. This is the structural half of the rule that says a model
may propose limit changes and never apply them: even if something did apply one, it could
not then trade on it.

**What this gate does not do.** It does not decide that a strategy is profitable, and
passing it is not evidence that it is. It is a check that the machinery is in a known-good
state, nothing more. A system in perfect health can lose money steadily.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from tia.core.clock import Clock
from tia.core.errors import LiveActivationError

#: Sentinel proving a token came from :meth:`LiveActivationGate.arm`. Module-private and
#: never exported: a token constructed anywhere else raises.
_ISSUER = object()

#: How long an activation stays valid before the gate must be re-run. One hour, because
#: that is roughly the timescale on which venue connectivity and data health change, and
#: because a re-check is cheap while a stale "everything is fine" is not.
DEFAULT_TTL_SECONDS = 3600

#: A ceiling on the TTL, so no configuration can turn the expiry into a formality.
MAX_TTL_SECONDS = 6 * 3600

#: The exact phrase an operator must type. Long and specific on purpose: a confirmation
#: that can be produced by hitting Enter is not a confirmation.
CONFIRMATION_PHRASE = "ACTIVAR TRADING REAL CON DINERO PROPIO"


class CheckName(StrEnum):
    """Every condition that must hold before real money is at risk.

    Each one is here because its absence has a specific, known way of losing money — the
    docstrings on :data:`CHECK_RATIONALE` say which.
    """

    TESTS_PASS = "tests_pass"  # noqa: S105 - a check name, not a credential
    MIGRATIONS_CURRENT = "migrations_current"
    MARKET_DATA_HEALTHY = "market_data_healthy"
    VENUE_CONNECTED = "venue_connected"
    VENUE_VALIDATION = "venue_validation"
    VALIDATION_FRESH = "validation_fresh"
    CLOCK_SKEW_OK = "clock_skew_ok"
    USER_DATA_STREAM = "user_data_stream"
    DATABASE_HEALTHY = "database_healthy"
    EXECUTION_HEALTHY = "execution_healthy"
    ORDER_IDEMPOTENCY = "order_idempotency"
    RISK_ENGINE_HEALTHY = "risk_engine_healthy"
    RECONCILIATION_HEALTHY = "reconciliation_healthy"
    CAPITAL_LEDGER_READY = "capital_ledger_ready"
    EDGE_PERSISTENCE = "edge_persistence"
    EV_ENFORCEMENT = "ev_enforcement"
    SECURITY_REVIEW = "security_review"
    CONFIGURATION_COHERENT = "configuration_coherent"
    OBSERVABILITY = "observability"
    FEES_VERIFIED_AT_SOURCE = "fees_verified_at_source"
    CAPITAL_POLICY_SET = "capital_policy_set"
    KILL_SWITCH_CLEAR = "kill_switch_clear"
    EMERGENCY_CONTROLS = "emergency_controls"
    RESTART_RECOVERY = "restart_recovery"
    CREDENTIALS_SCOPED = "credentials_scoped"
    EDGE_EVIDENCE = "edge_evidence"
    PAPER_TRACK_RECORD = "paper_track_record"


#: Why each check exists, in terms of the failure it prevents. Shown in the UI beside a
#: failing check, because "reconciliation_healthy: false" tells an operator nothing about
#: what to do next.
CHECK_RATIONALE: Mapping[CheckName, str] = {
    CheckName.TESTS_PASS: (
        "The suite passed against the exact commit that would trade. A green run from an "
        "earlier commit proves nothing about this one."
    ),
    CheckName.MARKET_DATA_HEALTHY: (
        "Decisions are made from prices. Trading on a stale or gapped feed is trading on a "
        "market that no longer exists."
    ),
    CheckName.VENUE_CONNECTED: (
        "An order sent into a dropped connection has an unknown state, and an unknown "
        "order state is the precondition for a duplicate."
    ),
    CheckName.DATABASE_HEALTHY: (
        "The order journal is what makes a retry safe. Without it, a restart cannot tell a "
        "sent order from an unsent one."
    ),
    CheckName.EXECUTION_HEALTHY: (
        "The order state machine must be able to accept, track and cancel. A degraded "
        "execution path can open a position it cannot close."
    ),
    CheckName.RISK_ENGINE_HEALTHY: (
        "The risk engine holds the veto. If it is not evaluating, nothing is stopping a bad "
        "trade — the rest of the system has no opinion about size."
    ),
    CheckName.RECONCILIATION_HEALTHY: (
        "Our picture of the account must match the venue's. A divergence means one of the "
        "two is wrong about what we own, and position sizing runs off the wrong one."
    ),
    CheckName.SECURITY_REVIEW: (
        "No secret in logs, config or frontend bundle; API key scoped without withdrawal "
        "permission. A leaked trading key is a total loss, not a degraded service."
    ),
    CheckName.FEES_VERIFIED_AT_SOURCE: (
        "Fees must be read from the account, not configured. A fee tier guessed 5 bps low "
        "turns a losing strategy into a winning-looking one on paper only."
    ),
    CheckName.CAPITAL_POLICY_SET: (
        "max_live_capital must be set deliberately. Without a ceiling, the amount at risk "
        "is whatever happens to be in the account."
    ),
    CheckName.KILL_SWITCH_CLEAR: (
        "Arming while halted would discard the reason something halted it."
    ),
    CheckName.CREDENTIALS_SCOPED: (
        "The API key must have trading permission and must NOT have withdrawal or transfer "
        "permission. This is checked against the venue, not assumed from configuration."
    ),
    CheckName.EDGE_EVIDENCE: (
        "The expected-value engine must have enough closed trades to estimate an edge. "
        "Going live with no measured edge is not trading, it is donating."
    ),
    CheckName.PAPER_TRACK_RECORD: (
        "The same code must have run in paper mode long enough — in days AND in closed "
        "trades — to have exercised its own failure paths. Live is not the place to "
        "discover the first reconnect."
    ),
    CheckName.MIGRATIONS_CURRENT: (
        "The database schema must be at the exact version this build expects. A schema "
        "one migration behind reads plausibly and wrongly."
    ),
    CheckName.VENUE_VALIDATION: (
        "The venue-validation record must exist, match its schema, name this environment "
        "and symbol, and carry an intact fingerprint. A hand-edited or truncated record "
        "satisfying the gate would make every downstream check decorative."
    ),
    CheckName.VALIDATION_FRESH: (
        "Venue facts age: fee tiers change, permissions get edited, filters move. A "
        "validation older than the freshness bound proves what was true then, not now."
    ),
    CheckName.CLOCK_SKEW_OK: (
        "Signed requests are rejected outside recvWindow, and the venue's error does not "
        "mention the clock. The skew must have been measured, recently, and be small."
    ),
    CheckName.USER_DATA_STREAM: (
        "Order updates must have a working delivery path from the venue. Without one, "
        "fills are discovered by polling — later, and sometimes not at all."
    ),
    CheckName.ORDER_IDEMPOTENCY: (
        "The venue must demonstrably reject a duplicate clientOrderId. If it does not, a "
        "retry after a timeout can open a second position, and the local dedup is the "
        "only barrier left."
    ),
    CheckName.CAPITAL_LEDGER_READY: (
        "The capital ledger is what keeps a deposit from being booked as profit and an "
        "unexplained balance from being traded against. Live cannot start without it "
        "wired and unhalted."
    ),
    CheckName.EDGE_PERSISTENCE: (
        "Evidence must survive a restart. A system whose track record lives in process "
        "memory becomes a fresh system at every deploy while claiming otherwise."
    ),
    CheckName.EV_ENFORCEMENT: (
        "In live mode the expected-value gate must enforce, structurally. A signal "
        "without a measured edge that clears its costs must not become an order."
    ),
    CheckName.CONFIGURATION_COHERENT: (
        "The live configuration must be internally consistent: a symbol, a venue, a "
        "positive ceiling, and no placeholder secrets. Incoherent configuration fails "
        "at the worst possible moment, which is mid-session."
    ),
    CheckName.OBSERVABILITY: (
        "A live session nobody can observe is a live session nobody can stop in time. "
        "Metrics, logs and the event stream must be on."
    ),
    CheckName.EMERGENCY_CONTROLS: (
        "The kill switch and emergency flatten must exist, be reachable without the "
        "model, and be covered by passing tests. An untested emergency control is a "
        "hope, not a control."
    ),
    CheckName.RESTART_RECOVERY: (
        "A crash mid-session must be recoverable: state reloaded, orders deduplicated, "
        "books reconciled. Proven by the restart-recovery test having passed, not by "
        "intention."
    ),
}

#: Every check is required. There is no optional tier — an optional safety check is a
#: check that gets turned off on the day it would have mattered.
REQUIRED_CHECKS: tuple[CheckName, ...] = tuple(CheckName)


@dataclass(frozen=True)
class GateCheck:
    """One condition, its verdict, and what to do about it."""

    name: CheckName
    passed: bool
    detail: str
    #: What the operator should do if it failed. Empty when it passed.
    remedy: str = ""
    #: False when no probe reported this check at all, which is distinct from a probe that
    #: ran and said no — and worth distinguishing, because the fixes differ.
    reported: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name.value,
            "passed": self.passed,
            "reported": self.reported,
            "detail": self.detail,
            "remedy": self.remedy,
            "rationale": CHECK_RATIONALE[self.name],
        }


@dataclass(frozen=True)
class GateReport:
    """The full result of running the gate. Safe to show, safe to store, no secrets."""

    checks: tuple[GateCheck, ...]
    evaluated_at: datetime
    environment: str

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failures(self) -> tuple[GateCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)

    @property
    def unreported(self) -> tuple[GateCheck, ...]:
        return tuple(check for check in self.checks if not check.reported)

    def explain(self) -> str:
        if self.passed:
            return (
                f"All {len(self.checks)} activation checks passed at "
                f"{self.evaluated_at.isoformat()}. This means the machinery is in a known "
                "state. It does not mean the strategy is profitable."
            )
        lines = [
            f"LIVE REFUSED — {len(self.failures)} of {len(self.checks)} checks did not pass:"
        ]
        lines.extend(
            f"  - {check.name.value}: {check.detail}"
            + (f" -> {check.remedy}" if check.remedy else "")
            for check in self.failures
        )
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "evaluated_at": self.evaluated_at.isoformat(),
            "environment": self.environment,
            "total": len(self.checks),
            "failed": len(self.failures),
            "unreported": [check.name.value for check in self.unreported],
            "checks": [check.as_dict() for check in self.checks],
            "explanation": self.explain(),
        }


def configuration_fingerprint(*parts: Any) -> str:
    """A stable hash of everything that must not change under a live session.

    Pydantic models, dataclasses and plain mappings all reduce to sorted JSON, so the
    fingerprint is order-independent and survives a restart. Any change to a risk limit or
    a capital ceiling changes this value, which invalidates every token issued against the
    old one — including tokens held by objects that never look at configuration directly.
    """
    payload: list[Any] = []
    for part in parts:
        if hasattr(part, "model_dump"):
            payload.append(part.model_dump(mode="json"))
        elif hasattr(part, "__dict__"):
            payload.append({k: str(v) for k, v in sorted(vars(part).items())})
        else:
            payload.append(part)
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.blake2s(encoded, digest_size=16).hexdigest()


@dataclass(frozen=True)
class LiveActivationToken:
    """Proof that the gate passed, bound to a moment and a configuration.

    Constructible only by :meth:`LiveActivationGate.arm`. Everything that could plausibly
    want to bypass the gate — a test fixture, a debug endpoint, a helpfully-written
    adapter — has to go through the gate instead, because there is no other way to obtain
    one of these.
    """

    issuer: Any
    issued_at: datetime
    expires_at: datetime
    issued_by: str
    environment: str
    max_live_capital: float
    configuration_fingerprint: str
    report: GateReport

    def __post_init__(self) -> None:
        if self.issuer is not _ISSUER:
            raise LiveActivationError(
                "a live activation token may only be issued by LiveActivationGate.arm(). "
                "Constructing one directly would defeat every check the gate performs."
            )

    def is_valid_at(self, moment: datetime) -> bool:
        return self.issued_at <= moment < self.expires_at

    def seconds_remaining(self, moment: datetime) -> float:
        return max(0.0, (self.expires_at - moment).total_seconds())

    def assert_usable(self, *, now: datetime, fingerprint: str | None = None) -> None:
        """Raise unless this token is still good. Called on every live order.

        Checked per order rather than per session: a session that validated once at start
        would happily keep trading through an expiry and through a configuration change.
        """
        if not self.is_valid_at(now):
            raise LiveActivationError(
                f"the live activation issued at {self.issued_at.isoformat()} expired at "
                f"{self.expires_at.isoformat()}. Re-run the activation gate; do not extend "
                "the token."
            )
        if fingerprint is not None and fingerprint != self.configuration_fingerprint:
            raise LiveActivationError(
                "risk limits or capital policy changed after this activation was issued. "
                "The token is void. Nothing may trade live on limits that were not the "
                "ones the gate checked."
            )

    def as_dict(self) -> dict[str, Any]:
        """Serialisable form. Carries no secret — a token proves a state, it grants no
        access to anything by itself."""
        return {
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "issued_by": self.issued_by,
            "environment": self.environment,
            "max_live_capital": self.max_live_capital,
            "configuration_fingerprint": self.configuration_fingerprint,
        }


class LiveActivationGate:
    """Runs the checks and, only if all of them pass, mints a token.

    Probes are supplied by the caller as ``{CheckName: (passed, detail, remedy)}`` rather
    than reached for internally, so the gate is testable and so the wiring of each probe is
    visible at the call site instead of hidden in here.
    """

    def __init__(
        self,
        clock: Clock,
        *,
        environment: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._clock = clock
        self._environment = environment
        self._ttl = min(ttl_seconds, MAX_TTL_SECONDS)
        self._last_report: GateReport | None = None

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    @property
    def last_report(self) -> GateReport | None:
        return self._last_report

    def evaluate(self, probes: Mapping[CheckName, GateCheck]) -> GateReport:
        """Run every required check. Unreported checks fail.

        Deliberately takes the full probe map and ignores nothing: a probe for a check that
        is not required raises, because it means the caller and the gate disagree about
        what is being checked.
        """
        unknown = set(probes) - set(REQUIRED_CHECKS)
        if unknown:
            raise ValueError(
                f"probes supplied for checks the gate does not know about: {sorted(unknown)}"
            )

        checks: list[GateCheck] = []
        for name in REQUIRED_CHECKS:
            probe = probes.get(name)
            if probe is None:
                checks.append(
                    GateCheck(
                        name=name,
                        passed=False,
                        detail="not reported",
                        remedy=(
                            "wire up a probe for this check; an unreported check is treated "
                            "as failed and never as passed"
                        ),
                        reported=False,
                    )
                )
            else:
                checks.append(replace(probe, name=name))

        report = GateReport(
            checks=tuple(checks),
            evaluated_at=self._clock.now(),
            environment=self._environment,
        )
        self._last_report = report
        return report

    def arm(
        self,
        probes: Mapping[CheckName, GateCheck],
        *,
        operator: str,
        confirmation: str,
        max_live_capital: float,
        fingerprint: str,
    ) -> LiveActivationToken:
        """Mint a token, or raise explaining exactly what stopped it.

        The confirmation phrase and the named operator are required and are not
        conveniences: an activation with nobody's name on it is an activation nobody
        decided to make.
        """
        report = self.evaluate(probes)

        if not operator.strip():
            raise LiveActivationError(
                "arming live trading requires a named operator. An unattributed activation "
                "is one nobody is accountable for."
            )
        if confirmation.strip() != CONFIRMATION_PHRASE:
            raise LiveActivationError(
                "the confirmation phrase does not match. Type it exactly: "
                f"{CONFIRMATION_PHRASE!r}"
            )
        if max_live_capital <= 0:
            raise LiveActivationError(
                "max_live_capital must be a positive amount, set deliberately before arming"
            )
        if not report.passed:
            raise LiveActivationError(report.explain())

        now = self._clock.now()
        return LiveActivationToken(
            issuer=_ISSUER,
            issued_at=now,
            expires_at=now + timedelta(seconds=self._ttl),
            issued_by=operator.strip(),
            environment=self._environment,
            max_live_capital=max_live_capital,
            configuration_fingerprint=fingerprint,
            report=report,
        )


def passing(name: CheckName, detail: str) -> GateCheck:
    """Shorthand for a probe that succeeded."""
    return GateCheck(name=name, passed=True, detail=detail)


def failing(name: CheckName, detail: str, remedy: str = "") -> GateCheck:
    """Shorthand for a probe that failed."""
    return GateCheck(name=name, passed=False, detail=detail, remedy=remedy)


__all__ = [
    "CHECK_RATIONALE",
    "CONFIRMATION_PHRASE",
    "DEFAULT_TTL_SECONDS",
    "MAX_TTL_SECONDS",
    "REQUIRED_CHECKS",
    "CheckName",
    "GateCheck",
    "GateReport",
    "LiveActivationGate",
    "LiveActivationToken",
    "configuration_fingerprint",
    "failing",
    "passing",
]
