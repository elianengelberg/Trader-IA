"""R24-H1 — the market maker's incidents keep their kind whole.

The maker cut every kind to ``kind[:32]`` to fit the old column: a trigger whose name grew
would have been stored under a different, silently shortened kind. The column and the
repository's check now share one limit (``INCIDENT_KIND_MAX_LENGTH``); the maker passes the kind
as it is and the repository, the one place that writes the row, decides.
"""

from __future__ import annotations

from typing import Any

from tests.unit.mm.test_mm_live_service import _live


async def test_a_long_kind_reaches_the_writer_unshortened() -> None:
    live = await _live()
    seen: list[tuple[str, dict[str, Any]]] = []
    live.service._enqueue = lambda kind, payload: seen.append((kind, payload))  # type: ignore[method-assign]
    try:
        kind = "mm_" + "a_trigger_with_a_long_descriptive_name"  # 41 characters
        live.service._incident(kind, reason="r", actor="system", detail={})
        assert [(k, p["kind"]) for k, p in seen] == [("incident", kind)]
    finally:
        await live.market.close()
