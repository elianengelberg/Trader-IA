"""The CI's JUnit guard (scripts/ci_check_junit.py, mission v3) fails on what pytest's exit code
does not: nothing ran, something was skipped, an expected failure that is not the listed one."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("ci_check_junit", ROOT / "scripts/ci_check_junit.py")
assert _spec is not None and _spec.loader is not None
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

LISTED = "tests/unit/test_x.py::test_known"


def junit(tmp_path: Path, *cases: str) -> Path:
    path = tmp_path / "junit.xml"
    path.write_text('<?xml version="1.0"?><testsuites><testsuite name="pytest">' + "".join(cases) + "</testsuite></testsuites>",
                    encoding="utf-8")
    return path


def ok(name: str = "test_a") -> str:
    return f'<testcase classname="tests.unit.test_x" name="{name}" time="0.1"/>'


def xfail(name: str = "test_known") -> str:
    return (f'<testcase classname="tests.unit.test_x" name="{name}" time="0.1">'
            '<skipped type="pytest.xfail" message="known"/></testcase>')


def skipped(name: str = "test_s") -> str:
    return f'<testcase classname="tests.unit.test_x" name="{name}"><skipped type="pytest.skip" message="no server"/></testcase>'


def failed(name: str = "test_f") -> str:
    return f'<testcase classname="tests.unit.test_x" name="{name}"><failure message="boom"/></testcase>'


@pytest.fixture
def allowlist(tmp_path: Path) -> Path:
    path = tmp_path / "xfail.txt"
    path.write_text(f"# expected\n{LISTED}  # why\n", encoding="utf-8")
    return path


def run(path: Path, *args: str) -> int:
    return guard.main([str(path), *args])


def test_a_clean_run_with_the_listed_xfail_passes(tmp_path: Path, allowlist: Path) -> None:
    assert run(junit(tmp_path, ok("t1"), ok("t2"), xfail()), "--min-cases", "3", "--xfail-allowlist", str(allowlist)) == 0


@pytest.mark.parametrize("cases,min_cases,why", [
    ((ok(), skipped(), xfail()), "1", "a skipped case"),
    ((ok(), failed(), xfail()), "1", "a failed case"),
    ((ok(), xfail(), xfail("test_new")), "1", "an unlisted xfail"),
    ((ok(), ok("t2")), "1", "a listed xfail that did not occur"),
    ((ok(), xfail()), "5", "fewer cases than required"),
], ids=["skip", "fail", "new_xfail", "stale_list", "too_few"])
def test_each_way_a_green_run_can_lie_fails_the_guard(tmp_path: Path, allowlist: Path, cases: tuple[str, ...], min_cases: str, why: str) -> None:
    assert run(junit(tmp_path, *cases), "--min-cases", min_cases, "--xfail-allowlist", str(allowlist)) == 1, why


def test_an_unreadable_report_is_its_own_failure(tmp_path: Path) -> None:
    bad = tmp_path / "junit.xml"
    bad.write_text("<testsuites", encoding="utf-8")
    assert run(bad, "--min-cases", "1") == 2


def test_the_listed_nodeids_match_pytest_s_junit_names() -> None:
    """The allowlists name tests the way the guard reconstructs them from xunit2 classnames."""
    for name in ("ci/xfail_python.txt", "ci/xfail_postgres.txt"):
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
            entry = line.split("#", 1)[0].strip()
            if entry:
                path, _, test = entry.partition("::")
                assert (ROOT / path).is_file() and test, entry
                assert f"def {test.split('[', 1)[0]}(" in (ROOT / path).read_text(encoding="utf-8"), entry
