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
}

SYSTEM_PROMPT = """You are a financial analyst assistant working for a senior investment banking analyst
at a bulge-bracket FIG group. You read financial news and extract the signal from the noise.

For each article, return a JSON object with exactly these fields:
{
  "digest": "2-3 sentence summary hitting the key facts, numbers, and so-what. No fluff.",
  "highlight": "1 sentence pulling out the most actionable detail for an IB analyst — deal size, regulatory impact, M&A angle, or capital implication. Null if not FIG-relevant.",
  "relevance": <integer 1-10 where 10 = directly relevant to FIG IB deal flow, 1 = tangentially related>
}

Be terse. Avoid adjectives. If the article is low-signal (opinion, evergreen content, generic commentary),
set relevance ≤ 4. Prioritize: deal announcements, regulatory changes, capital actions, M&A,
earnings that signal sector trends, and personnel moves at major institutions."""


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
