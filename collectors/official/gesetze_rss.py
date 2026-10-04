import feedparser
import requests
import re
from bs4 import BeautifulSoup

RSS_URL = "https://www.gesetze-im-internet.de/aktuDienst-rss-feed.xml"

# ============================================================
# BCA RELEVANCE CONTEXT
# Темы, которые непосредственно интересуют клиентов BCA
# ============================================================

BCA_TOPICS = {

    # --------------------------------------------------------
    # 1. ВНЖ / ПРАВО НА ПРЕБЫВАНИЕ
    # --------------------------------------------------------
    "residence": [
        "Aufenthalt",
        "Aufenthaltstitel",
        "Aufenthaltserlaubnis",
        "Aufenthaltsrecht",
        "Aufenthaltsgesetz",
        "AufenthG",
        "Aufenthaltsverordnung",
        "AufenthV",
        "Niederlassungserlaubnis",
        "Daueraufenthalt",
        "Daueraufenthalt-EU",
        "Erlaubnis zum Daueraufenthalt",
        "Fiktionsbescheinigung",
        "Fiktionswirkung",
        "Aufenthaltszweck",
        "Zweckwechsel",
        "Spurwechsel",
    ],

    # --------------------------------------------------------
    # 2. EU BLUE CARD
    # --------------------------------------------------------
    "blue_card": [
        "Blaue Karte",
        "Blaue Karte EU",
        "EU Blue Card",
        "Blue Card",
        "Hochqualifizierte",
        "Mindestgehalt",
        "Gehaltsgrenze",
        "Gehaltsschwelle",
        "Mangelberuf",
        "Engpassberuf",
    ],

    # --------------------------------------------------------
    # 3. ТРУДОВАЯ МИГРАЦИЯ / FACHKRÄFTE
    # --------------------------------------------------------
    "skilled_workers": [
        "Fachkraft",
        "Fachkräfte",
        "Fachkräfteeinwanderung",
        "Fachkräfteeinwanderungsgesetz",
        "Arbeitsmigration",
        "Erwerbsmigration",
        "qualifizierte Beschäftigung",
        "Berufserfahrung",
        "Berufserfahrene",
        "Beschäftigungsverordnung",
        "BeschV",
        "Arbeitsmarktzugang",
        "Zustimmung zur Beschäftigung",
        "Bundesagentur für Arbeit",
    ],

    # --------------------------------------------------------
    # 4. CHANCENKARTE / ПОИСК РАБОТЫ
    # --------------------------------------------------------
    "opportunity_card": [
        "Chancenkarte",
        "Punktesystem",
        "Punktekarte",
        "Arbeitsplatzsuche",
        "Arbeitsplatzsuche für Fachkräfte",
        "Probebeschäftigung",
    ],

    # --------------------------------------------------------
    # 5. ВИЗЫ / ВЪЕЗД В ГЕРМАНИЮ
    # --------------------------------------------------------
    "visa_entry": [
        "Visum",
        "Visa",
        "Visaverfahren",
        "Visumantrag",
        "Visumerteilung",
        "nationales Visum",
        "D-Visum",
        "Einreise",
        "Einreisebestimmungen",
        "Einreisevoraussetzungen",
        "Auslandsvertretung",
        "Botschaft",
        "Konsulat",
    ],

    # --------------------------------------------------------
    # 6. ПРИЗНАНИЕ ИНОСТРАННЫХ КВАЛИФИКАЦИЙ
    # --------------------------------------------------------
    "qualification_recognition": [
        "ausländische Berufsqualifikation",
        "ausländischer Berufsabschluss",
        "ausländischer Hochschulabschluss",
        "Anerkennung ausländischer Berufsqualifikationen",
        "Berufsanerkennung",
        "Anerkennungsverfahren",
        "Anerkennungspartnerschaft",
        "Gleichwertigkeit",
        "Gleichwertigkeitsprüfung",
        "Qualifikationsanalyse",
        "Anpassungsqualifizierung",
        "Berufszulassung",
        "reglementierter Beruf",
        "Anerkennungsgesetz",
        "BQFG",
        "ZAB",
        "Zeugnisbewertung",
    ],

    # --------------------------------------------------------
    # 7. ГРАЖДАНСТВО / НАТУРАЛИЗАЦИЯ
    # --------------------------------------------------------
    "citizenship": [
        "Einbürgerung",
        "Einbürgerungsverfahren",
        "Einbürgerungsantrag",
        "Staatsangehörigkeit",
        "Staatsangehörigkeitsrecht",
        "Staatsangehörigkeitsgesetz",
        "StAG",
        "deutsche Staatsangehörigkeit",
        "Mehrstaatigkeit",
        "doppelte Staatsangehörigkeit",
        "Einbürgerungstest",
    ],

    # --------------------------------------------------------
    # 8. ВОССОЕДИНЕНИЕ СЕМЬИ
    # --------------------------------------------------------
    "family_reunification": [
        "Familiennachzug",
        "Familienzusammenführung",
        "Ehegattennachzug",
        "Kindernachzug",
        "Elternnachzug",
        "Nachzug zu Fachkräften",
        "Nachzug zu Deutschen",
        "Familienangehörige",
    ],

    # --------------------------------------------------------
    # 9. УЧЁБА / AUSBILDUNG
    # --------------------------------------------------------
    "study_training": [
        "Studium",
        "Studierende",
        "ausländische Studierende",
        "Ausbildung",
        "Berufsausbildung",
        "Ausbildungsplatzsuche",
        "Studienbewerbung",
        "Studienvisum",
        "Aufenthalt zum Studium",
        "Aufenthalt zur Ausbildung",
    ],

    # --------------------------------------------------------
    # 10. УКРАИНА / §24 / ВРЕМЕННАЯ ЗАЩИТА
    # --------------------------------------------------------
    "ukraine_temporary_protection": [
        "Ukraine",
        "Ukrainer",
        "Ukrainerinnen",
        "§ 24 AufenthG",
        "§24 AufenthG",
        "Paragraph 24",
        "vorübergehender Schutz",
        "temporärer Schutz",
        "Massenzustrom",
        "Massenzustrom-Richtlinie",
        "Ukraine-Aufenthalts",
        "Ukraine-Aufenthalts-Übergangsverordnung",
    ],

    # --------------------------------------------------------
    # 11. AUSLÄNDERBEHÖRDE / LEA / ПРОЦЕДУРЫ
    # --------------------------------------------------------
    "authorities_procedures": [
        "Ausländerbehörde",
        "Ausländerbehörden",
        "Einwanderungsamt",
        "Landesamt für Einwanderung",
        "LEA Berlin",
        "Termin Ausländerbehörde",
        "Online-Antrag",
        "Onlineantrag",
        "Antragsverfahren",
        "Bearbeitungszeit",
        "Terminvergabe",
        "Behördenverfahren",
    ],

    # --------------------------------------------------------
    # 12. МИГРАЦИОННОЕ ПРАВО В ЦЕЛОМ
    # --------------------------------------------------------
    "migration_law": [
        "Migration",
        "Zuwanderung",
        "Einwanderung",
        "Einwanderungsrecht",
        "Migrationsrecht",
        "Ausländerrecht",
        "Ausländer",
        "Drittstaatsangehörige",
        "Drittstaat",
    ],

    # --------------------------------------------------------
    # 13. ASYL / БЕЖЕНЦЫ
    # --------------------------------------------------------
    "asylum": [
        "Asyl",
        "Asylrecht",
        "Asylgesetz",
        "AsylG",
        "Asylverfahren",
        "Flüchtling",
        "Flüchtlinge",
        "Schutzberechtigte",
        "subsidiärer Schutz",
        "Schutzstatus",
    ],

    # --------------------------------------------------------
    # 14. РИСК ПОТЕРИ ПРАВА НА ПРЕБЫВАНИЕ
    # --------------------------------------------------------
    "residence_risk": [
        "Ausweisung",
        "Abschiebung",
        "Abschiebungsverbot",
        "Aufenthaltsbeendigung",
        "Widerruf des Aufenthaltstitels",
        "Rücknahme des Aufenthaltstitels",
        "Erlöschen des Aufenthaltstitels",
        "Ausreisepflicht",
        "Abschiebungsandrohung",
        "Einreiseverbot",
        "Aufenthaltsverbot",
    ],

    # --------------------------------------------------------
    # 15. РАБОТА И ПРАВО НА ТРУД
    # --------------------------------------------------------
    "employment": [
        "Beschäftigungserlaubnis",
        "Erwerbstätigkeit",
        "Erwerbstätigkeit gestattet",
        "Beschäftigung gestattet",
        "Arbeitserlaubnis",
        "Arbeitsgenehmigung",
        "Zustimmung der Bundesagentur für Arbeit",
        "Arbeitgeberwechsel",
    ],

    # --------------------------------------------------------
    # 16. САМОЗАНЯТОСТЬ / БИЗНЕС ДЛЯ МИГРАНТОВ
    # --------------------------------------------------------
    "self_employment": [
        "selbständige Tätigkeit",
        "Selbständigkeit",
        "Selbstständigkeit",
        "Unternehmensgründung",
        "Existenzgründung",
        "Aufenthalt zur selbständigen Tätigkeit",
    ],
}


