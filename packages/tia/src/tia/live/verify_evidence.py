"""Verification evidence bound to the exact artifact it vouches for (R22).

``make verify`` records its outcome in ``data/runtime/verify_passed.json`` and the
activation gate's ``tests_pass``, ``emergency_controls`` and ``restart_recovery`` checks
read it. Before R22 that file said ``{"passed": true, "commit": ...}`` and the gate believed
the first field and ignored the rest: a green run from another commit, from last month,
from a tree edited afterwards or under another configuration all authorised activation.

This module is both ends of the record, so that the writer and the reader cannot drift:

* :func:`begin` / :func:`finish` — called by ``scripts/verify.sh`` — compute the identity
  of what is being tested before and after the suites run, collect each suite's exit code,
  timestamps and junit counts, and write a **schema v2** marker sealed with a digest over
  its own content.
* :func:`assess` — called by the gate in the process that would trade — recomputes that
  identity *now* and accepts the marker only if every part of it matches. Anything it
  cannot establish is a refusal with the reason, never a pass.

**The identity** (:class:`ArtifactIdentity`) is: the commit SHA and its tree; whether the
work tree has *any* uncommitted change (staged, unstaged, untracked — ``git status
--untracked-files=all``, not ``git diff``); a SHA-256 over the content of every tracked and
untracked-but-not-ignored file, which also catches edits hidden from ``git status`` by
``--assume-unchanged``; the fingerprint of the trading configuration (risk, live, execution,
strategy, data quality, market making, environment and mode — through
:func:`tia.live.gate.configuration_fingerprint`, with the venue credentials left out); and a
digest of the installed distributions and the interpreter version. A process that cannot
compute it — no ``.git``, no ``git`` executable, as in the Docker image — fails the checks
and says so; it never substitutes a build argument or a guess.

**What the digest is not.** The marker's ``digest`` is an unkeyed SHA-256. It detects
corruption, truncation and naive hand edits. It does *not* stop someone who edits the file
and recomputes the digest — the code that computes it is public. That forger still has to
match the identity this process computes for itself, which is the binding that matters;
a keyed signature would need key management this project does not have yet (see
README_R22, "riesgos residuales").
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, get_args
from xml.etree import ElementTree

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, ValidationError

from tia.core.clock import SystemClock
from tia.live.gate import configuration_fingerprint

if TYPE_CHECKING:  # pragma: no cover - typing only
    from tia.core.config import Settings

#: The marker's format. Anything else — including the pre-R22 ``{"passed": true}`` — is
#: refused, never reinterpreted.
KIND = "tia.verify-evidence"
SCHEMA_VERSION = 2
PRODUCER = "tia.live.verify_evidence"
PRODUCER_VERSION = 1

#: The areas of ``scripts/verify.sh`` that must have passed. This list is the gate's, not
#: the marker's: a marker that leaves a suite out is incomplete, whatever it claims.
#: The frontend checks are optional in verify.sh (WARN, not FAIL) and stay optional here.
REQUIRED_SUITES: tuple[str, ...] = (
    "lint",
    "unit",
    "integration",
    "property",
    "failure",
    "adversarial",
    "e2e",
    "smoke",
)
#: Required suites that are pytest runs: they must carry junit counts with at least one
#: test that actually ran, and no failure or error.
PYTEST_SUITES: frozenset[str] = frozenset(
    {"unit", "integration", "property", "failure", "adversarial", "e2e"}
)

#: Test modules a specific gate check rests on. Their suite passing is not enough: the
#: module must have run in it and passed (deselected or all-skipped proves nothing).
RESTART_RECOVERY_MODULES: tuple[tuple[str, str], ...] = (
    ("integration", "tests.integration.test_restart_recovery"),
)
EMERGENCY_CONTROL_MODULES: tuple[tuple[str, str], ...] = (
    ("integration", "tests.integration.test_live_runtime"),
    ("integration", "tests.integration.test_order_integrity"),
)

SUITES_FILE = "suites.tsv"
BEGIN_FILE = "begin.json"
_GIT_TIMEOUT_S = 20.0
_HEX64 = r"^[0-9a-f]{64}$"


class IdentityUnavailable(RuntimeError):
    """The running code's identity cannot be established. Never caught into a pass."""


