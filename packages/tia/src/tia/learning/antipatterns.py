"""The anti-pattern monitor — curated trading wisdom, turned on the system itself.

The user asked for "reliable, useful information for this kind of trading — no filler, no
garbage." The honest form of that is not a feed of scraped blog posts. It is a small set of
**well-established, hard-won trading principles** — the ones that actually decide whether a
retail account survives — encoded as checks the system runs against *its own recent
behaviour*.

Each check pairs a measurable condition with the principle behind it. Not "the internet
says buy the dip", but "costs, not direction, decide most outcomes; if fees are eating more
than ~40% of your gross edge, you are renting the exchange, not trading it — and here is the
number for the last N trades." Reliable because it is arithmetic over the system's own
record; useful because every one of these is a documented way real accounts are emptied.

Several of these behaviours the platform already forbids structurally — it cannot
martingale, the EV gate refuses negative-edge trades, the risk engine caps exposure. So the
monitor's job is mostly **verification**: confirming those protections are holding, and
raising a flag the moment behaviour drifts toward the edge of one. It is pure and
deterministic — a snapshot in, a verdict out — so it reads the same on every machine and a
test can pin every branch.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    """Worst-first ordering matters: the report sorts and summarises by this."""

    OK = "ok"
    WATCH = "watch"
    ALERT = "alert"


_RANK = {Severity.OK: 0, Severity.WATCH: 1, Severity.ALERT: 2}


@dataclass(frozen=True)
class AntiPatternCheck:
    """One principle, measured against the system's own recent behaviour."""

    key: str
    title: str
    severity: Severity
    #: What the numbers currently say — the measured condition, in plain language.
    detail: str
    #: The durable principle behind the check: *why* this is worth watching at all.
    principle: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "severity": self.severity.value,
            "detail": self.detail,
            "principle": self.principle,
        }


