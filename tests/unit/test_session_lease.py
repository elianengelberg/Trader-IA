"""The run row's heartbeat lease (Phase 1.3, G9): how a boot tells a session another
process is still running from one that died, without a new column."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from tia.runtime.session_limits import (
    HEARTBEAT_KEY,
    LEASE_SECONDS,
    clear_heartbeat,
    decode_heartbeat,
    decode_session_deadline,
    encode_heartbeat,
    encode_session_notes,
    lease_age_seconds,
    lease_is_held,
    resume_decision,
)

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def test_the_heartbeat_round_trips_and_keeps_the_deadline_beside_it() -> None:
    deadline = NOW + timedelta(hours=3)
    notes = encode_session_notes(deadline=deadline, max_hours=3.0)
    stamped = encode_heartbeat(notes, at=NOW)
    assert decode_heartbeat(stamped) == NOW
    assert decode_session_deadline(stamped) == deadline, "the deadline survives the stamp"
    assert json.loads(stamped)["max_hours"] == 3.0


def test_a_heartbeat_on_an_empty_or_free_text_note_keeps_the_text() -> None:
    assert decode_heartbeat(encode_heartbeat("", at=NOW)) == NOW
    stamped = encode_heartbeat("start_failed: clock skew", at=NOW)
    assert decode_heartbeat(stamped) == NOW
    assert json.loads(stamped)["note"] == "start_failed: clock skew"
    assert decode_session_deadline(stamped) is None


def test_no_heartbeat_means_no_lease() -> None:
    assert decode_heartbeat(None) is None and decode_heartbeat("") is None
    assert decode_heartbeat("free text") is None
    assert lease_age_seconds("", now=NOW) is None
    assert lease_is_held("", now=NOW) is False
    assert lease_is_held(encode_session_notes(deadline=NOW, max_hours=1.0), now=NOW) is False


def test_a_fresh_heartbeat_holds_the_lease_and_a_stale_one_does_not() -> None:
    fresh = encode_heartbeat("", at=NOW - timedelta(seconds=LEASE_SECONDS / 2))
    stale = encode_heartbeat("", at=NOW - timedelta(seconds=LEASE_SECONDS + 1))
    assert lease_is_held(fresh, now=NOW) is True
    assert lease_is_held(stale, now=NOW) is False
    assert lease_age_seconds(stale, now=NOW) == LEASE_SECONDS + 1
    # A heartbeat from a clock ahead of ours was still written recently.
    ahead = encode_heartbeat("", at=NOW + timedelta(seconds=30))
    assert lease_is_held(ahead, now=NOW) is True


def test_clearing_the_heartbeat_leaves_the_rest_of_the_notes() -> None:
    deadline = NOW + timedelta(hours=1)
    stamped = encode_heartbeat(encode_session_notes(deadline=deadline, max_hours=1.0), at=NOW)
    cleared = clear_heartbeat(stamped)
    assert decode_heartbeat(cleared) is None
    assert decode_session_deadline(cleared) == deadline
    assert HEARTBEAT_KEY not in json.loads(cleared)
    assert clear_heartbeat(encode_heartbeat("", at=NOW)) == "", "nothing else there: empty again"
    assert clear_heartbeat("free text") == "free text" and clear_heartbeat(None) is None


def test_a_held_lease_is_neither_resumed_nor_treated_as_interrupted() -> None:
    held = encode_heartbeat("", at=NOW - timedelta(seconds=10))
    decision = resume_decision(notes=held, halts=0, now=NOW)
    assert decision.resume is False and decision.held_by_other is True
    assert "another process" in decision.reason
    assert decision.as_dict()["held_by_other"] is True
    # The lease outranks everything else: even a halted run is left to its owner.
    assert resume_decision(notes=held, halts=2, now=NOW).held_by_other is True


def test_a_stale_lease_resumes_as_an_interrupted_run_does() -> None:
    stale = encode_heartbeat("", at=NOW - timedelta(seconds=LEASE_SECONDS * 2))
    decision = resume_decision(notes=stale, halts=0, now=NOW)
    assert decision.resume is True and decision.held_by_other is False
    deadline = NOW + timedelta(hours=2)
    with_deadline = encode_heartbeat(encode_session_notes(deadline=deadline, max_hours=2.0), at=NOW - timedelta(hours=1))
    decision = resume_decision(notes=with_deadline, halts=0, now=NOW)
    assert decision.resume is True and decision.deadline == deadline


def test_the_lease_window_can_be_set_aside_once_the_writer_is_known_dead() -> None:
    held = encode_heartbeat("", at=NOW - timedelta(seconds=10))
    assert resume_decision(notes=held, halts=0, now=NOW, lease_seconds=0.0).resume is True
    assert resume_decision(notes=held, halts=1, now=NOW, lease_seconds=0.0).resume is False
