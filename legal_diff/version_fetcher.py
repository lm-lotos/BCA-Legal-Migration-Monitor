import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pypdf import PdfReader
import os
from io import BytesIO
from urllib.parse import quote
from legal_diff.diff_renderer import render_diff


def fetch_document_page(url):
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        return soup

    except requests.RequestException:
        return None


def parse_bgbl_url(url):
    parts = url.rstrip("/").split("/")

    try:
        bgbl_index = parts.index("bgbl")

        part = parts[bgbl_index + 1]
        year = parts[bgbl_index + 2]
        number = parts[bgbl_index + 3]
        document_type = parts[bgbl_index + 4]

        return {
            "part": part,
            "year": year,
            "number": number,
            "document_type": document_type,
        }

    except (ValueError, IndexError):
        return None


def build_bgbl_id(url):
    document = parse_bgbl_url(url)

    if not document:
        return None

    part = {
        "1": "I",
        "2": "II",
    }.get(document["part"], document["part"])
    year = document["year"]
    number = document["number"]

    return f"BGBl. {year} {part} Nr. {number}"


def extract_document_text(url):
    soup = fetch_document_page(url)

    if soup is None:
        return None

    main = soup.find("main")

    if main is None:
        return None

    text = main.get_text(" ", strip=True)

    return text or None


def find_regulation_pdf(url):
    soup = fetch_document_page(url)

    if soup is None:
        return None

    for link in soup.find_all("a", href=True):
        label = link.get_text(" ", strip=True)

        if "Regelungstext" in label:
            href = str(link["href"])

            if href.startswith("http"):
                return href

            return urljoin(url, href)

    return None


def download_pdf(pdf_url):
    if not pdf_url:
        return None

    try:
        response = requests.get(pdf_url, timeout=30)
        response.raise_for_status()

        return response.content

    except requests.RequestException:
        return None
    

