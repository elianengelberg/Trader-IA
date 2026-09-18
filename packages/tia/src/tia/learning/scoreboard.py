"""Per-strategy accountability: each strategy answers for its own closed trades.

The edge estimator buckets outcomes by regime, direction and confidence — and deliberately
not by strategy, because a bucket that also split by strategy would take three times as
long to fill. The cost of that choice is that two strategies firing in the same regime
share one record: a good one can carry a bad one, and the bad one keeps trading on the
good one's evidence.

The scoreboard closes that gap from the other side. Every closed trade is also credited to
the strategy that proposed it, and a strategy whose own record is negative with enough
trades to mean it is **muted**: its signals are refused before risk, before expected
value, before anything. This can only ever refuse a trade — it never authorises one — so
it sits comfortably with every other learned influence in the system.

Exploration trades are recorded but do not count toward muting: they were taken because
the bucket had no evidence, not because the strategy claimed one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

#: Closed trades a strategy needs before its record can mute it. The estimator's floor,
#: for the same reason: below it, a mean is noise.
MIN_TRADES_TO_JUDGE = 30

#: A strategy is muted when its mean net return sits more than this many standard errors
#: below zero. One: the record has to be worse than its own noise, not just red.
MUTE_SE = 1.0


@dataclass
class StrategyRecord:
    strategy_id: str
    trades: int = 0
    wins: int = 0
    exploratory: int = 0
    _net: list[float] = field(default_factory=list)

    @property
    def mean_bps(self) -> float | None:
        return sum(self._net) / len(self._net) if self._net else None

    @property
    def standard_error_bps(self) -> float | None:
        n = len(self._net)
        if n < 2:
            return None
        mean = sum(self._net) / n
        variance = sum((v - mean) ** 2 for v in self._net) / (n - 1)
        return math.sqrt(variance / n)

    @property
    def t_statistic(self) -> float | None:
        mean, se = self.mean_bps, self.standard_error_bps
        if mean is None or se is None or se == 0:
            return None
        return mean / se

    @property
    def judged(self) -> int:
        """Trades that count toward the verdict: everything but exploration."""
        return len(self._net)

    @property
    def muted(self) -> bool:
        mean, se = self.mean_bps, self.standard_error_bps
        if self.judged < MIN_TRADES_TO_JUDGE or mean is None or se is None:
            return False
        return mean + MUTE_SE * se < 0.0

    def as_dict(self) -> dict[str, Any]:
        mean = self.mean_bps
        return {
            "strategy_id": self.strategy_id,
            "trades": self.trades,
            "judged": self.judged,
            "wins": self.wins,
            "win_rate": round(self.wins / self.trades, 4) if self.trades else None,
            "exploratory": self.exploratory,
            "mean_net_bps": round(mean, 3) if mean is not None else None,
            "standard_error_bps": (
                round(self.standard_error_bps, 3) if self.standard_error_bps is not None else None
            ),
            "t_statistic": round(self.t_statistic, 2) if self.t_statistic is not None else None,
            "muted": self.muted,
            "needed_to_judge": max(0, MIN_TRADES_TO_JUDGE - self.judged),
        }


class StrategyScoreboard:
    """Records credit and blame per strategy; answers "may this strategy trade?"."""

    def __init__(self) -> None:
        self._records: dict[str, StrategyRecord] = {}

    def record(self, strategy_id: str, net_bps: float, *, exploratory: bool = False) -> None:
        if not strategy_id:
            return
        record = self._records.setdefault(strategy_id, StrategyRecord(strategy_id=strategy_id))
        record.trades += 1
        if net_bps > 0:
            record.wins += 1
        if exploratory:
            record.exploratory += 1
        else:
            record._net.append(float(net_bps))

    def record_many(self, rows: list[dict[str, Any]]) -> int:
        """Rows with ``strategy_id``, ``net_bps`` and optionally ``exploratory``. Rows
        without a strategy id — evidence written before strategies were credited — are
        skipped; the count returned is what was actually credited."""
        credited = 0
        for row in rows:
            strategy_id = row.get("strategy_id")
            if not strategy_id:
                continue
            self.record(str(strategy_id), float(row["net_bps"]), exploratory=bool(row.get("exploratory")))
            credited += 1
        return credited

    def is_muted(self, strategy_id: str) -> bool:
        record = self._records.get(strategy_id)
        return record.muted if record else False

    def reason(self, strategy_id: str) -> str:
        record = self._records.get(strategy_id)
        if record is None or not record.muted:
            return ""
        return (
            f"strategy {strategy_id} is muted: its own {record.judged} trades average "
            f"{record.mean_bps:+.1f} bps net (t = {record.t_statistic:.1f}); it may propose "
            f"again when its record clears zero"
        )

    def report(self) -> list[dict[str, Any]]:
        rows = [record.as_dict() for record in self._records.values()]
        rows.sort(key=lambda r: (r["mean_net_bps"] is None, -(r["mean_net_bps"] or 0.0)))
        return rows


__all__ = ["MIN_TRADES_TO_JUDGE", "MUTE_SE", "StrategyRecord", "StrategyScoreboard"]
