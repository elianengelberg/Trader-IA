"""``TIA_LIVE__EV_EVIDENCE_POLICY``: the estimator's and the retrospective's evidence
policy is read from the environment, defaults to ``legacy`` so an upgrade changes
nothing, and refuses anything that is not one of the two policies."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tia.core.config import Settings


def test_the_ev_evidence_policy_defaults_to_legacy_and_validates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TIA_LIVE__EV_EVIDENCE_POLICY", raising=False)
    assert Settings(_env_file=None).live.ev_evidence_policy == "legacy"
    monkeypatch.setenv("TIA_LIVE__EV_EVIDENCE_POLICY", "real_only")
    assert Settings(_env_file=None).live.ev_evidence_policy == "real_only"
    monkeypatch.setenv("TIA_LIVE__EV_EVIDENCE_POLICY", "mostly_real")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_the_two_policies_are_independent_knobs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIA_LIVE__SCOREBOARD_POLICY", "real_only")
    monkeypatch.delenv("TIA_LIVE__EV_EVIDENCE_POLICY", raising=False)
    live = Settings(_env_file=None).live
    assert live.scoreboard_policy == "real_only"
    assert live.ev_evidence_policy == "legacy"