@dataclass(frozen=True)
class ArtifactIdentity:
    commit: str
    tree: str
    dirty: bool
    status_digest: str
    status_entries: int
    worktree_digest: str
    worktree_files: int
    config_fingerprint: str
    dependencies_digest: str
    python: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- identity


def _git(root: Path, *args: str) -> bytes:
    git = shutil.which("git")
    if git is None:
        raise IdentityUnavailable(
            "no git executable in this environment, so the code this process would run "
            "cannot be identified (the Docker image ships neither git nor .git)"
        )
    # Repository-redirecting variables (GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE, ...) would
    # make git describe some other tree; optional locks off so a read never writes.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell, local metadata only
            [git, "-c", "core.fsmonitor=false", *args],
            cwd=root,
            capture_output=True,
            timeout=_GIT_TIMEOUT_S,
            check=False,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise IdentityUnavailable(f"git could not be run in {root}: {exc}") from exc
    if proc.returncode != 0:
        reason = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise IdentityUnavailable(
            f"`git {args[0]}` failed in {root}: {reason[0] if reason else 'exit ' + str(proc.returncode)}"
        )
    return proc.stdout


def running_code_root() -> Path:
    """The directory of the ``tia`` package this process imported."""
    import tia

    return Path(tia.__file__).resolve().parent


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _worktree_digest(top: Path) -> tuple[str, int]:
    """SHA-256 over path, kind and content of every tracked and untracked-not-ignored file.

    Reads the files themselves rather than trusting git's index, so a modification hidden
    by ``update-index --assume-unchanged`` or ``--skip-worktree`` still changes the digest.
    Ignored files (``.env``, ``.venv``, ``data/runtime``) are outside it by design.
    """
    listing = _git(top, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    paths = sorted({p for p in listing.split(b"\0") if p})
    digest = hashlib.sha256()
    for raw in paths:
        full = top / os.fsdecode(raw)
        try:
            info = full.lstat()
        except FileNotFoundError:
            kind, content = "missing", ""
        except OSError as exc:
            raise IdentityUnavailable(f"cannot stat {raw!r}: {exc}") from exc
        else:
            if stat.S_ISLNK(info.st_mode):
                kind = "symlink"
                content = hashlib.sha256(os.fsencode(str(full.readlink()))).hexdigest()
            elif stat.S_ISREG(info.st_mode):
                kind = "file+x" if info.st_mode & 0o111 else "file"
                try:
                    content = _file_digest(full)
                except OSError as exc:
                    raise IdentityUnavailable(f"cannot read {raw!r}: {exc}") from exc
            elif stat.S_ISDIR(info.st_mode):
                kind, content = "gitlink", ""
            else:
                kind, content = "other", ""
        digest.update(raw + b"\0" + kind.encode() + b"\0" + content.encode() + b"\n")
    return digest.hexdigest(), len(paths)


def dependencies_fingerprint() -> tuple[str, str]:
    """(digest, interpreter) over every installed distribution and the interpreter."""
    interpreter = f"{sys.implementation.name}-{platform.python_version()}"
    entries: set[str] = set()
    for dist in metadata.distributions():
        name = dist.metadata["Name"] if dist.metadata else None
        if name:
            entries.add(f"{re.sub(r'[-_.]+', '-', name).lower()}=={dist.version}")
    payload = "\n".join([f"python=={interpreter}", *sorted(entries)]).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), interpreter


