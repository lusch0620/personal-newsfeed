"""
fetch_feeds.py
Pulls RSS feeds and scrapes niche sources defined in config/sources.yaml.
Outputs: data/raw_articles.json
"""

import feedparser
import yaml
import json
import hashlib
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
import time

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "config" / "sources.yaml"
OUTPUT_PATH = ROOT / "data" / "raw_articles.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PersonalNewsFeed/1.0; +https://github.com/luciusgao/personal-newsfeed)"
}

MAX_AGE_HOURS = 24  # Only keep articles from the last 24 hours


def article_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def parse_date(entry) -> str:
    """Try to extract a parseable ISO date from a feedparser entry."""
    for attr in ["published_parsed", "updated_parsed"]:
        t = getattr(entry, attr, None)
        if t:
            try:
                dt = datetime(*t[:6], tzinfo=timezone.utc)
                return dt.isoformat()
            except Exception:
                pass
    return datetime.now(timezone.utc).isoformat()


def is_recent(date_str: str) -> bool:
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
        return dt > cutoff
    except Exception:
        return True  # Include if we can't determine age


def fetch_rss(name: str, url: str, section: str) -> list[dict]:
    articles = []
    try:
        feed = feedparser.parse(url, request_headers=HEADERS)
        for entry in feed.entries[:15]:  # Cap per source
            link = getattr(entry, "link", "")
            if not link:
                continue
            date = parse_date(entry)
            if not is_recent(date):
                continue
            articles.append({
                "id": article_id(link),
                "title": getattr(entry, "title", "").strip(),
                "url": link,
                "source": name,
                "section": section,
                "date": date,
                "summary_raw": getattr(entry, "summary", "")[:500],
                "summary_ai": None,  # Filled by summarize.py
            })
    except Exception as e:
        print(f"[RSS ERROR] {name}: {e}")
    return articles


def fetch_scrape(name: str, url: str, section: str) -> list[dict]:
    """Basic scraper for niche targets — extracts article links and titles."""
    articles = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Generic: find <a> tags with substantial text inside article/main elements
        candidates = []
        for tag in soup.select("article a, main a, .story a, .card a, h2 a, h3 a"):
            href = tag.get("href", "")
            title = tag.get_text(strip=True)
            if len(title) > 30 and href.startswith("http"):
                candidates.append((title, href))

        # Deduplicate by URL
        seen = set()
        for title, href in candidates[:20]:
            if href in seen:
                continue
            seen.add(href)
            articles.append({
                "id": article_id(href),
                "title": title,
                "url": href,
                "source": name,
                "section": section,
                "date": datetime.now(timezone.utc).isoformat(),
                "summary_raw": "",
                "summary_ai": None,
            })
        time.sleep(1)  # Be polite
    except Exception as e:
        print(f"[SCRAPE ERROR] {name}: {e}")
    return articles


def main():
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    all_articles = []
    seen_ids = set()

    section_map = {
        "fig_banks": "FIG — Banks",
        "fig_asset_wealth": "FIG — Asset & Wealth Management",
        "fig_insurance": "FIG — Insurance",
        "fig_specialty_finance": "FIG — Specialty Finance",
        "markets_broad": "Markets & Macro",
        "newsletters": "Newsletters",
    }

    for section_key, section_label in section_map.items():
        sources = config.get(section_key, [])
        for source in sources:
            print(f"Fetching [{section_label}] {source['name']}...")
            arts = fetch_rss(source["name"], source["url"], section_label)
            for a in arts:
                if a["id"] not in seen_ids:
                    seen_ids.add(a["id"])
                    all_articles.append(a)

    # Scrape niche targets
    for target in config.get("scrape_targets", []):
        if not target.get("enabled", True):
            continue
        print(f"Scraping {target['name']}...")
        # Scrape targets go into their most relevant section
        section = "Newsletters" if "newsletter" in target["name"].lower() else "FIG — Banks"
        if "axios" in target["name"].lower():
            section = "Newsletters"
        elif "pitchbook" in target["name"].lower():
            section = "Markets & Macro"
        arts = fetch_scrape(target["name"], target["url"], section)
        for a in arts:
            if a["id"] not in seen_ids:
                seen_ids.add(a["id"])
                all_articles.append(a)

    # Sort by date descending
    all_articles.sort(key=lambda x: x["date"], reverse=True)

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_articles, f, indent=2)

    print(f"\nDone. {len(all_articles)} articles written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
