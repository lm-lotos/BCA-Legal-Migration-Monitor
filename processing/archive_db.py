from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone

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
    c.execute("CREATE INDEX IF NOT EXISTS idx_pub_year ON publications(year)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pub_source ON publications(source)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pub_level ON publications(relevance_level)")
    c.commit()
    return c


def _year(item):
    import re
    raw = str(item.get("date") or item.get("_first_seen") or "")
    m = re.search(r"(?:19|20)\d{2}", raw)
    return m.group(0) if m else ""


def _id(item):
    raw = (item.get("url") or "") + "\n" + (item.get("title") or item.get("document_title") or "") + "\n" + (item.get("source") or "")
    return hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()


def upsert(items):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _conn() as c:
        for x in items or []:
            pid = _id(x)
            old = c.execute("SELECT first_seen FROM publications WHERE id=?", (pid,)).fetchone()
            first = old["first_seen"] if old else x.get("_first_seen") or now
            c.execute("""
                INSERT OR REPLACE INTO publications
                (id,url,title,document_title,source,source_group,date,year,summary,description,
                 topics_json,reasons_json,relevance_level,bca_score,first_seen,last_seen,raw_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                pid, x.get("url",""), x.get("title",""), x.get("document_title",""), x.get("source",""),
                x.get("source_group",""), str(x.get("date", "")), _year(x), x.get("summary",""), x.get("description",""),
                json.dumps(x.get("topics") or [], ensure_ascii=False), json.dumps(x.get("reasons") or [], ensure_ascii=False),
                x.get("relevance_level",""), int(x.get("bca_score",0) or 0), first, now, json.dumps(x, ensure_ascii=False, default=str)
            ))
        c.commit()


def all_rows():
    with _conn() as c:
        rows = c.execute("SELECT * FROM publications ORDER BY date DESC, last_seen DESC").fetchall()
    out=[]
    for r in rows:
        try: x=json.loads(r["raw_json"] or "{}")
        except Exception: x={}
        x.update({"url":r["url"],"title":r["title"],"document_title":r["document_title"],"source":r["source"],
                  "source_group":r["source_group"],"date":r["date"],"summary":r["summary"],"description":r["description"],
                  "topics":json.loads(r["topics_json"] or "[]"),"reasons":json.loads(r["reasons_json"] or "[]"),
                  "relevance_level":r["relevance_level"],"bca_score":r["bca_score"],"_first_seen":r["first_seen"],"_last_seen":r["last_seen"]})
        out.append(x)
    return out
