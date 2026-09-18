"""Replay the market maker over recorded segments: the same engine, the same events,
in the same order, with the measured latency profile — and a hash to prove it.

Reads segments in (hour, part) order, feeds snapshot/checkpoint, depth, trade and
book lines to a :class:`MarketMakerEngine` exactly as the live service would, and
returns the engine's snapshot with the journal hash, the profile id, the scenario and
the configuration id. There is no random component; the seed is recorded for
provenance only. A missing latency profile is an error: nothing is assumed.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tia.mm.engine import MarketMakerConfig, MarketMakerEngine
from tia.mm.latency_model import LatencyProfile
from tia.mm.order_book import DepthSnapshot, DepthUpdate
from tia.mm.recorder import TickRecorder
from tia.mm.safety import GlobalTradingSafetyGate
from tia.mm.streams import TradeEvent


@dataclass
class MarketMakerReplayResult:
    segments: list[str]
    lines: int
    events_by_kind: dict[str, int]
    profile_id: str
    latency_scenario: str
    config_id: str
    seed: int
    journal_hash: str
    snapshot: dict[str, Any]
    journal: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if k != "journal"}


def _levels(rows: list[list[float]]) -> tuple[tuple[float, float], ...]:
    return tuple((float(p), float(q)) for p, q in rows)


def event_from_row(row: dict[str, Any]) -> tuple[str, Any, int] | None:
    """One tape line into (kind, event, received_at_ms); None for lines the engine ignores."""
    kind = row.get("k")
    t = int(row.get("R", 0) or 0)
    if kind in ("snapshot", "checkpoint"):
        return "snapshot", DepthSnapshot(int(row["id"]), _levels(row["b"]), _levels(row["a"])), t
    if kind == "depth":
        return "depth", DepthUpdate(int(row["U"]), int(row["u"]), _levels(row.get("b", [])), _levels(row.get("a", [])), int(row.get("E", 0)), t), t
    if kind == "trade":
        return "trade", TradeEvent(int(row["t"]), float(row["p"]), float(row["q"]), bool(row["m"]), int(row.get("T", 0)), int(row.get("E", 0)), t), t
    if kind == "book":
        return "book", row, t
    return None


def replay_market_maker(
    segments: list[Path | str],
    *,
    config: MarketMakerConfig,
    profile: LatencyProfile,
    scenario: str = "baseline",
    seed: int = 0,
    keep_journal: bool = False,
    journal_sink: Any = None,
) -> MarketMakerReplayResult:
    ordered = sorted((Path(s) for s in segments), key=TickRecorder.segment_sort_key)
    latency = profile.scenario(scenario)
    engine_ref: dict[str, MarketMakerEngine] = {}

    def data_usable() -> tuple[bool, str]:
        engine = engine_ref["engine"]
        return engine.book.is_valid, engine.book.last_invalid_reason or engine.book.state.value

    gate = GlobalTradingSafetyGate(risk_state=lambda: None, data_usable=data_usable)
    kept: list[dict[str, Any]] = []

    def sink(row: dict[str, Any]) -> None:
        if keep_journal:
            kept.append(row)
        if journal_sink is not None:
            journal_sink(row)

    engine = MarketMakerEngine(config, latency=latency, gate=gate, journal_sink=sink)
    engine_ref["engine"] = engine
    lines = 0
    by_kind: dict[str, int] = {}
    for path in ordered:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                lines += 1
                parsed = event_from_row(json.loads(raw))
                if parsed is None:
                    continue
                kind, event, t = parsed
                by_kind[kind] = by_kind.get(kind, 0) + 1
                engine.on_event(kind, event, t)
    return MarketMakerReplayResult(
        segments=[str(p) for p in ordered],
        lines=lines,
        events_by_kind=by_kind,
        profile_id=profile.profile_id,
        latency_scenario=scenario,
        config_id=config.config_id,
        seed=seed,
        journal_hash=engine.journal_hash(),
        snapshot=engine.snapshot(),
        journal=kept,
    )


__all__ = ["MarketMakerReplayResult", "event_from_row", "replay_market_maker"]
