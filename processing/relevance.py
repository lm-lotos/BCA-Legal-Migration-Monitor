from __future__ import annotations

import re
from collectors.official.gesetze_rss import calculate_relevance

EXTRA_TERMS = {
    "Blue Card": 7, "Blaue Karte": 7, "Chancenkarte": 7,
    "Aufenthalt": 5, "Aufenthaltstitel": 6, "Einbürgerung": 6,
    "Staatsangehörigkeit": 6, "Fachkräfteeinwanderung": 7,
    "Familiennachzug": 6, "Visum": 5, "Ausländerbehörde": 6,
    "Arbeitsmigration": 6, "Arbeitserlaubnis": 6, "Berufsanerkennung": 6,
    "Migration": 3, "Einwanderung": 4, "Fachkräfte": 3,
    "Jobcenter": 7, "Bürgergeld": 7, "SGB II": 7, "SGB III": 6,
    "Arbeitslos": 6, "arbeitssuchend": 6, "Weiterbildung": 6, "Bildungsgutschein": 7,
    "Ukraine": 3, "Asyl": 4, "Abschiebung": 4,
}


def _text(item: dict) -> str:
    return " ".join(str(item.get(k, "")) for k in ("title", "document_title", "summary", "description"))


def score_item(item: dict) -> dict:
    text = _text(item)
    base = calculate_relevance(text)
    score = int(base.get("score", 0) or 0)
    topics = list(base.get("topics") or [])
    reasons = list(base.get("reasons") or [])

    lower = text.lower()
    for term, weight in EXTRA_TERMS.items():
        if term.lower() in lower and score < weight:
            score = weight
    if re.search(r"§\s*(18[abdg]?|19c|20[ab]?|24|25|29|30|31|32|36|51|81|104c)\b", text, re.I):
        score = max(score, 8)
        if "relevanter §" not in topics:
            topics.append("relevanter §")

    if score >= 9:
        level = "GREEN"
    elif score >= 6:
        level = "YELLOW"
    elif score > 0:
        level = "RED"
    else:
        level = "DROP"

    result = dict(item)
    
    # Add canonical multi-label topics without removing source-specific topics.
    temp = dict(item)
    temp["topics"] = topics
    for topic in canonical_topics(temp):
        if topic not in topics:
            topics.append(topic)
    result.update({"bca_score": score, "relevance_level": level, "topics": topics[:16], "reasons": reasons[:8]})
    return result


def filter_relevant(items: list[dict]) -> list[dict]:
    result = []
    for item in items or []:
        scored = score_item(item)
        if scored["relevance_level"] != "DROP":
            result.append(scored)
    return result


def light(level: str) -> str:
    return {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(level, "⚪")


def counts(items: list[dict]) -> dict:
    return {
        "total": len(items),
        "green": sum(x.get("relevance_level") == "GREEN" for x in items),
        "yellow": sum(x.get("relevance_level") == "YELLOW" for x in items),
        "red": sum(x.get("relevance_level") == "RED" for x in items),
    }

# Canonical multi-label BCA taxonomy. A publication may belong to many groups.
TOPIC_ALIASES = {
    "Aufenthalt / ВНЖ": ["aufenthalt", "aufenthaltstitel", "aufenthg", "niederlassungserlaubnis", "daueraufenthalt"],
    "§24 / временная защита / Украина": ["§ 24", "§24", "ukraine", "ukrainer", "vorübergehender schutz", "temporary protection"],
    "Asyl / убежище / Flüchtlinge": ["asyl", "flüchtling", "schutzsuch", "geas", "internationaler schutz"],
    "Blue Card / Blaue Karte EU": ["blue card", "blaue karte"],
    "Chancenkarte / поиск работы": ["chancenkarte", "arbeitsplatzsuche", "punktesystem"],
    "Fachkräfte / трудовая миграция": ["fachkräft", "arbeitsmigration", "erwerbsmigration", "beschäftigung", "arbeitserlaubnis"],
    "Einbürgerung / гражданство": ["einbürger", "staatsangehör", "stag", "mehrstaatigkeit"],
    "Familiennachzug / семья": ["familiennachzug", "familienzusammenführung", "ehegattennachzug", "kindernachzug", "elternnachzug"],
    "Anerkennung / квалификации": ["anerkennung", "berufsqualifikation", "gleichwertigkeit", "zab", "zeugnisbewertung", "bqfg"],
    "Jobcenter / Bürgergeld / SGB II": ["jobcenter", "bürgergeld", "sgb ii", "grundsicherung"],
    "Agentur für Arbeit / SGB III": ["agentur für arbeit", "bundesagentur für arbeit", "sgb iii", "arbeitsförderung"],
    "Arbeitslos / arbeitssuchend": ["arbeitslos", "arbeitssuchend", "arbeitsuchend", "arbeitslosengeld"],
    "Sozialleistungen / выплаты": ["sozialleistung", "wohngeld", "kinderzuschlag", "sozialhilfe", "leistungen nach"],
    "Ausbildung / Weiterbildung": ["ausbildung", "weiterbildung", "qualifizierung", "umschulung", "bildungsgutschein"],
    "Studium / Studenten": ["studium", "studierende", "student", "hochschule"],
    "Sprache / Integration": ["integrationskurs", "berufssprach", "deutschkurs", "integration"],
    "Visum / Einreise": ["visum", "visa", "einreise", "auslandsvertretung", "botschaft", "konsulat"],
    "Ausländerbehörde / Verwaltung": ["ausländerbehörde", "landesamt für einwanderung", "lea berlin"],
    "Duldung": ["duldung", "geduldet"],
    "Abschiebung / Rückführung": ["abschieb", "rückführung", "ausreisepflicht"],
    "Selbständigkeit / бизнес": ["selbständig", "selbstständig", "freiberuf", "gründung"],
    "Gesetzgebung / парламент": ["gesetzentwurf", "bundestag", "bundesrat", "kleine anfrage", "drucksache", "ausschuss"],
}


def canonical_topics(item: dict) -> list[str]:
    text = _text(item).lower() + " " + " ".join(map(str, item.get("topics") or [])).lower()
    return [name for name, aliases in TOPIC_ALIASES.items() if any(a in text for a in aliases)]
