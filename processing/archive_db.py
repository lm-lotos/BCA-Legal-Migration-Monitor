from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "bca_archive.db")


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("""
        CREATE TABLE IF NOT EXISTS publications (
            id TEXT PRIMARY KEY,
            url TEXT, title TEXT, document_title TEXT, source TEXT, source_group TEXT,
            date TEXT, year TEXT, summary TEXT, description TEXT,
            topics_json TEXT, reasons_json TEXT, relevance_level TEXT, bca_score INTEGER,
            first_seen TEXT, last_seen TEXT, raw_json TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS source_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            checked_at TEXT NOT NULL,
            status TEXT NOT NULL,
            items_found INTEGER NOT NULL DEFAULT 0,
            error TEXT DEFAULT ''
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_pub_year ON publications(year)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pub_source ON publications(source)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pub_level ON publications(relevance_level)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_checks_source_time ON source_checks(source, checked_at DESC)")
    c.commit()
    return c


def _year(item):
    import re
    raw = str(item.get("date") or "")
    m = re.search(r"(?:19|20)\d{2}", raw)
    return m.group(0) if m else ""


def _id(item):
    # URL is the strongest identity. Title/source are fallback for URL-less rows.
    url = str(item.get("url") or "").strip()
    if url:
        raw = url
    else:
        raw = (item.get("title") or item.get("document_title") or "") + "\n" + (item.get("source") or "")
    return hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()


def upsert(items):
    """Remember publications without erasing their first-seen timestamp."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _conn() as c:
        for x in items or []:
            pid = _id(x)
            old = c.execute("SELECT first_seen FROM publications WHERE id=?", (pid,)).fetchone()
            first = old["first_seen"] if old else x.get("_first_seen") or now
            payload = dict(x)
            payload.pop("_publication_dt", None)
            c.execute("""
                INSERT OR REPLACE INTO publications
                (id,url,title,document_title,source,source_group,date,year,summary,description,
                 topics_json,reasons_json,relevance_level,bca_score,first_seen,last_seen,raw_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                pid, x.get("url", ""), x.get("title", ""), x.get("document_title", ""), x.get("source", ""),
                x.get("source_group", ""), str(x.get("date", "")), _year(x), x.get("summary", ""), x.get("description", ""),
                json.dumps(x.get("topics") or [], ensure_ascii=False), json.dumps(x.get("reasons") or [], ensure_ascii=False),
                x.get("relevance_level", ""), int(x.get("bca_score", 0) or 0), first, now,
                json.dumps(payload, ensure_ascii=False, default=str)
            ))
        c.commit()


def record_source_check(source, status, items_found=0, error=""):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _conn() as c:
        c.execute(
            "INSERT INTO source_checks(source,checked_at,status,items_found,error) VALUES (?,?,?,?,?)",
            (str(source), now, str(status), int(items_found or 0), str(error or "")[:1000]),
        )
        c.commit()


def latest_source_checks():
    """Return the latest technical check for each source."""
    with _conn() as c:
        rows = c.execute("""
            SELECT sc.source, sc.checked_at, sc.status, sc.items_found, sc.error
            FROM source_checks sc
            JOIN (
                SELECT source, MAX(id) AS max_id
                FROM source_checks GROUP BY source
            ) latest ON latest.max_id = sc.id
            ORDER BY sc.source
        """).fetchall()
    return [dict(r) for r in rows]


def prune_source_checks(days=30):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    with _conn() as c:
        c.execute("DELETE FROM source_checks WHERE checked_at < ?", (cutoff,))
        c.commit()


def all_rows():
    with _conn() as c:
        rows = c.execute("SELECT * FROM publications ORDER BY date DESC, last_seen DESC").fetchall()
    out = []
    for r in rows:
        try:
            x = json.loads(r["raw_json"] or "{}")
        except Exception:
            x = {}
        x.update({
            "url": r["url"], "title": r["title"], "document_title": r["document_title"], "source": r["source"],
            "source_group": r["source_group"], "date": r["date"], "summary": r["summary"], "description": r["description"],
            "topics": json.loads(r["topics_json"] or "[]"), "reasons": json.loads(r["reasons_json"] or "[]"),
            "relevance_level": r["relevance_level"], "bca_score": r["bca_score"],
            "_first_seen": r["first_seen"], "_last_seen": r["last_seen"],
        })
        out.append(x)
    return out
