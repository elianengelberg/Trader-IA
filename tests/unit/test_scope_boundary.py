"""The scope boundary.

``docs/ARCHITECTURE.md`` §1 says this platform is simulation-only and that no adapter to
a real trading venue may be added. A sentence in a document does not stop anyone; these
tests do. They walk the whole package — every module, every class, every source file —
and fail if the boundary has been crossed.

Two of the checks here are grep-shaped, which is unusual for a test suite and deliberate:
a structural check on imported objects cannot see a credential read from an environment
variable or an order endpoint pasted into a string literal, and those are exactly the
shapes the boundary is meant to catch.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from pathlib import Path

import pytest

import tia
from tia.core.config import Environment, settings_for_env
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


# --------------------------------------------------------------------------- the flag


def test_the_package_declares_itself_simulation_only() -> None:
    assert tia.SIMULATION_ONLY is True


# --------------------------------------------------------------------------- providers


def test_every_execution_provider_in_the_package_is_a_simulator() -> None:
    """The claim in ``tia/execution/provider.py`` made checkable.

    Any concrete provider added later is caught here unless it declares itself
    simulated — and it cannot declare otherwise, because the constructor refuses.
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
        assert "is_simulated=False" not in source, f"{cls.__name__} claims to be live"


def test_a_live_provider_cannot_be_constructed_at_all() -> None:
    """Structural, not advisory: the base constructor raises, so there is no code path
    that yields a non-simulated provider instance."""

    # Built from the ABC's own abstract-method set so that adding a method to the
    # interface never quietly turns this test into a no-op.
    attempt = type(
        "Attempt",
        (ExecutionProvider,),
        {name: (lambda self, *a, **k: None) for name in ExecutionProvider.__abstractmethods__},
    )

    with pytest.raises(ValueError, match="simulation-only"):
        attempt(ExecutionCapabilities(name="whatever", is_simulated=False))

    # ...and the same class is constructible when it declares the truth.
    assert attempt(ExecutionCapabilities(name="whatever")).capabilities.is_simulated


# --------------------------------------------------------------------------- credentials


#: Parameter and field names that would only exist to authenticate a *trading* account.
#: Public market data on the venues this project reads needs none of them.
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

#: Order-placing endpoints. A market-data client has no reason to name one.
_ORDER_ENDPOINT_TOKENS = (
    "/api/v3/order",
    "/fapi/v1/order",
    "/v2/orders",
    "/sapi/v1/margin/order",
    "/api/v3/openorders",
    "/v1/orders",
)


def test_no_source_file_carries_a_trading_credential_shape() -> None:
    offenders: list[str] = []
    for path in _source_files():
        lowered = path.read_text(encoding="utf-8").lower()
        for token in _TRADING_CREDENTIAL_TOKENS:
            if token in lowered:
                offenders.append(f"{path.relative_to(PACKAGE_ROOT)}: {token}")
    assert not offenders, f"trading-credential shapes found in the package: {offenders}"


def test_no_source_file_names_an_order_placing_endpoint() -> None:
    offenders: list[str] = []
    for path in _source_files():
        lowered = path.read_text(encoding="utf-8").lower()
        for token in _ORDER_ENDPOINT_TOKENS:
            if token in lowered:
                offenders.append(f"{path.relative_to(PACKAGE_ROOT)}: {token}")
    assert not offenders, f"order endpoints found in the package: {offenders}"


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


def test_nothing_outside_the_clock_module_reads_the_wall_clock() -> None:
    """``tia/core/clock.py`` claims no component calls ``datetime.now()`` directly.

    That claim is what makes a backtest reproducible: a stray wall-clock read is a
    non-determinism that only shows up as an unexplained difference between two runs of
    the same experiment.
    """
    offenders: list[str] = []
    for path in _source_files():
        if path.name == "clock.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"now", "utcnow", "today", "time"}:
                continue
            value = node.func.value
            named = isinstance(value, ast.Name) and value.id in {"datetime", "date", "time"}
            attributed = isinstance(value, ast.Attribute) and value.attr in {
                "datetime",
                "date",
            }
            if named or attributed:
                offenders.append(f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno}")

    assert not offenders, f"direct wall-clock reads outside the clock module: {offenders}"


# --------------------------------------------------------------------------- environment


def test_the_demo_environment_refuses_network_providers() -> None:
    """The zero-configuration path must be exercisable with no credentials and no
    egress, or "it works out of the box" is not a claim anyone can check."""
    demo = settings_for_env(Environment.DEMO)
    assert demo.market_data.provider in {"synthetic", "csv"}
    assert demo.env is Environment.DEMO
    assert demo.anthropic_api_key is None


def test_no_environment_enables_live_execution() -> None:
    for env in Environment:
        settings = settings_for_env(env)
        assert getattr(settings.execution, "allow_live", False) is False, (
            f"{env.value} appears to enable live execution"
        )
