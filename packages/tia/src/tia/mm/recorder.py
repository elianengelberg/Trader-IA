"""The tape, on disk: every tick the stream delivered, with both clocks, for replay.

Binance publishes historical trades but not historical depth, so a replay of the book
is only possible from a recording made while it happened. This recorder writes one
gzip-compressed JSONL file per hour per symbol, in arrival order, with the exchange
timestamp, the local receive timestamp and the venue's sequence ids on every line —
everything a replay needs to rebuild the book exactly as this process saw it.

What it promises, and what it does not:

* **Batches, not ticks, to disk.** Lines are buffered in memory and flushed every
  ``flush_interval_s`` or ``flush_lines``, whichever first. A crash loses at most one
  buffer; the manifest says so by the line count.
* **Honest segments.** Each hour's manifest carries counts, first/last ids, a SHA-256
  of the compressed bytes, and ``replayable``: False whenever the stream disconnected,
  the book reported a gap, or the recorder itself dropped events (buffer full) inside
  that hour. A segment marked not replayable is never used for a backtest.
* **A ceiling on disk.** Retention by days and by total bytes; the oldest hour goes
  first. The recorder can never eat the disk.
* **Corruption is detected, not assumed away.** ``verify()`` recomputes the checksum
  and reads the file end to end; a mismatch marks the segment corrupt.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tia.core.clock import SystemClock
from tia.core.logging import get_logger

_log = get_logger("mm.recorder")

MANIFEST_SUFFIX = ".manifest.json"

#: Kinds that carry a whole book: the REST snapshot the sync adopted, and a checkpoint
#: of the local book. Both make a segment self-contained for replay.
BOOK_STATE_KINDS = ("snapshot", "checkpoint")


@dataclass(frozen=True)
class BookStateEvent:
    """A whole book at one sequence id: what a replay starts from or is checked against."""

    update_id: int
    bids: tuple[tuple[float, float], ...]
    asks: tuple[tuple[float, float], ...]
    received_at_ms: int
    digest: str = ""


@dataclass
class SegmentManifest:
    """What one hour's file contains and whether it can be trusted for replay."""

    symbol: str
    hour: str  # YYYYMMDD-HH (UTC)
    path: str
    lines: int = 0
    bytes: int = 0
    sha256: str = ""
    first_received_at_ms: int | None = None
    last_received_at_ms: int | None = None
    first_depth_update_id: int | None = None
    last_depth_update_id: int | None = None
    first_trade_id: int | None = None
    last_trade_id: int | None = None
    raw_bytes: int = 0  # before compression
    depth_events: int = 0
    trade_events: int = 0
    book_events: int = 0
    snapshot_events: int = 0
    checkpoint_events: int = 0
    last_checkpoint_update_id: int | None = None
    last_checkpoint_digest: str = ""
    dropped_events: int = 0
    disconnects: int = 0
    book_gaps: int = 0
    faults_injected: list[str] = field(default_factory=list)
    replayable: bool = True
    not_replayable_reasons: list[str] = field(default_factory=list)
    corrupt: bool = False
    closed_at: str | None = None

    def flag(self, reason: str) -> None:
        if self.replayable:
            self.replayable = False
        if reason not in self.not_replayable_reasons:
            self.not_replayable_reasons.append(reason)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class TickRecorder:
    """Append-only, batched, bounded recorder of tick events."""

    def __init__(
        self,
        root: Path | str,
        symbol: str,
        *,
        flush_interval_s: float = 1.0,
        flush_lines: int = 500,
        max_buffer_lines: int = 50_000,
        retention_days: int = 14,
        max_total_bytes: int = 2 * 1024**3,
        now_ms: Callable[[], int] | None = None,
        checkpoint_source: Callable[[], BookStateEvent | None] | None = None,
    ) -> None:
        self.root = Path(root)
        self.symbol = symbol
        self._dir = self.root / symbol.replace("/", "-")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._flush_interval_s = flush_interval_s
        self._flush_lines = flush_lines
        self._max_buffer_lines = max_buffer_lines
        self._retention_days = retention_days
        self._max_total_bytes = max_total_bytes
        self._now_ms = now_ms or SystemClock().timestamp_ms
        #: Asked for the current book whenever a new hour opens, so every segment starts
        #: with the state a replay needs (None while the book is not valid).
        self._checkpoint_source = checkpoint_source

        self._buffer: list[bytes] = []
        self._buffer_hour = ""
        self._last_flush_ms = self._now_ms()
        self._manifest: SegmentManifest | None = None
        self._writer: gzip.GzipFile | None = None
        self._hasher: Any = None
        self.events_written = 0
        self.events_dropped = 0
        self.bytes_written = 0
        self.flushes = 0
        self.segments_closed = 0
        self.segments_evicted = 0
        self.last_error = ""

    # ------------------------------------------------------------------ recording

    def record(self, kind: str, event: Any) -> None:
        """Queue one event. Never blocks; a full buffer drops and counts."""
        received_at_ms = getattr(event, "received_at_ms", None) or self._now_ms()
        hour = datetime.fromtimestamp(received_at_ms / 1000.0, tz=UTC).strftime("%Y%m%d-%H")
        if hour != self._buffer_hour:
            self.flush(force=True)
            self._roll_segment(hour)
        if len(self._buffer) >= self._max_buffer_lines:
            self.events_dropped += 1
            if self._manifest is not None:
                self._manifest.dropped_events += 1
                self._manifest.flag("recorder buffer full: events dropped")
            return
        line = self._encode(kind, event, received_at_ms)
        self._buffer.append(line)
        self._note(kind, event, received_at_ms)
        due = self._now_ms() - self._last_flush_ms >= self._flush_interval_s * 1000.0
        if len(self._buffer) >= self._flush_lines or due:
            self.flush()

    def _current_manifest(self) -> SegmentManifest | None:
        """The manifest for this hour, opening the segment if no tick has arrived yet.

        An integrity event (disconnect, gap) before the first tick of the hour must
        still be written down: a manifest that never heard of it would call the hour
        replayable.
        """
        hour = datetime.fromtimestamp(self._now_ms() / 1000.0, tz=UTC).strftime("%Y%m%d-%H")
        if hour != self._buffer_hour:
            self.flush(force=True)
            self._roll_segment(hour)
        return self._manifest

    def note_disconnect(self) -> None:
        manifest = self._current_manifest()
        if manifest is not None:
            manifest.disconnects += 1
            manifest.flag("stream disconnected during the hour")

    def note_book_gap(self) -> None:
        manifest = self._current_manifest()
        if manifest is not None:
            manifest.book_gaps += 1
            manifest.flag("order book reported a sequence gap")

    def note_fault(self, reason: str) -> None:
        """A fault injected on purpose (a validation run): written down as such."""
        manifest = self._current_manifest()
        if manifest is not None:
            manifest.faults_injected.append(reason)
            manifest.flag(f"fault injected: {reason}")

    def _encode(self, kind: str, event: Any, received_at_ms: int) -> bytes:
        payload: dict[str, Any] = {"k": kind, "R": received_at_ms}
        if kind in BOOK_STATE_KINDS:
            payload.update(
                {"id": event.update_id, "b": [[p, q] for p, q in event.bids],
                 "a": [[p, q] for p, q in event.asks], "sha": event.digest}
            )
        elif kind == "depth":
            payload.update(
                {"E": event.event_time_ms, "U": event.first_update_id, "u": event.final_update_id,
                 "b": [[p, q] for p, q in event.bids], "a": [[p, q] for p, q in event.asks]}
            )
        elif kind == "trade":
            payload.update(
                {"E": event.event_time_ms, "T": event.trade_time_ms, "t": event.trade_id,
                 "p": event.price, "q": event.quantity, "m": event.buyer_is_maker}
            )
        elif kind == "book":
            payload.update(
                {"u": event.update_id, "b": event.bid, "B": event.bid_size, "a": event.ask, "A": event.ask_size}
            )
        else:
            payload["d"] = event if isinstance(event, dict) else str(event)
        return (json.dumps(payload, separators=(",", ":")) + "\n").encode()

    def _note(self, kind: str, event: Any, received_at_ms: int) -> None:
        m = self._manifest
        if m is None:
            return
        if m.first_received_at_ms is None:
            m.first_received_at_ms = received_at_ms
        m.last_received_at_ms = received_at_ms
        if kind == "depth":
            m.depth_events += 1
            if m.first_depth_update_id is None:
                m.first_depth_update_id = event.first_update_id
            m.last_depth_update_id = event.final_update_id
        elif kind == "trade":
            m.trade_events += 1
            if m.first_trade_id is None:
                m.first_trade_id = event.trade_id
            m.last_trade_id = event.trade_id
        elif kind == "book":
            m.book_events += 1
        elif kind == "snapshot":
            m.snapshot_events += 1
        elif kind == "checkpoint":
            m.checkpoint_events += 1
            m.last_checkpoint_update_id = event.update_id
            m.last_checkpoint_digest = event.digest

    # ------------------------------------------------------------------ segments

    def _roll_segment(self, hour: str) -> None:
        self.close_segment()
        path = self._dir / f"{hour}.jsonl.gz"
        self._manifest = SegmentManifest(symbol=self.symbol, hour=hour, path=str(path))
        self._writer = gzip.open(path, "ab")  # noqa: SIM115 - long-lived, closed in close_segment
        self._hasher = hashlib.sha256()
        self._buffer_hour = hour
        self._enforce_limits()
        if self._checkpoint_source is not None:
            state = self._checkpoint_source()
            if state is not None:
                # The first line of the hour: where a replay of this file starts.
                line = self._encode("checkpoint", state, state.received_at_ms)
                self._buffer.append(line)
                self._note("checkpoint", state, state.received_at_ms)

    def flush(self, *, force: bool = False) -> None:
        if not self._buffer or self._writer is None:
            self._last_flush_ms = self._now_ms()
            return
        try:
            chunk = b"".join(self._buffer)
            self._writer.write(chunk)
            self._writer.flush()
            self._hasher.update(chunk)
            self.events_written += len(self._buffer)
            self.bytes_written += len(chunk)
            if self._manifest is not None:
                self._manifest.lines += len(self._buffer)
                self._manifest.raw_bytes += len(chunk)
                self._manifest.bytes = Path(self._manifest.path).stat().st_size
            self.flushes += 1
        except OSError as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.events_dropped += len(self._buffer)
            if self._manifest is not None:
                self._manifest.flag(f"write failed: {self.last_error}")
            _log.error("tick_recorder_write_failed", error=self.last_error)
        finally:
            self._buffer.clear()
            self._last_flush_ms = self._now_ms()
        if force or self._manifest is not None:
            self._write_manifest()

    def close_segment(self) -> None:
        self.flush(force=True)
        if self._writer is not None:
            self._writer.close()
            self._writer = None
        if self._manifest is not None:
            current = Path(self._manifest.path)
            self._manifest.bytes = current.stat().st_size if current.exists() else 0
            self._manifest.sha256 = self._file_sha256(Path(self._manifest.path))
            self._manifest.closed_at = datetime.fromtimestamp(self._now_ms() / 1000.0, tz=UTC).isoformat()
            self._write_manifest()
            self.segments_closed += 1
            self._manifest = None
        self._buffer_hour = ""

    def close(self) -> None:
        self.close_segment()

    def _write_manifest(self) -> None:
        if self._manifest is None:
            return
        path = Path(self._manifest.path + MANIFEST_SUFFIX)
        try:
            path.write_text(json.dumps(self._manifest.as_dict(), indent=1))
        except OSError as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"

    @staticmethod
    def _file_sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()

    # ------------------------------------------------------------------ limits

    def _enforce_limits(self) -> None:
        segments = self.segments()
        cutoff = self._now_ms() / 1000.0 - self._retention_days * 86_400.0
        total = sum(s["bytes"] for s in segments)
        for seg in segments:  # oldest first
            if seg["path"] == (self._manifest.path if self._manifest else None):
                continue
            too_old = seg["mtime"] < cutoff
            too_big = total > self._max_total_bytes
            if not (too_old or too_big):
                continue
            for p in (Path(seg["path"]), Path(seg["path"] + MANIFEST_SUFFIX)):
                if p.exists():
                    p.unlink()
            total -= seg["bytes"]
            self.segments_evicted += 1

    # ------------------------------------------------------------------ reading

    def segments(self) -> list[dict[str, Any]]:
        """Every recorded hour, oldest first, with its manifest when one exists."""
        out = []
        for path in sorted(self._dir.glob("*.jsonl.gz")):
            manifest_path = Path(str(path) + MANIFEST_SUFFIX)
            manifest: dict[str, Any] = {}
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text())
                except (OSError, ValueError):
                    manifest = {"corrupt": True, "replayable": False}
            out.append(
                {
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "mtime": path.stat().st_mtime,
                    "manifest": manifest,
                    "replayable": bool(manifest.get("replayable", False)) and not manifest.get("corrupt", False),
                }
            )
        return out

    @classmethod
    def verify(cls, path: Path | str) -> dict[str, Any]:
        """Recompute the checksum and read the file end to end. Marks corruption."""
        path = Path(path)
        manifest_path = Path(str(path) + MANIFEST_SUFFIX)
        result: dict[str, Any] = {"path": str(path), "ok": False, "lines": 0, "reason": ""}
        if not path.exists():
            result["reason"] = "missing file"
            return result
        try:
            with gzip.open(path, "rb") as fh:
                for _ in fh:
                    result["lines"] += 1
        except (OSError, EOFError, gzip.BadGzipFile) as exc:
            result["reason"] = f"unreadable: {type(exc).__name__}: {exc}"
            cls._mark_corrupt(manifest_path)
            return result
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
            except (OSError, ValueError):
                result["reason"] = "manifest unreadable"
                return result
            expected = manifest.get("sha256")
            if expected:
                actual = cls._file_sha256(path)
                if actual != expected:
                    result["reason"] = "checksum mismatch"
                    cls._mark_corrupt(manifest_path)
                    return result
            if manifest.get("lines") not in (None, result["lines"]):
                result["reason"] = f"line count {result['lines']} != manifest {manifest.get('lines')}"
                cls._mark_corrupt(manifest_path)
                return result
        result["ok"] = True
        return result

    @staticmethod
    def _mark_corrupt(manifest_path: Path) -> None:
        if not manifest_path.exists():
            return
        try:
            manifest = json.loads(manifest_path.read_text())
            manifest["corrupt"] = True
            manifest["replayable"] = False
            manifest_path.write_text(json.dumps(manifest, indent=1))
        except (OSError, ValueError):
            pass

    def status(self) -> dict[str, Any]:
        segments = self.segments()
        return {
            "root": str(self._dir),
            "current_hour": self._buffer_hour or None,
            "buffered_lines": len(self._buffer),
            "events_written": self.events_written,
            "events_dropped": self.events_dropped,
            "bytes_written": self.bytes_written,
            "flushes": self.flushes,
            "segments": len(segments),
            "segments_replayable": sum(1 for s in segments if s["replayable"]),
            "segments_closed": self.segments_closed,
            "segments_evicted": self.segments_evicted,
            "total_bytes_on_disk": sum(s["bytes"] for s in segments),
            "max_total_bytes": self._max_total_bytes,
            "retention_days": self._retention_days,
            "current_manifest": self._manifest.as_dict() if self._manifest else None,
            "last_error": self.last_error,
        }


__all__ = ["BOOK_STATE_KINDS", "MANIFEST_SUFFIX", "BookStateEvent", "SegmentManifest", "TickRecorder"]