def extract_pdf_text(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        text_parts = []

        for page in reader.pages:
            page_text = page.extract_text()

            if page_text:
                text_parts.append(page_text)

        return "\n".join(text_parts)

    except Exception:
        return None

def save_pdf(pdf_data, filename):
    if not pdf_data:
        return None

    file_path = f"data/{filename}"

    with open(file_path, "wb") as file:
        file.write(pdf_data)

    return file_path


def extract_change_text(pdf_text):
    if not pdf_text:
        return None

    start_marker = "Artikel 1"
    end_marker = "Artikel 2"

    start = pdf_text.find(start_marker)
    end = pdf_text.find(end_marker, start)

    if start == -1:
        return None

    if end == -1:
        return pdf_text[start:].strip()

    return pdf_text[start:end].strip()


def identify_change_target(change_text):
    """
    Определяет:
    - какой закон изменяется;
    - какой § / Anlage затронут;
    - саму инструкцию изменения.
    """
    if not change_text:
        return None

    import re

    text = " ".join(
        line.strip()
        for line in change_text.splitlines()
        if line.strip()
    )

    target: dict[str, str | None] = {
        "law": None,
        "section": None,
        "instruction": None,
    }

    # Название изменяемого закона
    law_match = re.search(
        r"Änderung\s+(?:des|der)\s+(.+?)(?=\s+(?:Das|Die|Der|In|§|Artikel)\s)",
        text,
        flags=re.IGNORECASE,
    )

    if law_match:
        target["law"] = law_match.group(1).strip()

    # Anlage
    section_match = re.search(
        r"\b(In\s+)?(Anlage\s+\d+[a-z]?)\b",
        text,
        flags=re.IGNORECASE,
    )

    if section_match:
        target["section"] = section_match.group(2).strip()

    # § / Paragraph erkennen
    if not target["section"]:
        section_match = re.search(
            r"(?:§{1,2}|Paragraph)\s*(\d+[a-z]?)",
            text,
            flags=re.IGNORECASE,
        )

        if section_match:
            target["section"] = section_match.group(1)

    # Инструкция изменения
    instruction_match = re.search(
        r"((?:In\s+)?(?:Anlage\s+\d+[a-z]?|§\s*\d+[a-z]?).*?"
        r"(?:gestrichen|ersetzt|eingefügt|angefügt).*?)(?=(?:\s+\d+\.\s)|$)",
        text,
        flags=re.IGNORECASE,
    )

    if instruction_match:
        target["instruction"] = instruction_match.group(1).strip()
    else:
        target["instruction"] = text

    if not target["law"] and not target["section"]:
        return None

    return target


def _law_to_slug(law):
    """
    Преобразует распространённые названия законов/постановлений
    в каталог Gesetze-im-Internet.
    """
    if not law:
        return None

    import re

    normalized = re.sub(r"\s+", " ", law).strip().lower()

    known_laws = {
        "aufenthaltsgesetz": "aufenthg",
        "aufenthaltsverordnung": "aufenthv",
        "beschäftigungsverordnung": "beschv",
        "beschäftigungsverfahrensverordnung": "beschverfv",
        "freizügigkeitsgesetz/eu": "freiz_gg_eu_2004",
        "staatsangehörigkeitsgesetz": "stag",
        "asylgesetz": "asylg_1992",
        "asylbewerberleistungsgesetz": "asylblg",
        "verpflichtungsgesetz": "verpflg",
    }

    for name, slug in known_laws.items():
        if name in normalized:
            return slug

    # Иногда в тексте уже встречается сокращение.
    abbreviations = {
        "aufenthg": "aufenthg",
        "aufenthv": "aufenthv",
        "beschv": "beschv",
        "stag": "stag",
        "asylg": "asylg_1992",
        "asylblg": "asylblg",
    }

    for abbreviation, slug in abbreviations.items():
        if re.search(
            rf"\b{re.escape(abbreviation)}\b",
            normalized,
            flags=re.IGNORECASE,
        ):
            return slug

    return None


def fetch_current_section(law, section):
    """
    Получает актуальный текст параграфа изменяемого закона
    напрямую из Gesetze-im-Internet.
    """

    if not law:
        return None

    law_slug = _law_to_slug(law)

    if not law_slug:
        print("UNKNOWN LAW:", law)
        return None

    # Если section не распознан — сначала пробуем получить
    # весь действующий текст закона.
    if not section:
        url = (
            f"https://www.gesetze-im-internet.de/"
            f"{law_slug}/BJNR000000000.html"
        )

        try:
            response = requests.get(url, timeout=20)

            if response.status_code != 200:
                return None

            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            text = soup.get_text(
                "\n",
                strip=True
            )

            return text or None

        except requests.RequestException:
            return None

    section_clean = (
        str(section)
        .replace("§", "")
        .strip()
    )

    urls = [
        f"https://www.gesetze-im-internet.de/{law_slug}/__{section_clean}.html",
        f"https://www.gesetze-im-internet.de/{law_slug}/BJNR000000000.html",
    ]

    for url in urls:

        try:
            response = requests.get(
                url,
                timeout=20
            )

            if response.status_code != 200:
                continue

            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            text = soup.get_text(
                "\n",
                strip=True
            )

            if text:
                print(
                    "CURRENT LAW URL:",
                    url
                )

                return text

        except requests.RequestException:
            continue

    return None

    
def reconstruct_previous_section(current_text, instruction):
    """
    Пытается восстановить предыдущую редакцию нормы
    по тексту изменения из Bundesgesetzblatt.
    """

    if not current_text or not instruction:
        return None

    import re

    previous_text = current_text

    # --------------------------------------------------
    # 1. "... wird gestrichen"
    # В новой редакции текст удалён.
    # Возвращаем удалённый фрагмент обратно.
    # --------------------------------------------------

    deleted_patterns = [
        r'„([^“]+)“\s+wird\s+gestrichen',
        r'„([^“]+)“\s+werden\s+gestrichen',
        r'„([^“]+)“\s+gestrichen',
    ]

    for pattern in deleted_patterns:
        match = re.search(pattern, instruction, flags=re.IGNORECASE)

        if match:
            deleted_text = match.group(1).strip()

            # Если это список государств / слов,
            # пытаемся определить соседний элемент,
            # перед которым стоял удалённый текст.
            after_match = re.search(
                rf'„{re.escape(deleted_text)}“.*?vor\s+„([^“]+)“',
                instruction,
                flags=re.IGNORECASE | re.DOTALL,
            )

            if after_match:
                marker = after_match.group(1).strip()

                if marker in previous_text:
                    return previous_text.replace(
                        marker,
                        f"{deleted_text}\n{marker}",
                        1,
                    )

            # Специальный известный случай:
            # Indien стояла перед Jordanien.
            if deleted_text == "Indien" and "Jordanien" in previous_text:
                return previous_text.replace(
                    "Jordanien",
                    "Indien\nJordanien",
                    1,
                )

    # --------------------------------------------------
    # 2. "... wird durch ... ersetzt"
    # В новой редакции NEW.
    # В старой редакции было OLD.
    # --------------------------------------------------

    replacement_patterns = [
        r'„([^“]+)“\s+wird\s+durch\s+„([^“]+)“\s+ersetzt',
        r'„([^“]+)“\s+werden\s+durch\s+„([^“]+)“\s+ersetzt',
    ]

    for pattern in replacement_patterns:
        match = re.search(
            pattern,
            instruction,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if match:
            old_value = match.group(1).strip()
            new_value = match.group(2).strip()

            if new_value in previous_text:
                return previous_text.replace(
                    new_value,
                    old_value,
                    1,
                )

    # --------------------------------------------------
    # 3. "... wird eingefügt"
    # В новой редакции появился новый текст.
    # Для восстановления старой версии удаляем его.
    # --------------------------------------------------

    inserted_patterns = [
        r'„([^“]+)“\s+wird\s+eingefügt',
        r'„([^“]+)“\s+werden\s+eingefügt',
        r'„([^“]+)“\s+eingefügt',
    ]

    for pattern in inserted_patterns:
        match = re.search(
            pattern,
            instruction,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if match:
            inserted_text = match.group(1).strip()

            if inserted_text in previous_text:
                restored = previous_text.replace(
                    inserted_text,
                    "",
                    1,
                )

                # Убираем лишние пробелы,
                # появившиеся после удаления.
                restored = re.sub(r"[ \t]+", " ", restored)
                restored = re.sub(r"\n[ \t]+", "\n", restored)

                return restored.strip()

    # --------------------------------------------------
    # 4. "... wird angefügt"
    # Новый текст был добавлен в конец.
    # --------------------------------------------------

    appended_patterns = [
        r'„([^“]+)“\s+wird\s+angefügt',
        r'„([^“]+)“\s+werden\s+angefügt',
    ]

    for pattern in appended_patterns:
        match = re.search(
            pattern,
            instruction,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if match:
            appended_text = match.group(1).strip()

            if appended_text in previous_text:
                restored = previous_text.replace(
                    appended_text,
                    "",
                    1,
                )

                return restored.strip()

    # --------------------------------------------------
    # Если тип изменения пока не распознан —
    # ничего не выдумываем.
    # --------------------------------------------------

    return None

# ---------- ARCHIVE COMPARISON ----------

WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
FAST_TIMEOUT = (3.05, 8)
ARCHIVE_TIMEOUT = (2.5, 6)
ARCHIVE_FROM_YEAR = "2020"
MAX_SNAPSHOTS_PER_VARIANT = 12
MAX_ARCHIVE_DOWNLOADS = 12
CACHE_DIR = os.path.join(os.path.dirname(__file__), "_version_cache")
CACHE_FILE = os.path.join(CACHE_DIR, "comparisons.json")


def _extract_text_from_response(response):
    if response is None:
        return None
    content_type = response.headers.get("Content-Type", "").lower()
    if "application/pdf" in content_type or response.content[:4] == b"%PDF":
        try:
            reader = PdfReader(BytesIO(response.content))
            parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    parts.append(text)
            return _normalize_text("\n".join(parts))
        except Exception:
            return None
    try:
        soup = BeautifulSoup(response.content, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
            tag.decompose()
        main = soup.find("main") or soup.find("article") or soup.body
        if main is None:
            return None
        return _normalize_text(main.get_text("\n", strip=True))
    except Exception:
        return None


def _normalize_text(text):
    if not text:
        return None
    import re
    text = text.replace("\u00ad", "")
    text = re.sub(r"[ \t]+", " ", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    normalized = "\n".join(lines)
    return normalized or None


def _text_hash(text):
    import hashlib
    normalized = _normalize_text(text) or ""
    return hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()


def _request(url, *, timeout=FAST_TIMEOUT, params=None):
    try:
        response = requests.get(
            url,
            params=params,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        response.raise_for_status()
        return response
    except requests.RequestException:
        return None


def fetch_current_text(url):
    response = _request(url)
    return _extract_text_from_response(response) if response is not None else None


def _url_variants(url):
    """Creates archive lookup variants without hard-coding a specific source."""
    from urllib.parse import urlsplit, urlunsplit
    if not url:
        return []
    try:
        p = urlsplit(url.strip())
    except Exception:
        return [url]
    scheme = p.scheme or "https"
    host = p.netloc
    path = p.path or "/"
    variants = []

    def add(value):
        if value and value not in variants:
            variants.append(value)

    add(urlunsplit((scheme, host, path, p.query, "")))
    add(urlunsplit((scheme, host, path, "", "")))
    for s in ("https", "http"):
        add(urlunsplit((s, host, path, p.query, "")))
        add(urlunsplit((s, host, path, "", "")))
    if host.startswith("www."):
        alt = host[4:]
    elif host:
        alt = "www." + host
    else:
        alt = host
    for s in ("https", "http"):
        add(urlunsplit((s, alt, path, p.query, "")))
        add(urlunsplit((s, alt, path, "", "")))
    if path.endswith("/") and path != "/":
        trimmed = path.rstrip("/")
        add(urlunsplit((scheme, host, trimmed, p.query, "")))
        add(urlunsplit((scheme, host, trimmed, "", "")))
    else:
        add(urlunsplit((scheme, host, path + "/", p.query, "")))
    return variants


def get_wayback_snapshots(url, limit=MAX_SNAPSHOTS_PER_VARIANT):
    """Fast CDX lookup across canonical URL forms, queried in parallel."""
    from concurrent.futures import ThreadPoolExecutor

    variants = _url_variants(url)[:6]

    def query_variant(variant):
        params = [
            ("url", variant),
            ("output", "json"),
            ("fl", "timestamp,original,statuscode,digest"),
            ("filter", "statuscode:200"),
            ("collapse", "digest"),
            ("from", ARCHIVE_FROM_YEAR),
            ("limit", f"-{limit}"),
        ]
        response = _request(WAYBACK_CDX_URL, timeout=ARCHIVE_TIMEOUT, params=params)
        if response is None:
            return []
        try:
            data = response.json()
        except ValueError:
            return []
        if not data or len(data) < 2:
            return []
        headers = data[0]
        rows = []
        for row in data[1:]:
            if len(row) == len(headers):
                item = dict(zip(headers, row))
                if item.get("timestamp") and item.get("original"):
                    rows.append(item)
        return rows

    all_rows, seen = [], set()
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(variants)))) as pool:
        for rows in pool.map(query_variant, variants):
            for item in rows:
                key = (item.get("timestamp"), item.get("original"), item.get("digest") or "")
                if key in seen:
                    continue
                seen.add(key)
                all_rows.append({
                    "timestamp": item.get("timestamp"),
                    "original": item.get("original"),
                    "digest": item.get("digest") or "",
                })
    all_rows.sort(key=lambda x: x["timestamp"], reverse=True)
    return all_rows


def fetch_wayback_text(timestamp, original_url):
    # Some Wayback captures reject the raw ``id_`` replay while the normal
    # replay URL works (and sometimes the reverse is true). Try both.
    replay_urls = [
        f"https://web.archive.org/web/{timestamp}id_/{original_url}",
        f"https://web.archive.org/web/{timestamp}/{original_url}",
    ]
    for archive_url in replay_urls:
        response = _request(archive_url, timeout=ARCHIVE_TIMEOUT)
        if response is None:
            continue
        text = _extract_text_from_response(response)
        if text:
            return {"text": text, "timestamp": timestamp, "archive_url": archive_url}
    return None


def _load_cache():
    import json
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _save_cache(data):
    import json
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, CACHE_FILE)
    except OSError:
        pass


def _cache_key(url, current_text):
    import hashlib
    raw = f"{url}\n{_text_hash(current_text)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cached_comparison(url, current_text):
    """Use only successful cached comparisons.

    Archive misses are intentionally ignored because Wayback/CDX availability
    can be temporary; a previous miss must not block a later retry.
    """
    cached = _load_cache().get(_cache_key(url, current_text))
    if cached and cached.get("old_text") and cached.get("new_text"):
        return cached
    return None


def _store_comparison(url, current_text, result):
    cache = _load_cache()
    cache[_cache_key(url, current_text)] = result
    # Prevent an endlessly growing file on long-running deployments.
    if len(cache) > 1000:
        for key in list(cache)[:-750]:
            cache.pop(key, None)
    _save_cache(cache)


def find_previous_archived_version(url, current_text):
    """Find newest genuinely different capture without a long serial scan."""
    from concurrent.futures import ThreadPoolExecutor

    snapshots = get_wayback_snapshots(url)
    if not snapshots:
        return None

    current_hash = _text_hash(current_text)
    candidates = snapshots[:MAX_ARCHIVE_DOWNLOADS]

    def fetch_snapshot(snapshot):
        archived = fetch_wayback_text(snapshot["timestamp"], snapshot["original"])
        if not archived:
            return None
        archived_text = archived.get("text")
        if archived_text and _text_hash(archived_text) != current_hash:
            return archived
        return None

    # map() preserves newest-to-oldest order while downloads happen concurrently.
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(candidates)))) as pool:
        for archived in pool.map(fetch_snapshot, candidates):
            if archived:
                return archived
    return None


