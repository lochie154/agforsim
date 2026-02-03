#!/usr/bin/env python3
"""
scrape_sources.py

HTML-only, low-bloat scraper for multiple code / data platforms.
No official APIs, just GET + BeautifulSoup.

Currently implemented:
  - GitHub
  - GitLab
  - PyPI
  - CRAN
  - Zenodo

Stubs (pattern ready, you fill selectors later):
  - Figshare
  - OSF
  - Dryad
  - JuliaHub
  - Bioconductor
  - Gitee
  - CSDN
  - 51CTO
  - Habr
  - Qiita
  - Agrolivre
  - WUR

Be polite:
  - small delay between requests
  - small number of results per site
"""

import time
import json
import csv
from typing import List, Dict, Any

import requests
from bs4 import BeautifulSoup

from queries import iter_queries

REQUEST_DELAY = 2.0       # seconds between requests
MAX_RESULTS_PER_SITE = 10 # per query per site

OUTPUT_JSON = "harvest_html_results.json"
OUTPUT_CSV = "harvest_html_results.csv"

HEADERS = {
    "User-Agent": "FoodForestHarvester/0.1 (+contact: your-email@example.com)"
}


# ---------- BASIC RECORD FORMAT ----------

def make_record(platform: str,
                title: str,
                url: str,
                snippet: str,
                source_query: str) -> Dict[str, Any]:
    return {
        "platform": platform,
        "title": title.strip(),
        "url": url.strip(),
        "snippet": (snippet or "").strip(),
        "source_query": source_query,
    }


