"""The boundary around the live market maker, checked structurally.

``tia.mm`` depends on the abstract execution provider and on nothing that can reach a
venue by itself: no concrete adapter, no HTTP client, no signing module, no gate. A
provider that claims to be live without a token is refused at every layer that sees it."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

import tia
from tia.core.clock import SimulatedClock
from tia.core.config import Environment, settings_for_env
from tia.core.errors import LiveActivationError
from tia.mm.execution import LiveMarketMakerExecution, SymbolFilters

MM_SRC = Path(tia.__file__).parent / "mm"
FORBIDDEN_IMPORT_ROOTS = ("tia.data.providers", "tia.live", "tia.api", "tia.runtime", "httpx", "ccxt", "requests", "aiohttp")
#: Modules the market maker may import from outside its own package.
ALLOWED_OUTSIDE = ("tia.core", "tia.domain", "tia.execution.provider", "tia.risk", "tia.mm")


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_no_market_maker_module_imports_a_venue_client_the_gate_or_the_api() -> None:
    offenders: list[str] = []
    for path in sorted(MM_SRC.glob("*.py")):
        for name in _imports(path):
            if name.startswith(FORBIDDEN_IMPORT_ROOTS):
                offenders.append(f"{path.name}: {name}")
            if name.startswith("tia.") and not name.startswith(ALLOWED_OUTSIDE):
                offenders.append(f"{path.name}: {name} (outside the allowed roots)")
    assert offenders == []


def test_only_the_execution_boundary_imports_the_abstract_provider() -> None:
    importers = sorted(p.name for p in MM_SRC.glob("*.py") if "tia.execution.provider" in _imports(p))
    assert importers == ["execution.py", "live_service.py"]
    # The public market-data socket is the one websocket user in the package, and it is
    # neither of the two modules that can reach an execution provider.
    sockets = sorted(p.name for p in MM_SRC.glob("*.py") if any(n.startswith("websockets") for n in _imports(p)))
    assert sockets == ["streams.py"]


def test_a_live_provider_without_a_token_is_refused_by_the_adapter_and_by_the_provider_layer() -> None:
    clock = SimulatedClock.__new__(SimulatedClock)
    impostor = SimpleNamespace(is_live=True, activation=None, name="impostor", get_trades=lambda **k: None, get_orders=lambda **k: None)
    filters = SymbolFilters(symbol="BTC-USD", tick_size=0.01, step_size=0.00001, min_qty=0.00001, max_qty=9000.0, min_notional=5.0)
    with pytest.raises(LiveActivationError, match="without an activation token"):
        LiveMarketMakerExecution(impostor, clock=clock, filters=filters, symbol="BTC-USD", run_tag="x")  # type: ignore[arg-type]
    from tia.execution.provider import ExecutionCapabilities, ExecutionProvider

    attempt = type("Attempt", (ExecutionProvider,), {name: (lambda self, *a, **k: None) for name in ExecutionProvider.__abstractmethods__})
    with pytest.raises(LiveActivationError, match="LiveActivationToken"):
        attempt(ExecutionCapabilities(name="whatever", is_simulated=False))


def test_no_environment_profile_turns_the_market_maker_live_and_the_flag_reads_nothing() -> None:
    for env in Environment:
        mm = settings_for_env(env).mm
        assert mm.real_money is False and mm.adaptive_enabled is False and mm.enabled is False
    readers = [p.name for p in MM_SRC.glob("*.py") if "real_money" in p.read_text(encoding="utf-8")]
    assert readers == []