# ============================================================
# ОСОБЕННО СИЛЬНЫЕ BCA-СИГНАЛЫ
# Если встречается такое понятие, документ почти наверняка
# заслуживает проверки.
# ============================================================

STRONG_BCA_TERMS = [
    "Aufenthaltsgesetz",
    "AufenthG",
    "Aufenthaltstitel",
    "Niederlassungserlaubnis",
    "Daueraufenthalt-EU",
    "Blaue Karte EU",
    "EU Blue Card",
    "Fachkräfteeinwanderung",
    "Fachkräfteeinwanderungsgesetz",
    "Chancenkarte",
    "Familiennachzug",
    "Einbürgerung",
    "Staatsangehörigkeitsgesetz",
    "Anerkennungspartnerschaft",
    "Arbeitsmigration",
    "Ausländerbehörde",
    "Landesamt für Einwanderung",
    "§ 24 AufenthG",
    "§24 AufenthG",
]


# ============================================================
# ШИРОКИЕ СЛОВА
# Сами по себе НЕ означают, что документ релевантен BCA.
# ============================================================

CONTEXT_TERMS = [
    "Anerkennung",
    "Beschäftigung",
    "Ausbildung",
    "Studium",
    "Beruf",
    "Arbeit",
    "Familie",
    "Visum",
    "Einreise",
    "Migration",
    "Ausländer",
]

