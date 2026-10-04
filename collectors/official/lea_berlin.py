import requests
from bs4 import BeautifulSoup

LEA_AKTUELLES_URL = "https://www.berlin.de/einwanderung/ueber-uns/aktuelles/"

def fetch_lea_page():
    response = requests.get(LEA_AKTUELLES_URL, timeout=20)
    response.raise_for_status()

    return response.text

def parse_lea_page(html):
    soup = BeautifulSoup(html, "html.parser")

    return soup
def get_lea_publications():
    html = fetch_lea_page()
    soup = parse_lea_page(html)

    publications = []

    for link in soup.find_all("a"):
        text = link.get_text(" ", strip=True)
        href = link.get("href") or ""

        if text and "/einwanderung/ueber-uns/aktuelles/artikel." in href:
            publications.append({
                "title": text,
                "url": "https://www.berlin.de" + str(href),
                "source": "LEA Berlin",
                "source_type": "official",
            })

    return publications

