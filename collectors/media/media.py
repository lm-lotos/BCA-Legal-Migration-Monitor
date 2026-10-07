from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 BCA-Legal-Migration-Monitor/1.0"}

MEDIA_SOURCES = {
    # Federal / nationwide newsrooms
    "Tagesschau": ("tagesschau.de", ["Migration Deutschland", "Fachkräfte Einwanderung", "Aufenthaltsrecht Einbürgerung"]),
    "ZDFheute": ("zdf.de", ["Migration Deutschland", "Fachkräfte Deutschland", "Einbürgerung Aufenthaltsrecht"]),
    "Deutschlandfunk": ("deutschlandfunk.de", ["Migration Deutschland", "Fachkräfte Einwanderung", "Asyl Einbürgerung"]),
    "DW": ("dw.com", ["Migration Deutschland", "Aufenthaltsrecht Deutschland", "Einbürgerung Deutschland"]),
    "SPIEGEL": ("spiegel.de", ["Migration Deutschland", "Fachkräfte Einwanderung", "Asyl Einbürgerung"]),
    "ZEIT": ("zeit.de", ["Migration Deutschland", "Fachkräfte Einwanderung", "Aufenthaltsrecht Einbürgerung"]),
    "Süddeutsche": ("sueddeutsche.de", ["Migration Deutschland", "Fachkräfte Einwanderung", "Asyl Einbürgerung"]),
    "FAZ": ("faz.net", ["Migration Deutschland", "Fachkräfte Einwanderung", "Aufenthaltsrecht Einbürgerung"]),
    "Handelsblatt": ("handelsblatt.com", ["Fachkräfte Einwanderung", "Arbeitsmigration Deutschland", "Blue Card Deutschland"]),
    "WELT": ("welt.de", ["Migration Deutschland", "Fachkräfte Einwanderung", "Asyl Einbürgerung"]),
    "Tagesspiegel": ("tagesspiegel.de", ["Migration Deutschland", "Aufenthaltsrecht", "Einbürgerung"]),

    # Regional public-service coverage (the nine ARD Landesrundfunkanstalten)
    "WDR": ("wdr.de", ["Migration NRW", "Fachkräfte NRW", "Einbürgerung NRW"]),
    "NDR": ("ndr.de", ["Migration Norddeutschland", "Fachkräfte Norddeutschland", "Einbürgerung"]),
    "BR24": ("br.de", ["Migration Bayern", "Fachkräfte Bayern", "Einbürgerung Bayern"]),
    "SWR": ("swr.de", ["Migration Baden-Württemberg Rheinland-Pfalz", "Fachkräfte", "Einbürgerung"]),
    "MDR": ("mdr.de", ["Migration Sachsen Sachsen-Anhalt Thüringen", "Fachkräfte", "Einbürgerung"]),
    "rbb24": ("rbb24.de", ["Migration Berlin Brandenburg", "Ausländerbehörde Berlin", "Einbürgerung Berlin"]),
    "hr": ("hessenschau.de", ["Migration Hessen", "Fachkräfte Hessen", "Einbürgerung Hessen"]),
    "Radio Bremen": ("butenunbinnen.de", ["Migration Bremen", "Fachkräfte Bremen", "Einbürgerung Bremen"]),
    "SR": ("sr.de", ["Migration Saarland", "Fachkräfte Saarland", "Einbürgerung Saarland"]),
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
                "date_verified": True,
                "date_source": "google_news_rss",
                "source": source,
                "source_type": "media",
            })
    return rows


def fetch_media_publications(per_source_limit: int = 40) -> dict:
    """Fetch the same broad candidate set as before, but run RSS requests concurrently."""
    publications = []
    errors = {}

    jobs = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        for source, (domain, queries) in MEDIA_SOURCES.items():
            for query in queries:
                jobs.append((source, pool.submit(_fetch, source, domain, query)))

        by_source = {source: [] for source in MEDIA_SOURCES}
        for source, future in jobs:
            try:
                by_source[source].extend(future.result())
            except Exception as exc:
                errors[source] = str(exc)

    # Preserve the old per-source de-duplication and limits exactly.
    for source in MEDIA_SOURCES:
        seen = set()
        count = 0
        for row in by_source.get(source, []):
            key = re.sub(r"\W+", "", row["title"].lower())[:180]
            if not key or key in seen:
                continue
            seen.add(key)
            publications.append(row)
            count += 1
            if count >= per_source_limit:
                break

    return {"publications": publications, "errors": errors, "fetched_at": datetime.now(timezone.utc).isoformat()}
