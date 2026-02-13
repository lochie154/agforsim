#!/usr/bin/env python3
"""
scrape_sources.py

Data-driven HTML scraper for code / data platforms.
Platform URLs, query parameters, and CSS selectors live in platforms.yaml;
this file provides one generic scrape function and the harvest loop.

No official APIs — just GET + BeautifulSoup.

Usage:
    python scripts/scrape_sources.py                        # default
    python scripts/scrape_sources.py --platforms p.yaml      # custom config
    python scripts/scrape_sources.py --delay 3 --max 5       # tune behaviour
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any

import requests
import yaml
from bs4 import BeautifulSoup, Tag

from query_list import iter_queries

# ── defaults ────────────────────────────────────────────────────────────────

DEFAULT_PLATFORMS = Path(__file__).with_name("platforms.yaml")
REQUEST_DELAY = 2.0
MAX_RESULTS = 10
REQUEST_TIMEOUT = 20
OUTPUT_JSON = "harvest_html_results.json"
OUTPUT_CSV = "harvest_html_results.csv"

HEADERS = {
    "User-Agent": "FoodForestHarvester/0.1 (+contact: your-email@example.com)"
}


# ── record helpers ──────────────────────────────────────────────────────────

def make_record(
    platform: str,
    title: str,
    url: str,
    snippet: str,
    source_query: str,
) -> dict[str, Any]:
    return {
        "platform": platform,
        "title": title.strip(),
        "url": url.strip(),
        "snippet": (snippet or "").strip(),
        "source_query": source_query,
    }


def save_json(path: str, records: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2, ensure_ascii=False)


def save_csv(path: str, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    keys = sorted(records[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        writer.writerows(records)


# ── platform config loader ─────────────────────────────────────────────────

def load_platforms(path: Path) -> dict[str, dict[str, Any]]:
    """Return {name: config} for every *enabled* platform in the YAML file."""
    with open(path, "r", encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh)
    return {
        name: cfg
        for name, cfg in raw.items()
        if isinstance(cfg, dict) and cfg.get("enabled", False)
    }


# ── generic scraper ────────────────────────────────────────────────────────

def _resolve_href(href: str, cfg: dict[str, Any]) -> str:
    """Turn a potentially relative *href* into an absolute URL."""
    strip = cfg.get("link", {}).get("href_strip")
    if strip and strip in href:
        href = href.replace(strip, "")

    if href.startswith("http"):
        return href

    base = cfg.get("base_url", "")
    if not href.startswith("/"):
        return base + "/" + href
    return base + href


def _extract_snippet(element: Tag, cfg: dict[str, Any]) -> str:
    """Pull description text from *element* using the snippet config."""
    snip_cfg = cfg.get("snippet", {})
    if not snip_cfg or not snip_cfg.get("selector"):
        return ""

    context = snip_cfg.get("context", "")
    selector = snip_cfg["selector"]

    # Look inside a parent container when requested.
    if context == "parent_div":
        parent = element.find_parent("div")
        target = parent if parent else element
    elif context == "parent_li_or_div":
        target = element.find_parent("li") or element.find_parent("div") or element
    else:
        target = element

    tag = target.select_one(selector) if target else None
    return tag.text.strip() if tag else ""


def scrape_platform(
    name: str,
    cfg: dict[str, Any],
    query: str,
    *,
    max_results: int = MAX_RESULTS,
) -> list[dict[str, Any]]:
    """
    Generic HTML scraper driven entirely by a platform config dict.

    Supports two modes controlled by ``cfg``:
    * **search mode** (default) — sends *query* as a query-string parameter.
    * **filter mode** (``filter_mode: "contains"``) — fetches a static index
      page and keeps only entries whose title contains *query*.
    """
    search_url: str = cfg["search_url"]
    filter_mode: str | None = cfg.get("filter_mode")

    # ── fetch the page ──────────────────────────────────────────────────
    params: dict[str, str] = dict(cfg.get("extra_params", {}) or {})
    qp = cfg.get("query_param")
    if qp:
        params[qp] = query

    resp = requests.get(
        search_url, headers=HEADERS, params=params or None, timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        print(f"  [{name}] HTTP {resp.status_code}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    records: list[dict[str, Any]] = []

    # ── iterate result elements ─────────────────────────────────────────
    for el in soup.select(cfg["result_selector"]):
        # --- title ---
        title_cfg = cfg.get("title", {})
        title_sel = title_cfg.get("selector") if title_cfg else None
        if title_sel:
            title_tag = el.select_one(title_sel)
            title = title_tag.text.strip() if title_tag else ""
        else:
            title = el.text.strip()

        # --- filter mode: skip non-matching rows ---
        if filter_mode == "contains":
            if query.lower() not in title.lower():
                continue

        # --- link / href ---
        link_cfg = cfg.get("link", {})
        link_sel = link_cfg.get("selector") if link_cfg else None
        attr = (link_cfg.get("attr") if link_cfg else None) or "href"

        if link_sel:
            link_tag = el.select_one(link_sel)
        else:
            link_tag = el  # the result element itself is the <a>

        href = (link_tag.get(attr, "") if link_tag else "") or ""
        if not href:
            continue
        full_url = _resolve_href(href, cfg)

        # --- snippet ---
        snippet = _extract_snippet(el, cfg)

        records.append(make_record(name, title, full_url, snippet, query))
        if len(records) >= max_results:
            break

    return records


# ── harvest loop ────────────────────────────────────────────────────────────

def scrape_all(
    platforms: dict[str, dict[str, Any]],
    query: str,
    *,
    max_results: int = MAX_RESULTS,
    delay: float = REQUEST_DELAY,
) -> list[dict[str, Any]]:
    """Run every enabled platform for a single *query*."""
    all_records: list[dict[str, Any]] = []
    for name, cfg in platforms.items():
        try:
            print(f"  → {name} for '{query}'")
            recs = scrape_platform(name, cfg, query, max_results=max_results)
            print(f"    {len(recs)} results")
            all_records.extend(recs)
        except Exception as exc:
            print(f"  [WARN] {name} failed for '{query}': {exc}")
        time.sleep(delay)
    return all_records


# ── CLI ─────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="HTML source scraper")
    ap.add_argument(
        "--platforms", type=Path, default=DEFAULT_PLATFORMS,
        help="Path to platforms YAML config (default: platforms.yaml)",
    )
    ap.add_argument("--delay", type=float, default=REQUEST_DELAY)
    ap.add_argument("--max", type=int, default=MAX_RESULTS, dest="max_results")
    ap.add_argument("--out-json", default=OUTPUT_JSON)
    ap.add_argument("--out-csv", default=OUTPUT_CSV)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    platforms = load_platforms(args.platforms)

    if not platforms:
        print("No enabled platforms found — check platforms.yaml")
        return

    print(f"Enabled platforms: {', '.join(platforms)}")

    all_records: list[dict[str, Any]] = []
    for lang, term in iter_queries():
        print(f"\n=== {lang}: '{term}' ===")
        recs = scrape_all(
            platforms, term, max_results=args.max_results, delay=args.delay,
        )
        all_records.extend(recs)

    # dedupe by URL
    by_url: dict[str, dict[str, Any]] = {}
    for rec in all_records:
        by_url[rec["url"]] = rec
    final = list(by_url.values())

    print(f"\nTotal unique records: {len(final)}")
    save_json(args.out_json, final)
    save_csv(args.out_csv, final)
    print(f"Saved to {args.out_json} and {args.out_csv}")


if __name__ == "__main__":
    main()
