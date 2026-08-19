"""Market intelligence: curation that actually curates, and failure that degrades.

What must hold: the relevance rules keep macro and crypto signal and discard clickbait;
the parser reads real RSS and Atom shapes and refuses XML bombs; a dead source is recorded
as dead without emptying the report; and the same story never appears twice.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from tia.core.clock import SimulatedClock
from tia.data.intel import (
    IntelSource,
    MarketIntelService,
    parse_feed,
    score_headline,
)

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Test</title>
<item><title>Federal Reserve issues FOMC statement</title>
<link>https://example.org/fomc</link>
<pubDate>Mon, 17 Aug 2026 14:00:00 GMT</pubDate></item>
<item><title>Bitcoin ETF sees record weekly inflows</title>
<link>https://example.org/etf</link>
<pubDate>Mon, 17 Aug 2026 15:00:00 GMT</pubDate></item>
<item><title>Top 10 coins that could reach the moon</title>
<link>https://example.org/junk</link>
<pubDate>Mon, 17 Aug 2026 16:00:00 GMT</pubDate></item>
<item><title>Celebrity opens a restaurant in Lisbon</title>
<link>https://example.org/offtopic</link>
<pubDate>Mon, 17 Aug 2026 17:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Test Atom</title>
<entry><title>ECB holds interest rates, signals caution on inflation</title>
<link href="https://example.org/ecb"/>
<updated>2026-08-17T12:00:00Z</updated></entry>
</feed>"""

BOMB = """<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;">]>
<rss version="2.0"><channel><item><title>&lol2;</title></item></channel></rss>"""


def _clock() -> SimulatedClock:
    return SimulatedClock(start=datetime(2026, 8, 18, tzinfo=UTC))


def _service(handler, sources) -> MarketIntelService:  # type: ignore[no-untyped-def]
    return MarketIntelService(
        clock=_clock(),
        sources=sources,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


# ------------------------------------------------------------------ relevance rules


def test_official_macro_headlines_score_high_and_long_horizon() -> None:
    verdict = score_headline("Federal Reserve issues FOMC statement", tier="official")
    assert verdict.score >= 0.75
    assert verdict.kind == "macro"
    assert verdict.horizon == "long"
    assert "fomc" in verdict.matched


def test_crypto_headlines_classify_as_crypto_short_horizon() -> None:
    verdict = score_headline("Bitcoin ETF sees record weekly inflows", tier="premier")
    assert verdict.score >= 0.55
    assert verdict.kind == "crypto"
    assert verdict.horizon == "short"


def test_clickbait_is_discarded_not_downranked() -> None:
    verdict = score_headline("Top 10 coins that could reach the moon", tier="premier")
    assert verdict.discarded is True
    assert verdict.score == 0.0
    assert "garbage" in verdict.reason


def test_offtopic_filler_scores_below_the_bar() -> None:
    verdict = score_headline("Celebrity opens a restaurant in Lisbon", tier="premier")
    assert verdict.discarded is False
    assert verdict.score < 0.35  # premier tier base alone does not earn a place


def test_the_verdict_is_deterministic() -> None:
    a = score_headline("ECB cuts interest rates amid falling inflation", tier="official")
    b = score_headline("ECB cuts interest rates amid falling inflation", tier="official")
    assert a == b


# ------------------------------------------------------------------ parsing


def test_rss_2_0_parses_titles_links_and_dates() -> None:
    rows = parse_feed(RSS)
    assert len(rows) == 4
    assert rows[0]["title"] == "Federal Reserve issues FOMC statement"
    assert rows[0]["url"] == "https://example.org/fomc"
    assert rows[0]["published_at"] is not None
    assert rows[0]["published_at"].tzinfo is not None


def test_atom_parses_via_namespace() -> None:
    rows = parse_feed(ATOM)
    assert len(rows) == 1
    assert rows[0]["url"] == "https://example.org/ecb"


def test_an_entity_bomb_is_refused_outright() -> None:
    with pytest.raises(ValueError, match="refused"):
        parse_feed(BOMB)


def test_an_html_error_page_is_not_mistaken_for_a_feed() -> None:
    with pytest.raises(Exception):  # noqa: B017 - any parse/shape failure is a refusal
        parse_feed("<html><body>502 Bad Gateway</body></html>")


# ------------------------------------------------------------------ the service


async def test_one_dead_source_never_empties_the_report() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "good" in str(request.url):
            return httpx.Response(200, text=RSS)
        return httpx.Response(500, text="boom")

    # The good feed is *premier* tier on purpose: an official source's base relevance
    # alone clears the bar (a central bank does not publish filler), so the
    # filtered-irrelevant path is only exercisable through a press-tier source.
    service = _service(
        handler,
        (
            IntelSource("good", "Good Feed", "https://good.example/rss", tier="premier", region="US"),
            IntelSource("dead", "Dead Feed", "https://dead.example/rss", tier="premier", region="global"),
        ),
    )
    await service.refresh(force=True)
    report = service.report()

    assert report["sources_ok"] == 1
    dead = next(s for s in report["sources"] if s["source_id"] == "dead")
    assert dead["ok"] is False and "HTTPStatusError" in dead["detail"]
    # The good source's items survived: FOMC + ETF kept, junk discarded, filler filtered.
    headlines = [i["headline"] for i in report["items"]]
    assert "Federal Reserve issues FOMC statement" in headlines
    assert all("Top 10" not in h for h in headlines)
    assert report["discarded"] == 1
    assert report["filtered_irrelevant"] == 1


async def test_the_same_story_is_ingested_once_across_polls() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, text=RSS)

    service = _service(
        handler,
        (IntelSource("s", "S", "https://s.example/rss", tier="official", region="US"),),
    )
    await service.refresh(force=True)
    first = len(service.report()["items"])
    await service.refresh(force=True)
    assert len(service.report()["items"]) == first  # re-served, not re-counted
    assert calls["n"] == 2


async def test_refresh_is_rate_limited_unless_forced() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, text=RSS)

    service = _service(
        handler,
        (IntelSource("s", "S", "https://s.example/rss", tier="official", region="US"),),
    )
    await service.refresh(force=True)
    await service.refresh()  # inside the window — must not hit the network again
    assert calls["n"] == 1


async def test_items_can_be_filtered_by_kind_and_export_as_domain_news() -> None:
    service = _service(
        lambda request: httpx.Response(200, text=RSS),
        (IntelSource("s", "S", "https://s.example/rss", tier="official", region="US"),),
    )
    await service.refresh(force=True)

    macro = service.items(kind="macro")
    assert macro and all(i["kind"] == "macro" for i in macro)

    news = service.as_news_items(limit=5)
    assert news and news[0].headline
    crypto_rows = [n for n in news if n.symbols]
    assert all(n.symbols == ("BTC-USD",) for n in crypto_rows)