def _without_secrets(section: BaseModel) -> dict[str, Any]:
    """``section`` as JSON with every field *declared* secret left out.

    Credentials never enter the fingerprint: the key is checked against the venue by
    ``credentials_scoped``, and here its mere presence would make evidence produced in a
    shell without the secret (the safe way to run tests) unusable. Excluded by declared
    type, not by value, so "set" and "unset" fingerprint alike.
    """
    secret = {
        name
        for name, field in type(section).model_fields.items()
        if field.annotation is SecretStr or SecretStr in get_args(field.annotation)
    }
    return section.model_dump(mode="json", exclude=secret)


def evidence_configuration_fingerprint(settings: Settings) -> str:
    """The configuration the evidence is about — reusing the gate's own fingerprint."""
    return configuration_fingerprint(
        {"env": settings.env.value, "mode": settings.mode.value},
        *(
            _without_secrets(section)
            for section in (
                settings.risk,
                settings.live,
                settings.execution,
                settings.strategy,
                settings.data_quality,
                settings.mm,
            )
        ),
    )


def compute_identity(settings: Settings, root: Path | None = None) -> ArtifactIdentity:
    """The identity of the code at ``root`` (default: the running ``tia`` package's tree).

    Raises :class:`IdentityUnavailable` rather than returning anything partial.
    """
    start = root if root is not None else running_code_root()
    if not start.is_dir():
        raise IdentityUnavailable(f"{start} is not a directory")
    top_raw = _git(start, "rev-parse", "--show-toplevel").decode("utf-8", "replace").strip()
    if not top_raw:
        raise IdentityUnavailable(f"{start} is not inside a git work tree")
    top = Path(top_raw).resolve()
    # The tree only describes the running code if that code is *tracked* in it — not an
    # installed copy in an ignored .venv, nor an export sitting inside some other repo.
    try:
        relative = start.resolve().relative_to(top).as_posix() or "."
    except ValueError as exc:
        raise IdentityUnavailable(f"{start} is not inside the work tree {top}") from exc
    if not _git(top, "ls-files", "-z", "--cached", "--", relative).strip(b"\0"):
        raise IdentityUnavailable(
            f"the code at {start} is not tracked by the git work tree at {top} "
            "(an installed or exported copy?)"
        )
    commit = _git(top, "rev-parse", "--verify", "HEAD").decode().strip()
    tree = _git(top, "rev-parse", "--verify", "HEAD^{tree}").decode().strip()
    status = _git(
        top,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignore-submodules=none",
        "--no-renames",
    )
    worktree, files = _worktree_digest(top)
    deps, interpreter = dependencies_fingerprint()
    return ArtifactIdentity(
        commit=commit,
        tree=tree,
        dirty=bool(status),
        status_digest=hashlib.sha256(status).hexdigest(),
        status_entries=len([e for e in status.split(b"\0") if e]),
        worktree_digest=worktree,
        worktree_files=files,
        config_fingerprint=evidence_configuration_fingerprint(settings),
        dependencies_digest=deps,
        python=interpreter,
    )


def current_identity(
    settings: Settings, root: Path | None = None
) -> tuple[ArtifactIdentity | None, str]:
    """:func:`compute_identity`, or ``None`` with the reason it could not be computed."""
    try:
        return compute_identity(settings, root), ""
    except IdentityUnavailable as exc:
        return None, str(exc)
    except Exception as exc:  # unknown = failed, with the reason attached
        return None, f"identity computation failed: {type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------- the record


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ModuleCounts(_Strict):
    tests: int = Field(ge=0)
    failures: int = Field(ge=0)
    errors: int = Field(ge=0)
    skipped: int = Field(ge=0)

    @property
    def passed(self) -> int:
        return self.tests - self.failures - self.errors - self.skipped


class JunitSummary(ModuleCounts):
    sha256: str = Field(pattern=_HEX64)
    modules: dict[str, ModuleCounts]


