from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
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
from processing.archive_db import upsert as db_upsert, all_rows as db_all_rows
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


@st.cache_data(ttl=3600, show_spinner=False)
def load_data():
    laws = safe_call(fetch_updates, {"all_publications": [], "results": []})
    raw_official = list(laws.get("all_publications", []))
    richer = {x.get("url"): x for x in laws.get("results", []) if x.get("url")}
    raw_official = [{**x, **richer.get(x.get("url"), {})} for x in raw_official]
    raw_official += list(safe_call(get_lea_publications, []) or [])
    raw_official += list(safe_call(fetch_bamf_publications, []) or [])
    raw_official += list(safe_call(fetch_ba_publications, []) or [])
    raw_official += list(safe_call(fetch_ba_weisungen, []) or [])
    raw_official += list(safe_call(fetch_bundestag_publications, []) or [])
    raw_official += list(safe_call(fetch_federal_publications, []) or [])

    media_result = safe_call(fetch_media_publications, {"publications": [], "errors": {}})
    official = filter_relevant(raw_official)
    media = filter_relevant(media_result.get("publications", []))
    for x in official:
        x["source_group"] = "official"
    for x in media:
        x["source_group"] = "media"
    combined = official + media
    # Keep the legacy JSON archive for compatibility, but persist/search via SQLite.
    legacy_archive = merge_archive(combined)
    db_upsert(legacy_archive)
    archive = db_all_rows()
    return {"official": official, "media": media, "all": combined, "archive": archive,
            "media_errors": media_result.get("errors", {})}


data = load_data()
official, media, everything = data["official"], data["media"], data["all"]

for key, value in {"source_filter": "ALL", "level_filter": "ALL", "limit": 20, "archive_limit": 20, "stats_source": None, "stats_level": "ALL"}.items():
    if key not in st.session_state:
        st.session_state[key] = value


def reset_limit():
    st.session_state.limit = 20


def choose_source(value):
    st.session_state.source_filter = value
    # One clear active choice: choosing a concrete source clears a concrete relevance choice.
    if value not in {"ALL", "OFFICIAL_ALL", "MEDIA_ALL"}:
        st.session_state.level_filter = "ALL"
    # Keep Archive defaults visually consistent with the top filter.
    st.session_state.pop("archive_source", None)
    st.session_state.pop("archive_relevance", None)
    reset_limit()


def choose_level(value):
    st.session_state.level_filter = value
    # One clear active choice: choosing a concrete relevance clears a concrete source choice.
    if value != "ALL":
        st.session_state.source_filter = "ALL"
    st.session_state.pop("archive_source", None)
    st.session_state.pop("archive_relevance", None)
    reset_limit()


def source_ok(x):
    f = st.session_state.source_filter
    if f == "ALL": return True
    if f == "OFFICIAL_ALL": return x.get("source_group") == "official"
    if f == "MEDIA_ALL": return x.get("source_group") == "media"
    if f == "BA": return x.get("source") in {"Bundesagentur für Arbeit", "BA Weisungen"}
    return x.get("source") == f


def level_ok(x):
    f = st.session_state.level_filter
    return f == "ALL" or x.get("relevance_level") == f


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


def card(x, key, allow_diff=False):
    st.markdown("---")
    title = x.get("title") or x.get("document_title") or "Без названия"
    st.markdown(f"#### {light(x.get('relevance_level'))} {title}")
    st.caption(f"{x.get('source','')} · {datefmt(x.get('date'))} · BCA score: {x.get('bca_score',0)}")
    if x.get("topics"): st.write("**Темы BCA:** " + ", ".join(map(str, x["topics"])))
    if x.get("reasons"): st.write("**Почему релевантно:** " + "; ".join(map(str, x["reasons"][:4])))
    if x.get("summary"): st.caption(str(x["summary"])[:650])
    c1, c2, c3 = st.columns([1, 1, 5])
    with c1:
        if x.get("url"): st.link_button("Открыть источник ↗", x["url"], use_container_width=True)
    with c2:
        if st.button("🌐 Перевести", key=f"tr_{key}", use_container_width=True):
            st.session_state[f"show_tr_{key}"] = not st.session_state.get(f"show_tr_{key}", False)
    translate_block(x, key)
    if allow_diff and x.get("url"):
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
    st.caption("Только релевантные для BCA публикации: официальные источники + СМИ")
with h2:
    st.markdown('<div class="translator-spacer"></div>', unsafe_allow_html=True)
    lang_name = st.selectbox("🌐 Язык перевода", list(LANGUAGES), index=2, label_visibility="collapsed")
    st.session_state.lang = LANGUAGES[lang_name]
    st.session_state.deepl_key = st.text_input("DeepL API key", type="password", placeholder="DeepL API key", label_visibility="collapsed")
    st.link_button("🔑 Получить бесплатный DeepL API key ↗", "https://www.deepl.com/pro-api", use_container_width=True)

