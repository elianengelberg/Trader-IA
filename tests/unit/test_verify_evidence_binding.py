"""R22 — verification evidence must be bound to the exact artifact that would trade.

Before R22, ``TESTS_PASS`` (and ``EMERGENCY_CONTROLS`` / ``RESTART_RECOVERY``, which read
the same marker) passed on ``{"passed": true}`` alone: evidence from another commit, from
last month, from a tree edited afterwards or under a different configuration all
authorised activation. Every negative case below must make the checks FAIL; the positive
case shows that complete, matching evidence still passes.

The tests build throwaway git repositories under pytest's tmp_path (never the project's
own repository) so the identity the gate computes is real git output, deterministic, and
needs no network.

Red/green note: in the pre-R22 tree the evidence module does not exist, so the fixtures
fall back to the marker format that tree understands (``scripts/verify.sh``'s
``{"passed": true, ...}``) carrying the same underlying problem. The negative tests then
fail there because the old check *accepts* that evidence — which is the defect.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import tia.api.gate_probes as probes
from tia.core.config import Environment, LiveConfig, RiskLimits, settings_for_env
from tia.live.gate import CheckName, GateCheck

try:
    from tia.live import verify_evidence as ve
except ImportError:  # the pre-R22 tree: no evidence module (red run)
    ve = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The suites the gate must see, pinned here independently of the implementation.
REQUIRED_SUITES = ("lint", "unit", "integration", "property", "failure", "adversarial", "e2e", "smoke")
PYTEST_SUITES = ("unit", "integration", "property", "failure", "adversarial", "e2e")
RESTART_MODULE = "tests.integration.test_restart_recovery"
EMERGENCY_MODULES = ("tests.integration.test_live_runtime", "tests.integration.test_order_integrity")

BOUND_CHECKS = (CheckName.TESTS_PASS, CheckName.EMERGENCY_CONTROLS, CheckName.RESTART_RECOVERY)


# --------------------------------------------------------------------------- helpers


def _git_env(home: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["HOME"] = str(home)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def _git(repo: Path, *args: str) -> str:
    git = shutil.which("git")
    assert git, "these tests need a git executable"
    proc = subprocess.run(  # noqa: S603 - fixed args against a throwaway tmp repository
        [
            git,
            "-c", "user.name=r22-test",
            "-c", "user.email=r22-test@example.invalid",
            "-c", "commit.gpgsign=false",
            "-c", "init.defaultBranch=main",
            *args,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=_git_env(repo.parent),
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


class _State:
    """Just what ``build_probes`` reads, with no runtime running."""

    def __init__(self, *, live: LiveConfig | None = None, risk: RiskLimits | None = None) -> None:
        update: dict[str, Any] = {"live": live or LiveConfig(enabled=True, max_live_capital=100.0)}
        if risk is not None:
            update["risk"] = risk
        self.settings = settings_for_env(Environment.TESTING).model_copy(update=update)
        self.runtime = None
        self.live_runtime = None


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A committed, clean throwaway work tree, wired as the code the gate would run."""
    root = tmp_path / "work"
    (root / "src").mkdir(parents=True)
    (root / "tests" / "integration").mkdir(parents=True)
    (root / ".gitignore").write_text("data/runtime/\n", encoding="utf-8")
    (root / "src" / "app.py").write_text("LIMIT = 1\n", encoding="utf-8")
    (root / "README.md").write_text("throwaway repository for R22 tests\n", encoding="utf-8")
    (root / "tests" / "integration" / "test_restart_recovery.py").write_text(
        "def test_placeholder():\n    pass\n", encoding="utf-8"
    )
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial")

    marker = root / "data" / "runtime" / "verify_passed.json"
    marker.parent.mkdir(parents=True)
    monkeypatch.setattr(probes, "VERIFY_MARKER", marker)
    # The fix resolves the running code's tree from the package location; tests point it
    # at the throwaway repository instead. Harmless on the pre-R22 tree.
    monkeypatch.setattr(probes, "ARTIFACT_ROOT", root, raising=False)
    monkeypatch.chdir(root)
    return root


