from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
import time
import streamlit as st

from collectors.official.gesetze_rss import fetch_updates
from collectors.official.lea_berlin import get_lea_publications
from collectors.official.bamf import fetch_bamf_publications
from collectors.official.arbeitsagentur import fetch_ba_publications
from collectors.official.ba_weisungen import fetch_ba_weisungen
from collectors.official.bundestag import fetch_bundestag_publications
from collectors.official.federal_sources import fetch_federal_publications
from collectors.media.media import fetch_media_publications, MEDIA_SOURCES
from processing.translator import translate_text
from processing.relevance import filter_relevant, light, counts
from processing.archive_store import merge_archive
from processing.archive_db import (
    upsert as db_upsert, all_rows as db_all_rows,
    record_source_check, latest_source_checks, prune_source_checks,
)
from processing.publication_dates import enrich_publication_date
from legal_diff.diff_renderer import render_diff, DIFF_CSS
from legal_diff.version_fetcher import build_legal_comparison

st.set_page_config(page_title="BCA Legal & Migration Monitor", page_icon="🌍", layout="wide")

st.markdown("""
<style>
.block-container {max-width:100% !important;padding:2.35rem 1.25rem 2rem !important;}
[data-testid="stAppViewContainer"] .main {max-width:100% !important;}
[data-testid="stVerticalBlock"] {gap:.45rem;}
div[data-testid="stButton"] button {min-height:2.25rem;padding:.25rem .55rem;}
/* Selected source/relevance buttons: neutral grey, no checkmarks. */
div[data-testid="stButton"] button[kind="primary"] {
    background:#e9ecef !important; color:#1f2937 !important;
    border-color:#b8bec6 !important; box-shadow:inset 0 0 0 1px #b8bec6 !important;
}
div[data-testid="stButton"] button[kind="primary"] p {color:#1f2937 !important;}
/* Search relevance chips must stay neutral instead of Streamlit accent red. */
[data-baseweb="tag"] {background:#e9ecef !important;color:#1f2937 !important;}
[data-baseweb="tag"] span, [data-baseweb="tag"] svg {color:#1f2937 !important;fill:#1f2937 !important;}
.translator-spacer {height:1.7rem;}
.small-note {font-size:.82rem;color:#777;margin-top:-.25rem;}
</style>
""", unsafe_allow_html=True)

LANGUAGES = {
    "🇩🇪 Deutsch": "de", "🇬🇧 English": "en", "🇷🇺 Русский": "ru",
    "🇺🇦 Українська": "uk", "🌐 العربية": "ar",
}


def safe_call(fn, fallback):
    try:
        return fn()
    except Exception:
        return fallback


# ---------- FAST START + MANUAL REFRESH ----------

def _publication_dt(value):
    """Parse the publication's own date. Unknown/invalid dates are not treated as fresh."""
    if not value:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    # RFC / RSS dates, e.g. Tue, 06 Oct 2026 09:30:00 +0200
    try:
        dt = parsedate_to_datetime(raw)
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # ISO dates/timestamps.
    try:
        iso = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # Common German / European date forms.
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw[:19], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass

    # Do not use _first_seen as a substitute: an old article discovered today is still old.
    return None


def _fresh_rows(rows, hours=48):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    fresh = []

    for item in rows or []:
        x = dict(item)
        if not x.get("date_verified"):
            continue
        dt = _publication_dt(x.get("date"))
        if dt is None or dt < cutoff or dt > now + timedelta(hours=2):
            continue
        x["_publication_dt"] = dt
        fresh.append(x)

    # Primary rule from the brief: newest first.
    # BCA score is only a quiet tie-breaker and is not exposed as "relevance".
    fresh.sort(
        key=lambda x: (
            x.get("_publication_dt") or datetime.min.replace(tzinfo=timezone.utc),
            float(x.get("bca_score") or 0),
        ),
        reverse=True,
    )
    return fresh


def load_saved_data():
    """Fast start: show one fresh feed (max. 48h) from all stored sources."""
    stored = db_all_rows() or []
    fresh = _fresh_rows(stored, hours=48)

    official = [x for x in fresh if x.get("source_group") == "official"]
    media = [x for x in fresh if x.get("source_group") == "media"]

    return {
        "official": official,
        "media": media,
        "all": fresh,
        "media_errors": {},
    }

