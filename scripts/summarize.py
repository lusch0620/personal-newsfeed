"""
summarize.py
Reads raw_articles.json, calls Anthropic API (Claude Haiku) to generate:
  - 2-3 sentence AI digest per article
  - Deal/regulatory highlights for FIG stories
  - Relevance score (1-10) for prioritization
Outputs: data/feeds.json (the final file the site reads)

Cost: ~$0.10-0.30/month at typical volume with Haiku pricing.
"""

import anthropic
import json
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent
RAW_PATH = ROOT / "data" / "raw_articles.json"
OUTPUT_PATH = ROOT / "data" / "feeds.json"

# Only summarize articles with enough raw content or title length
MIN_TITLE_LEN = 20

# Skip re-summarizing if we already have a summary (incremental runs)
INCREMENTAL = True

FIG_SECTIONS = {
    "FIG — Banks",
    "FIG — Asset & Wealth Management",
    "FIG — Insurance",
    "FIG — Specialty Finance",
    "PE & Deals",
}

SYSTEM_PROMPT = """You are reading financial news for Lucius Gao, a Senior Analyst in the Financial Institutions Group at Cantor Fitzgerald (boutique). He built the FIG practice from scratch. Coverage: regional banks, fintech, digital/alternative assets, IRA platforms, specialty finance, asset and wealth management. He is actively looking to lateral to a bulge-bracket or elite boutique FIG team, or break into PE with a financial services focus.

For each article, return a JSON object with exactly these fields:
{
  "digest": "2-3 sentences. Lead with the key fact, number, or name. No adjectives, no filler.",
  "highlight": "1 sentence on the single most actionable detail: deal size and structure, acquirer/target names, regulatory trigger with M&A implications, capital raise terms, or senior banker move. Null if nothing actionable.",
  "relevance": <integer 1-10>
}

Relevance scoring:
10 — M&A deal announced with size; bank capital raise; regulatory action that catalyzes consolidation; fintech acquisition or strategic review; PE fund deploying into financial services
9  — Earnings with clear M&A or capital implication; bank stress test result; major regulatory enforcement; senior banker move between institutions
8  — PE fundraising (financial services); fintech valuation event; credit market signal affecting FIG deal flow; FDIC/OCC policy change
7  — Sector trend with deal flow read-through; RIA M&A; insurance consolidation
≤4 — Opinion, evergreen, generic macro with no FIG angle, non-finance content

Be terse. If it would bore an IB analyst on a live mandate, score ≤ 4."""


def build_user_prompt(article: dict) -> str:
    title = article.get("title", "")
    raw = article.get("summary_raw", "")
    section = article.get("section", "")
    source = article.get("source", "")
    is_fig = section in FIG_SECTIONS

    content = f"Title: {title}\nSource: {source}\nSection: {section}\n"
    if raw:
        content += f"Excerpt: {raw[:400]}\n"
    if is_fig:
        content += "\nThis is a FIG-specific article. Extract deal/regulatory/capital highlights."

    return content


def summarize_batch(client: anthropic.Anthropic, articles: list[dict]) -> list[dict]:
    """Summarize articles. Each call is individual to keep prompts focused."""
    results = []
    for i, article in enumerate(articles):
        if INCREMENTAL and article.get("summary_ai"):
            results.append(article)
            continue

        title = article.get("title", "")
        if len(title) < MIN_TITLE_LEN:
            article["summary_ai"] = {"digest": title, "highlight": None, "relevance": 3}
            results.append(article)
            continue

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_prompt(article)}],
            )
            text = response.content[0].text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            parsed = json.loads(text)
            article["summary_ai"] = parsed
        except json.JSONDecodeError:
            article["summary_ai"] = {
                "digest": article.get("summary_raw", title)[:200],
                "highlight": None,
                "relevance": 5,
            }
        except Exception as e:
            print(f"  [AI ERROR] {title[:50]}: {e}")
            article["summary_ai"] = {
                "digest": title,
                "highlight": None,
                "relevance": 5,
            }

        results.append(article)
        if (i + 1) % 10 == 0:
            print(f"  Summarized {i + 1}/{len(articles)}")

    return results


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)

    with open(RAW_PATH) as f:
        articles = json.load(f)

    print(f"Summarizing {len(articles)} articles...")
    articles = summarize_batch(client, articles)

    # Sort by relevance (desc), then date (desc)
    def sort_key(a):
        rel = (a.get("summary_ai") or {}).get("relevance", 5)
        return (-rel, a.get("date", "") or "")

    articles.sort(key=sort_key)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(articles, f, indent=2)

    print(f"Done. {len(articles)} articles written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