class SuiteRecord(_Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    required: bool
    command: str = Field(min_length=1)
    exit_code: int
    status: Literal["pass", "fail"]
    started_at: AwareDatetime
    finished_at: AwareDatetime
    junit: JunitSummary | None


class ArtifactRecord(_Strict):
    commit: str = Field(pattern=r"^[0-9a-f]{40}([0-9a-f]{24})?$")
    tree: str = Field(pattern=r"^[0-9a-f]{40}([0-9a-f]{24})?$")
    dirty: bool
    status_digest: str = Field(pattern=_HEX64)
    status_entries: int = Field(ge=0)
    worktree_digest: str = Field(pattern=_HEX64)
    worktree_files: int = Field(ge=1)
    config_fingerprint: str = Field(pattern=r"^[0-9a-f]{32}$")
    dependencies_digest: str = Field(pattern=_HEX64)
    python: str = Field(min_length=1)


class Provenance(_Strict):
    producer: Literal["tia.live.verify_evidence"]
    producer_version: int = Field(ge=1)
    entrypoint: str = Field(min_length=1)
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    host: str = Field(min_length=1)
    user: str = Field(min_length=1)
    python_executable: str = Field(min_length=1)
    cwd: str = Field(min_length=1)
    repo_root: str = Field(min_length=1)
    started_at: AwareDatetime
    finished_at: AwareDatetime


class SealDigest(_Strict):
    algorithm: Literal["sha256"]
    value: str = Field(pattern=_HEX64)


class VerifyEvidence(_Strict):
    kind: Literal["tia.verify-evidence"]
    schema_version: Literal[2]
    passed: bool
    failed: int = Field(ge=0)
    problems: list[str]
    artifact: ArtifactRecord | None
    provenance: Provenance
    suites: list[SuiteRecord]
    digest: SealDigest

    def suite(self, suite_id: str) -> SuiteRecord | None:
        found = [s for s in self.suites if s.id == suite_id]
        return found[0] if len(found) == 1 else None

    def modules_problem(self, required: Sequence[tuple[str, str]]) -> str:
        """Empty if every ``(suite, module)`` ran with at least one passing test and no
        failure or error; otherwise what is missing."""
        problems: list[str] = []
        for suite_id, module in required:
            suite = self.suite(suite_id)
            counts = suite.junit.modules.get(module) if suite and suite.junit else None
            if counts is None:
                problems.append(f"{module} did not run in the {suite_id} suite")
            elif counts.failures or counts.errors or counts.passed < 1:
                problems.append(
                    f"{module}: {counts.passed} passed, {counts.failures} failed, "
                    f"{counts.errors} errors, {counts.skipped} skipped"
                )
        return "; ".join(problems)


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    body = {k: v for k, v in payload.items() if k != "digest"}
    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def seal(payload: Mapping[str, Any]) -> dict[str, Any]:
    """``payload`` with ``digest`` set to SHA-256 over everything else (unkeyed)."""
    sealed = {k: v for k, v in payload.items() if k != "digest"}
    sealed["digest"] = {
        "algorithm": "sha256",
        "value": hashlib.sha256(canonical_bytes(sealed)).hexdigest(),
    }
    return sealed


# --------------------------------------------------------------------------- the check


@dataclass(frozen=True)
class Assessment:
    evidence: VerifyEvidence
    age_hours: float

    def summary(self) -> str:
        artifact = self.evidence.artifact
        if artifact is None:  # assess() never builds one like this; say so if it happens
            return "evidence without an artifact identity"
        tests = sum(
            s.junit.tests for s in self.evidence.suites if s.junit and s.id in REQUIRED_SUITES
        )
        return (
            f"verified at {self.evidence.provenance.finished_at.isoformat()} "
            f"({self.age_hours:.1f} h ago) on commit {artifact.commit[:12]}, clean tree, "
            f"same configuration ({artifact.config_fingerprint[:8]}) and dependencies "
            f"({artifact.dependencies_digest[:8]}); {len(REQUIRED_SUITES)} required suites, "
            f"{tests} tests"
        )


def _entries(count: int) -> str:
    return f"{count} entry" if count == 1 else f"{count} entries"


def _differences(recorded: ArtifactRecord, current: ArtifactIdentity) -> list[str]:
    out: list[str] = []
    if recorded.commit != current.commit:
        out.append(
            f"the evidence is for commit {recorded.commit[:12]} but this process would run "
            f"{current.commit[:12]} — evidence from one commit does not authorise another"
        )
    elif recorded.tree != current.tree:
        out.append("same commit SHA but a different tree — the repository was rewritten")
    if recorded.worktree_digest != current.worktree_digest:
        out.append(
            "the files on disk differ from the ones that were tested (worktree digest "
            f"{recorded.worktree_digest[:12]} -> {current.worktree_digest[:12]})"
        )
    if recorded.config_fingerprint != current.config_fingerprint:
        out.append(
            "the configuration differs from the one present when the suite ran "
            f"(fingerprint {recorded.config_fingerprint[:8]} -> {current.config_fingerprint[:8]})"
        )
    if recorded.python != current.python:
        out.append(f"the interpreter differs ({recorded.python} -> {current.python})")
    if recorded.dependencies_digest != current.dependencies_digest:
        out.append(
            "the installed dependencies differ from the ones the suite ran with "
            f"({recorded.dependencies_digest[:8]} -> {current.dependencies_digest[:8]})"
        )
    return out


def _suite_problems(evidence: VerifyEvidence) -> list[str]:
    problems: list[str] = []
    run_start = evidence.provenance.started_at
    run_end = evidence.provenance.finished_at
    for suite in evidence.suites:
        if (suite.status == "pass") != (suite.exit_code == 0):
            problems.append(
                f"suite {suite.id} is recorded as {suite.status} with exit code "
                f"{suite.exit_code} — incoherent"
            )
        if not (run_start <= suite.started_at <= suite.finished_at <= run_end):
            problems.append(f"suite {suite.id} has timestamps outside its own run")
    ids = [s.id for s in evidence.suites]
    missing = [s for s in REQUIRED_SUITES if s not in ids]
    if missing:
        problems.append(f"the run is incomplete: required suites missing {missing}")
    duplicated = sorted({s for s in ids if ids.count(s) > 1})
    if duplicated:
        problems.append(f"suites recorded more than once {duplicated}")
    for suite_id in REQUIRED_SUITES:
        suite = evidence.suite(suite_id)
        if suite is None:
            continue
        if suite.status != "pass" or suite.exit_code != 0:
            problems.append(f"required suite {suite_id} failed (exit {suite.exit_code})")
        if suite_id not in PYTEST_SUITES:
            continue
        junit = suite.junit
        if junit is None:
            problems.append(f"suite {suite_id} carries no junit result")
            continue
        if junit.failures or junit.errors:
            problems.append(
                f"suite {suite_id}: {junit.failures} failures, {junit.errors} errors in junit"
            )
        if junit.passed < 1:
            problems.append(f"suite {suite_id} ran no test ({junit.tests} collected, "
                            f"{junit.skipped} skipped) — it proved nothing")
        module_totals = [sum(getattr(m, f) for m in junit.modules.values())
                         for f in ("tests", "failures", "errors", "skipped")]
        if module_totals != [junit.tests, junit.failures, junit.errors, junit.skipped]:
            problems.append(f"suite {suite_id}: per-module counts do not add up to its totals")
    return problems


def assess(
    raw_text: str | None,
    *,
    current: ArtifactIdentity | None,
    identity_problem: str,
    now: datetime,
    max_age_hours: float,
    source: str = "the verification marker",
) -> tuple[Assessment | None, str]:
    """Accept the marker only if it is intact, complete, passing, fresh, clean and about
    the artifact identified as ``current``. Otherwise ``(None, reason)``."""
    if current is None:
        return None, (
            "this process cannot determine the identity of the code it would run "
            f"({identity_problem or 'unknown reason'}), so no verification evidence can be "
            "matched to it — refused rather than assumed"
        )
    if raw_text is None:
        return None, f"no verification evidence at {source}"
    try:
        raw = json.loads(raw_text)
    except ValueError:
        return None, f"{source} is unreadable (not JSON); it is not evidence"
    if not isinstance(raw, dict):
        return None, f"{source} is not a JSON object; it is not evidence"
    if raw.get("kind") != KIND or raw.get("schema_version") != SCHEMA_VERSION:
        legacy = "passed" in raw and "schema_version" not in raw
        return None, (
            f"{source} uses "
            + ("the pre-R22 schema (a bare passed flag that binds nothing)" if legacy
               else f"an unknown schema ({raw.get('kind')!r} v{raw.get('schema_version')!r})")
            + f"; this build requires {KIND} v{SCHEMA_VERSION}"
        )
    digest = raw.get("digest")
    if not isinstance(digest, dict) or not isinstance(digest.get("value"), str):
        return None, f"{source} carries no digest over its content; it cannot be checked"
    try:
        expected = hashlib.sha256(canonical_bytes(raw)).hexdigest()
    except (TypeError, ValueError):
        return None, f"{source} cannot be canonicalised; it is not evidence"
    if digest.get("algorithm") != "sha256" or digest["value"] != expected:
        return None, (
            f"the digest of {source} does not match its content — the file was modified "
            "after it was written (edited evidence is no evidence)"
        )
    try:
        # Validate exactly the object the digest was computed over (re-serialised), so a
        # duplicated key cannot show the digest one value and the schema another.
        evidence = VerifyEvidence.model_validate_json(json.dumps(raw))
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first.get("loc", ())) or "<root>"
        return None, (
            f"{source} does not match its schema ({exc.error_count()} problems; first: "
            f"{where}: {first.get('msg')})"
        )
    prov = evidence.provenance
    if prov.finished_at < prov.started_at:
        return None, "the evidence's provenance ends before it starts"
    age_hours = (now - prov.finished_at).total_seconds() / 3600.0
    if age_hours < 0:
        return None, (
            f"the evidence claims to be from {abs(age_hours):.1f} hours in the future — "
            "a clock is wrong"
        )
    if age_hours > max_age_hours:
        return None, (
            f"the evidence is {age_hours:.1f} hours old; the bound is {max_age_hours:g} hours "
            "(setting live.verify_evidence_max_age_hours)"
        )
    if not evidence.passed or evidence.failed or evidence.problems:
        detail = "; ".join(evidence.problems) or (
            f"{evidence.failed} required areas failed" if evidence.failed
            else "it is recorded as not passed"
        )
        return None, f"the recorded verification run did not pass: {detail}"
    suite_problems = _suite_problems(evidence)
    if suite_problems:
        return None, "; ".join(suite_problems)
    artifact = evidence.artifact
    if artifact is None:
        return None, "the verification run could not identify what it tested"
    if artifact.dirty:
        return None, (
            f"the suite ran on a tree with uncommitted changes ({_entries(artifact.status_entries)} "
            "in git status); evidence must be about a commit"
        )
    if current.dirty:
        return None, (
            f"the code this process would run has uncommitted changes "
            f"({_entries(current.status_entries)} in git status: staged, unstaged or untracked)"
        )
    differences = _differences(artifact, current)
    if differences:
        return None, "; ".join(differences)
    return Assessment(evidence=evidence, age_hours=age_hours), ""


