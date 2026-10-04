import requests
from bs4 import BeautifulSoup

BAMF_URL = "https://www.bamf.de/DE/Startseite/startseite_node.html"


def fetch_bamf_publications():
    response = requests.get(BAMF_URL, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    publications = []

    for link in soup.find_all("a", href=True):
            title = link.get_text(" ", strip=True)
            href = link["href"]
            if title and title.lower() != "weiterlesen" and "/SharedDocs/" in href:
               publications.append({
                    "title": title,
                    "url": href,
                    "source": "BAMF",
                    "source_type": "official",
                })

    return publications