# Общий список BCA-ключевых слов для первичного поиска
KEYWORDS = list(dict.fromkeys(
    term
    for terms in BCA_TOPICS.values()
    for term in terms
))


OPPORTUNITY_WORDS = [
    "Erleichterung",
    "erleichtert",
    "erweitert",
    "Anspruch",
    "Verlängerung",
    "Zulassung",
    "Chancenkarte",
    "Blaue Karte",
    "Fachkräfte",
]


IMPORTANT_WORDS = [
    "Aufenthalt",
    "Aufenthaltsgesetz",
    "AufenthG",
    "Einbürgerung",
    "Staatsangehörigkeit",
    "Familiennachzug",
    "Visum",
    "Visa",
    "Migration",
    "Zuwanderung",
    "Ausländer",
    "Beschäftigung",
    "Anerkennung",
    "Asyl",
    "Ukraine",
]


RISK_WORDS = [
    "Widerruf",
    "Ablehnung",
    "Abschiebung",
    "Ausweisung",
    "Verschärfung",
    "Einschränkung",
    "Verkürzung",
    "Bußgeld",
    "Sanktion",
    "Verbot",
    "erlischt",
]

def find_keywords(text):
    found = []

    for keyword in KEYWORDS:
        pattern = rf"(?<!\w){re.escape(keyword)}(?!\w)"

        if re.search(pattern, text, re.IGNORECASE):
            found.append(keyword)

    return found