@dataclass
class AntiPatternMonitor:
    """Audits recent trading behaviour against a fixed set of trading principles."""

    #: A round trip whose fees exceed this share of its gross move is mostly cost.
    cost_share_watch: float = 0.25
    cost_share_alert: float = 0.40
    #: Losing streak lengths at which the temptation to "win it back" is worth naming.
    streak_watch: int = 3
    streak_alert: int = 5
    #: A single symbol holding more than this share of equity as notional is concentrated.
    concentration_watch: float = 0.6
    #: How full the daily trade budget must get before turnover is flagged.
    turnover_watch: float = 0.8
    #: Fewest recent trades before an average-based check will speak at all.
    min_trades: int = 8

    def evaluate(self, snapshot: dict[str, Any]) -> list[AntiPatternCheck]:
        """Return every check, most severe first."""
        trades = list(snapshot.get("recent_trades", []))
        checks = [
            self._cost_drag(trades),
            self._negative_edge(trades),
            self._loss_streak(snapshot),
            self._overtrading(snapshot),
            self._concentration(snapshot),
            self._win_rate(trades),
        ]
        return sorted(checks, key=lambda c: _RANK[c.severity], reverse=True)

    def report(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        checks = self.evaluate(snapshot)
        worst = checks[0].severity if checks else Severity.OK
        return {
            "worst_severity": worst.value,
            "alerts": sum(1 for c in checks if c.severity is Severity.ALERT),
            "watches": sum(1 for c in checks if c.severity is Severity.WATCH),
            "checks": [c.as_dict() for c in checks],
            "explanation": (
                "These are not opinions scraped from the internet. Each is a documented way "
                "trading accounts are emptied, measured against this system's own recent "
                "trades. The platform already forbids several of them by construction; the "
                "monitor's job is to confirm those guards are holding and flag any drift."
            ),
        }

    # ------------------------------------------------------------------ checks

    def _cost_drag(self, trades: list[dict[str, Any]]) -> AntiPatternCheck:
        principle = (
            "Costs, not direction, decide most retail outcomes. If fees consume more than "
            "~40% of your gross edge, you are renting the exchange rather than trading it — "
            "and the way out is fewer, larger, higher-conviction trades, not more of them."
        )
        gross = [abs(float(t.get("gross_bps", 0.0))) for t in trades]
        fees = [abs(float(t.get("fees_bps", 0.0))) for t in trades]
        if len(trades) < self.min_trades or sum(gross) <= 0:
            return AntiPatternCheck(
                "cost_drag", "Cost drag", Severity.OK,
                f"Only {len(trades)} recent round trips — too few to judge cost efficiency.",
                principle,
            )
        share = sum(fees) / sum(gross)
        if share >= self.cost_share_alert:
            sev, verb = Severity.ALERT, "is eating"
        elif share >= self.cost_share_watch:
            sev, verb = Severity.WATCH, "is starting to eat"
        else:
            sev, verb = Severity.OK, "is a healthy fraction of"
        return AntiPatternCheck(
            "cost_drag", "Cost drag", sev,
            f"Over the last {len(trades)} round trips, fees averaged {share:.0%} of the "
            f"gross move — cost {verb} the edge.",
            principle,
        )

    def _negative_edge(self, trades: list[dict[str, Any]]) -> AntiPatternCheck:
        principle = (
            "A negative average net return across many trades is the market's verdict that "
            "the edge is not there after costs. The disciplined response is to stop and "
            "gather evidence, not to trade more hoping the average turns."
        )
        nets = [float(t.get("net_bps", 0.0)) for t in trades]
        if len(nets) < self.min_trades:
            return AntiPatternCheck(
                "negative_edge", "Trading at a loss after costs", Severity.OK,
                f"Only {len(nets)} recent round trips — too few to call the average.",
                principle,
            )
        mean = sum(nets) / len(nets)
        if mean <= -5.0:
            sev = Severity.ALERT
        elif mean < 0.0:
            sev = Severity.WATCH
        else:
            sev = Severity.OK
        return AntiPatternCheck(
            "negative_edge", "Trading at a loss after costs", sev,
            f"The last {len(nets)} round trips averaged {mean:+.1f} bps net of fees.",
            principle,
        )

    def _loss_streak(self, snapshot: dict[str, Any]) -> AntiPatternCheck:
        principle = (
            "After a run of losses the pull is to size up and 'win it back' — the single "
            "fastest way to ruin. This system forbids martingale by construction: a losing "
            "streak can only shrink the next position, never grow it."
        )
        streak = int(snapshot.get("consecutive_losses", 0))
        allowed = bool(snapshot.get("new_trades_allowed", True))
        if streak >= self.streak_alert:
            sev = Severity.ALERT
            note = (
                "the budget should be defensive and sizing reduced — confirm that on the "
                "Risk page" if allowed else "and new entries are already halted"
            )
        elif streak >= self.streak_watch:
            sev = Severity.WATCH
            note = "the risk budget is tightening automatically as designed"
        else:
            sev = Severity.OK
            note = "no streak worth naming"
        return AntiPatternCheck(
            "loss_streak", "Losing streak / revenge-trading risk", sev,
            f"{streak} consecutive losing round trips — {note}.",
            principle,
        )

    def _overtrading(self, snapshot: dict[str, Any]) -> AntiPatternCheck:
        principle = (
            "Turnover is a cost multiplier: every round trip pays the spread and the fees "
            "whether or not it carried an edge. A day spent near the trade cap is usually a "
            "day of paying to be busy."
        )
        done = int(snapshot.get("trades_today", 0))
        cap = int(snapshot.get("max_trades_per_day", 0) or 0)
        if cap <= 0:
            return AntiPatternCheck(
                "overtrading", "Overtrading", Severity.OK,
                f"{done} trades today; no daily cap is configured to compare against.",
                principle,
            )
        ratio = done / cap
        if ratio >= 1.0:
            sev = Severity.ALERT
        elif ratio >= self.turnover_watch:
            sev = Severity.WATCH
        else:
            sev = Severity.OK
        return AntiPatternCheck(
            "overtrading", "Overtrading", sev,
            f"{done} of the {cap} daily trades used ({ratio:.0%} of the cap).",
            principle,
        )

    def _concentration(self, snapshot: dict[str, Any]) -> AntiPatternCheck:
        principle = (
            "Concentration turns an idiosyncratic move into a portfolio event. The risk "
            "engine caps gross exposure; this simply confirms no single name has quietly "
            "become the whole book."
        )
        equity = float(snapshot.get("equity", 0.0))
        positions = snapshot.get("positions", []) or []
        if equity <= 0 or not positions:
            return AntiPatternCheck(
                "concentration", "Over-concentration", Severity.OK,
                "No open positions to concentrate." if not positions else "Equity unknown.",
                principle,
            )
        by_symbol: dict[str, float] = {}
        for pos in positions:
            by_symbol[pos.get("symbol", "?")] = by_symbol.get(pos.get("symbol", "?"), 0.0) + abs(
                float(pos.get("notional", 0.0))
            )
        symbol, notional = max(by_symbol.items(), key=lambda kv: kv[1])
        share = notional / equity
        sev = Severity.WATCH if share >= self.concentration_watch else Severity.OK
        return AntiPatternCheck(
            "concentration", "Over-concentration", sev,
            f"{symbol} is {share:.0%} of equity as notional"
            + ("." if sev is Severity.OK else " — a large single-name bet."),
            principle,
        )

    def _win_rate(self, trades: list[dict[str, Any]]) -> AntiPatternCheck:
        principle = (
            "A low hit rate is survivable only when winners are much larger than losers. "
            "The number that matters is the payoff ratio, not the win rate — a system that "
            "wins 30% of the time and triples its risk on winners is fine."
        )
        if len(trades) < self.min_trades:
            return AntiPatternCheck(
                "win_rate", "Low win rate without payoff", Severity.OK,
                f"Only {len(trades)} recent round trips — too few to judge.",
                principle,
            )
        wins = [float(t.get("net_bps", 0.0)) for t in trades if float(t.get("net_bps", 0.0)) > 0]
        losses = [float(t.get("net_bps", 0.0)) for t in trades if float(t.get("net_bps", 0.0)) <= 0]
        win_rate = len(wins) / len(trades)
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = -sum(losses) / len(losses) if losses else 0.0
        payoff = avg_win / avg_loss if avg_loss > 0 else float("inf")
        # Low win rate is only a concern when the payoff does not compensate for it.
        breakeven_payoff = (1 - win_rate) / win_rate if win_rate > 0 else float("inf")
        low_and_unpaid = win_rate < 0.35 and payoff < breakeven_payoff
        sev = Severity.WATCH if low_and_unpaid else Severity.OK
        payoff_str = "inf" if payoff == float("inf") else f"{payoff:.1f}x"
        return AntiPatternCheck(
            "win_rate", "Low win rate without payoff", sev,
            f"{win_rate:.0%} of the last {len(trades)} trades won, average winner "
            f"{payoff_str} the average loser.",
            principle,
        )


__all__ = ["AntiPatternCheck", "AntiPatternMonitor", "Severity"]
