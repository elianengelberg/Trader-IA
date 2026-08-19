"""The behaviour audit: does it name the right anti-pattern, and only when it is real?

The monitor exists to catch the system drifting toward a documented way accounts are
emptied. So the tests it must pass are: it stays quiet on healthy behaviour, it speaks when
a threshold is genuinely crossed, and every check it raises carries the principle behind it
so the warning is teaching, not scolding.
"""

from __future__ import annotations

from tia.learning.antipatterns import AntiPatternMonitor, Severity


def _trades(net_bps: float, fees_bps: float, n: int) -> list[dict]:
    gross = net_bps + fees_bps
    return [
        {"net_bps": net_bps, "gross_bps": gross, "fees_bps": fees_bps, "direction": "long",
         "symbol": "BTC-USD", "closed_at": "2026-01-01T00:00:00Z"}
        for _ in range(n)
    ]


def _check(report: dict, key: str) -> dict:
    return next(c for c in report["checks"] if c["key"] == key)


def test_a_healthy_session_raises_nothing() -> None:
    monitor = AntiPatternMonitor()
    snapshot = {
        "recent_trades": _trades(net_bps=20.0, fees_bps=4.0, n=12),
        "trades_today": 2,
        "max_trades_per_day": 20,
        "consecutive_losses": 0,
        "positions": [],
        "equity": 10_000.0,
        "new_trades_allowed": True,
    }
    report = monitor.report(snapshot)
    assert report["worst_severity"] == "ok"
    assert report["alerts"] == 0


def test_cost_drag_fires_when_fees_eat_the_edge() -> None:
    monitor = AntiPatternMonitor()
    # Gross 10 bps, fees 5 bps -> fees are 50% of gross, above the 40% alert line.
    snapshot = {"recent_trades": _trades(net_bps=5.0, fees_bps=5.0, n=12), "equity": 1.0}
    check = _check(monitor.report(snapshot), "cost_drag")
    assert check["severity"] == "alert"
    assert "renting the exchange" in check["principle"]


def test_negative_edge_is_an_alert_when_the_average_is_clearly_red() -> None:
    monitor = AntiPatternMonitor()
    snapshot = {"recent_trades": _trades(net_bps=-8.0, fees_bps=4.0, n=12), "equity": 1.0}
    check = _check(monitor.report(snapshot), "negative_edge")
    assert check["severity"] == "alert"


def test_a_short_history_stays_silent_rather_than_guessing() -> None:
    monitor = AntiPatternMonitor(min_trades=8)
    snapshot = {"recent_trades": _trades(net_bps=-50.0, fees_bps=10.0, n=3), "equity": 1.0}
    # Three awful trades is not yet evidence — the average-based checks must not fire.
    report = monitor.report(snapshot)
    assert _check(report, "cost_drag")["severity"] == "ok"
    assert _check(report, "negative_edge")["severity"] == "ok"


def test_a_losing_streak_is_flagged_and_tied_to_the_no_martingale_guarantee() -> None:
    monitor = AntiPatternMonitor()
    snapshot = {"recent_trades": [], "consecutive_losses": 6, "new_trades_allowed": True}
    check = _check(monitor.report(snapshot), "loss_streak")
    assert check["severity"] == "alert"
    assert "martingale" in check["principle"]


def test_overtrading_scales_with_how_full_the_daily_cap_is() -> None:
    monitor = AntiPatternMonitor()
    at_cap = _check(
        monitor.report({"recent_trades": [], "trades_today": 20, "max_trades_per_day": 20}),
        "overtrading",
    )
    assert at_cap["severity"] == "alert"
    calm = _check(
        monitor.report({"recent_trades": [], "trades_today": 3, "max_trades_per_day": 20}),
        "overtrading",
    )
    assert calm["severity"] == "ok"


def test_concentration_notices_a_single_name_dominating_the_book() -> None:
    monitor = AntiPatternMonitor()
    snapshot = {
        "recent_trades": [],
        "equity": 10_000.0,
        "positions": [{"symbol": "BTC-USD", "direction": "long", "notional": 9_000.0}],
    }
    check = _check(monitor.report(snapshot), "concentration")
    assert check["severity"] == "watch"
    assert "BTC-USD" in check["detail"]


def test_a_low_win_rate_with_a_big_payoff_is_not_flagged() -> None:
    """The point of the payoff check: 30% winners is fine if the winners are large."""
    monitor = AntiPatternMonitor()
    trades = _trades(net_bps=-10.0, fees_bps=4.0, n=7) + _trades(net_bps=60.0, fees_bps=4.0, n=3)
    check = _check(monitor.report({"recent_trades": trades}), "win_rate")
    assert check["severity"] == "ok"


def test_every_check_carries_its_principle() -> None:
    monitor = AntiPatternMonitor()
    report = monitor.report({"recent_trades": _trades(20.0, 4.0, 12), "equity": 1.0})
    assert report["checks"]
    for check in report["checks"]:
        assert check["principle"], f"{check['key']} has no principle attached"
    # The report sorts worst-first.
    severities = [Severity(c["severity"]) for c in report["checks"]]
    assert severities == sorted(severities, key=lambda s: {"ok": 0, "watch": 1, "alert": 2}[s.value], reverse=True)
