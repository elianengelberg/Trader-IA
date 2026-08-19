#!/usr/bin/env python3
"""Exercise the curated intel feeds against the real internet.

The build environment blocks egress, so the feed URLs in ``tia.data.intel`` ship marked
REQUIRES VALIDATION. Run this from a machine that can reach them (the VPS qualifies):

    PYTHONPATH=packages/tia/src python scripts/validate_intel.py

It fetches every source in the registry, prints per-source health and the top headlines
that survived the relevance filter, and exits non-zero if not a single source answered —
the same picture the dashboard's "Macro & News" page shows, without the browser.
"""

from __future__ import annotations

import asyncio


async def main() -> int:
    from tia.core.clock import SystemClock
    from tia.data.intel import MarketIntelService

    service = MarketIntelService(clock=SystemClock())
    print(f"Fetching {len(service.sources)} curated sources…\n")
    await service.refresh(force=True)
    report = service.report()

    for source in report["sources"]:
        mark = " OK " if source["ok"] else "FAIL"
        print(f"[{mark}] {source['name']:<24} {source['detail']}")

    print(
        f"\n{len(report['items'])} relevant items kept · "
        f"{report['discarded']} discarded as garbage · "
        f"{report['filtered_irrelevant']} filtered as irrelevant\n"
    )
    for item in report["items"][:12]:
        print(f"  {item['relevance']:.2f} [{item['kind']:>6}] {item['headline'][:96]}")

    await service.close()
    if report["sources_ok"] == 0:
        print("\nRESULT: FAIL — no source reachable. Run from a machine with egress.")
        return 1
    print(f"\nRESULT: OK — {report['sources_ok']}/{report['sources_total']} sources alive.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
