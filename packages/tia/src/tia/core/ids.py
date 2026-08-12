"""Identifier generation.

Two families of identifier, with deliberately different properties:

* **Sortable event ids** — ULID-shaped (48-bit millisecond timestamp + randomness),
  lexicographically ordered by creation time. Good index locality, human-debuggable.
* **Deterministic ids** — a BLAKE2s digest of the semantic inputs. The same logical
  thing always produces the same id, on any machine, in any process. This is what makes
  ``client_order_id`` a real idempotency anchor rather than a hopeful one.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from typing import Any

from tia.core.clock import Clock, millis_from_utc

# Crockford base32 — no I, L, O, U, so ids survive being read aloud or transcribed.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_MASK = len(_ALPHABET) - 1


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_ALPHABET[value & _MASK])
        value >>= 5
    return "".join(reversed(chars))


def new_ulid(clock: Clock, *, randomness: bytes | None = None) -> str:
    """Return a 26-character ULID-shaped identifier ordered by ``clock``."""
    ts = millis_from_utc(clock.now())
    rand = randomness if randomness is not None else os.urandom(10)
    if len(rand) != 10:
        raise ValueError("randomness must be exactly 10 bytes")
    return _encode(ts, 10) + _encode(int.from_bytes(rand, "big"), 16)


def ulid_from_parts(moment: datetime, counter: int) -> str:
    """A fully deterministic ULID-shaped id.

    Used by the backtest engine and by tests, where two runs with the same inputs must
    produce byte-identical output including identifiers.
    """
    ts = millis_from_utc(moment)
    return _encode(ts, 10) + _encode(counter & ((1 << 80) - 1), 16)


def _stable_repr(value: Any) -> str:
    """Canonical string form used for hashing.

    Dicts are key-sorted so that ``{"a": 1, "b": 2}`` and ``{"b": 2, "a": 1}`` hash
    identically — otherwise idempotency would depend on dict insertion order.
    """
    if isinstance(value, dict):
        return "{" + ",".join(f"{k}:{_stable_repr(value[k])}" for k in sorted(value)) + "}"
    if isinstance(value, list | tuple):
        return "[" + ",".join(_stable_repr(v) for v in value) + "]"
    if isinstance(value, datetime):
        return value.astimezone(tz=value.tzinfo).isoformat()
    if isinstance(value, float):
        # Fixed precision: 1.0 and 1.0000000001 must not silently produce distinct ids
        # for what the domain considers the same quantity.
        return f"{value:.12g}"
    if value is None:
        return "\x00none"
    return str(value)


def deterministic_id(prefix: str, *parts: Any, length: int = 24) -> str:
    """Return ``prefix_<digest>`` derived only from ``parts``.

    Same inputs anywhere, same id. Used for ``client_order_id``, idempotency keys, and
    content-addressed snapshot/feature hashes.
    """
    if length < 8 or length > 40:
        raise ValueError("length must be between 8 and 40")
    payload = "|".join(_stable_repr(p) for p in parts).encode("utf-8")
    digest = hashlib.blake2s(payload, digest_size=20).digest()
    encoded = _encode(int.from_bytes(digest, "big"), 32)
    return f"{prefix}_{encoded[:length]}"


def content_hash(payload: Any) -> str:
    """Stable 32-hex-character content hash, for snapshots and feature sets."""
    return hashlib.blake2s(_stable_repr(payload).encode("utf-8"), digest_size=16).hexdigest()


__all__ = ["content_hash", "deterministic_id", "new_ulid", "ulid_from_parts"]
