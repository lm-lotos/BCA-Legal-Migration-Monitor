import requests
from bs4 import BeautifulSoup

BA_WEISUNGEN_URL = "https://www.arbeitsagentur.de/ueber-uns/veroeffentlichungen/weisungen"

def fetch_ba_weisungen():
    response = requests.get(BA_WEISUNGEN_URL, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    publications = []
    for link in soup.find_all("a", href=True):
        title = link.get_text(" ", strip=True)
        href = str(link["href"])
        title = title.replace("Öffnet in neuem Tab ", "")
        title = title.split(" pdf |")[0].strip()
        if title and "weisung" in title.lower() and ("sgb ii" in title.lower() or "jobcenter" in title.lower()):
            publications.append({
                "title": title,
                "url": href,
                "source": "BA Weisungen",
            })
    return publications