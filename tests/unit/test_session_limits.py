"""The validation session's deadline outside the runtime: how it is written into the run
row and what a boot does when it finds an interrupted run."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tia.runtime.session_limits import (
    decode_session_deadline,
    encode_session_notes,
    resume_decision,
)

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def test_the_deadline_round_trips_through_the_notes_column() -> None:
    notes = encode_session_notes(deadline=NOW + timedelta(hours=8), max_hours=8.0)
    assert decode_session_deadline(notes) == NOW + timedelta(hours=8)


def test_no_deadline_writes_nothing_and_old_free_text_reads_as_no_deadline() -> None:
    assert encode_session_notes(deadline=None, max_hours=None) == ""
    assert decode_session_deadline("") is None
    assert decode_session_deadline(None) is None
    assert decode_session_deadline("Deterministic simulation. Contains no real market information.") is None
    assert decode_session_deadline('{"other": 1}') is None
    assert decode_session_deadline('{"session_deadline": "not a date"}') is None
    assert decode_session_deadline("[1, 2]") is None


def test_a_naive_deadline_in_the_notes_is_read_as_utc() -> None:
    assert decode_session_deadline('{"session_deadline": "2026-10-10T20:00:00"}') == NOW + timedelta(hours=8)


def test_a_halted_run_never_resumes_whatever_its_deadline() -> None:
    notes = encode_session_notes(deadline=NOW + timedelta(hours=8), max_hours=8.0)
    decision = resume_decision(notes=notes, halts=1, now=NOW)
    assert decision.resume is False and "halt" in decision.reason


def test_a_run_whose_deadline_passed_does_not_resume() -> None:
    notes = encode_session_notes(deadline=NOW - timedelta(minutes=1), max_hours=8.0)
    decision = resume_decision(notes=notes, halts=0, now=NOW)
    assert decision.resume is False and "deadline" in decision.reason
    assert decision.deadline == NOW - timedelta(minutes=1)


def test_a_run_with_time_left_resumes_under_the_same_deadline_not_a_fresh_one() -> None:
    deadline = NOW + timedelta(hours=3)
    decision = resume_decision(notes=encode_session_notes(deadline=deadline, max_hours=8.0), halts=0, now=NOW)
    assert decision.resume is True
    assert decision.deadline == deadline, "a restart buys no extra hours"


def test_a_run_without_a_deadline_resumes_as_the_24_7_session_always_has() -> None:
    decision = resume_decision(notes="", halts=0, now=NOW)
    assert decision.resume is True and decision.deadline is None
    assert decision.as_dict()["deadline"] is None


def test_at_the_exact_deadline_the_run_is_over() -> None:
    notes = encode_session_notes(deadline=NOW, max_hours=1.0)
    assert resume_decision(notes=notes, halts=0, now=NOW).resume is False
