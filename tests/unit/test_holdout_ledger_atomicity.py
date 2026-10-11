"""An access to the holdout is on record from the moment it is opened (Phase 1.3): a run
that dies between the gate and the result still counts as having read the data."""

from __future__ import annotations

import json
from pathlib import Path

from tests.unit.test_holdout_ledger import _access
from tia.backtest.holdout import HoldoutAccess, HoldoutLedger


def test_opening_an_access_writes_a_line_before_any_result_exists(tmp_path: Path) -> None:
    ledger = HoldoutLedger(tmp_path / "holdout.jsonl")
    opened = ledger.open_access(
        dataset_id="ds1", config_hash="cfgA", variants_on_validation=0, git_head="abc", git_dirty=False,
        reason="", at="2026-10-11T00:00:00+00:00",
    )
    assert opened.status == "opened" and opened.verdicts == {} and opened.reopen is False
    lines = [json.loads(line) for line in (tmp_path / "holdout.jsonl").read_text().splitlines()]
    assert len(lines) == 1 and lines[0]["status"] == "opened"
    assert ledger.prior("ds1") == [opened]


def test_a_repeat_after_an_opened_but_never_completed_access_is_refused(tmp_path: Path) -> None:
    ledger = HoldoutLedger(tmp_path / "holdout.jsonl")
    ledger.open_access(
        dataset_id="ds1", config_hash="cfgA", variants_on_validation=0, git_head="abc", git_dirty=False,
        reason="", at="2026-10-11T00:00:00+00:00",
    )
    allowed, why = ledger.check(dataset_id="ds1", config_hash="cfgA", reopen_reason="the process crashed")
    assert not allowed
    assert "opened (and never completed)" in why and "the data was read" in why
    # A changed configuration still needs a reason, as before.
    refused, why2 = ledger.check(dataset_id="ds1", config_hash="cfgB", reopen_reason="")
    assert not refused and "--holdout-reopen-reason" in why2


def test_a_completed_access_follows_the_opened_one_and_old_lines_read_as_completed(tmp_path: Path) -> None:
    path = tmp_path / "holdout.jsonl"
    ledger = HoldoutLedger(path)
    ledger.open_access(
        dataset_id="ds1", config_hash="cfgA", variants_on_validation=0, git_head="abc", git_dirty=False,
        reason="", at="2026-10-11T00:00:00+00:00",
    )
    ledger.record(_access(verdicts={"trend_following@5m": "INCONCLUSIVE"}, status="completed"))
    # A line from before the field existed: no "status" key.
    legacy = {"at": "2026-10-09T00:00:00+00:00", "dataset_id": "ds2", "config_hash": "cfgZ",
              "variants_on_validation": 3, "verdicts": {}, "git_head": "x", "git_dirty": False,
              "reason": "", "reopen": False}
    path.write_text(path.read_text() + json.dumps(legacy) + "\n")
    entries = ledger.entries()
    assert [e.status for e in entries] == ["opened", "completed", "completed"]
    allowed, why = ledger.check(dataset_id="ds1", config_hash="cfgA", reopen_reason="")
    assert not allowed and "already computed" in why
    assert HoldoutAccess(at="", dataset_id="", config_hash="", variants_on_validation=0).status == "completed"
