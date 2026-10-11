"""A validation session's deadline, and what a restart does with it.

The deadline is enforced inside :class:`~tia.runtime.live.LiveRuntime` (see
``_check_deadline``). This module holds the two pieces that live outside the runtime: how
the deadline is written into the run row so it survives the process, and the decision a
boot makes when it finds a run the process died in the middle of.

The run row's ``notes`` column carries a small JSON document rather than a new column: no
migration, and a reader that finds free text there (every run before this existed) gets
"no deadline", which is what those runs had.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from tia.core.clock import ensure_utc

NOTES_KEY = "session_deadline"
#: The run row's heartbeat (Phase 1.3, G9): the session's clock, stamped by the running
#: process every :attr:`~tia.runtime.live.LiveRuntime._heartbeat_every_seconds`. A boot
#: that finds an open run with a heartbeat younger than ``LEASE_SECONDS`` is looking at a
#: session another process is still running — not at one that died — and must neither
#: stamp it nor start a second session over the same account.
HEARTBEAT_KEY = "heartbeat_at"
LEASE_SECONDS = 120.0


def encode_session_notes(*, deadline: datetime | None, max_hours: float | None) -> str:
    if deadline is None:
        return ""
    return json.dumps(
        {NOTES_KEY: ensure_utc(deadline).isoformat(), "max_hours": max_hours},
        sort_keys=True,
    )


def decode_session_deadline(notes: str | None) -> datetime | None:
    """The deadline a run row carries, or ``None`` for free text, empty text or no key."""
    if not notes:
        return None
    try:
        payload: Any = json.loads(notes)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    raw = payload.get(NOTES_KEY)
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _notes_payload(notes: str | None) -> dict[str, Any] | None:
    """The JSON document in ``notes``, or ``None`` for empty or free text."""
    if not notes:
        return None
    try:
        payload: Any = json.loads(notes)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def encode_heartbeat(notes: str | None, *, at: datetime) -> str:
    """``notes`` with the heartbeat set to ``at``; other keys (the deadline, a note) are
    kept. Free text an older run left there becomes the document's ``note``."""
    payload = _notes_payload(notes)
    if payload is None:
        payload = {"note": notes} if notes else {}
    payload[HEARTBEAT_KEY] = ensure_utc(at).isoformat()
    return json.dumps(payload, sort_keys=True)


def clear_heartbeat(notes: str | None) -> str | None:
    """``notes`` without its heartbeat: what a clean shutdown leaves, so the next boot
    reads an interrupted session rather than one another process holds."""
    payload = _notes_payload(notes)
    if payload is None or HEARTBEAT_KEY not in payload:
        return notes
    payload.pop(HEARTBEAT_KEY, None)
    if not payload:
        return ""
    return json.dumps(payload, sort_keys=True)


def decode_heartbeat(notes: str | None) -> datetime | None:
    payload = _notes_payload(notes)
    if payload is None:
        return None
    raw = payload.get(HEARTBEAT_KEY)
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def lease_age_seconds(notes: str | None, *, now: datetime) -> float | None:
    """Seconds since the run's last heartbeat, or ``None`` when it never had one."""
    beat = decode_heartbeat(notes)
    if beat is None:
        return None
    return (ensure_utc(now) - beat).total_seconds()


def lease_is_held(notes: str | None, *, now: datetime, lease_seconds: float = LEASE_SECONDS) -> bool:
    """Whether another process is, by its heartbeat, still running this run. A heartbeat
    from the future (a clock ahead of ours) also counts as held: it was written recently."""
    age = lease_age_seconds(notes, now=now)
    return age is not None and age < lease_seconds


@dataclass(frozen=True)
class ResumeDecision:
    resume: bool
    reason: str
    deadline: datetime | None = None
    #: True when the run is not resumed because another process is still running it
    #: (its heartbeat is fresh). The caller must then leave the row unstamped.
    held_by_other: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "resume": self.resume,
            "reason": self.reason,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "held_by_other": self.held_by_other,
        }


def resume_decision(
    *, notes: str | None, halts: int, now: datetime, lease_seconds: float = LEASE_SECONDS
) -> ResumeDecision:
    """Whether a run the process died in resumes, and under which deadline.

    * A run whose heartbeat is younger than ``lease_seconds`` did not die: another
      process is running it. It is neither resumed nor stamped (Phase 1.3, G9).
    * An operator-level halt (kill switch, emergency flatten, safe mode) never resumes:
      sticky means sticky.
    * A run whose deadline has passed never resumes: the session it was is over, and a
      new one is a person's decision.
    * A run with a live deadline resumes *under the same deadline*, not a fresh one — a
      restart buys no extra hours.
    * A run without a deadline resumes as it always has (the 24/7 session).
    """
    now = ensure_utc(now)
    if lease_is_held(notes, now=now, lease_seconds=lease_seconds):
        age = lease_age_seconds(notes, now=now) or 0.0
        return ResumeDecision(
            False,
            f"another process heartbeated this run {age:.0f}s ago (lease {lease_seconds:.0f}s); "
            "it is still running — not resumed, not stamped",
            decode_session_deadline(notes),
            held_by_other=True,
        )
    if halts:
        return ResumeDecision(False, "an operator-level halt was engaged; restart it deliberately")
    deadline = decode_session_deadline(notes)
    if deadline is not None and now >= deadline:
        return ResumeDecision(
            False, f"the session's deadline {deadline.isoformat()} has passed", deadline
        )
    if deadline is not None:
        return ResumeDecision(True, "resumed under the interrupted session's deadline", deadline)
    return ResumeDecision(True, "resumed; no deadline was set")


__all__ = [
    "HEARTBEAT_KEY",
    "LEASE_SECONDS",
    "NOTES_KEY",
    "ResumeDecision",
    "clear_heartbeat",
    "decode_heartbeat",
    "decode_session_deadline",
    "encode_heartbeat",
    "encode_session_notes",
    "lease_age_seconds",
    "lease_is_held",
    "resume_decision",
]
