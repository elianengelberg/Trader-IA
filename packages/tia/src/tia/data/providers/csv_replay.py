"""CSV replay provider — reproducible research on committed datasets.

The synthetic provider proves the plumbing works. This one is how a *result* becomes
citable: point it at a committed CSV, record the file's content hash in the experiment,
and the study can be re-run byte-for-byte by anyone, forever, with no network.

Expected schema (header required, column order irrelevant):

    open_time,open,high,low,close,volume[,trade_count]

``open_time`` accepts an ISO-8601 timestamp or epoch seconds/milliseconds. Rows that
fail validation are collected with their line numbers rather than silently skipped — a
dataset that quietly lost 3% of its rows produces a study nobody can trust.
"""

from __future__ import annotations

import csv
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tia.core.clock import ensure_utc
from tia.core.errors import DataError
from tia.core.logging import get_logger
from tia.data.providers.base import MarketDataProvider, ProviderCapabilities
from tia.domain.instruments import Timeframe
from tia.domain.market import Candle

_log = get_logger("data.csv_replay")

_REQUIRED = {"open_time", "open", "high", "low", "close", "volume"}


def _parse_time(raw: str) -> datetime:
    raw = raw.strip()
    if raw.isdigit():
        value = int(raw)
        # Heuristic on magnitude: 1e12 separates seconds from milliseconds for any date
        # this century, and getting it wrong shifts a dataset by ~50000 years, which is
        # obvious rather than subtle.
        return datetime.fromtimestamp(value / 1000 if value > 1_000_000_000_000 else value, tz=UTC)
    return ensure_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")), field="open_time")


class CsvReplayProvider(MarketDataProvider):
    """Serves candles from ``<fixtures_dir>/<symbol>_<timeframe>.csv``."""

    def __init__(self, fixtures_dir: Path | str, *, strict: bool = True) -> None:
        super().__init__(
            ProviderCapabilities(
                name="csv",
                candles=True,
                historical=True,
                streaming=False,
                requires_credentials=False,
                requires_network=False,
                max_history_bars=1_000_000,
                notes="Replays committed CSV fixtures. Fully reproducible.",
            )
        )
        self._dir = Path(fixtures_dir)
        self._strict = strict
        self._cache: dict[tuple[str, str], list[Candle]] = {}
        self.rejected_rows: list[tuple[int, str]] = []

    def path_for(self, symbol: str, timeframe: str) -> Path:
        return self._dir / f"{symbol}_{timeframe}.csv"

    def dataset_hash(self, symbol: str, timeframe: str) -> str:
        """Content hash of the source file — recorded in every experiment."""
        path = self.path_for(symbol, timeframe)
        if not path.exists():
            raise DataError(f"no fixture at {path}", symbol=symbol, timeframe=timeframe)
        return hashlib.blake2s(path.read_bytes(), digest_size=16).hexdigest()

    def available(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        if not self._dir.exists():
            return out
        for path in sorted(self._dir.glob("*.csv")):
            stem = path.stem
            if "_" in stem:
                symbol, _, timeframe = stem.rpartition("_")
                out.append((symbol, timeframe))
        return out

    def load(self, symbol: str, timeframe: str) -> list[Candle]:
        key = (symbol, timeframe)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        path = self.path_for(symbol, timeframe)
        if not path.exists():
            raise DataError(
                f"no fixture for {symbol} {timeframe} at {path}",
                symbol=symbol,
                timeframe=timeframe,
                path=str(path),
            )

        tf = Timeframe.parse(timeframe)
        candles: list[Candle] = []
        rejected: list[tuple[int, str]] = []

        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            missing = _REQUIRED - set(reader.fieldnames or [])
            if missing:
                raise DataError(
                    f"fixture {path.name} is missing columns: {sorted(missing)}",
                    path=str(path),
                    missing=sorted(missing),
                )
            for line_no, row in enumerate(reader, start=2):
                try:
                    open_time = _parse_time(row["open_time"])
                    candles.append(
                        Candle(
                            symbol=symbol,
                            timeframe=timeframe,
                            open_time=open_time,
                            close_time=open_time + tf.delta,
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=float(row["volume"]),
                            trade_count=int(float(row.get("trade_count") or 0)),
                            provider=self.name,
                        )
                    )
                except Exception as exc:
                    rejected.append((line_no, str(exc)))

        self.rejected_rows = rejected
        if rejected:
            _log.warning(
                "csv_rows_rejected",
                path=str(path),
                rejected=len(rejected),
                accepted=len(candles),
                first_error=rejected[0][1][:200],
            )
            if self._strict:
                raise DataError(
                    f"{len(rejected)} invalid rows in {path.name}; refusing to serve a "
                    f"silently truncated dataset (first: line {rejected[0][0]}: {rejected[0][1]})",
                    path=str(path),
                    rejected=len(rejected),
                )

        candles.sort(key=lambda c: c.open_time)
        self._cache[key] = candles
        return candles

    async def get_candles(
        self, symbol: str, timeframe: str, *, limit: int = 500, end: datetime | None = None
    ) -> list[Candle]:
        series = self.load(symbol, timeframe)
        if end is not None:
            cutoff = ensure_utc(end)
            series = [c for c in series if c.close_time <= cutoff]
        result = series[-limit:] if limit and limit < len(series) else series
        if result:
            self._record_success(result[-1].close_time)
        return list(result)


def write_fixture(path: Path, candles: list[Candle]) -> None:
    """Write candles in the schema :class:`CsvReplayProvider` reads."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["open_time", "open", "high", "low", "close", "volume", "trade_count"])
        for candle in candles:
            writer.writerow(
                [
                    candle.open_time.isoformat().replace("+00:00", "Z"),
                    f"{candle.open:.8f}",
                    f"{candle.high:.8f}",
                    f"{candle.low:.8f}",
                    f"{candle.close:.8f}",
                    f"{candle.volume:.8f}",
                    candle.trade_count,
                ]
            )


def synthesize_gap(candles: list[Candle], *, drop_from: int, drop_count: int) -> list[Candle]:
    """Remove a contiguous run of bars — used by tests to prove gap detection fires."""
    return candles[:drop_from] + candles[drop_from + drop_count :]


def shift_timestamps(candles: list[Candle], delta: timedelta) -> list[Candle]:
    """Shift a whole series — used by staleness tests."""
    return [
        c.model_copy(update={"open_time": c.open_time + delta, "close_time": c.close_time + delta})
        for c in candles
    ]


__all__ = ["CsvReplayProvider", "shift_timestamps", "synthesize_gap", "write_fixture"]