def find_matches(text, words):
    found = []

    for word in words:
        pattern = rf"(?<!\w){re.escape(word)}(?!\w)"

        if re.search(pattern, text, re.IGNORECASE):
            found.append(word)

    return found


def calculate_relevance(text):
    score = 0
    matched_topics = []
    strong_matches = []
    context_matches = []
    reasons = []

    # ---------------------------------------------------------
    # 1. ОЧЕНЬ СИЛЬНЫЕ МИГРАЦИОННЫЕ ТЕРМИНЫ
    # Эти понятия практически сами по себе означают,
    # что документ относится к миграции / пребыванию иностранцев.
    # ---------------------------------------------------------

    very_strong_terms = [
        "Aufenthaltsgesetz",
        "AufenthG",
        "Aufenthaltsverordnung",
        "Aufenthaltstitel",
        "Aufenthaltserlaubnis",
        "Niederlassungserlaubnis",
        "Daueraufenthalt-EU",
        "Daueraufenthalt – EU",
        "Blaue Karte EU",
        "Blue Card",
        "EU Blue Card",
        "Chancenkarte",
        "Fachkräfteeinwanderung",
        "Fachkräfteeinwanderungsgesetz",
        "Familiennachzug",
        "Ehegattennachzug",
        "Kindernachzug",
        "Visumverfahren",
        "Ausländerbehörde",
        "Ausländerzentralregister",
        "AZR",
        "Asylgesetz",
        "AsylG",
        "Asylbewerberleistungsgesetz",
        "AsylbLG",
        "Freizügigkeitsgesetz/EU",
        "FreizügG/EU",
        "Beschäftigungsverordnung",
        "BeschV",
        "ICT-Karte",
        "Mobiler-ICT-Karte",
        "Fiktionsbescheinigung",
        "Duldung",
        "Aufenthaltsgestattung",
        "Aufenthaltsgesetzes",
        "Beschäftigung von Fachkräften",
        "Beschäftigung ausländischer Fachkräfte",
    ]

    very_strong_matches = find_matches(text, very_strong_terms)

    if very_strong_matches:
        score += 6
        strong_matches.extend(very_strong_matches)
        reasons.append("прямой миграционно-правовой термин")

    # ---------------------------------------------------------
    # 2. ТРУДОВАЯ МИГРАЦИЯ
    # ---------------------------------------------------------

    labour_migration_terms = [
        "Fachkraft mit Berufsausbildung",
        "Fachkraft mit akademischer Ausbildung",
        "ausländische Fachkräfte",
        "ausländischer Arbeitnehmer",
        "ausländische Arbeitnehmer",
        "Arbeitsmigration",
        "Erwerbsmigration",
        "qualifizierte Beschäftigung",
        "Arbeitsmarktzugang",
        "Zustimmung der Bundesagentur für Arbeit",
        "Westbalkanregelung",
        "Arbeitsplatzsuche",
        "Beschäftigung ausländischer Arbeitnehmer",
    ]

    labour_matches = find_matches(text, labour_migration_terms)

    if labour_matches:
        score += 5
        strong_matches.extend(labour_matches)
        matched_topics.append("Трудовая миграция")
        reasons.append("трудовая миграция / доступ к рынку труда")

    # ---------------------------------------------------------
    # 3. ПРИЗНАНИЕ ИНОСТРАННЫХ КВАЛИФИКАЦИЙ
    #
    # Просто слово Anerkennung НЕ считается достаточным.
    # ---------------------------------------------------------

    recognition_terms = [
        "ausländische Berufsqualifikation",
        "ausländischer Berufsqualifikation",
        "ausländischer Berufsqualifikationen",
        "Anerkennung ausländischer Berufsqualifikationen",
        "Anerkennungsverfahren ausländischer Berufsqualifikationen",
        "Berufsanerkennung",
        "ausländischer Berufsabschluss",
        "ausländische Berufsabschlüsse",
        "ausländischer Hochschulabschluss",
        "ausländische Hochschulabschlüsse",
        "Gleichwertigkeit ausländischer Berufsqualifikationen",
        "Anerkennungspartnerschaft",
        "Qualifikationsanalyse",
    ]

    recognition_matches = find_matches(text, recognition_terms)

    if recognition_matches:
        score += 6
        strong_matches.extend(recognition_matches)
        matched_topics.append("Признание иностранных квалификаций")
        reasons.append("признание иностранной квалификации")

    # ---------------------------------------------------------
    # 4. ГРАЖДАНСТВО / НАТУРАЛИЗАЦИЯ
    # ---------------------------------------------------------

    citizenship_terms = [
        "Staatsangehörigkeitsgesetz",
        "StAG",
        "Einbürgerung",
        "Einbürgerungsverfahren",
        "Einbürgerungsantrag",
        "Staatsangehörigkeit",
        "deutsche Staatsangehörigkeit",
        "Mehrstaatigkeit",
    ]

    citizenship_matches = find_matches(text, citizenship_terms)

    if citizenship_matches:
        score += 5
        strong_matches.extend(citizenship_matches)
        matched_topics.append("Гражданство")
        reasons.append("гражданство / натурализация")

    # ---------------------------------------------------------
    # 5. УБЕЖИЩЕ / ЗАЩИТА / УКРАИНА / §24
    # ---------------------------------------------------------

    protection_terms = [
        "vorübergehender Schutz",
        "temporärer Schutz",
        "§ 24 AufenthG",
        "Ukraine-Aufenthaltserlaubnis",
        "Ukraine-Aufenthalts",
        "UkraineAufenth",
        "Schutzsuchende",
        "Asylverfahren",
        "Asylantrag",
        "Asylberechtigte",
        "Flüchtlingsschutz",
        "subsidiärer Schutz",
        "Abschiebungsverbot",
        "Abschiebung",
        "Ausweisung",
        "Rückführung",
    ]

    protection_matches = find_matches(text, protection_terms)

    if protection_matches:
        score += 5
        strong_matches.extend(protection_matches)
        matched_topics.append("Защита / убежище / §24")
        reasons.append("убежище / временная или международная защита")

    # ---------------------------------------------------------
    # 6. СЕМЬЯ / ВОССОЕДИНЕНИЕ
    # ---------------------------------------------------------

    family_terms = [
        "Familiennachzug",
        "Familienzusammenführung",
        "Ehegattennachzug",
        "Kindernachzug",
        "Nachzug der Eltern",
        "Nachzug von Familienangehörigen",
        "Familienangehörige eines Ausländers",
    ]

    family_matches = find_matches(text, family_terms)

    if family_matches:
        score += 5
        strong_matches.extend(family_matches)
        matched_topics.append("Воссоединение семьи")
        reasons.append("семейная миграция")

    # ---------------------------------------------------------
    # 7. ВИЗЫ / ВЪЕЗД
    # ---------------------------------------------------------

    visa_terms = [
        "nationales Visum",
        "nationalen Visum",
        "Visumverfahren",
        "Visumerteilung",
        "Visumantrag",
        "Einreisevisum",
        "Einreise und Aufenthalt",
        "Visakodex",
    ]

    visa_matches = find_matches(text, visa_terms)

    if visa_matches:
        score += 4
        strong_matches.extend(visa_matches)
        matched_topics.append("Визы / въезд")
        reasons.append("виза / въезд в Германию")

    # ---------------------------------------------------------
    # 8. МИГРАЦИОННЫЕ ВЕДОМСТВА
    # ---------------------------------------------------------

    authority_terms = [
        "Bundesamt für Migration und Flüchtlinge",
        "BAMF",
        "Ausländerbehörde",
        "Landesamt für Einwanderung",
        "LEA Berlin",
    ]

    authority_matches = find_matches(text, authority_terms)

    if authority_matches:
        score += 3
        context_matches.extend(authority_matches)
        reasons.append("миграционное ведомство")

    # ---------------------------------------------------------
    # 9. ОБЩИЙ МИГРАЦИОННЫЙ КОНТЕКСТ
    # ---------------------------------------------------------

    migrant_context_terms = [
        "Ausländer",
        "Ausländerin",
        "Ausländerinnen",
        "Ausländern",
        "Drittstaatsangehörige",
        "Drittstaatsangehöriger",
        "Drittstaat",
        "Migration",
        "Zuwanderung",
        "Einwanderung",
        "Flüchtling",
        "Flüchtlinge",
        "Geflüchtete",
        "Schutzberechtigte",
    ]

    migrant_context_matches = find_matches(text, migrant_context_terms)

    if migrant_context_matches:
        score += len(migrant_context_matches)
        context_matches.extend(migrant_context_matches)

    # ---------------------------------------------------------
    # 10. СЛАБЫЕ / ДВУСМЫСЛЕННЫЕ ТЕРМИНЫ
    #
    # Ausbildung, Anerkennung, Beschäftigung и т.п.
    # сами по себе НЕ означают миграционную тему.
    # Баллы получают только при наличии миграционного контекста.
    # ---------------------------------------------------------

    ambiguous_terms = [
        "Ausbildung",
        "Berufsausbildung",
        "Studium",
        "Hochschulabschluss",
        "Beschäftigung",
        "Erwerbstätigkeit",
        "Anerkennung",
        "Berufsqualifikation",
        "Qualifikation",
        "Arbeitsvertrag",
        "Arbeitsplatz",
        "Bundesagentur für Arbeit",
    ]

    ambiguous_matches = find_matches(text, ambiguous_terms)

    has_migration_context = bool(
        very_strong_matches
        or migrant_context_matches
        or labour_matches
        or recognition_matches
        or protection_matches
        or family_matches
        or visa_matches
    )

    if ambiguous_matches and has_migration_context:
        score += len(ambiguous_matches) * 2
        context_matches.extend(ambiguous_matches)
        reasons.append("образование/работа в миграционном контексте")

    # ---------------------------------------------------------
    # 11. ОПРЕДЕЛЯЕМ КОНКРЕТНЫЕ ТЕМЫ BCA
    # ---------------------------------------------------------

    residence_words = [
        "Aufenthaltsgesetz",
        "AufenthG",
        "Aufenthaltsverordnung",
        "Aufenthaltstitel",
        "Aufenthaltserlaubnis",
        "Niederlassungserlaubnis",
        "Daueraufenthalt-EU",
        "Daueraufenthalt – EU",
        "Fiktionsbescheinigung",
    ]

    if find_matches(text, residence_words):
        matched_topics.append("ВНЖ / право пребывания")

    if find_matches(
        text,
        ["Blaue Karte EU", "Blue Card", "EU Blue Card"]
    ):
        matched_topics.append("EU Blue Card")

    if find_matches(text, ["Chancenkarte"]):
        matched_topics.append("Chancenkarte")

    if find_matches(
        text,
        ["ICT-Karte", "Mobiler-ICT-Karte"]
    ):
        matched_topics.append("ICT / мобильность работников")

    # ---------------------------------------------------------
    # 12. УБИРАЕМ ДУБЛИ ИЗ СПИСКОВ
    # ---------------------------------------------------------

    matched_topics = list(dict.fromkeys(matched_topics))
    strong_matches = list(dict.fromkeys(strong_matches))
    context_matches = list(dict.fromkeys(context_matches))
    reasons = list(dict.fromkeys(reasons))

    return {
        "score": score,
        "topics": matched_topics,
        "strong_matches": strong_matches,
        "context_matches": context_matches,
        "reasons": reasons,
    }


