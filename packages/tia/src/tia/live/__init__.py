"""The live boundary.

Two modules, both concerned with the same question: is it acceptable, right now, for this
process to send an order that spends the user's money?

* :mod:`tia.live.gate` — the activation gate and its unforgeable, expiring token.
* :mod:`tia.live.permissions` — what the venue says the API key is allowed to do, and the
  refusal to trade with a key that can withdraw.

Nothing here executes anything. This package decides whether execution is permitted; the
execution adapters ask it and obey.
"""

from tia.live.gate import (
    CONFIRMATION_PHRASE,
    REQUIRED_CHECKS,
    CheckName,
    GateCheck,
    GateReport,
    LiveActivationGate,
    LiveActivationToken,
    configuration_fingerprint,
    failing,
    passing,
)
from tia.live.permissions import PermissionReport, check_permissions

__all__ = [
    "CONFIRMATION_PHRASE",
    "REQUIRED_CHECKS",
    "CheckName",
    "GateCheck",
    "GateReport",
    "LiveActivationGate",
    "LiveActivationToken",
    "PermissionReport",
    "check_permissions",
    "configuration_fingerprint",
    "failing",
    "passing",
]
