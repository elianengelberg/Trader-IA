"""The experiment harness end to end on the committed synthetic fixtures.

These runs prove the pipeline — partitions, resampling, inference, the record and the
holdout ledger — and nothing about any market: the fixtures are generated. The holdout is
never computed here; what is tested of it is the refusal path.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "strategy_experiment.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT / "packages" / "tia" / "src"))
    return subprocess.run(  # noqa: S603 - fixed argv, test-owned inputs
        [sys.executable, str(SCRIPT), "--fixtures", str(REPO_ROOT / "data" / "fixtures"),
         "--symbol", "BTC-USD", "--timeframes", "5m", "--strategies", "trend_following",
         "--fee-multipliers", "1.0,1.5", "--extra-slippage-bps", "0", "--resamples", "300", *args],
        capture_output=True, text=True, cwd=REPO_ROOT, env=env, timeout=600, check=False,
    )


def test_a_sealed_run_records_inference_and_multiplicity_and_computes_no_holdout(tmp_path: Path) -> None:
    out = tmp_path / "record.json"
    ledger = tmp_path / "holdout.jsonl"
    result = _run("--json", str(out), "--holdout-log", str(ledger))
    assert result.returncode == 0, result.stderr[-2000:]
    record = json.loads(out.read_text())
    assert record["holdout"]["unlocked"] is False and record["holdout"]["recorded"] is False
    assert not ledger.exists(), "a sealed run touches no ledger"
    assert {c["partition"] for c in record["cells"]} <= {"research", "validation"}
    assert record["inference"]["interval"] == "circular_block"
    assert record["inference"]["family_size"] == 1
    assert record["inference"]["adjusted_level"] == 0.90
    assert record["criteria"]["ci_lower_min_bps"] == 0.0
    verdicts = record["verdicts"]
    assert set(verdicts) == {"trend_following@5m"}
    entry = verdicts["trend_following@5m"]
    assert entry["verdict"] in {"INSUFFICIENT", "UNFAVOURABLE", "INCONCLUSIVE", "FRAGILE", "PROMISING_ON_VALIDATION"}
    assert entry["reason"]
    for cell in record["cells"]:
        assert cell["ci_adjusted_level"] == 0.90
        if cell["trades"] >= 2:
            assert cell["ci90_bps"] is not None and cell["ci_iid_bps"] is not None
            assert cell["block_length"] >= 1
    assert "SEALED" in result.stdout and "synthetic" in result.stdout


def test_unlocking_a_holdout_already_computed_under_the_same_configuration_is_refused(tmp_path: Path) -> None:
    """The ledger holds an access under this exact dataset and configuration (as a prior
    computation would have written it): the unlock is refused before anything runs and
    the ledger is not extended. No holdout is computed by this test."""
    out = tmp_path / "record.json"
    ledger = tmp_path / "holdout.jsonl"
    sealed = _run("--json", str(out), "--holdout-log", str(ledger))
    assert sealed.returncode == 0, sealed.stderr[-2000:]
    record = json.loads(out.read_text())
    prior = {
        "at": "2026-10-09T00:00:00+00:00", "dataset_id": record["holdout"]["dataset_id"],
        "config_hash": record["frozen_config_hash"], "variants_on_validation": 2,
        "verdicts": {}, "git_head": "abc", "git_dirty": False, "reason": "", "reopen": False,
    }
    ledger.write_text(json.dumps(prior) + "\n")

    refused = _run("--unlock-holdout", "--holdout-log", str(ledger), "--json", str(tmp_path / "never.json"))
    assert refused.returncode == 2
    assert "holdout REFUSED" in refused.stderr and "already computed under this exact configuration" in refused.stderr
    assert not (tmp_path / "never.json").exists(), "nothing was computed"
    assert len(ledger.read_text().splitlines()) == 1, "the ledger was not extended"

    reopened_without_reason = _run(
        "--unlock-holdout", "--holdout-log", str(ledger), "--seed", "7",  # a changed configuration
        "--json", str(tmp_path / "never2.json"),
    )
    assert reopened_without_reason.returncode == 2
    assert "--holdout-reopen-reason" in reopened_without_reason.stderr
    assert not (tmp_path / "never2.json").exists()