def refresh_data():
    """Poll sources, remember new hits, then rebuild the 48h feed from SQLite memory."""
    total_started = time.perf_counter()
    print("\n" + "=" * 72)
    print("[REFRESH] START")
    print("=" * 72, flush=True)

    def collect(name, fn, fallback):
        started = time.perf_counter()
        try:
            value = fn()
            if isinstance(value, dict):
                n = len(value.get("publications", value.get("all_publications", [])) or [])
            else:
                n = len(value or [])
            record_source_check(name, "ok", n, "")
            print(f"[SOURCE] {name:<28} {time.perf_counter()-started:7.2f}s | found: {n}", flush=True)
            return value
        except Exception as exc:
            record_source_check(name, "error", 0, str(exc))
            print(f"[ERROR ] {name:<28} {time.perf_counter()-started:7.2f}s | {exc}", flush=True)
            return fallback

    laws = collect("Gesetze im Internet", fetch_updates, {"all_publications": [], "results": []})
    raw_official = list(laws.get("all_publications", []))
    richer = {x.get("url"): x for x in laws.get("results", []) if x.get("url")}
    raw_official = [{**x, **richer.get(x.get("url"), {})} for x in raw_official]

    official_collectors = [
        ("LEA Berlin", get_lea_publications),
        ("BAMF", fetch_bamf_publications),
        ("Bundesagentur für Arbeit", fetch_ba_publications),
        ("BA Weisungen", fetch_ba_weisungen),
        ("Bundestag", fetch_bundestag_publications),
        ("Federal sources", fetch_federal_publications),
    ]
    for name, fn in official_collectors:
        raw_official += list(collect(name, fn, []) or [])

    media_started = time.perf_counter()
    try:
        media_result = fetch_media_publications()
        media_rows = list(media_result.get("publications", []) or [])
        media_errors = dict(media_result.get("errors", {}) or {})
        by_source = {}
        for row in media_rows:
            by_source[row.get("source") or "Media"] = by_source.get(row.get("source") or "Media", 0) + 1
        for source in MEDIA_SOURCES.keys():
            if source in media_errors:
                record_source_check(source, "error", by_source.get(source, 0), media_errors[source])
            else:
                record_source_check(source, "ok", by_source.get(source, 0), "")
        print(f"[SOURCE] {'Media total':<28} {time.perf_counter()-media_started:7.2f}s | found: {len(media_rows)}", flush=True)
    except Exception as exc:
        media_rows, media_errors = [], {"Media": str(exc)}
        for source in MEDIA_SOURCES.keys():
            record_source_check(source, "error", 0, str(exc))
        print(f"[ERROR ] {'Media total':<28} {time.perf_counter()-media_started:7.2f}s | {exc}", flush=True)

    relevance_started = time.perf_counter()
    official = filter_relevant(raw_official)
    media = filter_relevant(media_rows)
    print(f"[STEP  ] {'Relevance filtering':<28} {time.perf_counter()-relevance_started:7.2f}s | official: {len(official)}, media: {len(media)}", flush=True)

    dates_started = time.perf_counter()
    # Keep the exact same candidate set, but verify independent pages concurrently.
    # executor.map preserves input order, so UI/result semantics stay unchanged.
    with ThreadPoolExecutor(max_workers=16) as pool:
        official = list(pool.map(enrich_publication_date, official))
        media = list(pool.map(enrich_publication_date, media))
    print(f"[STEP  ] {'Date verification':<28} {time.perf_counter()-dates_started:7.2f}s | items: {len(official)+len(media)}", flush=True)
    for x in official:
        x["source_group"] = "official"
    for x in media:
        x["source_group"] = "media"

    db_started = time.perf_counter()
    verified = [x for x in official + media if x.get("date_verified") and _publication_dt(x.get("date"))]
    db_upsert(verified)
    prune_source_checks(days=30)
    data = load_saved_data()
    data["media_errors"] = media_errors
    print(f"[STEP  ] {'DB save + rebuild':<28} {time.perf_counter()-db_started:7.2f}s | verified: {len(verified)}, fresh: {len(data['all'])}", flush=True)
    print(f"[REFRESH] TOTAL {time.perf_counter()-total_started:.2f}s", flush=True)
    print("=" * 72 + "\n", flush=True)
    return data


