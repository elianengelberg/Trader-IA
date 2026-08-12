"""Trader-IA — autonomous quantitative research and paper-trading platform.

**Simulation only.** This package contains no adapter to any real trading venue and none
may be added: every ``ExecutionProvider`` implementation here is a simulator. See
``docs/ARCHITECTURE.md`` §1 and ``docs/SECURITY.md`` §1.

Nothing in this package makes a claim about future returns. Backtest and paper-trading
results describe what an experiment produced under stated conditions, nothing more.
"""

__version__ = "0.1.0"

SIMULATION_ONLY = True
"""Invariant asserted by ``tests/unit/test_scope_boundary.py``."""

__all__ = ["SIMULATION_ONLY", "__version__"]
