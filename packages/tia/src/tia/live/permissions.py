"""API key permissions, checked against the venue rather than assumed.

The single worst outcome available to this system is not a losing trade. It is an API key
with withdrawal permission ending up somewhere it should not be — because a losing trade
costs a fraction of the account and a compromised withdrawal key costs all of it, instantly
and irreversibly.

So the rule is not "we do not call the withdrawal endpoint". That is a promise about code,
and code changes. The rule is **the key must not be able to withdraw at all**, verified by
asking the venue what the key is permitted to do and refusing to trade if the answer
includes moving funds anywhere.

**The unknown-permission rule.** Venues add permissions. A checker that enumerates the
flags it knows about will silently approve a flag invented after it was written, and the
flag most likely to be invented is another way to move money. So this module treats an
*unrecognised* flag that is enabled and whose name matches a fund-movement shape as
forbidden. False positives are cheap here — someone reads a message and adds an entry to a
list. A false negative is the whole account.

Nothing in this module reads, stores, logs or transports a secret. It handles a
description of what a key may do, never the key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: Flags that must be enabled, or the system cannot do its job. Named in the venue's own
#: vocabulary so the mapping from a permissions screenshot to this list is one-to-one.
REQUIRED_PERMISSIONS: tuple[str, ...] = (
    "enableReading",
    "enableSpotAndMarginTrading",
)

#: Flags that must be disabled. Every one of these permits value to leave the account.
FORBIDDEN_PERMISSIONS: tuple[str, ...] = (
    "enableWithdrawals",
    "enableInternalTransfer",
    "permitsUniversalTransfer",
)

#: Flags that must be disabled because they expose leverage this system does not model.
#: A spot strategy running on a key with futures permission is one bug away from a
#: liquidation, and the risk engine's sizing assumes it cannot happen.
FORBIDDEN_LEVERAGE_PERMISSIONS: tuple[str, ...] = (
    "enableFutures",
    "enableMargin",
    "enableVanillaOptions",
)

#: Name shapes that mean "this moves money". Applied to any flag not otherwise recognised.
_FUND_MOVEMENT_PATTERN = re.compile(
    r"withdraw|transfer|payout|remit|send|redeem|convert|borrow|repay|loan|lend",
    re.IGNORECASE,
)

#: Everything below is the documented shape of Binance's API-restriction response.
#: REQUIRES VALIDATION — this environment has no egress to any Binance host, so the field
#: names here were written from documentation and have not been confirmed against a live
#: response. ``scripts/validate_binance.py`` confirms them; until it has been run against a
#: real key, ``PermissionReport.verified_at_source`` stays False and the activation gate
#: refuses to arm.
_KNOWN_FLAGS: frozenset[str] = frozenset(
    (
        *REQUIRED_PERMISSIONS,
        *FORBIDDEN_PERMISSIONS,
        *FORBIDDEN_LEVERAGE_PERMISSIONS,
        "ipRestrict",
        "enableSpotAndMarginTrading",
        "enablePortfolioMarginTrading",
        "enableFixApiTrade",
        "enableFixReadOnly",
        "createTime",
        "tradingAuthorityExpirationTime",
    )
)


@dataclass(frozen=True)
class PermissionProblem:
    flag: str
    detail: str
    #: True when the flag was not in the known set and was rejected by name shape. Worth
    #: surfacing separately: it means this module is out of date, not that the user did
    #: something wrong.
    unrecognised: bool = False


@dataclass(frozen=True)
class PermissionReport:
    """What the key may do, and whether that is acceptable."""

    problems: tuple[PermissionProblem, ...]
    ip_restricted: bool
    verified_at_source: bool
    checked_flags: tuple[str, ...]

    @property
    def acceptable(self) -> bool:
        return not self.problems and self.verified_at_source

    def explain(self) -> str:
        if not self.verified_at_source:
            return (
                "API key permissions have not been read from the venue. Until they have, "
                "the system treats the key as potentially able to withdraw and refuses to "
                "trade live."
            )
        if not self.problems:
            note = "" if self.ip_restricted else (
                " Note: the key is not IP-restricted. Restricting it to your server's IP is "
                "the single cheapest reduction in blast radius available and is strongly "
                "recommended, though not required by this check."
            )
            return (
                f"The key can trade and cannot move funds. {len(self.checked_flags)} flags "
                f"checked.{note}"
            )
        lines = ["The API key permissions are not acceptable for live trading:"]
        lines.extend(f"  - {problem.flag}: {problem.detail}" for problem in self.problems)
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {
            "acceptable": self.acceptable,
            "verified_at_source": self.verified_at_source,
            "ip_restricted": self.ip_restricted,
            "checked_flags": list(self.checked_flags),
            "problems": [
                {
                    "flag": problem.flag,
                    "detail": problem.detail,
                    "unrecognised": problem.unrecognised,
                }
                for problem in self.problems
            ],
            "explanation": self.explain(),
        }


def check_permissions(
    restrictions: dict[str, Any], *, verified_at_source: bool = True
) -> PermissionReport:
    """Judge a permissions payload read from the venue.

    ``restrictions`` is the venue's own response, passed through unmodified. Interpreting
    it here rather than at the call site keeps the decision in one auditable place.
    """
    problems: list[PermissionProblem] = []

    for flag in REQUIRED_PERMISSIONS:
        if not _truthy(restrictions.get(flag)):
            problems.append(
                PermissionProblem(
                    flag=flag,
                    detail=(
                        "required but not enabled; the system cannot read prices or place "
                        "orders without it"
                    ),
                )
            )

    for flag in FORBIDDEN_PERMISSIONS:
        if _truthy(restrictions.get(flag)):
            problems.append(
                PermissionProblem(
                    flag=flag,
                    detail=(
                        "FORBIDDEN — this permits funds to leave the account. Disable it in "
                        "the venue's API management screen and re-check. The system will "
                        "not trade with a key that can move money."
                    ),
                )
            )

    for flag in FORBIDDEN_LEVERAGE_PERMISSIONS:
        if _truthy(restrictions.get(flag)):
            problems.append(
                PermissionProblem(
                    flag=flag,
                    detail=(
                        "forbidden — this system models spot positions only, and its "
                        "position sizing assumes no leverage and no liquidation"
                    ),
                )
            )

    for flag, value in restrictions.items():
        if flag in _KNOWN_FLAGS or not _truthy(value):
            continue
        if _FUND_MOVEMENT_PATTERN.search(flag):
            problems.append(
                PermissionProblem(
                    flag=flag,
                    detail=(
                        "unrecognised permission whose name suggests it can move funds, and "
                        "it is enabled. Treated as forbidden until someone confirms what it "
                        "does. If it is harmless, add it to the known set deliberately."
                    ),
                    unrecognised=True,
                )
            )

    return PermissionReport(
        problems=tuple(problems),
        ip_restricted=_truthy(restrictions.get("ipRestrict")),
        verified_at_source=verified_at_source,
        checked_flags=tuple(sorted(restrictions)),
    )


def _truthy(value: Any) -> bool:
    """Venues are inconsistent about booleans; ``"false"`` is not falsy in Python."""
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


__all__ = [
    "FORBIDDEN_LEVERAGE_PERMISSIONS",
    "FORBIDDEN_PERMISSIONS",
    "REQUIRED_PERMISSIONS",
    "PermissionProblem",
    "PermissionReport",
    "check_permissions",
]