# При обычном открытии приложения НИКУДА в интернет не идём.
data = load_saved_data()

official = data["official"]
media = data["media"]
everything = data["all"]

for key, value in {"source_filter": "ALL", "limit": 10, "stats_source": None}.items():
    if key not in st.session_state:
        st.session_state[key] = value


def reset_limit():
    st.session_state.limit = 10


def choose_source(value):
    st.session_state.source_filter = value
    reset_limit()


def source_ok(x):
    f = st.session_state.source_filter
    if f == "ALL": return True
    if f == "OFFICIAL_ALL": return x.get("source_group") == "official"
    if f == "MEDIA_ALL": return x.get("source_group") == "media"
    if f == "BA": return x.get("source") in {"Bundesagentur für Arbeit", "BA Weisungen"}
    return x.get("source") == f



def datefmt(v):
    if not v: return "—"
    try:
        if "," in str(v): return parsedate_to_datetime(v).strftime("%d.%m.%Y %H:%M")
    except Exception:
        pass
    return str(v).replace("T", " ")[:16]


def compact_source_button(label, items, key, value):
    cc = counts(items)
    active = st.session_state.source_filter == value
    text = f"{label} - {cc['total']}:   🟢 {cc['green']}   🟡 {cc['yellow']}   🔴 {cc['red']}"
    if st.button(text, key=key, use_container_width=True, type="primary" if active else "secondary"):
        choose_source(value)
        st.rerun()


def translate_block(x, key):
    if st.session_state.get(f"show_tr_{key}"):
        title = x.get("title") or x.get("document_title") or ""
        summary = x.get("summary") or x.get("description") or ""
        payload = (title + "\n\n" + summary).strip()
        if st.session_state.lang == "de":
            st.info("Текст уже на немецком.")
            return
        if not st.session_state.deepl_key:
            st.warning("Для перевода вставьте DeepL API key вверху страницы.")
            return
        try:
            translated = translate_text(payload, st.session_state.lang, api_key=st.session_state.deepl_key)
            if translated:
                st.success(translated)
            else:
                st.info("Перевод не получен.")
        except Exception as e:
            st.warning(f"Перевод временно недоступен: {e}")


def can_compare_versions(x):
    """Show version comparison only for federal legal gazette documents it can actually handle."""
    if x.get("source_group") != "official":
        return False
    url = str(x.get("url") or "").lower()
    return "recht.bund.de" in url and "/bgbl/" in url


def card(x, key, allow_diff=False):
    st.markdown("---")
    title = x.get("title") or x.get("document_title") or "Без названия"
    st.markdown(f"#### {title}")
    st.caption(f"{x.get('source','')} · {datefmt(x.get('date'))}")
    if x.get("topics"): st.write("**Темы BCA:** " + ", ".join(map(str, x["topics"])))
    if x.get("reasons"): st.write("**Почему материал полезен:** " + "; ".join(map(str, x["reasons"][:4])))
    if x.get("summary"): st.caption(str(x["summary"])[:650])
    c1, c2, c3 = st.columns([1, 1, 5])
    with c1:
        if x.get("url"): st.link_button("Открыть источник ↗", x["url"], use_container_width=True)
    with c2:
        if st.button("🌐 Перевести", key=f"tr_{key}", use_container_width=True):
            st.session_state[f"show_tr_{key}"] = not st.session_state.get(f"show_tr_{key}", False)
    translate_block(x, key)
    if allow_diff and can_compare_versions(x):
        if st.button("⚖️ БЫЛО ↔ СТАЛО", key=f"diff_{key}"):
            with st.spinner("Ищу редакции…"):
                st.session_state[f"cmp_{key}"] = build_legal_comparison(x["url"])
        cmp = st.session_state.get(f"cmp_{key}")
        if cmp:
            old, new = cmp.get("old_text"), cmp.get("new_text")
            if old and new:
                od, nd = render_diff(old, new)
                st.markdown(DIFF_CSS, unsafe_allow_html=True)
                l, r = st.columns(2)
                with l: st.markdown("#### 🔴 БЫЛО"); st.markdown(od, unsafe_allow_html=True)
                with r: st.markdown("#### 🟢 СТАЛО"); st.markdown(nd, unsafe_allow_html=True)
            else:
                st.warning(cmp.get("instruction") or "Для этой публикации пока не удалось получить две различающиеся архивные редакции.")


