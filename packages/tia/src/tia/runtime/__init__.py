"""The paper-trading runtime and its demo scenarios."""

from tia.runtime.engine import Counters, RuntimeConfig, RuntimeEngine, RuntimeState
from tia.runtime.scenarios import (
    SCENARIOS,
    Scenario,
    ScenarioId,
    generate_series,
    get_scenario,
    scenario_catalogue,
)

__all__ = [
    "SCENARIOS",
    "Counters",
    "RuntimeConfig",
    "RuntimeEngine",
    "RuntimeState",
    "Scenario",
    "ScenarioId",
    "generate_series",
    "get_scenario",
    "scenario_catalogue",
]
