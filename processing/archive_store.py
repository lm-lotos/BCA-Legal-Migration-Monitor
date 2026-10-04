from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

STORE = Path("data") / "publication_archive.json"


def _key(item: dict) -> str:
    raw = f"{item.get('source','')}|{item.get('url','')}|{item.get('title', item.get('document_title',''))}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:24]


def load_archive() -> list[dict]:
    try:
        if not STORE.exists():
            return []
        data = json.loads(STORE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def merge_archive(items: list[dict]) -> list[dict]:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    old = {_key(x): x for x in load_archive()}
    now = datetime.now(timezone.utc).isoformat()
    for item in items:
        row = dict(item)
        key = _key(row)
        row["_first_seen"] = old.get(key, {}).get("_first_seen", now)
        row["_last_seen"] = now
        old[key] = row
    rows = list(old.values())
    rows.sort(key=lambda x: str(x.get("date") or x.get("_first_seen") or ""), reverse=True)
    try:
        STORE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return rows
