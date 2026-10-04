import requests
from bs4 import BeautifulSoup

BA_URL = "https://www.arbeitsagentur.de/news"


def fetch_ba_publications():
    response = requests.get(BA_URL, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    publications = []

    for link in soup.find_all("a", href=True):
        title = link.get_text(" ", strip=True)
        href = str(link["href"])
        if title and href.startswith("/"):
            publications.append({
                "title": title,
                "url": "https://www.arbeitsagentur.de" + href,
                "source": "Bundesagentur für Arbeit",
        })
            
    return publications
