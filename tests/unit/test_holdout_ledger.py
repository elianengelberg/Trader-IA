"""The holdout's procedural lock: every computation recorded, a repeat under the same
configuration refused, a reopen under a changed configuration requires a named reason.
Nothing here computes a holdout."""

from __future__ import annotations

import json
from pathlib import Path

from tia.backtest.holdout import HoldoutAccess, HoldoutLedger, config_hash, git_state


def _access(dataset: str = "ds1", config: str = "cfgA", **extra: object) -> HoldoutAccess:
    base = {"at": "2026-10-10T00:00:00+00:00", "dataset_id": dataset, "config_hash": config,
            "variants_on_validation": 6}
    base.update(extra)
    return HoldoutAccess(**base)  # type: ignore[arg-type]


def test_first_access_is_allowed_and_recorded(tmp_path: Path) -> None:
    ledger = HoldoutLedger(tmp_path / "holdout.jsonl")
    allowed, why = ledger.check(dataset_id="ds1", config_hash="cfgA", reopen_reason="")
    assert allowed and "first access" in why
    ledger.record(_access())
    entries = ledger.entries()
    assert len(entries) == 1 and entries[0].dataset_id == "ds1"
    assert ledger.prior("ds1") and not ledger.prior("other")


def test_a_repeat_under_the_same_configuration_is_refused_even_with_a_reason(tmp_path: Path) -> None:
    ledger = HoldoutLedger(tmp_path / "holdout.jsonl")
    ledger.record(_access())
    allowed, why = ledger.check(dataset_id="ds1", config_hash="cfgA", reopen_reason="I would like to")
    assert not allowed and "already computed under this exact configuration" in why


def test_a_changed_configuration_needs_a_named_reason(tmp_path: Path) -> None:
    ledger = HoldoutLedger(tmp_path / "holdout.jsonl")
    ledger.record(_access())
    refused, why = ledger.check(dataset_id="ds1", config_hash="cfgB", reopen_reason="")
    assert not refused and "--holdout-reopen-reason" in why
    allowed, why2 = ledger.check(dataset_id="ds1", config_hash="cfgB", reopen_reason="new out-of-sample period after a frozen change")
    assert allowed and "reopened" in why2


def test_another_dataset_is_a_first_access(tmp_path: Path) -> None:
    ledger = HoldoutLedger(tmp_path / "holdout.jsonl")
    ledger.record(_access())
    allowed, _ = ledger.check(dataset_id="ds2", config_hash="cfgA", reopen_reason="")
    assert allowed


def test_the_ledger_is_append_only_and_tolerates_a_corrupt_line(tmp_path: Path) -> None:
    path = tmp_path / "holdout.jsonl"
    ledger = HoldoutLedger(path)
    ledger.record(_access())
    path.write_text(path.read_text() + "not json\n")
    ledger.record(_access(dataset="ds2"))
    lines = [line for line in path.read_text().splitlines() if line.strip()]
    assert len(lines) == 3
    assert [e.dataset_id for e in ledger.entries()] == ["ds1", "ds2"]
    assert json.loads(lines[0])["dataset_id"] == "ds1"


def test_the_configuration_hash_covers_the_strategy_code(tmp_path: Path) -> None:
    code = tmp_path / "strategy.py"
    code.write_text("def signal(): return 1\n")
    config = {"criteria": {"min_trades": 30}, "strategies": ["a"]}
    before = config_hash(config, code_paths=[code])
    assert before == config_hash(config, code_paths=[code]), "deterministic"
    assert before != config_hash({**config, "strategies": ["b"]}, code_paths=[code])
    code.write_text("def signal(): return 2\n")
    assert before != config_hash(config, code_paths=[code]), "a code change is a configuration change"


def test_git_state_never_raises() -> None:
    head, dirty = git_state(Path("/nonexistent-directory-for-this-test"))
    assert isinstance(head, str) and (dirty is None or isinstance(dirty, bool))
