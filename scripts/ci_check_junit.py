"""Fail a CI job whose test run did not test what it claims (mission v3).

A green pytest exit code says nothing failed. It does not say that anything ran: a suite whose
every test was skipped (PostgreSQL without its server) exits 0. Nor does it say that the known
failures are still the known ones. This reads the JUnit file of a run and fails unless:

* it has at least ``--min-cases`` test cases;
* no case failed or errored (a second look, independent of pytest's exit code);
* no case was skipped, unless ``--allow-skips`` (there is no such job today);
* every expected failure is one listed in ``--xfail-allowlist`` (``nodeid`` per line, ``#``
  comments), and every listed one actually occurred: a strict xfail that now passes already
  fails pytest; a listed one that disappeared means the list is stale and is reported too.

Usage: python scripts/ci_check_junit.py <junit.xml> --min-cases N [--xfail-allowlist FILE]
Exit codes: 0 ok, 1 a check failed, 2 the file could not be read.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _nodeid(case: ET.Element) -> str:
    classname = case.get("classname", "")
    name = case.get("name", "")
    path = classname.replace(".", "/")
    # pytest's xunit2 classname is the module path with dots; the nodeid is path.py::name
    return f"{path}.py::{name}" if classname else name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("junit")
    parser.add_argument("--min-cases", type=int, required=True)
    parser.add_argument("--xfail-allowlist", type=Path)
    parser.add_argument("--allow-skips", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = ET.parse(args.junit).getroot()  # noqa: S314 - our own pytest output, not untrusted input
    except (OSError, ET.ParseError) as exc:
        print(f"cannot read {args.junit}: {exc}")
        return 2
    allowed: set[str] = set()
    if args.xfail_allowlist is not None:
        for line in args.xfail_allowlist.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                allowed.add(line)
    cases = list(root.iter("testcase"))
    failed, skipped, xfailed = [], [], []
    for case in cases:
        if case.find("failure") is not None or case.find("error") is not None:
            failed.append(_nodeid(case))
        skip = case.find("skipped")
        if skip is not None:
            (xfailed if skip.get("type") == "pytest.xfail" else skipped).append(_nodeid(case))
    problems: list[str] = []
    if len(cases) < args.min_cases:
        problems.append(f"{len(cases)} test cases, fewer than the {args.min_cases} this job must run")
    problems += [f"FAILED/ERROR: {n}" for n in failed]
    if not args.allow_skips:
        problems += [f"SKIPPED: {n}" for n in skipped]
    problems += [f"UNEXPECTED XFAIL (not in the allowlist): {n}" for n in xfailed if n not in allowed]
    problems += [f"STALE ALLOWLIST ENTRY (did not xfail in this run): {n}" for n in sorted(allowed - set(xfailed))]
    print(f"{args.junit}: {len(cases)} cases, {len(failed)} failed/error, {len(skipped)} skipped, "
          f"{len(xfailed)} xfail ({len(allowed)} allowed)")
    for line in problems:
        print(line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