# --------------------------------------------------------------------------- the writer


def _stamp(moment: datetime | None = None) -> datetime:
    # Seconds, like the `date -u` stamps verify.sh writes per suite, so the run window
    # [begin, finish] always contains them.
    return (moment or SystemClock().now()).astimezone(UTC).replace(microsecond=0)


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _module_of(classname: str) -> str:
    parts = classname.split(".")
    for i, part in enumerate(parts):
        if part.startswith("test_") or part.endswith("_test"):
            return ".".join(parts[: i + 1])
    return classname or "<unknown>"


def junit_summary(path: Path) -> dict[str, Any]:
    """Counts per test module from a junit XML pytest just wrote in this run."""
    data = path.read_bytes()
    root = ElementTree.fromstring(data)  # noqa: S314 - our own pytest output from this run
    modules: dict[str, dict[str, int]] = {}
    for case in root.iter("testcase"):
        counts = modules.setdefault(
            _module_of(case.get("classname", "")),
            {"tests": 0, "failures": 0, "errors": 0, "skipped": 0},
        )
        counts["tests"] += 1
        if case.find("error") is not None:
            counts["errors"] += 1
        elif case.find("failure") is not None:
            counts["failures"] += 1
        elif case.find("skipped") is not None:
            counts["skipped"] += 1
    # If pytest's own <testsuite> attributes report more failures or errors than the
    # testcases show, believe the worse number (booked to a synthetic module so the
    # per-module counts still add up to the totals).
    for attr in ("failures", "errors"):
        reported = sum(int(s.get(attr) or 0) for s in root.iter("testsuite"))
        counted = sum(m[attr] for m in modules.values())
        if reported > counted:
            extra = modules.setdefault(
                "<suite>", {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
            )
            extra[attr] += reported - counted
            extra["tests"] += reported - counted
    totals = {
        f: sum(m[f] for m in modules.values()) for f in ("tests", "failures", "errors", "skipped")
    }
    return {**totals, "sha256": hashlib.sha256(data).hexdigest(), "modules": modules}


def _user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return f"uid:{os.getuid()}" if hasattr(os, "getuid") else "unknown"


def begin(
    run_dir: Path,
    marker: Path,
    *,
    settings: Settings,
    root: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Start a run: discard the old marker, record what is about to be tested."""
    marker.unlink(missing_ok=True)  # an interrupted run must leave no evidence behind
    run_dir.mkdir(parents=True, exist_ok=True)
    for stale in (*run_dir.glob("*.xml"), run_dir / SUITES_FILE, run_dir / BEGIN_FILE):
        stale.unlink(missing_ok=True)
    identity, problem = current_identity(settings, root)
    record = {
        "run_id": uuid.uuid4().hex,
        "started_at": _iso(_stamp(now)),
        "identity": identity.as_dict() if identity else None,
        "identity_problem": problem,
    }
    (run_dir / BEGIN_FILE).write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def _read_suites(run_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    suites: list[dict[str, Any]] = []
    problems: list[str] = []
    path = run_dir / SUITES_FILE
    if not path.is_file():
        return suites, [f"no suite results at {path}"]
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) != 6:
            problems.append(f"{SUITES_FILE}:{number} is malformed")
            continue
        suite_id, required, exit_code, started, finished, command = fields
        try:
            code = int(exit_code)
        except ValueError:
            problems.append(f"{SUITES_FILE}:{number} has a non-numeric exit code")
            continue
        junit_path = run_dir / f"{suite_id}.xml"
        junit: dict[str, Any] | None = None
        if junit_path.is_file():
            try:
                junit = junit_summary(junit_path)
            except (OSError, ValueError, ElementTree.ParseError) as exc:
                problems.append(f"junit for {suite_id} is unreadable: {exc}")
        suites.append({
            "id": suite_id,
            "required": required == "1",
            "command": command,
            "exit_code": code,
            "status": "pass" if code == 0 else "fail",
            "started_at": started,
            "finished_at": finished,
            "junit": junit,
        })
    return suites, problems


def finish(
    run_dir: Path,
    marker: Path,
    *,
    settings: Settings,
    root: Path | None = None,
    entrypoint: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Collect the run, re-identify the artifact, write the sealed marker atomically."""
    problems: list[str] = []
    try:
        started = json.loads((run_dir / BEGIN_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        started = None
    if not isinstance(started, dict):
        started = {}
        problems.append("the run has no readable begin record; it cannot say what it tested")
    before = started.get("identity")
    if before is None and started:
        problems.append(f"the tested artifact could not be identified: {started.get('identity_problem')}")
    after, after_problem = current_identity(settings, root)
    if after is None:
        problems.append(f"the artifact could not be re-identified after the run: {after_problem}")
    elif before is not None and after.as_dict() != before:
        changed = sorted(k for k, v in after.as_dict().items() if before.get(k) != v)
        problems.append(f"the artifact changed while the suite ran ({', '.join(changed)})")
    suites, suite_problems = _read_suites(run_dir)
    problems.extend(suite_problems)
    recorded = {s["id"] for s in suites}
    missing = [s for s in REQUIRED_SUITES if s not in recorded]
    if missing:
        problems.append(f"required suites were not run: {missing}")
    failed = sum(1 for s in suites if s["required"] and s["status"] != "pass")
    start = root if root is not None else running_code_root()
    try:
        repo_root = _git(start, "rev-parse", "--show-toplevel").decode().strip() or str(start)
    except IdentityUnavailable:
        repo_root = str(start)
    payload = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "passed": not problems and failed == 0,
        "failed": failed,
        "problems": problems,
        # What was tested: the identity taken before the suites ran. If it changed during
        # the run, ``problems`` says so and ``passed`` is false.
        "artifact": before,
        "provenance": {
            "producer": PRODUCER,
            "producer_version": PRODUCER_VERSION,
            "entrypoint": entrypoint,
            "run_id": started.get("run_id") or uuid.uuid4().hex,
            "host": socket.gethostname() or "unknown",
            "user": _user(),
            "python_executable": sys.executable or "unknown",
            "cwd": str(Path.cwd()),
            "repo_root": repo_root,
            "started_at": started.get("started_at") or _iso(_stamp(now)),
            "finished_at": _iso(_stamp(now)),
        },
        "suites": suites,
    }
    sealed = seal(payload)
    marker.parent.mkdir(parents=True, exist_ok=True)
    tmp = marker.with_name(marker.name + ".tmp")
    tmp.write_text(json.dumps(sealed, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(marker)
    return sealed


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m tia.live.verify_evidence {begin,finish}`` — used by scripts/verify.sh."""
    parser = argparse.ArgumentParser(prog="python -m tia.live.verify_evidence")
    parser.add_argument("step", choices=("begin", "finish"))
    parser.add_argument("--run-dir", type=Path, default=Path("data/runtime/verify_run"))
    parser.add_argument("--marker", type=Path, default=Path("data/runtime/verify_passed.json"))
    parser.add_argument("--entrypoint", default="scripts/verify.sh")
    args = parser.parse_args(argv)

    if args.step == "begin":
        args.marker.unlink(missing_ok=True)  # before anything else can fail

    from tia.core.config import get_settings

    settings = get_settings()
    if args.step == "begin":
        record = begin(args.run_dir, args.marker, settings=settings)
        if record["identity"] is None:
            sys.stderr.write(
                f"verify evidence: the artifact cannot be identified ({record['identity_problem']}); "
                "this run will not produce usable evidence\n"
            )
        return 0
    sealed = finish(args.run_dir, args.marker, settings=settings, entrypoint=args.entrypoint)
    artifact = sealed.get("artifact") or {}
    if sealed["passed"]:
        sys.stdout.write(
            f"verify evidence: written to {args.marker} for commit "
            f"{str(artifact.get('commit', ''))[:12]}\n"
        )
        return 0
    sys.stderr.write(
        f"verify evidence: {args.marker} records a run that does NOT pass: "
        f"{'; '.join(sealed['problems']) or str(sealed['failed']) + ' areas failed'}\n"
    )
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())


__all__ = [
    "EMERGENCY_CONTROL_MODULES",
    "KIND",
    "PYTEST_SUITES",
    "REQUIRED_SUITES",
    "RESTART_RECOVERY_MODULES",
    "SCHEMA_VERSION",
    "ArtifactIdentity",
    "Assessment",
    "IdentityUnavailable",
    "VerifyEvidence",
    "assess",
    "begin",
    "compute_identity",
    "current_identity",
    "dependencies_fingerprint",
    "evidence_configuration_fingerprint",
    "finish",
    "running_code_root",
    "seal",
]
