from __future__ import annotations

import re
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 BCA-Legal-Monitor/1.0"}

# Five additional high-value federal sources. Multiple candidate feeds are intentional:
# federal sites occasionally move RSS endpoints; the first feed that returns entries wins.
SOURCES = {
    "Bundesrat": {
        "feeds": [
            "https://www.bundesrat.de/SharedDocs/RSS/DE/termine.xml?nn=4352766",
            "https://www.bundesrat.de/SharedDocs/RSS/DE/pressemitteilungen.xml",
        ],
        "page": "https://www.bundesrat.de/DE/presse/presse-node.html",
    },
    "BMI": {
        "feeds": [
            "https://www.bmi.bund.de/SiteGlobals/Functions/RSSFeed/DE/RSSNewsfeed/RSSNewsfeed.xml",
            "https://www.bmi.bund.de/SharedDocs/feeds/DE/pressemitteilungen.xml",
        ],
        "page": "https://www.bmi.bund.de/DE/presse/pressemitteilungen/pressemitteilungen-node.html",
    },
    "BMAS": {
        "feeds": [
            "https://www.bmas.de/SiteGlobals/Functions/RSSFeed/DE/RSSNewsfeed/RSSNewsfeed.xml",
            "https://www.bmas.de/SharedDocs/Feeds/DE/RSS-News.xml",
        ],
        "page": "https://www.bmas.de/DE/Service/Presse/Pressemitteilungen/pressemitteilungen.html",
    },
    "Bundesregierung": {
        "feeds": [
            "https://www.bundesregierung.de/breg-de/service/newsletter-und-abos/rss-newsfeed-1532806",
            "https://www.bundesregierung.de/resource/blob/975232/1532804/rss-newsfeed.xml",
        ],
        "page": "https://www.bundesregierung.de/breg-de/aktuelles",
    },
}


def _clean_html(value: str) -> str:
    if not value:
        return ""
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


def _feed_items(source: str, urls: list[str], limit: int) -> list[dict]:
    for feed_url in urls:
        try:
            feed = feedparser.parse(feed_url)
            if not getattr(feed, "entries", None):
                continue
            out = []
            for e in feed.entries[:limit]:
                title = _clean_html(e.get("title", ""))
                link = e.get("link", "").strip()
                if not title or not link:
                    continue
                out.append({
                    "title": title,
                    "url": link,
                    "date": e.get("published", e.get("updated", "")),
                    "summary": _clean_html(e.get("summary", e.get("description", ""))),
                    "source": source,
                    "category": "Bundesquelle",
                })
            if out:
                return out
        except Exception:
            continue
    return []


def _page_fallback(source: str, page_url: str, limit: int) -> list[dict]:
    """Small resilient fallback. Relevance filtering later removes unrelated links."""
    try:
        r = requests.get(page_url, timeout=8, headers=HEADERS)
        r.raise_for_status()
    except requests.RequestException:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    out, seen = [], set()
    for a in soup.select("a[href]"):
        title = " ".join(a.get_text(" ", strip=True).split())
        href = a.get("href", "")
        if len(title) < 18 or not href:
            continue
        url = urljoin(page_url, href)
        if url in seen or not url.startswith("http"):
            continue
        # Avoid navigation and generic service links.
        if re.search(r"(kontakt|datenschutz|impressum|newsletter|facebook|instagram|youtube)", url, re.I):
            continue
        seen.add(url)
        out.append({"title": title, "url": url, "date": "", "summary": "", "source": source, "category": "Bundesquelle"})
        if len(out) >= limit:
            break
    return out


def fetch_federal_publications(limit_per_source: int = 40) -> list[dict]:
    all_items = []
    for source, cfg in SOURCES.items():
        items = _feed_items(source, cfg["feeds"], limit_per_source)
        if not items:
            items = _page_fallback(source, cfg["page"], limit_per_source)
        all_items.extend(items)
    return all_items