def classify_signals(text):
    return {
        "opportunity": find_matches(text, OPPORTUNITY_WORDS),
        "important": find_matches(text, IMPORTANT_WORDS),
        "risk": find_matches(text, RISK_WORDS),
    }

def is_relevant(text):
    relevance = calculate_relevance(text)
    return relevance["score"] > 0


def get_document_title(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.find_all("h1")[1]

        if title:
            return title.get_text(" ", strip=True)

        return "Название не найдено"

    except requests.RequestException as error:
        return f"Ошибка загрузки: {error}"


def fetch_updates():
    feed = feedparser.parse(RSS_URL)

    print("BCA Legal Monitor")
    print("=" * 60)
    print(f"Источник: {feed.feed.get('title', 'Gesetze im Internet')}")
    print(f"Найдено публикаций: {len(feed.entries)}")
    print("=" * 60)

    relevant_entries = []
    results = []

    all_publications = []

    for entry in feed.entries:
        title = entry.get("title", "")
        summary = entry.get("summary", "")
        text = f"{title} {summary}"

        all_publications.append({
            "title": title,
            "date": entry.get("published", ""),
            "url": entry.get("link", ""),
            "source": "Gesetze im Internet",
            "source_type": "official",
        })

        if is_relevant(text):
            relevant_entries.append(entry)

    print(f"Кандидатов для BCA-проверки: {len(relevant_entries)}")
    print("=" * 60)

    final_relevant_count = 0

    for entry in relevant_entries:
        title = entry.get("title", "")
        summary = entry.get("summary", "")
        text = f"{title} {summary}"

        link = entry.get("link", "")
        document_title = get_document_title(link)
        full_text = f"{title} {summary} {document_title}"

        for publication in all_publications:
            if publication.get("url") == link:
                publication["document_title"] = document_title
                break

        keywords = find_keywords(full_text)
        relevance = calculate_relevance(full_text)

        if relevance["score"] >= 6:
            relevance_level = "HIGH"
        elif relevance["score"] > 0:
            relevance_level = "POSSIBLE"
        else:
            relevance_level = "LOW"

        results.append({
            "title": title,
            "document_title": document_title,
            "date": entry.get("published", ""),
            "url": link,
            "score": relevance["score"],
            "relevance_level": relevance_level,
            "topics": relevance["topics"],
            "strong_matches": relevance["strong_matches"],
            "reasons": relevance["reasons"],
        })

        if relevance_level in ("HIGH", "POSSIBLE"):
            final_relevant_count += 1

        signals = classify_signals(full_text)

        print()  
        print("Название:", title)
        print("Документ:", document_title)
        print("BCA SCORE:", relevance["score"])
        print(
              "Темы BCA:",
              ", ".join(relevance["topics"]) if relevance["topics"] else "—"
        )
        print(
              "Сильные BCA-сигналы:",
              ", ".join(relevance["strong_matches"])
        if relevance["strong_matches"]
        else "—"
        )
        print(
              "Почему релевантно:",
              ", ".join(relevance["reasons"])
        if relevance["reasons"]
        else "—"
      )
        print("Ключевые темы:", ", ".join(keywords) if keywords else "—")
        print(
            "🟢 Возможности:",
            ", ".join(signals["opportunity"])
            if signals["opportunity"]
            else "—"
        )
        print(
            "🟡 Важно:",
            ", ".join(signals["important"])
            if signals["important"]
            else "—"
        )
        print(
            "🔴 Риски:",
            ", ".join(signals["risk"])
            if signals["risk"]
            else "—"
        )
        print("Дата:", entry.get("published", ""))
        print("Ссылка:", entry.get("link", ""))

    print("=" * 60)
    print(f"Релевантных для BCA: {final_relevant_count}")

    return {
        "total_publications": len(feed.entries),
        "candidate_count": len(relevant_entries),
        "relevant_count": final_relevant_count,
        "results": results,
        "all_publications": all_publications,
    }


if __name__ == "__main__":
    fetch_updates()

  