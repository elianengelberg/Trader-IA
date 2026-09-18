"""The latency profile: what was measured, on which commit, for how long — and nothing else.

A market-making simulation lives or dies by the delay between deciding and arriving.
This module refuses to assume that delay. A :class:`LatencyProfile` is **written from a
real run** (``scripts/mm_market_data_check.py --write-latency-profile``) with the
measurement's timestamp, the commit, the duration and the sample counts; it is loaded
back for replay and paper quoting, and a replay records the profile's id so any result
can be traced to the measurement it rests on. A missing, malformed or empty profile is
an error, never a default.

Three components are measurable today: exchange→local for depth, exchange→local for
trades, and local processing. Two are not measurable until the pipeline exists
(decision→simulated order, simulated order→fill evaluation); they are written as
``null`` with the word "not measured", and the scenarios derive order and cancel
latency from the measured network path instead — with a floor, because zero latency is
the one value that is known to be wrong.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROFILE_FORMAT = 1
MEASURED_KEYS = ("exchange_to_local_depth_ms", "exchange_to_local_trade_ms", "local_processing_us")
PIPELINE_KEYS = ("decision_to_simulated_order_ms", "simulated_order_to_fill_evaluation_ms")
#: Below this, a simulated order would beat the physics of the path it travels.
MIN_LATENCY_MS = 5.0
SCENARIOS = ("optimistic", "baseline", "conservative")


class LatencyProfileError(ValueError):
    """The profile is missing, malformed, or holds no measurement."""


@dataclass(frozen=True)
class LatencyStatsSummary:
    count: int
    p50: float
    p95: float
    p99: float
    min: float
    max: float

    @classmethod
    def from_stats(cls, stats: dict[str, Any]) -> LatencyStatsSummary:
        """From ``LatencyStats.as_dict()`` (count, p50_ms, p95_ms, p99_ms, min_ms, max_ms)."""
        count = int(stats.get("count", 0) or 0)
        if count <= 0:
            raise LatencyProfileError("no samples")
        return cls(
            count=count,
            p50=float(stats["p50_ms"]),
            p95=float(stats["p95_ms"]),
            p99=float(stats["p99_ms"]),
            min=float(stats["min_ms"]),
            max=float(stats["max_ms"]),
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> LatencyStatsSummary:
        try:
            summary = cls(
                count=int(raw["count"]),
                p50=float(raw["p50"]),
                p95=float(raw["p95"]),
                p99=float(raw["p99"]),
                min=float(raw["min"]),
                max=float(raw["max"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise LatencyProfileError(f"malformed latency summary: {exc}") from exc
        if summary.count <= 0:
            raise LatencyProfileError("a latency summary with zero samples is not a measurement")
        if not (summary.min <= summary.p50 <= summary.p95 <= summary.p99 <= summary.max):
            raise LatencyProfileError("latency percentiles are not ordered: not a measurement")
        return summary

    def as_dict(self) -> dict[str, Any]:
        return {"count": self.count, "p50": self.p50, "p95": self.p95, "p99": self.p99, "min": self.min, "max": self.max}


@dataclass(frozen=True)
class LatencyScenario:
    """The delays a simulation applies, and where they came from."""

    name: str
    profile_id: str
    order_latency_ms: float
    cancel_latency_ms: float
    data_latency_ms: float
    processing_ms: float
    basis: str

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class LatencyProfile:
    measured_at_utc: str
    commit: str
    duration_s: float
    symbol: str
    measured: dict[str, LatencyStatsSummary]
    pipeline: dict[str, LatencyStatsSummary | None] = field(default_factory=dict)
    source: str = ""
    format: int = PROFILE_FORMAT

    # ------------------------------------------------------------------ identity

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "measured_at_utc": self.measured_at_utc,
            "commit": self.commit,
            "duration_s": self.duration_s,
            "symbol": self.symbol,
            "source": self.source,
            "measured": {k: v.as_dict() for k, v in self.measured.items()},
            "pipeline": {
                k: (v.as_dict() if v is not None else None) for k, v in self.pipeline.items()
            },
            "note": (
                "Measured on the named commit for the stated duration. Pipeline components "
                "are null until the pipeline that produces them exists: not measured, not "
                "invented. Scenarios derive order/cancel latency from the measured "
                "exchange->local depth path."
            ),
        }

    @property
    def profile_id(self) -> str:
        """Content hash: two profiles with the same measurements share an id."""
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------ scenarios

    def scenario(self, name: str) -> LatencyScenario:
        if name not in SCENARIOS:
            raise LatencyProfileError(f"unknown latency scenario {name!r}; one of {SCENARIOS}")
        depth = self.measured["exchange_to_local_depth_ms"]
        processing_ms = self.measured["local_processing_us"].p95 / 1000.0
        if name == "optimistic":
            raw, basis = depth.p50, "exchange->local depth p50"
        elif name == "baseline":
            raw, basis = depth.p95, "exchange->local depth p95"
        else:
            raw, basis = depth.p99 * 2.0, "2 x exchange->local depth p99"
        order = max(MIN_LATENCY_MS, raw)
        return LatencyScenario(
            name=name,
            profile_id=self.profile_id,
            order_latency_ms=order,
            cancel_latency_ms=order,
            data_latency_ms=max(MIN_LATENCY_MS, depth.p50 if name == "optimistic" else depth.p95),
            processing_ms=processing_ms,
            basis=f"{basis}, floor {MIN_LATENCY_MS:.0f} ms, from profile {self.profile_id}",
        )

    # ------------------------------------------------------------------ io

    def write(self, path: Path | str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=1))
        return path

    @classmethod
    def load(cls, path: Path | str) -> LatencyProfile:
        path = Path(path)
        if not path.exists():
            raise LatencyProfileError(
                f"latency profile not found at {path}: measure it on the server with "
                "scripts/mm_market_data_check.py --write-latency-profile; no default is assumed"
            )
        try:
            raw = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise LatencyProfileError(f"latency profile unreadable: {exc}") from exc
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> LatencyProfile:
        if not isinstance(raw, dict) or int(raw.get("format", 0) or 0) != PROFILE_FORMAT:
            raise LatencyProfileError("latency profile has no known format")
        measured_raw = raw.get("measured") or {}
        measured: dict[str, LatencyStatsSummary] = {}
        for key in MEASURED_KEYS:
            if key not in measured_raw:
                raise LatencyProfileError(f"latency profile lacks {key}")
            measured[key] = LatencyStatsSummary.from_dict(measured_raw[key])
        pipeline: dict[str, LatencyStatsSummary | None] = {}
        for key in PIPELINE_KEYS:
            value = (raw.get("pipeline") or {}).get(key)
            pipeline[key] = LatencyStatsSummary.from_dict(value) if value else None
        try:
            return cls(
                measured_at_utc=str(raw["measured_at_utc"]),
                commit=str(raw.get("commit") or "unknown"),
                duration_s=float(raw["duration_s"]),
                symbol=str(raw.get("symbol") or ""),
                measured=measured,
                pipeline=pipeline,
                source=str(raw.get("source") or ""),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise LatencyProfileError(f"latency profile malformed: {exc}") from exc


def build_latency_profile(
    *,
    stream: dict[str, Any],
    processing_us: dict[str, Any],
    measured_at_utc: str,
    commit: str,
    duration_s: float,
    symbol: str,
    source: str = "scripts/mm_market_data_check.py",
) -> LatencyProfile:
    """From a live run's stream stats (``MarketDataStream.as_dict()``) and the service's
    processing stats. Raises when any measured component has no samples."""
    try:
        measured = {
            "exchange_to_local_depth_ms": LatencyStatsSummary.from_stats(stream["latency_depth_ms"]),
            "exchange_to_local_trade_ms": LatencyStatsSummary.from_stats(stream["latency_trade_ms"]),
            "local_processing_us": LatencyStatsSummary.from_stats(processing_us),
        }
    except KeyError as exc:
        raise LatencyProfileError(f"stream stats lack {exc}") from exc
    return LatencyProfile(
        measured_at_utc=measured_at_utc,
        commit=commit,
        duration_s=round(float(duration_s), 1),
        symbol=symbol,
        measured=measured,
        pipeline=dict.fromkeys(PIPELINE_KEYS),
        source=source,
    )


__all__ = [
    "MEASURED_KEYS",
    "MIN_LATENCY_MS",
    "PIPELINE_KEYS",
    "PROFILE_FORMAT",
    "SCENARIOS",
    "LatencyProfile",
    "LatencyProfileError",
    "LatencyScenario",
    "LatencyStatsSummary",
    "build_latency_profile",
]
