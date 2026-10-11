"""Multiplicity does not reset between invocations (Phase 1.3).

Two runs on the same validation partition, each with one candidate, are two candidates
judged on the same data: the second run's Bonferroni family is two. The same candidate
judged twice under the same strategy code is one look. Synthetic fixtures; nothing here is
evidence about a market, and the holdout is never computed.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.integration.test_strategy_experiment_script import _run


def test_the_family_accumulates_across_runs_on_the_same_partition(tmp_path: Path) -> None:
    ledger = tmp_path / "holdout.jsonl"
    log = tmp_path / "research_runs.jsonl"
    first = _run("--json", str(tmp_path / "first.json"), "--holdout-log", str(ledger))
    assert first.returncode == 0, first.stderr[-2000:]
    record_1 = json.loads((tmp_path / "first.json").read_text())
    assert record_1["inference"]["family_size"] == 1
    assert record_1["inference"]["family_cumulative"] == 1
    assert record_1["inference"]["adjusted_level"] == 0.90
    assert record_1["inference"]["research_log"] == str(log), "next to the holdout ledger by default"
    assert log.exists() and len(log.read_text().splitlines()) == 1

    # Another candidate on the same partition: a different strategy.
    second = _run("--json", str(tmp_path / "second.json"), "--holdout-log", str(ledger),
                  "--strategies", "mean_reversion")
    assert second.returncode == 0, second.stderr[-2000:]
    record_2 = json.loads((tmp_path / "second.json").read_text())
    assert record_2["inference"]["family_size"] == 1, "one candidate in this run"
    assert record_2["inference"]["family_cumulative"] == 2, "two ever on this partition"
    assert record_2["inference"]["adjusted_level"] == 0.95
    assert record_2["inference"]["partition_id"] == record_1["inference"]["partition_id"]
    for cell in record_2["cells"]:
        assert cell["ci_adjusted_level"] == 0.95
    assert "2 ever on this partition" in second.stdout

    # The same candidate again, same code: one look, the family does not grow.
    third = _run("--json", str(tmp_path / "third.json"), "--holdout-log", str(ledger),
                 "--strategies", "mean_reversion")
    assert third.returncode == 0, third.stderr[-2000:]
    record_3 = json.loads((tmp_path / "third.json").read_text())
    assert record_3["inference"]["family_cumulative"] == 2
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(lines) == 3 and all(line["partition_id"] == record_1["inference"]["partition_id"] for line in lines)
    assert lines[1]["candidates"] == lines[2]["candidates"]
    assert all(line["holdout_unlocked"] is False for line in lines)
    assert not ledger.exists(), "sealed runs touch no holdout ledger"


def test_a_different_partition_is_its_own_family_and_the_record_carries_the_half_split(tmp_path: Path) -> None:
    ledger = tmp_path / "holdout.jsonl"
    log = tmp_path / "log.jsonl"
    a = _run("--json", str(tmp_path / "a.json"), "--holdout-log", str(ledger), "--research-log", str(log))
    assert a.returncode == 0, a.stderr[-2000:]
    b = _run("--json", str(tmp_path / "b.json"), "--holdout-log", str(ledger), "--research-log", str(log),
             "--strategies", "breakout", "--split", "0.4,0.3")
    assert b.returncode == 0, b.stderr[-2000:]
    record_b = json.loads((tmp_path / "b.json").read_text())
    assert record_b["inference"]["family_cumulative"] == 1, "a different cut of the data is another partition"
    assert record_b["inference"]["research_log"] == str(log)
    record_a = json.loads((tmp_path / "a.json").read_text())
    assert record_a["inference"]["percentile_method"].startswith("linear interpolation")
    validation = [c for c in record_a["cells"] if c["partition"] == "validation" and c["cost_variant"] == "base"]
    assert validation
    for cell in validation:
        split = cell["half_split"]
        if cell["trades"] >= 4:
            assert split is not None and set(split) >= {"first_half_mean_bps", "second_half_mean_bps", "same_sign"}
            assert split["first_half_trades"] + split["second_half_trades"] == cell["trades"]
        else:
            assert split is None