r1, r2 = st.columns([1, 5])
with r1:
    if st.button("🔄 Проверить сейчас", use_container_width=True):
        st.cache_data.clear(); st.rerun()
with r2:
    st.caption(f"Автообновление: 60 мин. · {datetime.now().strftime('%d.%m.%Y %H:%M')}")

# ---------- CLICKABLE SOURCE COUNTERS ----------
st.markdown("##### 🌐 Официальные источники")
official_defs = [
    ("🌐 ВСЕ", official, "off_all", "OFFICIAL_ALL"),
    ("⚖️ Gesetze", [x for x in official if x.get("source") == "Gesetze im Internet"], "off_law", "Gesetze im Internet"),
    ("💼 BA", [x for x in official if x.get("source") in {"Bundesagentur für Arbeit", "BA Weisungen"}], "off_ba", "BA"),
    ("🛂 BAMF", [x for x in official if x.get("source") == "BAMF"], "off_bamf", "BAMF"),
    ("📍 LEA Berlin", [x for x in official if x.get("source") == "LEA Berlin"], "off_lea", "LEA Berlin"),
    ("🏛 Bundestag", [x for x in official if x.get("source") == "Bundestag"], "off_bt", "Bundestag"),
    ("🏛 Bundesrat", [x for x in official if x.get("source") == "Bundesrat"], "off_br", "Bundesrat"),
    ("🏢 BMI", [x for x in official if x.get("source") == "BMI"], "off_bmi", "BMI"),
    ("⚙️ BMAS", [x for x in official if x.get("source") == "BMAS"], "off_bmas", "BMAS"),
    ("🇩🇪 Bundesregierung", [x for x in official if x.get("source") == "Bundesregierung"], "off_breg", "Bundesregierung"),
]
for start in range(0, len(official_defs), 5):
    chunk = official_defs[start:start+5]
    cols = st.columns(len(chunk))
    for col, args in zip(cols, chunk):
        with col: compact_source_button(*args)

st.markdown("##### 📰 СМИ")
media_defs = [("📰 ВСЕ СМИ", media, "med_all", "MEDIA_ALL")]
for name in MEDIA_SOURCES:
    media_defs.append((name, [x for x in media if x.get("source") == name], f"med_{name}", name))
cols = st.columns(len(media_defs))
for col, args in zip(cols, media_defs):
    with col: compact_source_button(*args)

# ---------- COMPACT CLICKABLE RELEVANCE ----------
cc = counts(everything)
traffic = [
    ("🌐 ВСЕ", cc["total"], "ALL"),
    ("🟢 Высокая", cc["green"], "GREEN"),
    ("🟡 Средняя", cc["yellow"], "YELLOW"),
    ("🔴 Низкая", cc["red"], "RED"),
]
label_col, *traffic_cols = st.columns([1.55, 1, 1, 1, 1])
with label_col:
    st.markdown("##### Релевантность для BCA")
for col, (label, number, value) in zip(traffic_cols, traffic):
    with col:
        active = (st.session_state.level_filter == value) and not (value == "ALL" and st.session_state.source_filter != "ALL")
        if st.button(f"{label} - {number}", key=f"level_{value}", use_container_width=True, type="primary" if active else "secondary"):
            choose_level(value); st.rerun()

# ---------- CURRENT FILTER / RESULTS ----------
source_label = st.session_state.source_filter
level_label = {"ALL":"все уровни", "GREEN":"🟢 высокая", "YELLOW":"🟡 средняя", "RED":"🔴 низкая"}[st.session_state.level_filter]
bar1, bar2 = st.columns([5, 1])
with bar1:
    st.caption(f"Сейчас показано: источник — {source_label}; релевантность — {level_label}")
with bar2:
    if st.button("↩ Сбросить фильтры", use_container_width=True):
        st.session_state.source_filter = "ALL"; st.session_state.level_filter = "ALL"; reset_limit(); st.rerun()

nav_all, nav_archive, nav_search, nav_stats = st.tabs(["📚 Публикации", "🕘 Архив", "🔎 Поиск", "📊 Источники"])

with nav_all:
    rows = [x for x in everything if source_ok(x) and level_ok(x)]
    rows.sort(key=lambda x: (x.get("bca_score", 0), str(x.get("date", ""))), reverse=True)
    st.markdown(f"### Публикации — {len(rows)}")
    st.caption("Здесь только материалы, прошедшие BCA-фильтр.")
    st.caption("Степень релевантности выбирается кнопками выше. По умолчанию показываются первые 20 публикаций.")
    shown = rows[:st.session_state.limit]
    if rows:
        st.caption(f"Показано: 1–{len(shown)} из {len(rows)}")
    else:
        st.info("Для выбранных фильтров публикаций пока нет.")
    for i, x in enumerate(shown): card(x, f"pub_{i}", allow_diff=True)
    if len(rows) > len(shown):
        if st.button("Показать ещё 20", key="more_main", use_container_width=True):
            st.session_state.limit += 20; st.rerun()