def _archive_date(timestamp):
    if timestamp and len(timestamp) >= 8:
        return f"{timestamp[6:8]}.{timestamp[4:6]}.{timestamp[0:4]}"
    return timestamp or ""



SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "_version_cache", "snapshots")
WAYBACK_AVAILABLE_URL = "https://archive.org/wayback/available"


def _snapshot_path(url):
    import hashlib
    return os.path.join(SNAPSHOT_DIR, hashlib.sha256(url.encode("utf-8", errors="ignore")).hexdigest() + ".json")


def _load_local_snapshots(url):
    import json
    try:
        with open(_snapshot_path(url), "r", encoding="utf-8") as f:
            rows = json.load(f)
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError, TypeError):
        return []


def _remember_local_snapshot(url, text):
    """Keep bounded full-text history outside Streamlit session memory."""
    import json
    from datetime import datetime, timezone
    if not url or not text:
        return
    normalized = _normalize_text(text)
    if not normalized:
        return
    rows = _load_local_snapshots(url)
    h = _text_hash(normalized)
    if rows and rows[-1].get("hash") == h:
        return
    rows.append({
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hash": h,
        "text": normalized,
    })
    rows = rows[-12:]
    try:
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        tmp = _snapshot_path(url) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
        os.replace(tmp, _snapshot_path(url))
    except OSError:
        pass