# ---------- HEADER + TRANSLATOR ----------
h1, h2 = st.columns([4.6, 1.4])
with h1:
    st.title("BCA Legal & Migration Monitor")
    st.caption("Единая подборка из официальных источников и СМИ за последние 48 часов. Сначала самые новые.")
with h2:
    st.markdown('<div class="translator-spacer"></div>', unsafe_allow_html=True)
    lang_name = st.selectbox("🌐 Язык перевода", list(LANGUAGES), index=2, label_visibility="collapsed")
    st.session_state.lang = LANGUAGES[lang_name]
    st.session_state.deepl_key = st.text_input("DeepL API key", type="password", placeholder="DeepL API key", label_visibility="collapsed")
    st.link_button("🔑 Получить бесплатный DeepL API key ↗", "https://www.deepl.com/pro-api", use_container_width=True)

r1, r2 = st.columns([1, 5])
with r1:
    if st.button("🔄 Проверить сейчас", use_container_width=True):
        with st.spinner("Проверяю источники и обновляю архив…"):
            refresh_data()
        st.success("Данные обновлены.")
        st.rerun()
with r2:
    st.caption(f"Период: последние 48 часов · обновление по кнопке · {datetime.now().strftime('%d.%m.%Y %H:%M')}")

# ---------- FRESH FEED SOURCE FILTERS ----------
st.markdown("##### Источники свежей подборки")

# Three primary filters keep the operational view compact.
source_defs = [
    ("🌐 Все источники", everything, "src_all", "ALL"),
    ("🏛 Официальные", official, "src_off", "OFFICIAL_ALL"),
    ("📰 СМИ", media, "src_media", "MEDIA_ALL"),
]

# Show every official source that actually contributed to the 48-hour feed.
# This keeps the counters transparent: "Официальные · N" can always be explained.
official_source_labels = {
    "Gesetze im Internet": "⚖️ Gesetze",
    "Bundesagentur für Arbeit": "💼 BA",
    "BA Weisungen": "📋 BA Weisungen",
    "BAMF": "🛂 BAMF",
    "LEA Berlin": "📍 LEA Berlin",
    "Bundestag": "🏛 Bundestag",
    "Bundesrat": "🏛 Bundesrat",
    "BMI": "🏢 BMI",
    "BMAS": "💼 BMAS",
    "Bundesregierung": "🇩🇪 Bundesregierung",
}

for source_name in sorted({str(x.get("source") or "") for x in official if x.get("source")}):
    subset = [x for x in official if str(x.get("source") or "") == source_name]
    source_defs.append((
        official_source_labels.get(source_name, f"🏛 {source_name}"),
        subset,
        "src_off_" + re.sub(r"\W+", "_", source_name.lower()).strip("_"),
        source_name,
    ))

