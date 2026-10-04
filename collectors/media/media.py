from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
import re
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 BCA-Legal-Migration-Monitor/1.0"}

MEDIA_SOURCES = {
    "DW": ("dw.com", ["Migration Deutschland", "Aufenthaltsrecht Deutschland", "Einbürgerung Deutschland"]),
    "rbb24": ("rbb24.de", ["Migration Berlin", "Ausländerbehörde Berlin", "Einbürgerung Berlin"]),
    "Tagesspiegel": ("tagesspiegel.de", ["Migration Deutschland", "Aufenthaltsrecht", "Einbürgerung"]),
    "Handelsblatt": ("handelsblatt.com", ["Fachkräfte Einwanderung", "Arbeitsmigration Deutschland", "Blue Card Deutschland"]),
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)).strip()


def _date(value: str) -> str:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        return value or ""


def _fetch(source: str, domain: str, query: str, limit: int = 18) -> list[dict]:
    q = quote_plus(f"{query} site:{domain}")
    url = f"https://news.google.com/rss/search?q={q}&hl=de&gl=DE&ceid=DE:de"
    response = requests.get(url, headers=HEADERS, timeout=8)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    rows = []
    for item in root.findall(".//item")[:limit]:
        title = _clean(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        if title and link:
            rows.append({
                "title": title,
                "document_title": title,
                "summary": _clean(item.findtext("description")),
                "url": link,
                "date": _date(item.findtext("pubDate")),
                "source": source,
                "source_type": "media",
            })
    return rows


def fetch_media_publications(per_source_limit: int = 40) -> dict:
    publications = []
    errors = {}
    for source, (domain, queries) in MEDIA_SOURCES.items():
        collected = []
        for query in queries:
            try:
                collected.extend(_fetch(source, domain, query))
            except Exception as exc:
                errors[source] = str(exc)
        seen = set()
        count = 0
        for row in collected:
            key = re.sub(r"\W+", "", row["title"].lower())[:180]
            if not key or key in seen:
                continue
            seen.add(key)
            publications.append(row)
            count += 1
            if count >= per_source_limit:
                break
    return {"publications": publications, "errors": errors, "fetched_at": datetime.now(timezone.utc).isoformat()}