def _ts(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _junit(suite: str, modules: dict[str, int], failing: tuple[str, ...] = ()) -> str:
    cases = []
    for module, count in modules.items():
        for i in range(count):
            body = '<failure message="boom"/>' if module in failing and i == 0 else ""
            cases.append(f'<testcase classname="{module}" name="test_{i}" time="0.01">{body}</testcase>')
    failures = sum(1 for m in failing if m in modules)
    total = sum(modules.values())
    return (
        '<?xml version="1.0" encoding="utf-8"?><testsuites>'
        f'<testsuite name="pytest" errors="0" failures="{failures}" skipped="0" tests="{total}">'
        + "".join(cases)
        + "</testsuite></testsuites>"
    )


def _modules_for(suite: str) -> dict[str, int]:
    if suite == "integration":
        return {RESTART_MODULE: 1, EMERGENCY_MODULES[0]: 3, EMERGENCY_MODULES[1]: 2, "tests.integration.test_other": 4}
    return {f"tests.{suite}.test_sample": 3}


def _record_run(run_dir: Path, start: datetime, failing: dict[str, tuple[str, ...]] | None = None) -> None:
    """What ``scripts/verify.sh`` leaves in the run directory: one line per area plus
    pytest's junit XML for the pytest areas."""
    failing = failing or {}
    lines = []
    clock = start + timedelta(seconds=1)
    for suite in (*REQUIRED_SUITES, "frontend-build"):
        required = suite != "frontend-build"
        command = f"python -m pytest tests/{suite} -q" if suite in PYTEST_SUITES else f"run {suite}"
        exit_code = 1 if (suite in failing or not required) else 0
        if suite in PYTEST_SUITES:
            (run_dir / f"{suite}.xml").write_text(
                _junit(suite, _modules_for(suite), failing.get(suite, ())), encoding="utf-8"
            )
        lines.append(
            "\t".join([suite, "1" if required else "0", str(exit_code), _ts(clock), _ts(clock + timedelta(seconds=2)), command])
        )
        clock += timedelta(seconds=3)
    (run_dir / "suites.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _legacy_marker(repo: Path, when: datetime, **overrides: Any) -> dict[str, Any]:
    """The marker ``scripts/verify.sh`` writes before R22."""
    marker = {
        "passed": True,
        "failed": 0,
        "at": _ts(when),
        "commit": _git(repo, "rev-parse", "HEAD"),
        "dirty": False,
    }
    marker.update(overrides)
    return marker


def _produce(repo: Path, state: _State, *, when: datetime | None = None,
             failing: dict[str, tuple[str, ...]] | None = None) -> dict[str, Any]:
    """Run the real evidence writer (begin → suites → finish) against ``repo`` and
    return the marker it wrote. Pre-R22: write the legacy marker instead."""
    start = when or (datetime.now(UTC) - timedelta(minutes=5))
    marker_path = probes.VERIFY_MARKER
    if ve is None:
        marker = _legacy_marker(repo, start + timedelta(seconds=40))
        marker_path.write_text(json.dumps(marker), encoding="utf-8")
        return marker
    run_dir = marker_path.parent / "verify_run"
    ve.begin(run_dir, marker_path, settings=state.settings, root=repo, now=start)
    _record_run(run_dir, start, failing)
    ve.finish(run_dir, marker_path, settings=state.settings, root=repo,
              entrypoint="scripts/verify.sh", now=start + timedelta(seconds=40))
    return json.loads(marker_path.read_text(encoding="utf-8"))


def _write(marker: dict[str, Any] | list[Any] | str) -> None:
    text = marker if isinstance(marker, str) else json.dumps(marker)
    probes.VERIFY_MARKER.write_text(text, encoding="utf-8")


def _reseal(marker: dict[str, Any]) -> dict[str, Any]:
    """Recompute the self-digest after an edit — i.e. a *consistent* forgery, so the
    test proves the specific check rather than the digest."""
    return ve.seal(marker) if ve is not None else marker


def _checks(state: _State) -> dict[CheckName, GateCheck]:
    probes_map = probes.build_probes(state, database_ok=True)  # type: ignore[arg-type]
    return {name: probes_map[name] for name in BOUND_CHECKS}


def _assert_refused(state: _State, *needles: str, checks: tuple[CheckName, ...] = BOUND_CHECKS) -> None:
    results = _checks(state)
    for name in checks:
        check = results[name]
        assert not check.passed, f"{name.value} passed on evidence it must refuse: {check.detail}"
        text = check.detail.lower()  # the reason itself, not the generic remedy
        for needle in needles:
            assert needle.lower() in text, f"{name.value}: expected {needle!r} in {text!r}"


def _suite(marker: dict[str, Any], suite_id: str) -> dict[str, Any]:
    return next(s for s in marker["suites"] if s["id"] == suite_id)


# --------------------------------------------------------------------------- positive


def test_complete_matching_evidence_passes(repo: Path) -> None:
    state = _State()
    _produce(repo, state)
    results = _checks(state)
    for name in BOUND_CHECKS:
        assert results[name].passed, f"{name.value}: {results[name].detail}"
    if ve is not None:
        head = _git(repo, "rev-parse", "HEAD")
        assert head[:12] in results[CheckName.TESTS_PASS].detail


def test_writer_records_what_the_gate_needs(repo: Path) -> None:
    """The writer's own output: schema v2, provenance, artifact identity, every suite with
    exit code and timestamps, junit counts, and a digest over its own content."""
    state = _State()
    marker = _produce(repo, state)
    assert marker.get("schema_version") == 2
    assert marker["passed"] is True and marker["problems"] == []
    artifact = marker["artifact"]
    assert artifact["commit"] == _git(repo, "rev-parse", "HEAD")
    assert artifact["tree"] == _git(repo, "rev-parse", "HEAD^{tree}")
    assert artifact["dirty"] is False
    for key in ("worktree_digest", "status_digest", "config_fingerprint", "dependencies_digest"):
        assert artifact[key], key
    provenance = marker["provenance"]
    for key in ("producer", "entrypoint", "run_id", "host", "started_at", "finished_at"):
        assert provenance[key], key
    ids = [s["id"] for s in marker["suites"]]
    assert set(REQUIRED_SUITES) <= set(ids)
    unit = _suite(marker, "unit")
    assert unit["exit_code"] == 0 and unit["status"] == "pass" and unit["junit"]["tests"] == 3
    optional = _suite(marker, "frontend-build")
    assert optional["required"] is False and optional["exit_code"] == 1
    assert marker["digest"]["algorithm"] == "sha256"
    assert ve.seal(marker) == marker


# --------------------------------------------------------------------------- negatives


def test_evidence_from_another_commit_fails(repo: Path) -> None:
    """1) A green run on commit A says nothing about commit B."""
    state = _State()
    _produce(repo, state)
    (repo / "src" / "app.py").write_text("LIMIT = 1000\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "widen a limit after verifying")
    _assert_refused(state, "commit")


def test_evidence_from_an_older_commit_does_not_authorize_a_later_one_even_if_files_match(repo: Path) -> None:
    """Same content, new commit (e.g. an empty commit or a rebase): still another artifact."""
    state = _State()
    _produce(repo, state)
    _git(repo, "commit", "-q", "--allow-empty", "-m", "nothing changed, but it is not the tested commit")
    _assert_refused(state, "commit")


def test_stale_evidence_fails(repo: Path) -> None:
    """2) Evidence older than the configured bound is refused, and the bound is named."""
    state = _State()
    _produce(repo, state, when=datetime.now(UTC) - timedelta(hours=48))
    _assert_refused(state, "old", "verify_evidence_max_age_hours")


def test_evidence_from_the_future_fails(repo: Path) -> None:
    state = _State()
    _produce(repo, state, when=datetime.now(UTC) + timedelta(hours=3))
    _assert_refused(state, "future")


def test_max_age_is_an_explicit_setting_with_a_conservative_default(repo: Path) -> None:
    assert LiveConfig().verify_evidence_max_age_hours == 24.0
    with pytest.raises(ValueError):
        LiveConfig(verify_evidence_max_age_hours=24 * 365)  # cannot become a formality
    with pytest.raises(ValueError):
        LiveConfig(verify_evidence_max_age_hours=0)
    # A deliberately longer bound is honoured — for evidence produced under that config.
    state = _State(live=LiveConfig(enabled=True, max_live_capital=100.0, verify_evidence_max_age_hours=72))
    _produce(repo, state, when=datetime.now(UTC) - timedelta(hours=48))
    assert _checks(state)[CheckName.TESTS_PASS].passed


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("edit_tracked", "uncommitted"),
        ("stage_change", "uncommitted"),
        ("add_untracked", "uncommitted"),
        ("delete_tracked", "uncommitted"),
        ("hidden_by_assume_unchanged", "files on disk differ"),
    ],
)
def test_tree_modified_after_the_run_fails(repo: Path, change: str, reason: str) -> None:
    """3) Uncommitted changes of every kind — not only what ``git diff`` shows."""
    state = _State()
    _produce(repo, state)
    app = repo / "src" / "app.py"
    if change == "edit_tracked":
        app.write_text("LIMIT = 2\n", encoding="utf-8")
    elif change == "stage_change":
        app.write_text("LIMIT = 3\n", encoding="utf-8")
        _git(repo, "add", "src/app.py")
    elif change == "add_untracked":
        (repo / "src" / "sitecustomize.py").write_text("print('injected')\n", encoding="utf-8")
    elif change == "delete_tracked":
        (repo / "README.md").unlink()
    elif change == "hidden_by_assume_unchanged":
        # git status stays clean here; only hashing the files themselves notices.
        _git(repo, "update-index", "--assume-unchanged", "src/app.py")
        app.write_text("LIMIT = 4\n", encoding="utf-8")
        assert _git(repo, "status", "--porcelain") == ""
    _assert_refused(state, reason)


def test_evidence_from_a_dirty_tree_fails_even_if_nothing_changed_since(repo: Path) -> None:
    """Uncommitted code is not an artifact anyone can name; evidence about it is refused."""
    state = _State()
    (repo / "src" / "scratch.py").write_text("X = 1\n", encoding="utf-8")
    _produce(repo, state)
    _assert_refused(state, "uncommitted")


@pytest.mark.parametrize(
    ("variant", "reason"),
    [
        ("integration_missing", "incomplete"),
        ("smoke_missing", "incomplete"),
        ("unit_collected_nothing", "ran no test"),
    ],
)
def test_incomplete_suite_fails(repo: Path, variant: str, reason: str) -> None:
    """4) The gate decides which suites are required — not the marker — and a pytest
    suite that collected nothing proved nothing."""
    state = _State()
    marker = _produce(repo, state)
    if ve is not None:
        if variant == "integration_missing":
            marker["suites"] = [s for s in marker["suites"] if s["id"] != "integration"]
        elif variant == "smoke_missing":
            marker["suites"] = [s for s in marker["suites"] if s["id"] != "smoke"]
        else:
            unit = _suite(marker, "unit")
            unit["junit"].update(tests=0, failures=0, errors=0, skipped=0, modules={})
        _write(_reseal(marker))
    _assert_refused(state, reason, checks=(CheckName.TESTS_PASS,))


@pytest.mark.parametrize("variant", ["suite_failed", "exit_zero_but_junit_failure", "status_pass_exit_nonzero", "top_level_not_passed"])
def test_failed_test_fails(repo: Path, variant: str) -> None:
    """5) A failure anywhere in the required suites refuses, whatever ``passed`` says."""
    state = _State()
    if ve is None:
        _produce(repo, state)
        _assert_refused(state, checks=(CheckName.TESTS_PASS,))
        return
    if variant == "suite_failed":
        # The honest writer records it — and must not record it as passed.
        marker = _produce(repo, state, failing={"integration": ("tests.integration.test_other",)})
        assert marker["passed"] is False
        _assert_refused(state, "did not pass")
        # Forge "passed": true over the same failure and reseal it: still refused.
        marker["passed"], marker["failed"], marker["problems"] = True, 0, []
        _write(_reseal(marker))
        _assert_refused(state, "integration failed")
        return
    marker = _produce(repo, state)
    integration = _suite(marker, "integration")
    if variant == "exit_zero_but_junit_failure":
        integration["junit"]["failures"] = 1
        integration["junit"]["modules"]["tests.integration.test_other"]["failures"] = 1
        reason = "1 failures"
    elif variant == "status_pass_exit_nonzero":
        integration["exit_code"] = 2
        reason = "incoherent"
    else:
        marker["passed"] = False
        reason = "not passed"
    _write(_reseal(marker))
    _assert_refused(state, reason, checks=(CheckName.TESTS_PASS,))


@pytest.mark.parametrize("variant", ["commit_edited", "suite_flipped", "digest_removed", "digest_value_edited"])
def test_altered_manifest_fails(repo: Path, variant: str) -> None:
    """6) An edit that does not recompute the digest is detected.

    (The digest is unkeyed: it catches corruption and naive edits, not a forger who
    recomputes it — that case is covered by the other checks, see README_R22.)"""
    state = _State()
    marker = _produce(repo, state, failing={"e2e": ("tests.e2e.test_sample",)})
    if ve is None:
        _write(_legacy_marker(repo, datetime.now(UTC), commit="deadbeef"))
        _assert_refused(state)
        return
    if variant == "commit_edited":
        marker["artifact"]["commit"] = "0" * 40
    elif variant == "suite_flipped":
        e2e = _suite(marker, "e2e")
        e2e.update(exit_code=0, status="pass")
        e2e["junit"]["failures"] = 0
        marker.update(passed=True, failed=0, problems=[])
    elif variant == "digest_removed":
        marker.pop("digest")
    else:
        marker["digest"]["value"] = "f" * 64
    _write(marker)  # NOT resealed
    _assert_refused(state, "digest")


@pytest.mark.parametrize("variant", ["risk_limit", "capital_ceiling", "environment_target"])
def test_different_configuration_fails(repo: Path, variant: str) -> None:
    """7) Same code, other configuration: the suite did not vouch for this one."""
    verified = _State()
    _produce(repo, verified)
    if variant == "risk_limit":
        running = _State(risk=RiskLimits(**{**verified.settings.risk.model_dump(), "daily_loss_limit_pct": 9.0}))
    elif variant == "capital_ceiling":
        running = _State(live=LiveConfig(enabled=True, max_live_capital=5_000.0))
    else:
        running = _State(live=LiveConfig(enabled=True, max_live_capital=100.0, use_testnet=False))
    assert running.settings != verified.settings
    _assert_refused(running, "configuration")


def test_credentials_do_not_enter_the_configuration_identity(repo: Path) -> None:
    """Tests are best run without the venue secret in the shell; evidence produced that
    way must still match a deployment that has it (the key is checked by
    credentials_scoped, against the venue)."""
    from pydantic import SecretStr

    without_key = _State()
    _produce(repo, without_key)
    with_key = _State(live=LiveConfig(
        enabled=True,
        max_live_capital=100.0,
        binance_api_key=SecretStr("not-a-real-key"),
        binance_api_secret=SecretStr("not-a-real-secret"),
    ))
    check = _checks(with_key)[CheckName.TESTS_PASS]
    assert check.passed, check.detail


def test_different_dependencies_fail(repo: Path) -> None:
    """Same code and config, other installed packages: refused."""
    state = _State()
    marker = _produce(repo, state)
    if ve is not None:
        marker["artifact"]["dependencies_digest"] = "a" * 64
        _write(_reseal(marker))
    _assert_refused(state, "dependencies", checks=(CheckName.TESTS_PASS,))


@pytest.mark.parametrize("variant", ["provenance_removed", "provenance_blank"])
def test_missing_provenance_fails(repo: Path, variant: str) -> None:
    """8) Evidence that cannot say who produced it, where and when is not evidence."""
    state = _State()
    marker = _produce(repo, state)
    if ve is not None:
        if variant == "provenance_removed":
            marker.pop("provenance")
        else:
            marker["provenance"].update(host="", run_id="", entrypoint="")
        _write(_reseal(marker))
    _assert_refused(state, "provenance")


def test_missing_marker_fails(repo: Path) -> None:
    state = _State()
    assert not probes.VERIFY_MARKER.exists()
    _assert_refused(state, *(("no verification evidence",) if ve is not None else ()))


@pytest.mark.parametrize("content", ["{not json", "", "\x00\x01\x02", "[1, 2, 3]", '"passed"'])
def test_unreadable_marker_fails(repo: Path, content: str) -> None:
    state = _State()
    _write(content)
    _assert_refused(state, *(("json",) if ve is not None else ()))


def test_legacy_marker_format_fails_even_on_the_right_commit(repo: Path) -> None:
    """The pre-R22 format (exactly what scripts/verify.sh wrote) binds nothing, so it is
    refused — even when its commit happens to be HEAD and it claims a clean tree."""
    state = _State()
    _write(_legacy_marker(repo, datetime.now(UTC) - timedelta(minutes=1)))
    _assert_refused(state, "schema")


def test_identity_undeterminable_without_git_metadata_fails(repo: Path, tmp_path: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """Like the Docker image (no .git): the process cannot say what it is running, so the
    check fails and says why — it does not invent an identity."""
    state = _State()
    _produce(repo, state)
    exported = tmp_path / "exported"
    shutil.copytree(repo, exported, ignore=shutil.ignore_patterns(".git"))
    monkeypatch.setattr(probes, "ARTIFACT_ROOT", exported, raising=False)
    _assert_refused(state, "identity")


def test_identity_undeterminable_without_git_executable_fails(repo: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    state = _State()
    _produce(repo, state)
    monkeypatch.setenv("PATH", "")
    _assert_refused(state, "identity", "git")


def test_restart_and_emergency_checks_require_their_own_tests_to_have_run(repo: Path) -> None:
    """The suite passing is not enough for these two: the specific test modules must
    have run and passed in it (deselected or skipped proves nothing)."""
    state = _State()
    marker = _produce(repo, state)
    if ve is not None:
        integration = _suite(marker, "integration")
        modules = integration["junit"]["modules"]
        removed = modules.pop(RESTART_MODULE)["tests"] + modules.pop(EMERGENCY_MODULES[0])["tests"]
        integration["junit"]["tests"] -= removed
        _write(_reseal(marker))
    results = _checks(state)
    if ve is not None:
        assert results[CheckName.TESTS_PASS].passed, results[CheckName.TESTS_PASS].detail
    for name, needle in ((CheckName.RESTART_RECOVERY, RESTART_MODULE),
                         (CheckName.EMERGENCY_CONTROLS, EMERGENCY_MODULES[0])):
        assert not results[name].passed, f"{name.value}: {results[name].detail}"
        assert needle in results[name].detail


def test_writer_refuses_when_the_tree_changes_during_the_run(repo: Path) -> None:
    """Edits made while the suite runs mean the run tested neither version."""
    assert ve is not None, "pre-R22 tree: there is no evidence writer to bind a run"
    state = _State()
    marker_path = probes.VERIFY_MARKER
    run_dir = marker_path.parent / "verify_run"
    start = datetime.now(UTC) - timedelta(minutes=5)
    ve.begin(run_dir, marker_path, settings=state.settings, root=repo, now=start)
    _record_run(run_dir, start)
    (repo / "src" / "app.py").write_text("LIMIT = 5\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "changed mid-run")
    marker = ve.finish(run_dir, marker_path, settings=state.settings, root=repo,
                       entrypoint="scripts/verify.sh", now=start + timedelta(seconds=40))
    assert marker["passed"] is False
    assert any("changed" in p for p in marker["problems"])
    _assert_refused(state)


def test_begin_discards_the_previous_marker(repo: Path) -> None:
    """A run that starts and never finishes must leave no evidence behind."""
    assert ve is not None, "pre-R22 tree: there is no evidence writer"
    state = _State()
    _produce(repo, state)
    assert probes.VERIFY_MARKER.exists()
    ve.begin(probes.VERIFY_MARKER.parent / "verify_run", probes.VERIFY_MARKER,
             settings=state.settings, root=repo)
    assert not probes.VERIFY_MARKER.exists()
    _assert_refused(state, "no verification evidence")


def test_verify_script_writes_bound_evidence_not_a_bare_flag() -> None:
    """scripts/verify.sh must delegate the marker to the evidence writer."""
    script = (REPO_ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
    assert "tia.live.verify_evidence begin" in script
    assert "tia.live.verify_evidence finish" in script
    assert "--junitxml" in script
    assert "cat > data/runtime/verify_passed.json" not in script