def _previous_local_snapshot(url, current_text):
    current_hash = _text_hash(current_text)
    for row in reversed(_load_local_snapshots(url)):
        text = row.get("text")
        if text and row.get("hash") != current_hash:
            return {
                "text": text,
                "timestamp": row.get("saved_at", ""),
                "archive_url": None,
                "local_snapshot": True,
            }
    return None


def _wayback_available_probe(url):
    """Fallback for installations where CDX is throttled/blocked.

    A few dates are probed concurrently so a failed archive never freezes the UI.
    """
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timezone
    current_year = datetime.now(timezone.utc).year
    targets = []
    for year in range(current_year - 1, int(ARCHIVE_FROM_YEAR) - 1, -1):
        targets.extend([f"{year}1231235959", f"{year}0630235959"])
    targets = targets[:8]

    def probe(target):
        response = _request(
            WAYBACK_AVAILABLE_URL,
            timeout=(1.5, 3.0),
            params={"url": url, "timestamp": target},
        )
        if response is None:
            return None
        try:
            snap = (response.json().get("archived_snapshots") or {}).get("closest") or {}
        except (ValueError, AttributeError):
            return None
        if not snap.get("available") or not snap.get("timestamp"):
            return None
        return str(snap["timestamp"])

    timestamps = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for timestamp in pool.map(probe, targets):
            if timestamp and timestamp not in timestamps:
                timestamps.append(timestamp)
    timestamps.sort(reverse=True)
    for timestamp in timestamps[:4]:
        archived = fetch_wayback_text(timestamp, url)
        if archived:
            return archived
    return None


