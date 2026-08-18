#!/usr/bin/env python3
"""Drive the dashboard in a real browser and assert it works.

The point is to catch what an API test cannot: a view that throws on render, a chart that
crashes on empty data, a stream that never connects, a number that never appears. Those
failures are invisible to `curl` and obvious to anyone who opens the page — which makes
them exactly the ones worth automating.

It fails on the first browser console error, because a dashboard that logs an exception is
a dashboard someone will eventually see break.

Usage:
    python scripts/browser_smoke.py [--url http://127.0.0.1:8000] [--shots out/dir]
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

VIEWS = [
    "Dashboard",
    "Markets",
    "Portfolio",
    "Orders & Fills",
    "Strategy & Costs",
    "AI Decisions",
    "Risk",
    "Ruin Analytics",
    "News",
    "Backtests",
    "Live Trading",
    "System",
    "Logs",
    "Settings",
]

#: Console noise that is not a defect. Kept explicit and short — a broad filter here would
#: defeat the purpose of failing on console errors at all.
#:
#: The 401 is the app checking for an existing session on load. It is the correct
#: behaviour — an unauthenticated visitor *should* be refused — and the browser logs every
#: 401 as a console error regardless of whether the code handled it.
IGNORED_CONSOLE = (
    "favicon",
    "Download the React DevTools",
    "401 (Unauthorized)",
)


def shows(page, text: str) -> bool:
    """Whether the main region displays this text.

    Case-insensitive on purpose: the stylesheet uppercases every label through
    ``text-transform``, and ``inner_text()`` returns the *rendered* text. Comparing
    case-sensitively here tests the CSS, not the application.
    """
    return text.casefold() in page.locator("main").inner_text().casefold()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("TIA_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--user", default=os.environ.get("TIA_DEMO_USER", "operator"))
    parser.add_argument("--password", default=os.environ.get("TIA_DEMO_PASSWORD", "demo-secret"))
    parser.add_argument("--shots", default="")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    shots = Path(args.shots) if args.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    failures: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=not args.headed, executable_path="/opt/pw-browsers/chromium"
        )
        page = browser.new_page(viewport={"width": 1440, "height": 960})

        page.on(
            "console",
            lambda message: errors.append(f"console.{message.type}: {message.text}")
            if message.type == "error"
            and not any(skip in message.text for skip in IGNORED_CONSOLE)
            else None,
        )
        page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))

        def check(name: str, condition: bool, detail: str = "") -> None:
            status = "PASS" if condition else "FAIL"
            print(f"  [{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
            if not condition:
                failures.append(f"{name}{': ' + detail if detail else ''}")

        print(f"Opening {args.url}")
        page.goto(args.url, wait_until="networkidle", timeout=30_000)

        # ---- login -------------------------------------------------------
        print("\nAuthentication")
        check("login form is shown to an unauthenticated visitor", page.locator("form").count() > 0)
        page.fill('input[autocomplete="username"]', args.user)
        page.fill('input[autocomplete="current-password"]', args.password)
        page.click('button[type="submit"]')
        page.wait_for_selector(".topbar", timeout=15_000)
        check("session established", page.locator(".topbar").count() > 0)
        check(
            "simulated-capital banner is visible",
            "SIMULATED CAPITAL" in page.locator(".sim-badge").inner_text(),
        )
        if shots:
            page.screenshot(path=str(shots / "01-after-login.png"), full_page=True)

        # ---- start a run -------------------------------------------------
        print("\nStarting a paper-trading run")
        page.select_option("select >> nth=0", "mixed")
        page.select_option("select >> nth=1", "10000")
        # Deliberately not the fastest setting: the control checks further down need the
        # run to still be active, and "Fast" finishes 660 bars before they are reached.
        page.select_option("select >> nth=2", "0.12")
        page.click("button:has-text('Start paper trading')")
        page.wait_for_timeout(1500)

        page.wait_for_selector(".pill:has-text('Running'), .pill:has-text('Finished')", timeout=20_000)
        check("run reached a live state", True)

        print("  waiting for the pipeline to produce activity…")
        produced = False
        for _ in range(60):
            page.wait_for_timeout(1000)
            if shows(page, "bars processed"):
                bars = page.locator(".stat", has_text="BARS PROCESSED").first
                if bars.count() and bars.inner_text().strip().splitlines()[-1] not in {"0", ""}:
                    produced = True
                    break
        check("bars are being processed", produced)

        # ---- the live view -----------------------------------------------
        print("\nDashboard content")
        check("equity is displayed", shows(page, "equity (simulated)"))
        check("P&L is displayed", shows(page, "total p&l"))
        check("drawdown is displayed", shows(page, "max drawdown"))
        check("pipeline counters are displayed", shows(page, "risk approved"))
        check("fills are displayed", shows(page, "recent fills"))
        check(
            "stream reports connected",
            page.locator(".pill:has-text('Connected')").count() > 0,
        )
        check(
            "the simulation disclaimer is present",
            shows(page, "every number on this page is simulated"),
        )
        if shots:
            page.screenshot(path=str(shots / "02-dashboard-live.png"), full_page=True)

        # ---- every view renders ------------------------------------------
        print("\nViews")
        for index, view in enumerate(VIEWS, start=3):
            before = len(errors)
            page.click(f".sidenav button:has-text('{view}')")
            page.wait_for_timeout(900)
            heading = page.locator("main h1").first.inner_text()
            check(f"{view} renders", len(errors) == before, f"{len(errors) - before} console error(s)")
            check(f"{view} has a heading", bool(heading.strip()))
            if shots:
                page.screenshot(
                    path=str(shots / f"{index:02d}-{view.lower().replace(' ', '-').replace('&', 'and')}.png"),
                    full_page=True,
                )

        # ---- a decision opens its journal --------------------------------
        print("\nTrade journal")
        page.click(".sidenav button:has-text('AI Decisions')")
        # The runtime processes a warm-up stretch before it will decide anything, so an
        # empty table here early in a run is correct behaviour rather than a defect. Poll
        # rather than assume, and fail only if decisions never arrive.
        rows = page.locator("tr.clickable")
        for _ in range(45):
            page.wait_for_timeout(1000)
            if rows.count() > 0:
                break
        if rows.count() > 0:
            rows.first.click()
            page.wait_for_selector(".drawer", timeout=8_000)
            drawer = page.locator(".drawer").inner_text().casefold()
            check("decision drawer opens", True)
            check("it explains why the system decided", "why the system decided this" in drawer)
            check("it shows the risk checks", "risk checks" in drawer)
            check("it shows the AI's effect", "ai context" in drawer)
            check("it shows the features it saw", "features at decision time" in drawer)
            if shots:
                page.screenshot(path=str(shots / "20-decision-journal.png"), full_page=True)
            page.click(".drawer button:has-text('Close')")
        else:
            check("decisions are available to inspect", False, "no decision rows rendered")

        # ---- run a backtest from the UI ----------------------------------
        print("\nBacktest from the dashboard")
        page.click(".sidenav button:has-text('Backtests')")
        page.wait_for_timeout(600)
        page.click("button:has-text('Run backtest')")
        try:
            page.wait_for_selector(".drawer", timeout=90_000)
            drawer = page.locator(".drawer").inner_text().casefold()
            check("backtest completed and opened its report", True)
            check("baselines are shown", "mandatory baselines" in drawer)
            check(
                "the evidence statement is shown",
                "makes no claim about future results" in drawer,
            )
            if shots:
                page.screenshot(path=str(shots / "21-backtest-report.png"), full_page=True)
            page.click(".drawer button:has-text('Close')")
        except PlaywrightError:
            check("backtest completed", False, "timed out waiting for the report")

        # ---- controls ----------------------------------------------------
        print("\nControls")
        page.click(".sidenav button:has-text('Dashboard')")
        page.wait_for_timeout(400)
        if page.locator("button:has-text('Kill switch')").count() > 0:
            page.click("button:has-text('Kill switch')")
            page.wait_for_selector("text=Engage kill switch?", timeout=5_000)
            check("kill switch asks for confirmation", True)
            page.click("button:has-text('Cancel')")
        check(
            "stop control is available while the run is active",
            page.locator("button:has-text('Stop run')").count() > 0,
        )
        if page.locator("button:has-text('Stop run')").count() > 0:
            page.click("button:has-text('Stop run')")
            page.wait_for_timeout(3000)
            check(
                "run can be stopped",
                page.locator(".pill:has-text('Stopped')").count() > 0,
            )

        # ---- responsive --------------------------------------------------
        print("\nResponsive layout")
        page.set_viewport_size({"width": 820, "height": 1180})
        page.wait_for_timeout(700)
        check("tablet layout renders", page.locator(".sidenav").count() > 0)
        if shots:
            page.screenshot(path=str(shots / "22-tablet.png"), full_page=True)

        browser.close()

    print("\n" + "=" * 68)
    if errors:
        print(f"BROWSER CONSOLE ERRORS ({len(errors)}):")
        for error in errors[:20]:
            print(f"  {error}")
    if failures:
        print(f"FAILED CHECKS ({len(failures)}):")
        for failure in failures:
            print(f"  {failure}")
        print("RESULT: FAIL")
        return 1
    if errors:
        print("RESULT: FAIL (console errors)")
        return 1
    print("RESULT: PASS — every view rendered, the pipeline ran, no console errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
