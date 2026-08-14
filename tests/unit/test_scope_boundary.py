"""The scope boundary.

This platform can now reach a real venue, which moves the boundary rather than removing
it. Three things must hold, and a sentence in a document does not make them hold — these
tests do, by walking the whole package: every module, every class, every source file.

1. **No provider goes live except through the gate.** Declaring ``is_simulated=False`` is
   not enough and never becomes enough; construction requires a token that only
   :meth:`~tia.live.gate.LiveActivationGate.arm` can mint.
2. **Nothing can move funds.** No source file names a withdrawal or transfer endpoint,
   and the permission checker refuses any key that is allowed to.
3. **The decision path stays deterministic.** No wall-clock reads where they would make a
   backtest irreproducible.

Several checks here are grep-shaped, which is unusual for a test suite and deliberate: a
structural check on imported objects cannot see an endpoint pasted into a string literal or
a credential read from an environment variable, and those are exactly the shapes that
matter. Where a token now legitimately appears — the Binance adapters have to name the
order endpoint they call — the allowance is a per-file list here, so the grep keeps its
value everywhere else and widening it is a visible diff.
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import pkgutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

import tia
from tia.core.clock import FrozenClock
from tia.core.config import Environment, settings_for_env
from tia.core.errors import LiveActivationError
from tia.execution.provider import ExecutionCapabilities, ExecutionProvider

PACKAGE_ROOT = Path(tia.__file__).parent


def _source_files() -> list[Path]:
    return sorted(p for p in PACKAGE_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def _import_every_module() -> list[str]:
    """Import the whole package so subclass registries are fully populated.

    A boundary check that only sees the modules a test happened to import is a boundary
    check with holes in it.
    """
    names: list[str] = []
    for info in pkgutil.walk_packages(tia.__path__, prefix="tia."):
        try:
            importlib.import_module(info.name)
        except ImportError as exc:  # pragma: no cover - optional extras
            pytest.skip(f"module {info.name} needs an optional dependency: {exc}")
        names.append(info.name)
    return names


def _all_subclasses(root: type) -> set[type]:
    found: set[type] = set()
    frontier = [root]
    while frontier:
        for child in frontier.pop().__subclasses__():
            if child not in found:
                found.add(child)
                frontier.append(child)
    return found


# --------------------------------------------------------------------------- the flags


def test_the_package_declares_its_unconditional_invariants() -> None:
    """Two properties that hold in every mode, simulated or live."""
    assert tia.NEVER_TAKES_CUSTODY is True
    assert tia.NEVER_WITHDRAWS is True
    assert tia.SIMULATED_BY_DEFAULT is True


def test_the_old_simulation_only_flag_is_gone_rather_than_left_lying() -> None:
    """A constant asserting something no longer true is worse than no constant.

    The platform gained a gated live path; a ``SIMULATION_ONLY = True`` left in place
    would read as a guarantee to anyone grepping for one.
    """
    assert not hasattr(tia, "SIMULATION_ONLY")


# --------------------------------------------------------------------------- providers


def _attempt_class() -> type[ExecutionProvider]:
    """A minimal concrete subclass, built from the ABC's own abstract-method set so that
    adding a method to the interface never quietly turns these tests into no-ops."""
    return type(
        "Attempt",
        (ExecutionProvider,),
        {name: (lambda self, *a, **k: None) for name in ExecutionProvider.__abstractmethods__},
    )


def test_no_provider_in_the_package_declares_itself_live_at_construction() -> None:
    """Live is a runtime decision made by the gate, never a hardcoded capability.

    A provider whose source hardcodes ``is_simulated=False`` would be one that is live by
    definition rather than by activation. The Binance adapter takes it as a parameter and
    is caught here if that ever changes.
    """
    _import_every_module()

    concrete = [
        cls
        for cls in _all_subclasses(ExecutionProvider)
        if not inspect.isabstract(cls)
        and cls.__module__.startswith("tia.")
        and "test" not in cls.__module__
    ]
    assert concrete, "no execution providers were discovered; the walk found nothing"

    for cls in concrete:
        source = inspect.getsource(cls)
        assert "is_simulated=False" not in source, (
            f"{cls.__name__} hardcodes itself live; liveness must come from the gate"
        )


def test_a_live_provider_cannot_be_constructed_without_an_activation_token() -> None:
    """The replacement for the old blanket prohibition, and the same kind of guarantee.

    Structural, not advisory: the base constructor raises, so no code path yields a live
    provider instance from a flag alone. The token is unforgeable (see
    :mod:`tia.live.gate`), so this cannot be satisfied by constructing one.
    """
    attempt = _attempt_class()

    with pytest.raises(LiveActivationError, match="LiveActivationToken"):
        attempt(ExecutionCapabilities(name="whatever", is_simulated=False))

    # ...and a simulator is constructible with no ceremony at all.
    assert attempt(ExecutionCapabilities(name="whatever")).capabilities.is_simulated


def test_an_activation_token_cannot_be_forged() -> None:
    """The gate is only a gate if the thing it issues cannot be made without it."""
    from tia.live.gate import GateReport, LiveActivationToken

    now = FrozenClock(datetime(2026, 8, 13, tzinfo=UTC)).now()
    with pytest.raises(LiveActivationError, match="only be issued by"):
        LiveActivationToken(
            issuer=object(),
            issued_at=now,
            expires_at=now,
            issued_by="attacker",
            environment="live",
            max_live_capital=1_000_000.0,
            configuration_fingerprint="whatever",
            report=GateReport(checks=(), evaluated_at=now, environment="live"),
        )


# --------------------------------------------------------------------------- credentials


#: Endpoints and parameters that move value out of the account. **No allowance list.**
#: Nothing in this package may name one, in any file, for any reason — not in a constant,
#: not in a comment, not in a docstring. A path string is one edit away from a request, and
#: the edit that adds it should have to delete this test first.
_FUND_MOVEMENT_TOKENS = (
    "/sapi/v1/capital/withdraw",
    "/sapi/v1/asset/transfer",
    "/sapi/v1/futures/transfer",
    "/sapi/v1/margin/isolated/transfer",
    "/sapi/v1/sub-account/transfer",
    "/sapi/v1/asset/dust",
    "/wapi/v3/withdraw",
    "withdraw/apply",
)
# Note: the tokens are deliberately *path*-shaped rather than word-shaped. Permission flag
# names like ``permitsUniversalTransfer`` must appear in the package — the checker whose
# job is to forbid them has to name them — and a word-shaped grep would flag the one module
# doing the right thing while missing a path assembled from a variable elsewhere.

#: Files permitted to name an order-placing endpoint, because placing orders is what they
#: are for. Everything else in the package is still forbidden from naming one: a
#: market-data client or a strategy module that mentions an order path is a mistake or
#: something worse.
_ORDER_ENDPOINT_ALLOWANCE = frozenset(
    {
        # Placing orders is what it is for.
        "data/providers/binance_live.py",
        # Names the order endpoints only to assign them request weights; it can neither
        # build a request nor sign one.
        "data/providers/binance_budget.py",
    }
)

#: Order-placing endpoints.
_ORDER_ENDPOINT_TOKENS = (
    "/api/v3/order",
    "/fapi/v1/order",
    "/v2/orders",
    "/sapi/v1/margin/order",
    "/api/v3/openorders",
    "/v1/orders",
)

#: The only two files permitted to name a *trading* credential: the one that loads it from
#: the environment, and the one that signs with it. Two, not one, because loading and using
#: are genuinely different jobs — but two is the whole list, which is what makes "which code
#: touches the secret?" a question with a one-line answer.
_SIGNING_ALLOWANCE = frozenset(
    {"data/providers/binance_signing.py", "core/config.py"}
)

_TRADING_CREDENTIAL_TOKENS = (
    "api_secret",
    "apisecret",
    "secret_key",
    "secretkey",
    "private_key",
    "signature=",
    "hmac_sha256",
    "x-mbx-apikey",
)


def _relative(path: Path) -> str:
    return path.relative_to(PACKAGE_ROOT).as_posix()


def test_nothing_in_the_package_names_a_way_to_move_funds() -> None:
    """The invariant that has no exceptions and is never getting one.

    A trading key that cannot withdraw makes this test redundant, and that is the point:
    two independent barriers, so that a mistake in either one is not sufficient. This is
    the cheaper of the two to verify and the harder to weaken by accident.
    """
    offenders: list[str] = []
    for path in _source_files():
        lowered = path.read_text(encoding="utf-8").lower()
        offenders.extend(
            f"{_relative(path)}: {token}"
            for token in _FUND_MOVEMENT_TOKENS
            if token in lowered
        )
    assert not offenders, (
        "fund-movement endpoints found in the package — this platform never withdraws or "
        f"transfers, in any mode: {offenders}"
    )


def test_the_permission_checker_refuses_a_key_that_can_withdraw() -> None:
    """The other barrier, at runtime: what the venue says the key may do."""
    from tia.live.permissions import check_permissions

    report = check_permissions(
        {
            "enableReading": True,
            "enableSpotAndMarginTrading": True,
            "enableWithdrawals": True,
        }
    )
    assert not report.acceptable
    assert any(problem.flag == "enableWithdrawals" for problem in report.problems)

    # An unrecognised, enabled flag whose name suggests fund movement is also refused —
    # the venue can add a permission faster than this list gets updated.
    invented = check_permissions(
        {
            "enableReading": True,
            "enableSpotAndMarginTrading": True,
            "enableInstantPayout": True,
        }
    )
    assert not invented.acceptable
    assert any(problem.unrecognised for problem in invented.problems)


def test_only_the_signing_module_carries_a_trading_credential_shape() -> None:
    offenders: list[str] = []
    for path in _source_files():
        if _relative(path) in _SIGNING_ALLOWANCE:
            continue
        lowered = path.read_text(encoding="utf-8").lower()
        offenders.extend(
            f"{_relative(path)}: {token}"
            for token in _TRADING_CREDENTIAL_TOKENS
            if token in lowered
        )
    assert not offenders, f"trading-credential shapes outside the signing module: {offenders}"


def test_only_the_live_adapter_names_an_order_placing_endpoint() -> None:
    offenders: list[str] = []
    for path in _source_files():
        if _relative(path) in _ORDER_ENDPOINT_ALLOWANCE:
            continue
        lowered = path.read_text(encoding="utf-8").lower()
        offenders.extend(
            f"{_relative(path)}: {token}"
            for token in _ORDER_ENDPOINT_TOKENS
            if token in lowered
        )
    assert not offenders, f"order endpoints outside the live adapter: {offenders}"


def test_the_allowance_lists_point_at_files_that_exist() -> None:
    """An allowance for a deleted file is an allowance nobody notices growing stale."""
    for allowed in (*_ORDER_ENDPOINT_ALLOWANCE, *_SIGNING_ALLOWANCE):
        assert (PACKAGE_ROOT / allowed).is_file(), (
            f"{allowed} is exempted from a boundary check but does not exist"
        )


def test_no_real_broker_sdk_is_imported() -> None:
    """A dependency is a decision. These are the libraries whose only purpose is to
    reach a live account, and none of them belongs in this package."""
    forbidden = {"ccxt", "alpaca", "alpaca_trade_api", "ib_insync", "ibapi", "oandapyV20"}
    offenders: list[str] = []

    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            for name in names:
                if name in forbidden:
                    offenders.append(f"{path.relative_to(PACKAGE_ROOT)}: {name}")

    assert not offenders, f"live-trading SDKs imported: {offenders}"


# --------------------------------------------------------------------------- the clock


#: Modules that compute or influence a trading decision. A wall-clock read anywhere in
#: here would make a backtest irreproducible, so the rule is absolute for them.
DECISION_PATH = (
    "core", "domain", "data", "quant", "regime", "strategy", "risk", "execution",
    "backtest", "llm", "events",
    # The economics of a trade, the capital it is sized against, and the gate that
    # decides whether it may be real. All three feed decisions; none may read the wall
    # clock, so that a replayed session reaches the same verdicts it reached live.
    "economics", "portfolio", "live",
    # Persistence belongs here rather than in the exemption: it *receives* timestamps
    # and never invents one, so a wall-clock read appearing in it would mean a stored
    # record disagreed with the decision it describes.
    "persistence",
)

#: Modules that serve HTTP and run the process. A session expiry, an uptime counter, a
#: rate-limit window and a log timestamp are wall-clock facts by nature; injecting a Clock
#: into them would add indirection without buying reproducibility, because none of them
#: feeds a decision. The exemption is listed here rather than left implicit.
OPERATIONAL = ("api", "runtime")


def _wall_clock_reads(path: Path) -> list[int]:
    """Line numbers of direct `datetime.now()` / `.utcnow()` / `date.today()` calls."""
    lines: list[int] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"now", "utcnow", "today", "time"}:
            continue
        value = node.func.value
        named = isinstance(value, ast.Name) and value.id in {"datetime", "date", "time"}
        attributed = isinstance(value, ast.Attribute) and value.attr in {"datetime", "date"}
        if named or attributed:
            lines.append(node.lineno)
    return lines


def test_the_decision_path_never_reads_the_wall_clock() -> None:
    """The property that makes a backtest reproducible.

    Every component that computes or influences a decision receives a ``Clock``. A stray
    wall-clock read is a non-determinism that only shows up as an unexplained difference
    between two runs of the same experiment — the hardest kind of bug to notice, because
    the numbers still look plausible.
    """
    offenders: list[str] = []
    for path in _source_files():
        if path.name == "clock.py":
            continue
        relative = path.relative_to(PACKAGE_ROOT)
        if not relative.parts or relative.parts[0] not in DECISION_PATH:
            continue
        offenders.extend(f"{relative}:{line}" for line in _wall_clock_reads(path))

    assert not offenders, f"wall-clock reads on the decision path: {offenders}"


def test_the_operational_layer_is_the_only_exemption() -> None:
    """Whatever wall-clock reads exist are confined to the modules listed as exempt.

    Stated as a test so the exemption cannot quietly widen: a new package that starts
    reading the wall clock fails here until it is either fixed or added to one of the two
    lists above, deliberately.
    """
    stray: list[str] = []
    for path in _source_files():
        if path.name == "clock.py":
            continue
        relative = path.relative_to(PACKAGE_ROOT)
        top = relative.parts[0] if len(relative.parts) > 1 else relative.name
        if top in DECISION_PATH or top in OPERATIONAL:
            continue
        stray.extend(f"{relative}:{line}" for line in _wall_clock_reads(path))

    assert not stray, (
        "a module outside both the decision path and the operational layer reads the "
        f"wall clock: {stray}"
    )


def test_every_package_is_classified() -> None:
    """No package may sit outside both lists unnoticed."""
    packages = {
        p.relative_to(PACKAGE_ROOT).parts[0]
        for p in _source_files()
        if len(p.relative_to(PACKAGE_ROOT).parts) > 1
    }
    unclassified = packages - set(DECISION_PATH) - set(OPERATIONAL)
    assert not unclassified, (
        f"these packages are in neither DECISION_PATH nor OPERATIONAL: {sorted(unclassified)}"
    )


async def test_runtime_decisions_are_stamped_by_the_simulated_clock() -> None:
    """The behavioural half of the rule.

    The runtime is exempt from the *structural* check because it stamps logs and run
    boundaries with wall-clock time. What must still hold is that its **decisions** carry
    simulated time — otherwise the exemption would have quietly swallowed the property it
    was meant to preserve.
    """
    from tia.core.config import Environment, settings_for_env
    from tia.runtime import RuntimeConfig, RuntimeEngine

    engine = RuntimeEngine(
        settings_for_env(Environment.DEMO),
        RuntimeConfig(scenario="trend_up", bar_interval_seconds=0.0, initial_capital=10_000.0),
    )
    await engine.start()
    for _ in range(400):
        await asyncio.sleep(0)
        if engine.counters.signals > 5:
            break
    await engine.stop()

    assert engine.recent_decisions, "the run produced no decisions to check"
    for row in list(engine.recent_decisions)[:20]:
        # SCENARIO_START is 2026-01-05; a wall-clock stamp would be the real current year.
        assert row["decided_at"].startswith("2026-01-05"), (
            f"a decision carried a wall-clock timestamp: {row['decided_at']}"
        )


# --------------------------------------------------------------------------- environment


def test_the_demo_environment_refuses_network_providers() -> None:
    """The zero-configuration path must be exercisable with no credentials and no
    egress, or "it works out of the box" is not a claim anyone can check."""
    demo = settings_for_env(Environment.DEMO)
    assert demo.market_data.provider in {"synthetic", "csv"}
    assert demo.env is Environment.DEMO
    assert demo.anthropic_api_key is None


def test_no_configuration_alone_enables_live_execution() -> None:
    """Configuration may *permit* live; it may never *be* the activation.

    The distinction is the whole design. A settings flag that turned on live trading would
    mean a copied ``.env``, a typo, or a container inheriting the wrong profile could put
    real money at risk with nobody deciding to. Liveness comes from a token minted by the
    gate after every check passed, and no environment profile can produce one.
    """
    for env in Environment:
        settings = settings_for_env(env)
        assert getattr(settings.execution, "allow_live", False) is False, (
            f"{env.value} appears to enable live execution from configuration alone"
        )


def test_the_gate_refuses_when_a_check_is_simply_not_reported() -> None:
    """Absence is failure. The most dangerous check is the one nobody wired up.

    A gate that defaulted unreported checks to pass would arm a system whose
    reconciliation had never run, and would do it silently.
    """
    from tia.live.gate import CheckName, LiveActivationGate, passing

    gate = LiveActivationGate(
        FrozenClock(datetime(2026, 8, 13, tzinfo=UTC)), environment="live"
    )
    report = gate.evaluate({CheckName.TESTS_PASS: passing(CheckName.TESTS_PASS, "green")})

    assert not report.passed
    assert len(report.unreported) == len(report.checks) - 1
    assert all(not check.passed for check in report.unreported)