with nav_archive:
    archive_rows = list(data["archive"])
    st.markdown(f"### Архив публикаций — {len(archive_rows)}")
    st.caption("Здесь сохраняются публикации, которые монитор уже видел. Фильтры архива не меняют фильтры главной страницы.")

    def archive_year(x):
        raw = str(x.get("date") or x.get("_first_seen") or "")
        import re
        m = re.search(r"(?:19|20)\d{2}", raw)
        return m.group(0) if m else "Без даты"

    archive_sources = sorted({str(x.get("source") or "—") for x in archive_rows})
    archive_years = [str(y) for y in range(2026, 2019, -1)]
    archive_topics = sorted({str(t).strip() for x in archive_rows for t in (x.get("topics") or []) if str(t).strip()})
    f1, f2, f3, f4 = st.columns([1, 1.25, 1, 1.5])
    with f1:
        ay = st.selectbox("Год", ["Все годы"] + archive_years + (["Без даты"] if any(archive_year(x)=="Без даты" for x in archive_rows) else []), key="archive_year")
    archive_source_options = ["Все источники"] + archive_sources
    top_source = st.session_state.source_filter
    if "archive_source" not in st.session_state:
        if top_source == "BA":
            st.session_state.archive_source = "Все источники"
        elif top_source in archive_sources:
            st.session_state.archive_source = top_source
        else:
            st.session_state.archive_source = "Все источники"
    archive_rel_options = ["Все уровни", "🟢 Высокая", "🟡 Средняя", "🔴 Низкая"]
    top_rel = {"ALL":"Все уровни", "GREEN":"🟢 Высокая", "YELLOW":"🟡 Средняя", "RED":"🔴 Низкая"}[st.session_state.level_filter]
    if "archive_relevance" not in st.session_state:
        st.session_state.archive_relevance = top_rel
    with f2:
        ass = st.selectbox("Источник", archive_source_options, key="archive_source")
    with f3:
        ar = st.selectbox("Релевантность", archive_rel_options, key="archive_relevance")
    with f4:
        at = st.selectbox("Тема BCA", ["Все темы"] + archive_topics, key="archive_topic")
    q = st.text_input("🔎 Глобальный поиск по архиву", placeholder="Любой запрос: Jobcenter Ukraine, §18b Arbeitsplatzverlust, Vermögen Ausland, Einbürgerung…", key="archive_query")
    sort_new = st.radio("Сортировка", ["Сначала новые", "Сначала старые"], horizontal=True, key="archive_sort")

    level_map_a = {"Все уровни": None, "🟢 Высокая": "GREEN", "🟡 Средняя": "YELLOW", "🔴 Низкая": "RED"}
    rows = archive_rows
    if ay != "Все годы": rows = [x for x in rows if archive_year(x) == ay]
    if ass != "Все источники": rows = [x for x in rows if str(x.get("source") or "—") == ass]
    if level_map_a[ar]: rows = [x for x in rows if x.get("relevance_level") == level_map_a[ar]]
    if at != "Все темы": rows = [x for x in rows if at in [str(t) for t in (x.get("topics") or [])]]
    if q.strip():
        n=q.lower().strip()
        rows=[x for x in rows if n in " ".join([str(x.get("title", "")), str(x.get("document_title", "")), str(x.get("summary", "")), str(x.get("source", "")), " ".join(map(str,x.get("topics") or [])), " ".join(map(str,x.get("reasons") or []))]).lower()]
    rows.sort(key=lambda x: str(x.get("date") or x.get("_first_seen") or ""), reverse=(sort_new=="Сначала новые"))
    st.caption(f"Найдено в архиве: {len(rows)} · показаны первые {min(st.session_state.archive_limit, len(rows))}")
    shown=rows[:st.session_state.archive_limit]
    for i,x in enumerate(shown): card(x, f"archive_{i}", allow_diff=True)
    if len(rows)>len(shown):
        if st.button("Показать ещё 20", key="more_archive", use_container_width=True):
            st.session_state.archive_limit += 20; st.rerun()

