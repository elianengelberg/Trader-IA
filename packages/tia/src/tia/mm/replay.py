"""Replay of a recorded segment: the proof that the tape can rebuild the book.

A segment is self-contained when it starts with the book (a REST snapshot the live sync
adopted, or a checkpoint of the local book written when the hour opened) and ends with a
checkpoint. Replaying it means running the very same :class:`LocalOrderBook` over the very
same lines, in the very same order, and checking that:

* the file reads end to end and its checksum matches the manifest;
* every gap the replay finds was registered in the manifest (no silent loss);
* every checkpoint met along the way equals the replayed book, level for level;
* the book ends SYNCED, uncrossed, at the sequence id the manifest recorded.

Nothing here is a backtest and nothing here estimates an edge: this module only
answers "does the recording reproduce the market this process saw?".
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tia.mm.order_book import BookState, DepthSnapshot, DepthUpdate, LocalOrderBook
from tia.mm.recorder import MANIFEST_SUFFIX, TickRecorder


@dataclass
class ReplayResult:
    path: str
    ok: bool = False
    reasons: list[str] = field(default_factory=list)
    checksum: str = "not checked"
    lines: int = 0
    events: dict[str, int] = field(default_factory=dict)
    manifest_replayable: bool | None = None
    manifest_flags: list[str] = field(default_factory=list)
    sealed: bool = False
    manifest_format: int | None = None
    part: int = 0
    snapshots_applied: int = 0
    snapshots_rejected: int = 0
    checkpoints_adopted: int = 0
    checkpoints_compared: int = 0
    checkpoint_mismatches: int = 0
    first_mismatch: dict[str, Any] | None = None
    gaps_in_replay: int = 0
    gaps_in_manifest: int = 0
    unregistered_gaps: int = 0
    sequence_breaks: int = 0
    trade_id_jumps: int = 0
    crossed_books: int = 0
    updates_applied: int = 0
    updates_ignored_old: int = 0
    final_state: str = BookState.EMPTY.value
    final_valid: bool = False
    final_update_id: int = 0
    manifest_last_depth_update_id: int | None = None
    manifest_last_checkpoint_update_id: int | None = None
    final_matches_manifest: bool | None = None
    final_digest: str = ""
    manifest_last_checkpoint_digest: str = ""
    digest_matches_manifest: bool | None = None
    best_bid: tuple[float, float] | None = None
    best_ask: tuple[float, float] | None = None
    spread_bps: float | None = None
    levels_bid: int = 0
    levels_ask: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_manifest(path: Path) -> dict[str, Any]:
    manifest_path = Path(str(path) + MANIFEST_SUFFIX)
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text())
    except (OSError, ValueError):
        return {"corrupt": True, "replayable": False}


def _levels(rows: list[list[float]]) -> tuple[tuple[float, float], ...]:
    return tuple((float(p), float(q)) for p, q in rows)


def replay_segment(path: Path | str, *, allow_flagged: bool = False, symbol: str = "") -> ReplayResult:
    """Rebuild the book from one segment and compare it with what was recorded."""
    path = Path(path)
    result = ReplayResult(path=str(path))
    manifest = _read_manifest(path)
    replayable, why_not = TickRecorder.replayable_from_manifest(manifest)
    result.manifest_replayable = replayable if manifest else None
    result.manifest_flags = list(manifest.get("not_replayable_reasons", []))
    result.sealed = bool(manifest.get("closed_at"))
    result.manifest_format = int(manifest.get("format", 1) or 1) if manifest else None
    result.part = int(manifest.get("part", 0) or 0)
    result.gaps_in_manifest = int(manifest.get("book_gaps", 0) or 0)
    result.manifest_last_depth_update_id = manifest.get("last_depth_update_id")
    result.manifest_last_checkpoint_update_id = manifest.get("last_checkpoint_update_id")
    result.manifest_last_checkpoint_digest = manifest.get("last_checkpoint_digest", "") or ""

    if not manifest:
        result.reasons.append("no manifest: nothing to verify the file against")
    elif manifest.get("corrupt"):
        result.reasons.append("manifest says corrupt")
    elif not result.sealed:
        result.reasons.append("segment not sealed: the recorder never closed it, no checksum to verify")
    elif not replayable and not allow_flagged:
        result.reasons.append(f"segment not replayable: {why_not}")

    verified = TickRecorder.verify(path)
    if not verified["ok"]:
        result.checksum = verified["reason"] or "failed"
        result.reasons.append(f"integrity check failed: {result.checksum}")
        if "unreadable" in result.checksum or "missing" in result.checksum:
            return result
    else:
        result.checksum = "ok" if manifest.get("sha256") else "not recorded (segment still open)"

    book = LocalOrderBook(symbol=symbol or str(manifest.get("symbol", "")))
    book.begin_sync()
    events: dict[str, int] = {}
    prev_trade_id: int | None = None
    applied_since_snapshot = 0

    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line_no, raw in enumerate(fh, start=1):
                raw = raw.strip()
                if not raw:
                    continue
                result.lines += 1
                row = json.loads(raw)
                kind = row.get("k", "?")
                events[kind] = events.get(kind, 0) + 1

                if kind == "checkpoint":
                    state = DepthSnapshot(int(row["id"]), _levels(row["b"]), _levels(row["a"]))
                    if book.is_valid:
                        result.checkpoints_compared += 1
                        same_id = book.update_id == state.last_update_id
                        replayed_bids, replayed_asks = book.levels()
                        same_levels = (
                            tuple(replayed_bids) == state.bids and tuple(replayed_asks) == state.asks
                        )
                        same_digest = not row.get("sha") or book.digest() == row["sha"]
                        if not (same_id and same_levels and same_digest):
                            result.checkpoint_mismatches += 1
                            if result.first_mismatch is None:
                                result.first_mismatch = {
                                    "line": line_no,
                                    "checkpoint_update_id": state.last_update_id,
                                    "replayed_update_id": book.update_id,
                                    "checkpoint_levels": len(state.bids) + len(state.asks),
                                    "replayed_levels": len(replayed_bids) + len(replayed_asks),
                                    "same_id": same_id,
                                    "same_levels": same_levels,
                                    "same_digest": same_digest,
                                }
                    else:
                        book.begin_sync()
                        if book.apply_snapshot(state, received_at_ms=int(row.get("R", 0))):
                            result.checkpoints_adopted += 1
                            applied_since_snapshot = 0
                elif kind == "snapshot":
                    state = DepthSnapshot(int(row["id"]), _levels(row["b"]), _levels(row["a"]))
                    if book.state is not BookState.SYNCING:
                        # Live re-synced here (a disconnect, say) without a visible gap in
                        # the ids: the venue's snapshot is authoritative, adopt it too.
                        book.begin_sync()
                    if book.apply_snapshot(state, received_at_ms=int(row.get("R", 0))):
                        result.snapshots_applied += 1
                        applied_since_snapshot = 0
                    else:
                        result.snapshots_rejected += 1
                elif kind == "depth":
                    update = DepthUpdate(
                        first_update_id=int(row["U"]),
                        final_update_id=int(row["u"]),
                        bids=_levels(row.get("b", [])),
                        asks=_levels(row.get("a", [])),
                        event_time_ms=int(row.get("E", 0)),
                        received_at_ms=int(row.get("R", 0)),
                    )
                    was_synced = book.state is BookState.SYNCED
                    prev_id = book.update_id
                    ok = book.apply_update(update)
                    continuous = update.first_update_id == prev_id + 1
                    if was_synced and applied_since_snapshot > 0 and update.final_update_id >= prev_id and not continuous:
                        result.sequence_breaks += 1
                    if ok and was_synced:
                        applied_since_snapshot += 1
                    if not ok and book.state is BookState.OUT_OF_SYNC:
                        if "gap" in book.last_invalid_reason:
                            result.gaps_in_replay += 1
                        book.begin_sync()
                        book.buffer_update(update)
                elif kind == "trade":
                    trade_id = int(row["t"])
                    if prev_trade_id is not None and trade_id != prev_trade_id + 1:
                        result.trade_id_jumps += 1
                    prev_trade_id = trade_id
    except (OSError, EOFError, gzip.BadGzipFile, ValueError, KeyError) as exc:
        result.reasons.append(f"unreadable at line {result.lines + 1}: {type(exc).__name__}: {exc}")
        return result

    result.events = events
    result.crossed_books = book.metrics.crossed_books
    result.updates_applied = book.metrics.updates_applied
    result.updates_ignored_old = book.metrics.updates_ignored_old
    result.unregistered_gaps = max(0, result.gaps_in_replay - result.gaps_in_manifest)
    result.final_state = book.state.value
    result.final_valid = book.is_valid
    result.final_update_id = book.update_id
    result.final_digest = book.digest() if book.is_valid else ""
    result.best_bid = book.best_bid()
    result.best_ask = book.best_ask()
    result.spread_bps = round(book.spread_bps, 4) if book.spread_bps is not None else None
    bids, asks = book.levels()
    result.levels_bid, result.levels_ask = len(bids), len(asks)

    expected_id = result.manifest_last_checkpoint_update_id or result.manifest_last_depth_update_id
    if expected_id is not None:
        result.final_matches_manifest = book.update_id == expected_id
    if result.manifest_last_checkpoint_digest:
        result.digest_matches_manifest = result.final_digest == result.manifest_last_checkpoint_digest

    if manifest.get("lines") not in (None, result.lines):
        result.reasons.append(f"read {result.lines} lines, manifest says {manifest.get('lines')}")
    if result.unregistered_gaps:
        result.reasons.append(f"{result.unregistered_gaps} gap(s) not registered in the manifest")
    if result.checkpoint_mismatches:
        result.reasons.append(f"{result.checkpoint_mismatches} checkpoint(s) differ from the replayed book")
    if result.crossed_books:
        result.reasons.append(f"{result.crossed_books} crossed book(s) during replay")
    if not result.final_valid:
        result.reasons.append(f"book ended {result.final_state}, not valid")
    if result.final_matches_manifest is False:
        result.reasons.append(f"final id {book.update_id} != manifest {expected_id}")
    if result.digest_matches_manifest is False:
        result.reasons.append("final book digest differs from the last recorded checkpoint")
    if not events.get("snapshot") and not events.get("checkpoint"):
        result.reasons.append("segment holds no snapshot or checkpoint: nothing to rebuild from")
    result.ok = not result.reasons
    return result


def replay_directory(root: Path | str, symbol: str, *, allow_flagged: bool = False) -> list[ReplayResult]:
    """Replay every segment of one symbol, oldest first."""
    folder = Path(root) / symbol.replace("/", "-")
    return [
        replay_segment(path, allow_flagged=allow_flagged, symbol=symbol)
        for path in sorted(folder.glob("*.jsonl.gz"))
    ]


__all__ = ["ReplayResult", "replay_directory", "replay_segment"]
