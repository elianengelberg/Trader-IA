"""R24-H1 — the contract of ``incidents.kind``, checked without a database.

PostgreSQL enforces ``VARCHAR(n)``; SQLite does not. The column was ``VARCHAR(32)`` while the
live runtime wrote ``entries_blocked:protection_unverified`` (37 characters): every SQLite
suite stored it, production refused it, and the incident was lost. One constant now sizes the
column and the repository's check, and this file pins that every kind the code can write is
within it — by reading the code, so a new producer is covered the day it is added.

How the kinds are found (``incident_kinds``): every ``._incident(<kind>, ...)`` and
``._block_entries(<key>, ...)`` call and every dict literal with ``incident_id``, ``kind`` and
``actor`` (the shape of an incident row) in the package. A kind that is not a literal is a *template*; each template the code has today
is resolved from the code itself (the ``what=`` of ``_count_unknown``, the market maker's kill
triggers). A template nobody resolved fails the test: it is a kind of unknown length.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tia.persistence import models, repositories
from tia.persistence.models import IncidentRow


# The contract is looked up when a test runs, not at import: on a tree without it the tests
# fail on what is missing, one by one, instead of the module failing to import.
def limit() -> int:
    value = getattr(models, "INCIDENT_KIND_MAX_LENGTH", None)
    assert value is not None, "no single limit for incidents.kind: the column and the code can disagree"
    return int(value)


def incident_kind_problem(kind: object) -> str | None:
    check = getattr(repositories, "incident_kind_problem", None)
    assert check is not None, "the repository does not check a kind before writing it"
    return check(kind)


def invalid_kind() -> str:
    value = getattr(repositories, "INVALID_INCIDENT_KIND", None)
    assert value is not None, "there is no explicit kind for an invalid one"
    return str(value)

PACKAGE = Path(__file__).resolve().parents[2] / "packages" / "tia" / "src" / "tia"

#: Templates that are the definitions of the producers, not values of their own: their values
#: are the calls, which are enumerated as literals.
DEFINITIONS = {"{kind}", "entries_blocked:{key}"}


def _text(node: ast.AST) -> tuple[str, bool]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, True
    if isinstance(node, ast.JoinedStr):
        parts = [str(v.value) if isinstance(v, ast.Constant) else "{" + ast.unparse(v.value) + "}" for v in node.values]
        return "".join(parts), False
    return "{" + ast.unparse(node) + "}", False


def _trees(sub: str = "") -> list[tuple[str, ast.AST]]:
    return [(str(p.relative_to(PACKAGE)), ast.parse(p.read_text(encoding="utf-8"))) for p in sorted((PACKAGE / sub).rglob("*.py"))]


def _call_literals(method: str, *, keyword: str | None = None, sub: str = "") -> set[str]:
    found: set[str] = set()
    for _, tree in _trees(sub):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == method:
                if keyword is None and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    found.add(node.args[0].value)
                found |= {str(k.value.value) for k in node.keywords if k.arg == keyword and isinstance(k.value, ast.Constant)}
    return found


def _dict_keys(name: str, relative: str) -> set[str]:
    for node in ast.walk(ast.parse((PACKAGE / relative).read_text(encoding="utf-8"))):
        target = getattr(node, "target", None) or (node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(target, ast.Name) and target.id == name and isinstance(getattr(node, "value", None), ast.Dict):
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    raise AssertionError(f"{name} not found in {relative}")


def _resolutions() -> dict[str, set[str]]:
    lost = {f"{w.replace(' ', '_')}_lost" for w in _call_literals("_count_unknown", keyword="what")}
    triggers = (_call_literals("engage", sub="mm") | _dict_keys("CRITICAL_RESPONSE", "mm/live_service.py")
                | _call_literals("_critical", sub="mm") | {"kill_switch"})
    return {
        "{what.replace(' ', '_')}_lost": lost,
        "mm_{row.get('trigger', 'kill_switch')}": {f"mm_{t}" for t in triggers},
    }


def incident_kinds() -> tuple[dict[str, list[str]], list[str]]:
    """``({kind: [where]}, [unresolved templates])`` for the whole package."""
    kinds: dict[str, list[str]] = {}
    unresolved: list[str] = []
    resolutions = _resolutions()

    def add(text: str, literal: bool, where: str) -> None:
        if literal:
            kinds.setdefault(text, []).append(where)
        elif text in resolutions:
            for value in resolutions[text]:
                kinds.setdefault(value, []).append(f"{where} ({text})")
        elif text not in DEFINITIONS:
            unresolved.append(f"{where}: {text}")

    for relative, tree in _trees():
        for node in ast.walk(tree):
            where = f"{relative}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.args:
                if node.func.attr == "_incident":
                    add(*_text(node.args[0]), where)
                elif node.func.attr == "_block_entries":
                    text, literal = _text(node.args[0])
                    add("entries_blocked:" + text, literal, where)
            if isinstance(node, ast.Dict) and None not in node.keys:
                keys = [k.value if isinstance(k, ast.Constant) else None for k in node.keys]
                if {"incident_id", "kind", "actor"} <= set(keys):  # an incident row, not a report about one
                    add(*_text(node.values[keys.index("kind")]), where)
    return kinds, unresolved


def test_the_enumeration_sees_the_producers_it_must_see() -> None:
    """A guard on the guard: the kinds that were lost on PostgreSQL are found."""
    kinds, _ = incident_kinds()
    for expected in ("entries_blocked:protection_unverified", "entries_blocked:protection_failed",
                     "entries_blocked:position_unverified", "entries_blocked:orders_unverified",
                     "protection_failed", "protection_unknown", "risk_profile_change", "mentor_apply",
                     "protective_stop_lost", "mm_venue_order_unknown_locally", "mm_operator"):
        assert expected in kinds, expected
    assert len(kinds) >= 40


def test_every_kind_the_code_can_write_is_resolved() -> None:
    _, unresolved = incident_kinds()
    assert unresolved == [], (
        "an incident kind built at run time that this test cannot bound; resolve it here: " + "; ".join(unresolved)
    )


def test_every_kind_the_code_can_write_fits_the_column_and_the_contract() -> None:
    kinds, _ = incident_kinds()
    bad = {k: (len(k), incident_kind_problem(k), where[:2]) for k, where in kinds.items() if incident_kind_problem(k) is not None}
    assert bad == {}, bad
    assert max(len(k) for k in kinds) <= limit()


def test_the_column_is_exactly_as_wide_as_the_contract() -> None:
    assert IncidentRow.__table__.c.kind.type.length == limit()
    assert IncidentRow.__table__.c.kind.nullable is False


@pytest.mark.parametrize("kind", [
    "", "too_long", None, 42, "Has Space", "entries_blocked:Protection", "-leading", "tab\tkind",
])
def test_the_contract_refuses_what_the_column_must_not_hold(kind: object) -> None:
    if kind == "too_long":
        kind = "x" * (limit() + 1)
    assert incident_kind_problem(kind) is not None


@pytest.mark.parametrize("kind", ["safe_mode", "at_limit", "entries_blocked:protection_unverified", "a.b-c:d_e9"])
def test_the_contract_accepts_what_the_column_holds(kind: str) -> None:
    if kind == "at_limit":
        kind = "x" * limit()
    assert incident_kind_problem(kind) is None


def test_the_replacement_kind_is_itself_valid() -> None:
    assert incident_kind_problem(invalid_kind()) is None
