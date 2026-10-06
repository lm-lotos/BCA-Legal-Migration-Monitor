from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 BCA-Legal-Migration-Monitor/1.1"}

DATE_KEYS = (
    "article:published_time", "date", "datepublished", "datePublished",
    "publishdate", "pubdate", "publication_date", "dc.date", "dcterms.date",
)


def parse_date(value):
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d. %B %Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat() if dt else ""


def _from_jsonld(soup):
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            obj = json.loads(tag.string or tag.get_text() or "{}")
        except Exception:
            continue
        stack = obj if isinstance(obj, list) else [obj]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for key in ("datePublished", "dateCreated"):
                    dt = parse_date(node.get(key))
                    if dt:
                        return dt, f"jsonld:{key}"
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
            elif isinstance(node, list):
                stack.extend(node)
    return None, ""


def extract_page_date(url: str, timeout: int = 8):
    if not url or not str(url).startswith("http"):
        return None, ""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
    except Exception:
        return None, ""

    soup = BeautifulSoup(r.text, "html.parser")

    # Structured metadata first.
    for meta in soup.find_all("meta"):
        key = (meta.get("property") or meta.get("name") or meta.get("itemprop") or "").strip()
        content = (meta.get("content") or "").strip()
        if key and content and key.lower() in {k.lower() for k in DATE_KEYS}:
            dt = parse_date(content)
            if dt:
                return dt, f"meta:{key}"

    dt, source = _from_jsonld(soup)
    if dt:
        return dt, source

    for tag in soup.find_all("time"):
        dt = parse_date(tag.get("datetime") or tag.get_text(" ", strip=True))
        if dt:
            return dt, "time"

    # German government pages frequently expose a visible publication date.
    text = " ".join(soup.stripped_strings)
    patterns = [
        r"(?:Datum|Ausfertigungsdatum|Stand|Veröffentlicht(?:\s+am)?|Veröffentlichung|Publikationsdatum)\s*[:\-]?\s*(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})",
        r"(?:Datum|Ausfertigungsdatum|Stand|Veröffentlicht(?:\s+am)?|Veröffentlichung|Publikationsdatum)\s*[:\-]?\s*(\d{1,2}\.\s*(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+\d{4})",
    ]
    months = {"Januar":1,"Februar":2,"März":3,"April":4,"Mai":5,"Juni":6,"Juli":7,"August":8,"September":9,"Oktober":10,"November":11,"Dezember":12}
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        raw = re.sub(r"\s+", " ", m.group(1)).strip()
        mnum = re.match(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", raw)
        if mnum:
            return datetime(int(mnum.group(3)), int(mnum.group(2)), int(mnum.group(1)), tzinfo=timezone.utc), "visible-date"
        mword = re.match(r"(\d{1,2})\.\s*([A-Za-zÄÖÜäöüß]+)\s+(\d{4})", raw)
        if mword:
            month = next((v for k,v in months.items() if k.lower() == mword.group(2).lower()), None)
            if month:
                return datetime(int(mword.group(3)), month, int(mword.group(1)), tzinfo=timezone.utc), "visible-date"
    return None, ""


def enrich_publication_date(item: dict) -> dict:
    x = dict(item)

    # Trusted feed dates: Bundestag and Google News RSS are publication timestamps.
    if x.get("date_verified") and parse_date(x.get("date")):
        return x

    dt, source = extract_page_date(str(x.get("url") or ""))
    if dt:
        x["date"] = _iso(dt)
        x["date_verified"] = True
        x["date_source"] = source
        return x

    # If collector explicitly marks its feed timestamp as trustworthy, keep it.
    if x.get("date_source") in {"bundestag_rss", "federal_rss", "google_news_rss"}:
        dt = parse_date(x.get("date"))
        if dt:
            x["date"] = _iso(dt)
            x["date_verified"] = True
            return x

    x["date_verified"] = False
    return x