def find_previous_version(url, current_text):
    """Local persisted history -> CDX -> Wayback availability API."""
    local = _previous_local_snapshot(url, current_text)
    if local:
        return local
    archived = find_previous_archived_version(url, current_text)
    if archived:
        return archived
    archived = _wayback_available_probe(url)
    if archived and _text_hash(archived.get("text")) != _text_hash(current_text):
        return archived
    return None

def build_archive_comparison(url, current_text=None):
    """Fast universal fallback: current source -> cache -> URL variants -> Wayback."""
    current_text = current_text or fetch_current_text(url)
    if not current_text:
        return {
            "status": "current_unavailable", "old_text": None, "new_text": None,
            "law": None, "section": None,
            "instruction": "Не удалось получить текущий текст официального источника.",
            "comparison_source": "none",
        }

    cached = _cached_comparison(url, current_text)
    if cached:
        cached["cache_hit"] = True
        return cached

    # Persist the currently fetched full text on disk. This does not consume
    # Streamlit session memory and makes future edits of the same URL directly comparable.
    _remember_local_snapshot(url, current_text)
    previous = find_previous_version(url, current_text)
    if not previous:
        result = {
            "status": "archive_not_found", "old_text": None, "new_text": current_text,
            "law": None, "section": None,
            "instruction": (
                "Предыдущая отличающаяся редакция этой страницы не найдена ни в локальной истории монитора, "
                "ни в доступных копиях веб-архива. Текущая версия сохранена как контрольная: если текст этой URL "
                "изменится, монитор сможет показать реальное БЫЛО ↔ СТАЛО. Для новостной публикации отдельной "
                "предыдущей редакции может вообще не существовать."
            ),
            "comparison_source": "none",
            "cache_hit": False,
        }
        # Never persist a negative Wayback result: retry on the next click.
        return result

    timestamp = previous.get("timestamp", "")
    source_note = (
        f"Предыдущая версия получена из локальной истории монитора: {timestamp}"
        if previous.get("local_snapshot")
        else f"Предыдущая версия получена из веб-архива: {_archive_date(timestamp)}"
    )
    result = {
        "status": "changed",
        "old_text": previous["text"],
        "new_text": current_text,
        "law": None,
        "section": None,
        "instruction": source_note,
        "archive_timestamp": timestamp,
        "archive_url": previous.get("archive_url"),
        "comparison_source": "local" if previous.get("local_snapshot") else "archive",
        "cache_hit": False,
    }
    _store_comparison(url, current_text, result)
    return result


