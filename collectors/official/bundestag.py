import feedparser


BUNDESTAG_FEEDS = {
    "Drucksachen": "https://www.bundestag.de/static/appdata/includes/rss/drucksachen.rss",
    "Arbeit und Soziales": "https://www.bundestag.de/static/appdata/includes/rss/arbeitsoziales.rss",
    "Inneres": "https://www.bundestag.de/static/appdata/includes/rss/inneres.rss",
    "Recht und Verbraucherschutz": "https://www.bundestag.de/static/appdata/includes/rss/recht.rss",
}


def fetch_bundestag_publications(limit_per_feed=20):
    publications = []
    seen_links = set()

    for category, feed_url in BUNDESTAG_FEEDS.items():
        feed = feedparser.parse(feed_url)

        for entry in feed.entries[:limit_per_feed]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            published = entry.get("published", "").strip()
            summary = entry.get("summary", "").strip()

            if not title or not link:
                continue

            # Одна публикация Bundestag может появиться
            # одновременно в нескольких тематических RSS.
            if link in seen_links:
                continue

            seen_links.add(link)

            publications.append(
                {
                    "title": title,
                    "url": link,
                    "date": published,
                    "summary": summary,
                    "source": "Bundestag",
                    "category": category,
                }
            )

    return publications


if __name__ == "__main__":
    items = fetch_bundestag_publications()

    print("BUNDESTAG PUBLICATIONS:", len(items))
    print()

    for item in items[:10]:
        print("TITLE:", item["title"])
        print("CATEGORY:", item["category"])
        print("DATE:", item["date"])
        print("URL:", item["url"])
        print("-" * 80)