def save_results_json(path: str, records: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


def save_results_csv(path: str, records: List[Dict[str, Any]]) -> None:
    if not records:
        return
    keys = sorted(records[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for r in records:
            writer.writerow(r)


# ---------- GITHUB (HTML search) ----------

def scrape_github(query: str) -> List[Dict[str, Any]]:
    """
    Scrape GitHub search via HTML.
    URL pattern: https://github.com/search?q=<query>&type=repositories
    """
    url = "https://github.com/search"
    params = {"q": query, "type": "repositories"}
    resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
    if resp.status_code != 200:
        print(f"[github] HTTP {resp.status_code} for {query}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    records: List[Dict[str, Any]] = []

    # This selector may need tweaking if GitHub changes layout.
    for a in soup.select("a.v-align-middle"):
        href = a.get("href", "")
        if not href.startswith("/"):
            continue
        full_url = "https://github.com" + href
        title = a.text.strip()
        # Try to find nearby description
        desc_tag = a.find_parent("div")
        snippet = ""
        if desc_tag:
            p = desc_tag.find_next("p")
            if p:
                snippet = p.text.strip()

        records.append(make_record("github", title, full_url, snippet, query))
        if len(records) >= MAX_RESULTS_PER_SITE:
            break

    return records


# ---------- GITLAB (HTML search) ----------

def scrape_gitlab(query: str) -> List[Dict[str, Any]]:
    """
    Scrape GitLab project search via HTML.
    URL pattern (public GitLab):
      https://gitlab.com/search?search=<query>&scope=projects
    """
    url = "https://gitlab.com/search"
    params = {"search": query, "scope": "projects"}
    resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
    if resp.status_code != 200:
        print(f"[gitlab] HTTP {resp.status_code} for {query}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    records: List[Dict[str, Any]] = []

    # Selector may change; this is approximate.
    for link in soup.select("a.search-result-link"):
        href = link.get("href", "")
        if not href:
            continue
        full_url = href if href.startswith("http") else "https://gitlab.com" + href
        title = link.text.strip()
        # Try to get snippet in the surrounding element
        parent = link.find_parent("li") or link.find_parent("div")
        snippet = ""
        if parent:
            desc = parent.find("p")
            if desc:
                snippet = desc.text.strip()

        records.append(make_record("gitlab", title, full_url, snippet, query))
        if len(records) >= MAX_RESULTS_PER_SITE:
            break

    return records


# ---------- PYPI (HTML search) ----------

def scrape_pypi(query: str) -> List[Dict[str, Any]]:
    """
    Scrape PyPI search via HTML.
    URL pattern:
      https://pypi.org/search/?q=<query>
    """
    url = "https://pypi.org/search/"
    params = {"q": query}
    resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
    if resp.status_code != 200:
        print(f"[pypi] HTTP {resp.status_code} for {query}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    records: List[Dict[str, Any]] = []

    for proj in soup.select("a.package-snippet"):
        href = proj.get("href", "")
        full_url = "https://pypi.org" + href
        name_tag = proj.select_one("span.package-snippet__name")
        ver_tag = proj.select_one("span.package-snippet__version")
        desc_tag = proj.select_one("p.package-snippet__description")

        title = ""
        if name_tag:
            title = name_tag.text.strip()
            if ver_tag:
                title += f" {ver_tag.text.strip()}"

        snippet = desc_tag.text.strip() if desc_tag else ""

        records.append(make_record("pypi", title, full_url, snippet, query))
        if len(records) >= MAX_RESULTS_PER_SITE:
            break

    return records


# ---------- CRAN (HTML search) ----------

def scrape_cran(query: str) -> List[Dict[str, Any]]:
    """
    Very simple CRAN search shim using the web search page.
    URL pattern:
      https://cran.r-project.org/web/packages/available_packages_by_name.html
    That page lists all packages; but CRAN also has a web search:
      https://cran.r-project.org/web/packages/available_packages_by_name.html
    To keep it light, hit the CRAN package-by-name page once, then filter.
    """
    url = "https://cran.r-project.org/web/packages/available_packages_by_name.html"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    if resp.status_code != 200:
        print(f"[cran] HTTP {resp.status_code} when loading index")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    records: List[Dict[str, Any]] = []

    # Each package is an <a href="../package/pkgname/index.html">Name</a>
    for a in soup.select("table a"):
        name = a.text.strip()
        if query.lower() not in name.lower():
            continue
        href = a.get("href", "")
        if "../" in href:
            href = href.replace("../", "")
        full_url = "https://cran.r-project.org/web/packages/" + href
        records.append(make_record("cran", name, full_url, "", query))
        if len(records) >= MAX_RESULTS_PER_SITE:
            break

    return records


# ---------- ZENODO (HTML search) ----------

def scrape_zenodo(query: str) -> List[Dict[str, Any]]:
    """
    Scrape Zenodo HTML search.
    URL pattern:
      https://zenodo.org/search?q=<query>
    """
    url = "https://zenodo.org/search"
    params = {"q": query}
    resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
    if resp.status_code != 200:
        print(f"[zenodo] HTTP {resp.status_code} for {query}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    records: List[Dict[str, Any]] = []

    # Each result is usually in an 'article' with a title link
    for art in soup.select("article"):
        title_link = art.find("a")
        if not title_link:
            continue
        href = title_link.get("href", "")
        full_url = href if href.startswith("http") else "https://zenodo.org" + href
        title = title_link.text.strip()

        # Try to find a summary snippet
        snippet = ""
        desc_tag = art.find("p")
        if desc_tag:
            snippet = desc_tag.text.strip()

        records.append(make_record("zenodo", title, full_url, snippet, query))
        if len(records) >= MAX_RESULTS_PER_SITE:
            break

    return records


# ---------- STUBS FOR THE REST (PATTERN READY) ----------

def scrape_figshare(query: str) -> List[Dict[str, Any]]:
    """
    TODO: implement HTML search for Figshare:
      - Search page: https://figshare.com/search?q=<query>
      - Parse result cards: title + link + snippet
    """
    return []


def scrape_osf(query: str) -> List[Dict[str, Any]]:
    """
    TODO: implement HTML search for OSF:
      - Search: https://osf.io/search/?q=<query>
    """
    return []


def scrape_dryad(query: str) -> List[Dict[str, Any]]:
    """
    TODO: implement HTML search for Dryad:
      - Search: https://datadryad.org/search?q=<query>
    """
    return []


def scrape_juliahub(query: str) -> List[Dict[str, Any]]:
    """
    TODO: implement HTML search for JuliaHub:
      - Search: https://juliahub.com/search?q=<query>
    """
    return []


def scrape_bioconductor(query: str) -> List[Dict[str, Any]]:
    """
    TODO: Bioconductor software listing is HTML; you can:
      - Scrape package list page
      - Filter by query in name/description
    """
    return []


def scrape_gitee(query: str) -> List[Dict[str, Any]]:
    """
    TODO: Gitee search (Chinese Git hosting):
      - Search: https://search.gitee.com/?q=<query>&type=repository
    """
    return []


def scrape_csdn(query: str) -> List[Dict[str, Any]]:
    """
    TODO: CSDN search:
      - Search for blog posts / code snippets with your query
      - Extract any repo links from result cards
    """
    return []


def scrape_51cto(query: str) -> List[Dict[str, Any]]:
    """
    TODO: Similar approach to CSDN.
    """
    return []


def scrape_habr(query: str) -> List[Dict[str, Any]]:
    """
    TODO: Habr search:
      - Parse article list and pull out repo links.
    """
    return []


def scrape_qiita(query: str) -> List[Dict[str, Any]]:
    """
    TODO: Qiita search:
      - https://qiita.com/search?q=<query>
      - Extract article titles and URLs
      - Optionally parse article pages for GitHub/GitLab links
    """
    return []


def scrape_agrolivre(query: str) -> List[Dict[str, Any]]:
    """
    TODO: Depending on Agrolivre site structure:
      - Find project catalogue page
      - Filter entries containing query
    """
    return []


def scrape_wur(query: str) -> List[Dict[str, Any]]:
    """
    TODO: WUR (Wageningen) research/software:
      - Either scrape WUR's open data portal
      - Or target WUR GitHub org directly (that's back to GitHub)
    """
    return []


# ---------- CENTRAL HARVEST LOOP ----------

def scrape_all_for_query(query: str) -> List[Dict[str, Any]]:
    all_records: List[Dict[str, Any]] = []

    platforms = [
        ("github", scrape_github),
        ("gitlab", scrape_gitlab),
        ("pypi", scrape_pypi),
        ("cran", scrape_cran),
        ("zenodo", scrape_zenodo),
        # Add the others as you implement them:
        ("figshare", scrape_figshare),
        ("osf", scrape_osf),
        ("dryad", scrape_dryad),
        ("juliahub", scrape_juliahub),
        ("bioconductor", scrape_bioconductor),
        ("gitee", scrape_gitee),
        ("csdn", scrape_csdn),
        ("51cto", scrape_51cto),
        ("habr", scrape_habr),
        ("qiita", scrape_qiita),
        ("agrolivre", scrape_agrolivre),
        ("wur", scrape_wur),
    ]

    for name, func in platforms:
        try:
            print(f"  → {name} for '{query}'")
            recs = func(query)
            print(f"    {len(recs)} results")
            all_records.extend(recs)
        except Exception as e:
            print(f"[WARN] {name} failed for '{query}': {e}")
        time.sleep(REQUEST_DELAY)

    return all_records


def main():
    all_records: List[Dict[str, Any]] = []

    for lang, term in iter_queries():
        print(f"\n=== {lang}: '{term}' ===")
        recs = scrape_all_for_query(term)
        all_records.extend(recs)

    # dedupe by URL
    by_url: Dict[str, Dict[str, Any]] = {}
    for r in all_records:
        by_url[r["url"]] = r

    final = list(by_url.values())
    print(f"\nTotal unique records: {len(final)}")

    save_results_json(OUTPUT_JSON, final)
    save_results_csv(OUTPUT_CSV, final)
    print(f"Saved to {OUTPUT_JSON} and {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