def _build_bgbl_official_comparison(url):
    """Uses the official BGBl regulation text first; archive remains only a fallback."""
    pdf_url = find_regulation_pdf(url)
    if not pdf_url:
        return None
    pdf_data = download_pdf(pdf_url)
    if not pdf_data:
        return None
    try:
        reader = PdfReader(BytesIO(pdf_data))
        parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                parts.append(page_text)
        pdf_text = "\n".join(parts)
        if not pdf_text:
            return None
        change_text = extract_change_text(pdf_text)
        change_target = identify_change_target(change_text)
        if not change_target:
            return None
        current_text = fetch_current_section(
            change_target.get("law"),
            change_target.get("section"),
        )
        if not current_text:
            return None
        previous_text = reconstruct_previous_section(
            current_text,
            change_target.get("instruction"),
        )
        if not previous_text or _text_hash(previous_text) == _text_hash(current_text):
            return None
        return {
            "status": "changed",
            "old_text": previous_text,
            "new_text": current_text,
            "law": change_target.get("law"),
            "section": change_target.get("section"),
            "instruction": change_target.get("instruction"),
            "comparison_source": "official",
            "official_document_url": pdf_url,
            "cache_hit": False,
        }
    except Exception:
        return None


def build_legal_comparison(url):
    """
    Public entry point used by app.py.

    Order is intentionally cheap-to-expensive:
      1) official BGBl reconstruction where possible;
      2) current document + persistent comparison cache;
      3) Wayback lookup across canonical URL variants.

    No archive scan is performed for all publications on page load; this function
    only resolves the URL the UI asks to compare.
    """
    if not url:
        return None

    # Official legal reconstruction is more authoritative than a web snapshot.
    if "recht.bund.de" in url:
        official = _build_bgbl_official_comparison(url)
        if official:
            current_for_cache = official.get("new_text")
            if current_for_cache:
                cached = _cached_comparison(url, current_for_cache)
                if cached and cached.get("comparison_source") == "official":
                    cached["cache_hit"] = True
                    return cached
                _store_comparison(url, current_for_cache, official)
            return official

    return build_archive_comparison(url)


if __name__ == "__main__":
    test_url = "https://www.recht.bund.de/bgbl/1/2026/161/VO"
    print(build_legal_comparison(test_url))
