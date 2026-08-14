"""Trader-IA — autonomous quantitative research and trading platform.

**Simulated by default; live only through the gate.** Every execution provider in this
package is a simulator unless it holds a
:class:`~tia.live.gate.LiveActivationToken`, which
:meth:`~tia.live.gate.LiveActivationGate.arm` issues only when every activation check has
passed. See ``docs/LIVE_TRADING.md`` and ``docs/SECURITY.md``.

Two invariants below hold unconditionally, in every mode, and are asserted by
``tests/unit/test_scope_boundary.py``:

**No custody.** Funds stay at the venue. This platform never holds, receives or stores
money, and there is no wallet, no balance it controls, and no account it can pay into.

**No withdrawals, ever.** The API key must not have withdrawal or transfer permission —
checked against the venue by :func:`tia.live.permissions.check_permissions`, which refuses
to trade with a key that can move funds — and no source file in this package names a
withdrawal or transfer endpoint, which the boundary test enforces by inspection.

Nothing in this package makes a claim about future returns. Backtest, paper-trading and
live results describe what happened under stated conditions, nothing more.
"""

__version__ = "0.2.0"

SIMULATED_BY_DEFAULT = True
"""Execution is simulated unless a live activation token was minted by the gate."""

NEVER_TAKES_CUSTODY = True
"""The platform never holds user funds. They remain at the venue at all times."""

NEVER_WITHDRAWS = True
"""No code path withdraws or transfers funds, and the API key must not be able to."""

__all__ = [
    "NEVER_TAKES_CUSTODY",
    "NEVER_WITHDRAWS",
    "SIMULATED_BY_DEFAULT",
    "__version__",
]