for start in range(0, len(source_defs), 4):
    chunk = source_defs[start:start + 4]
    cols = st.columns(len(chunk))
    for col, (label, items, key, value) in zip(cols, chunk):
        with col:
            active = st.session_state.source_filter == value
            button_label = f"{label} · {len(items)}"
            if st.button(
                button_label,
                key=key,
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                choose_source(value)
                st.rerun()

st.markdown("---")

# ---------- ONE FRESH FEED ----------
feed, search_tab, source_tab = st.tabs(
    ["📰 Свежая подборка", "🔎 Поиск", "📊 Источники"]
)

with feed:
    rows = [x for x in everything if source_ok(x)]
    rows.sort(
        key=lambda x: (
            x.get("_publication_dt") or datetime.min.replace(tzinfo=timezone.utc),
            float(x.get("bca_score") or 0),
        ),
        reverse=True,
    )

    st.markdown(f"### Свежие публикации — {len(rows)}")
    st.caption("Показаны только материалы с датой публикации в пределах последних 48 часов. Старые публикации сюда не попадают.")

    shown = rows[:st.session_state.limit]
    if not rows:
        st.info("За последние 48 часов публикаций по выбранному источнику не найдено.")
    else:
        st.caption(f"Показано: 1–{len(shown)} из {len(rows)}")

    for i, x in enumerate(shown):
        card(x, f"fresh_{i}", allow_diff=True)

    if len(rows) > len(shown):
        if st.button("Показать ещё 10", key="more_fresh", use_container_width=True):
            st.session_state.limit += 10
            st.rerun()


with search_tab:
    st.markdown("### Поиск по свежей подборке")
    st.caption("Поиск выполняется только среди публикаций за последние 48 часов.")

    q = st.text_input(
        "🔎 Поиск",
        placeholder="Например: Blue Card, Chancenkarte, Fachkräfte, Einbürgerung, §24…",
        key="fresh_search",
    )

    rows = [x for x in everything if source_ok(x)]

    if q.strip():
        words = [w.lower() for w in q.split() if w.strip()]

        def hay(x):
            return " ".join([
                str(x.get("title", "")),
                str(x.get("document_title", "")),
                str(x.get("summary", "")),
                str(x.get("description", "")),
                str(x.get("source", "")),
                str(x.get("url", "")),
                " ".join(map(str, x.get("topics") or [])),
                " ".join(map(str, x.get("reasons") or [])),
            ]).lower()

        rows = [x for x in rows if all(w in hay(x) for w in words)]

    rows.sort(
        key=lambda x: (
            x.get("_publication_dt") or datetime.min.replace(tzinfo=timezone.utc),
            float(x.get("bca_score") or 0),
        ),
        reverse=True,
    )

    if not q.strip():
        st.caption("Введите тему или ключевое слово.")
    else:
        st.markdown(f"**Найдено свежих публикаций: {len(rows)}**")
        if not rows:
            st.info("По этому запросу за последние 48 часов публикаций не найдено.")
        for i, x in enumerate(rows[:20]):
            card(x, f"search_fresh_{i}", allow_diff=True)


with source_tab:
    st.markdown("### Подключённые источники")
    st.caption("Полный список источников монитора. Счётчик показывает, сколько материалов от источника вошло в свежую подборку за последние 48 часов.")

    official_catalog = [
        ("Gesetze im Internet", "Федеральные законы и правовые публикации"),
        ("Bundesagentur für Arbeit", "Bundesagentur für Arbeit"),
        ("BA Weisungen", "Указания и служебные документы BA"),
        ("BAMF", "Bundesamt für Migration und Flüchtlinge"),
        ("LEA Berlin", "Landesamt für Einwanderung Berlin"),
        ("Bundestag", "Deutscher Bundestag"),
        ("Bundesrat", "Bundesrat"),
        ("BMI", "Bundesministerium des Innern"),
        ("BMAS", "Bundesministerium für Arbeit und Soziales"),
        ("Bundesregierung", "Bundesregierung"),
    ]

    check_map = {x["source"]: x for x in latest_source_checks()}

    counts_by_source = {}
    latest_by_source = {}
    for item in everything:
        name = str(item.get("source") or "—")
        counts_by_source[name] = counts_by_source.get(name, 0) + 1
        dt = item.get("_publication_dt")
        if dt and (name not in latest_by_source or dt > latest_by_source[name]):
            latest_by_source[name] = dt

    def check_note(source):
        c = check_map.get(source)
        if not c:
            return "ещё не проверялся"
        if c.get("status") == "error":
            return "⚠️ ошибка последней проверки"
        return "✓ источник проверен"

    left, right = st.columns(2)
    with left:
        st.markdown("#### 🏛 Официальные источники")
        for source, description in official_catalog:
            count = counts_by_source.get(source, 0)
            latest = latest_by_source.get(source)
            latest_text = latest.astimezone().strftime("%d.%m.%Y %H:%M") if latest else "нет свежих публикаций"
            st.markdown(f"**{source} · {count}**  \n{description}  \n<span class='small-note'>{latest_text} · {check_note(source)}</span>", unsafe_allow_html=True)

    with right:
        st.markdown("#### 📰 СМИ")
        for source in MEDIA_SOURCES.keys():
            count = counts_by_source.get(source, 0)
            latest = latest_by_source.get(source)
            latest_text = latest.astimezone().strftime("%d.%m.%Y %H:%M") if latest else "нет свежих публикаций"
            st.markdown(f"**{source} · {count}**  \n<span class='small-note'>{latest_text} · {check_note(source)}</span>", unsafe_allow_html=True)