with nav_search:
    st.markdown("### Глобальный поиск по всему BCA-архиву")
    st.caption("Можно выбрать готовую тему или написать любой собственный запрос. Верхние фильтры главной страницы на поиск не влияют.")
    universal_topics = [
        "Все темы", "Aufenthalt / ВНЖ", "§24 / временная защита / Украина", "Asyl / убежище / Flüchtlinge",
        "Blue Card / Blaue Karte EU", "Chancenkarte / поиск работы", "Fachkräfte / трудовая миграция",
        "Einbürgerung / гражданство", "Familiennachzug / семья", "Anerkennung / квалификации",
        "Jobcenter / Bürgergeld / SGB II", "Agentur für Arbeit / SGB III", "Arbeitslos / arbeitssuchend",
        "Sozialleistungen / выплаты", "Ausbildung / Weiterbildung", "Studium / Studenten", "Sprache / Integration",
        "Visum / Einreise", "Ausländerbehörde / Verwaltung", "Duldung", "Abschiebung / Rückführung",
        "Selbständigkeit / бизнес", "Gesetzgebung / парламент"
    ]
    c1,c2 = st.columns([1.4,1])
    with c1:
        chosen_topic = st.selectbox("Быстрая тема", universal_topics, key="search_topic_v7")
    with c2:
        relevance_choice = st.selectbox("Релевантность", ["Все уровни", "🟢 Высокая", "🟡 Средняя", "🔴 Низкая"], key="search_relevance_v7")
    free_q = st.text_input("🔎 Свободный глобальный запрос", placeholder="Введите что угодно: Jobcenter ausländisches Bankkonto, §18b Arbeitsplatzverlust, Chancenkarte…", key="search_global_q")
    level_map = {"Все уровни": None, "🟢 Высокая": "GREEN", "🟡 Средняя": "YELLOW", "🔴 Низкая": "RED"}
    selected_level = level_map[relevance_choice]
    rows = list(data["archive"])
    if selected_level:
        rows = [x for x in rows if x.get("relevance_level") == selected_level]
    if chosen_topic != "Все темы":
        rows = [x for x in rows if chosen_topic in [str(t) for t in (x.get("topics") or [])]]
    if free_q.strip():
        words = [w.lower() for w in free_q.split() if w.strip()]
        def hay(x):
            return " ".join([str(x.get("title","")),str(x.get("document_title","")),str(x.get("summary","")),str(x.get("description","")),str(x.get("source","")),str(x.get("url",""))," ".join(map(str,x.get("topics") or []))," ".join(map(str,x.get("reasons") or []))]).lower()
        rows = [x for x in rows if all(w in hay(x) for w in words)]
    rows.sort(key=lambda x: (x.get("bca_score",0), str(x.get("date",""))), reverse=True)
    if chosen_topic == "Все темы" and not free_q.strip():
        st.caption("Выберите тему или введите собственный запрос. Без запроса поиск не ограничивает архив.")
    else:
        st.caption(f"Найдено: {len(rows)} · показаны первые {min(20,len(rows))} · тема: {chosen_topic} · {relevance_choice}")
        for i,x in enumerate(rows[:20]): card(x, f"search_v7_{i}", allow_diff=True)

with nav_stats:
    st.markdown("### Статистика по источникам")
    st.caption("Нажмите ВСЕ / 🟢 / 🟡 / 🔴 — публикации выбранного источника сразу появятся ниже.")
    sources = sorted({x.get("source", "—") for x in everything})
    for idx, source in enumerate(sources):
        subset = [x for x in everything if x.get("source") == source]
        sc = counts(subset)
        a,b,c,d,e = st.columns([2.0,.72,.72,.72,.72])
        a.markdown(f"**{source}**")
        mapping = [("ВСЕ", sc["total"], "ALL"), ("🟢", sc["green"], "GREEN"), ("🟡", sc["yellow"], "YELLOW"), ("🔴", sc["red"], "RED")]
        for col, (lab, num, lev) in zip([b,c,d,e], mapping):
            with col:
                active = st.session_state.stats_source == source and st.session_state.stats_level == lev
                if st.button(f"{lab} {num}", key=f"stat_{idx}_{lev}", use_container_width=True, type="primary" if active else "secondary"):
                    st.session_state.stats_source = source
                    st.session_state.stats_level = lev
                    st.rerun()

    if st.session_state.stats_source:
        source = st.session_state.stats_source
        lev = st.session_state.stats_level
        rows = [x for x in everything if x.get("source") == source and (lev == "ALL" or x.get("relevance_level") == lev)]
        rows.sort(key=lambda x: (x.get("bca_score", 0), str(x.get("date", ""))), reverse=True)
        lev_name = {"ALL":"все уровни", "GREEN":"🟢 высокая", "YELLOW":"🟡 средняя", "RED":"🔴 низкая"}[lev]
        st.markdown(f"### {source} — {lev_name} — {len(rows)}")
        st.caption(f"Показаны первые {min(20, len(rows))} публикаций. Каждая публикация кликабельна через кнопку «Открыть источник». ")
        for i, x in enumerate(rows[:20]):
            card(x, f"stats_{source}_{lev}_{i}")

