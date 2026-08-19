"""Market intelligence — curated macro and crypto headlines, filtered before shown.

The user asked for the system to "see news, articles and reports — useful, reliable
information only; the filler and the garbage serve nobody." This module is that request
taken literally, with the honesty constraints stated up front:

**Curated at the source, not scraped at large.** The registry below is a short, fixed list:
central-bank press feeds (the primary source for international macro — the Fed, the ECB,
the Bank of England publish their own decisions) and two premier crypto newsrooms. Nothing
is discovered dynamically; adding a source is a code change someone reviews. RSS on
purpose: keyless, stable, legal, and each item carries its own timestamp and link.

**Filtered by rules you can read.** Every headline is scored by a deterministic relevance
engine — macro terms, crypto terms, market terms, each with a visible weight — and clickbait
patterns ("price prediction", "top 10 coins", giveaways, promo content) are discarded
outright. The matched terms travel with each item, so "why is this here?" always has an
answer. A model is never asked to judge relevance: the filter must work identically with
the AI layer disabled.

**It informs; it does not steer.** These items feed the dashboard and the read-only
Advisor's grounding. They are deliberately NOT fed into the deterministic trading pipeline:
a headline is not evidence of edge, and this system only trades measured evidence. The one
model-facing surface (:meth:`MarketIntelService.as_news_items`) serves the *advisory*
context layer, whose output can only ever reduce or veto risk.

Integration status: **REQUIRES VALIDATION** — like the Binance client, the feed URLs could
not be exercised from this build environment (egress blocked). Every source's health is
part of the report, so a dead or changed feed is visible in the UI rather than silent, and
``scripts/validate_intel.py`` exercises the real feeds from a machine with egress.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from tia.core.clock import Clock, ensure_utc
from tia.core.logging import get_logger
from tia.domain.market import NewsItem

_log = get_logger("data.intel")

#: A feed response larger than this is not a headline feed; refuse rather than parse.
MAX_FEED_BYTES = 1_000_000


@dataclass(frozen=True)
class IntelSource:
    """One curated feed. The registry is code, so growing it is a reviewed decision."""

    source_id: str
    name: str
    url: str
    #: "official" — a primary source (central bank); "premier" — top-tier specialist press.
    tier: str
    region: str


#: The whole registry. Deliberately short: five sources someone can vouch for beat fifty
#: nobody has read. Official feeds cover the international macro the user asked about —
#: rate decisions and statements come from the institutions that make them.
DEFAULT_SOURCES: tuple[IntelSource, ...] = (
    IntelSource(
        "fed", "US Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml",
        tier="official", region="US",
    ),
    IntelSource(
        "ecb", "European Central Bank", "https://www.ecb.europa.eu/rss/press.html",
        tier="official", region="EU",
    ),
    IntelSource(
        "boe", "Bank of England", "https://www.bankofengland.co.uk/rss/news",
        tier="official", region="UK",
    ),
    IntelSource(
        "coindesk", "CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/",
        tier="premier", region="global",
    ),
    IntelSource(
        "cointelegraph", "Cointelegraph", "https://cointelegraph.com/rss",
        tier="premier", region="global",
    ),
)


# --------------------------------------------------------------------------- relevance

#: Clickbait and promo patterns. A headline matching any of these is discarded outright —
#: not down-ranked, discarded — because ranking garbage is still serving garbage.
GARBAGE_PATTERNS: tuple[str, ...] = (
    "price prediction",
    "price analysis",
    "could reach",
    "could hit",
    "top 10",
    "top 5",
    "how to buy",
    "giveaway",
    "airdrop",
    "sponsored",
    "partner content",
    "press release:",
    "presale",
    "meme coin",
    "memecoin",
    "casino",
    "here's why",
    "heres why",
)

#: Macro vocabulary — the international, long-horizon signal the user asked for.
MACRO_TERMS: tuple[str, ...] = (
    "federal reserve", "fomc", "fed ", "ecb", "bank of england", "boe",
    "interest rate", "rate decision", "rate cut", "rate hike", "monetary policy",
    "inflation", "cpi", "pce", "payrolls", "employment", "jobless", "gdp",
    "treasury", "yield", "bond", "dollar", "dxy", "recession", "tariff",
    "stimulus", "quantitative", "imf", "central bank",
)

CRYPTO_TERMS: tuple[str, ...] = (
    "bitcoin", "btc", "ethereum", "eth ", "crypto", "binance", "coinbase",
    "etf", "stablecoin", "sec ", "halving", "mining", "miner", "custody",
    "regulation", "defi", "exchange",
)

MARKET_TERMS: tuple[str, ...] = (
    "stocks", "equities", "s&p", "nasdaq", "gold", "oil", "futures", "wall street",
)

#: Below this score an item is dropped as irrelevant — present in the feed, absent from
#: the report. Chosen so a premier-press headline needs at least one matched term.
DEFAULT_MIN_RELEVANCE = 0.35

_TIER_BASE = {"official": 0.40, "premier": 0.25}


@dataclass(frozen=True)
class RelevanceVerdict:
    """Why an item scored what it scored. Travels with the item into the UI."""

    score: float
    kind: str  # "macro" | "crypto" | "market" | "other"
    horizon: str  # "long" | "short"
    matched: tuple[str, ...]
    discarded: bool = False
    reason: str = ""


def _hits(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def score_headline(headline: str, *, tier: str) -> RelevanceVerdict:
    """Deterministic relevance for one headline. Pure — same input, same verdict."""
    text = f" {headline.casefold()} "
    for pattern in GARBAGE_PATTERNS:
        if pattern in text:
            return RelevanceVerdict(
                score=0.0, kind="other", horizon="short", matched=(),
                discarded=True, reason=f"matched garbage pattern {pattern!r}",
            )

    macro = _hits(text, MACRO_TERMS)
    crypto = _hits(text, CRYPTO_TERMS)
    market = _hits(text, MARKET_TERMS)

    score = _TIER_BASE.get(tier, 0.15)
    if macro:
        score += 0.35 + min(0.15, 0.05 * (len(macro) - 1))
    if crypto:
        score += 0.30 + min(0.15, 0.05 * (len(crypto) - 1))
    if market:
        score += 0.15
    score = min(1.0, score)

    if macro and len(macro) >= len(crypto):
        kind = "macro"
    elif crypto:
        kind = "crypto"
    elif market:
        kind = "market"
    else:
        kind = "other"

    return RelevanceVerdict(
        score=round(score, 4),
        kind=kind,
        # Macro developments move on the horizon of months — the "international,
        # long-term" signal. Everything else is treated as short-horizon colour.
        horizon="long" if macro else "short",
        matched=tuple(macro + crypto + market),
    )


# --------------------------------------------------------------------------- parsing

_ATOM = "{http://www.w3.org/2005/Atom}"


#: DTD or entity declarations in a feed. No legitimate headline feed carries either, and
#: every XML entity-expansion attack requires one — so their mere presence is a refusal.
_FORBIDDEN_MARKUP = re.compile(r"<!(?:DOCTYPE|ENTITY)", re.IGNORECASE)


def _safe_xml(text: str) -> ET.Element:
    """Parse XML with DTD and entity declarations refused.

    ``xml.etree`` expands internal entities, which makes it vulnerable to entity-expansion
    bombs — and internal entities can only be declared inside a DOCTYPE. Refusing any
    document that contains one (checked *before* the parser sees it, because the C-level
    parser exposes no handler hooks) closes that class of attack; the size cap upstream
    closes the quadratic-blowup one.
    """
    if _FORBIDDEN_MARKUP.search(text):
        raise ValueError("feed contains DTD/entity declarations; refused")
    return ET.fromstring(text)  # noqa: S314 - DOCTYPE/ENTITY refused above; size capped by the fetcher


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    try:  # RFC 822, the RSS 2.0 convention
        return ensure_utc(parsedate_to_datetime(raw))
    except (TypeError, ValueError):
        pass
    try:  # ISO 8601, the Atom convention
        return ensure_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError:
        return None


def parse_feed(text: str) -> list[dict[str, Any]]:
    """Extract ``{title, url, published_at}`` rows from an RSS 2.0 or Atom document.

    Anything else — malformed XML, an HTML error page, a DTD — raises, and the caller
    records the source as failed rather than guessing at the content.
    """
    root = _safe_xml(text)
    rows: list[dict[str, Any]] = []

    for item in root.iter("item"):  # RSS 2.0
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        rows.append(
            {
                "title": re.sub(r"\s+", " ", title),
                "url": (item.findtext("link") or "").strip() or None,
                "published_at": _parse_date(item.findtext("pubDate")),
            }
        )

    for entry in root.iter(f"{_ATOM}entry"):  # Atom
        title = (entry.findtext(f"{_ATOM}title") or "").strip()
        if not title:
            continue
        link = entry.find(f"{_ATOM}link")
        rows.append(
            {
                "title": re.sub(r"\s+", " ", title),
                "url": (link.get("href") if link is not None else None) or None,
                "published_at": _parse_date(
                    entry.findtext(f"{_ATOM}published")
                    or entry.findtext(f"{_ATOM}updated")
                ),
            }
        )

    if not rows and root.tag not in {"rss", f"{_ATOM}feed"}:
        raise ValueError(f"not a recognised feed document (root <{root.tag}>)")
    return rows


# --------------------------------------------------------------------------- service


@dataclass
class _SourceHealth:
    source: IntelSource
    ok: bool | None = None  # None until first attempted
    detail: str = ""
    items_seen: int = 0
    last_attempt: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source.source_id,
            "name": self.source.name,
            "tier": self.source.tier,
            "region": self.source.region,
            "url": self.source.url,
            "ok": self.ok,
            "detail": self.detail,
            "items_seen": self.items_seen,
            "last_attempt": self.last_attempt.isoformat() if self.last_attempt else None,
        }


@dataclass
class MarketIntelService:
    """Fetches the curated feeds, filters them, and serves the survivors.

    Failure is a first-class outcome: a source that is down, moved, or blocked is recorded
    in its health row and skipped — one dead feed never empties the report, and no failure
    here can reach the trading loop because nothing here is on the trading loop.
    """

    clock: Clock
    sources: tuple[IntelSource, ...] = DEFAULT_SOURCES
    client: httpx.AsyncClient | None = None
    min_relevance: float = DEFAULT_MIN_RELEVANCE
    #: Feeds are polled at most this often; a forced refresh bypasses the limit.
    refresh_seconds: float = 900.0
    timeout_seconds: float = 8.0
    max_items: int = 200

    _items: dict[str, dict[str, Any]] = field(default_factory=dict)
    _health: dict[str, _SourceHealth] = field(default_factory=dict)
    _last_refresh: datetime | None = None
    _discarded: int = 0
    _irrelevant: int = 0
    _owns_client: bool = False

    def __post_init__(self) -> None:
        self._health = {s.source_id: _SourceHealth(source=s) for s in self.sources}
        if self.client is None:
            self._owns_client = True
            self.client = httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "trader-ia/0.1 (research; simulation-only)"},
            )

    # ------------------------------------------------------------------ refresh

    async def refresh(self, *, force: bool = False) -> None:
        """Fetch every source, isolating failures per source. Never raises."""
        now = self.clock.now()
        if (
            not force
            and self._last_refresh is not None
            and (now - self._last_refresh) < timedelta(seconds=self.refresh_seconds)
        ):
            return
        self._last_refresh = now
        await asyncio.gather(
            *(self._fetch_source(source) for source in self.sources),
            return_exceptions=True,  # belt and braces; _fetch_source already catches
        )
        self._prune()

    async def _fetch_source(self, source: IntelSource) -> None:
        health = self._health[source.source_id]
        health.last_attempt = self.clock.now()
        try:
            if self.client is None:  # pragma: no cover - __post_init__ guarantees one
                raise RuntimeError("intel client not initialised")
            response = await self.client.get(source.url)
            response.raise_for_status()
            if len(response.content) > MAX_FEED_BYTES:
                raise ValueError(f"feed exceeds {MAX_FEED_BYTES} bytes")
            rows = parse_feed(response.text)
        except Exception as exc:  # each source degrades independently
            health.ok = False
            health.detail = f"{type(exc).__name__}: {str(exc)[:160]}"
            _log.warning("intel_source_failed", source=source.source_id, error=health.detail)
            return

        health.ok = True
        health.detail = f"{len(rows)} entries"
        health.items_seen = len(rows)
        for row in rows:
            self._ingest(source, row)

    def _ingest(self, source: IntelSource, row: dict[str, Any]) -> None:
        verdict = score_headline(row["title"], tier=source.tier)
        if verdict.discarded:
            self._discarded += 1
            return
        if verdict.score < self.min_relevance:
            self._irrelevant += 1
            return
        item_id = hashlib.sha256(row["title"].casefold().encode()).hexdigest()[:16]
        if item_id in self._items:
            return  # the same story from a later poll is still one story
        published = row["published_at"] or self.clock.now()
        self._items[item_id] = {
            "item_id": item_id,
            "headline": row["title"],
            "url": row["url"],
            "source": source.name,
            "source_id": source.source_id,
            "tier": source.tier,
            "region": source.region,
            "published_at": published.isoformat(),
            "ingested_at": self.clock.now().isoformat(),
            "relevance": verdict.score,
            "kind": verdict.kind,
            "horizon": verdict.horizon,
            "matched": list(verdict.matched),
        }

    def _prune(self) -> None:
        if len(self._items) <= self.max_items:
            return
        ranked = sorted(
            self._items.values(), key=lambda i: i["published_at"], reverse=True
        )
        self._items = {i["item_id"]: i for i in ranked[: self.max_items]}

    # ------------------------------------------------------------------ reading

    def items(self, *, kind: str | None = None, limit: int = 60) -> list[dict[str, Any]]:
        rows = sorted(
            self._items.values(),
            key=lambda i: (i["published_at"], i["relevance"]),
            reverse=True,
        )
        if kind:
            rows = [r for r in rows if r["kind"] == kind]
        return rows[:limit]

    def report(self) -> dict[str, Any]:
        """Everything the dashboard shows, including which sources are alive."""
        sources = [self._health[s.source_id].as_dict() for s in self.sources]
        reachable = sum(1 for s in sources if s["ok"])
        return {
            "items": self.items(),
            "sources": sources,
            "sources_ok": reachable,
            "sources_total": len(sources),
            "discarded": self._discarded,
            "filtered_irrelevant": self._irrelevant,
            "last_refresh": self._last_refresh.isoformat() if self._last_refresh else None,
            "explanation": (
                "A fixed, curated registry — central-bank press feeds for international "
                "macro, plus premier crypto newsrooms — scored by a rules-based relevance "
                "filter that discards clickbait outright. Each item shows the terms that "
                "earned its place. This page informs you and grounds the Advisor; it does "
                "not feed the trading pipeline, because a headline is not measured edge."
            ),
        }

    def as_news_items(self, limit: int = 10) -> list[NewsItem]:
        """The top stories as domain ``NewsItem`` rows, for the advisory context layer."""
        out: list[NewsItem] = []
        for row in self.items(limit=limit):
            out.append(
                NewsItem(
                    news_id=row["item_id"],
                    published_at=datetime.fromisoformat(row["published_at"]),
                    ingested_at=datetime.fromisoformat(row["ingested_at"]),
                    source=row["source"],
                    headline=row["headline"],
                    body_hash=hashlib.sha256(row["headline"].encode()).hexdigest(),
                    url=row["url"],
                    symbols=("BTC-USD",) if row["kind"] == "crypto" else (),
                )
            )
        return out

    async def close(self) -> None:
        if self.client is not None and self._owns_client:
            await self.client.aclose()
            self.client = None


__all__ = [
    "DEFAULT_MIN_RELEVANCE",
    "DEFAULT_SOURCES",
    "GARBAGE_PATTERNS",
    "IntelSource",
    "MarketIntelService",
    "RelevanceVerdict",
    "parse_feed",
    "score_headline",
]
