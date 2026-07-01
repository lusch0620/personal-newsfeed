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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT        = Path(__file__).parent.parent
RAW_PATH    = ROOT / "data" / "raw_articles.json"
OUTPUT_PATH = ROOT / "data" / "feeds.json"
NOTES_PATH  = ROOT / "data" / "notes.md"
DOCS_FEEDS_PATH = ROOT / "docs" / "data" / "feeds.json"  # last published feed (committed, survives across CI runs)

# Only summarize articles with enough raw content or title length
MIN_TITLE_LEN = 20

# Skip re-summarizing if we already have a summary (incremental runs)
INCREMENTAL = True

# Concurrency — Haiku rate limit is 50 req/min on free tier, 1000 on paid
# 8 workers keeps us comfortably under paid tier limits with room for retries
MAX_WORKERS = 8

# Retry settings
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # seconds, doubled each retry

FIG_SECTIONS = {
    "FIG — Banks",
    "FIG — Asset & Wealth Management",
    "FIG — Insurance",
    "FIG — Specialty Finance",
    "PE & Deals",
}

SYSTEM_PROMPT = """You are reading the daily feed for Lucius Gao, a Senior Analyst in the Financial Institutions Group at Cantor Fitzgerald (boutique). He built the FIG practice from scratch. Coverage: regional banks, fintech, digital/alternative assets, IRA platforms, specialty finance, asset and wealth management. He is actively looking to lateral to a bulge-bracket or elite boutique FIG team, or break into PE with a financial services focus.

His feed spans five lanes. Score each article ONLY against the rubric for its own lane — do not penalize a Career or Learn piece for lacking a deal angle, and do not reward a deal piece for being interesting reading.

For each article, return a JSON object with exactly these fields:
{
  "digest": "2-3 sentences. Lead with the key fact, number, name, or argument. No adjectives, no filler.",
  "summary_long": "4-6 sentences. Enough context to extract talking points without opening the source. Explain the why and the so-what, not just the what.",
  "talking_points": [
    "Punchy, self-contained point a reader can say out loud in a meeting.",
    "Second point with the supporting number, name, or implication.",
    "Optional third point — only if genuinely distinct from the above."
  ],
  "topics": ["short-keyword-tag", "another-tag"],
  "highlight": "1 sentence on the single most actionable or memorable detail. Null if nothing stands out.",
  "relevance": <integer 1-10>
}

topics: 3-5 concise keyword tags capturing the article's themes. Prefer specific over generic: "regional bank M&A" not "mergers", "Fed rate path" not "interest rates", "RIA consolidation" not "wealth management". These power a personalization algorithm so keep them consistent across articles on the same theme.

=== LANE A — FIG, PE & Deals (sections: FIG — Banks, FIG — Asset & Wealth Management, FIG — Insurance, FIG — Specialty Finance, PE & Deals) ===
10 — M&A deal announced with size; bank capital raise; regulatory action that catalyzes consolidation; fintech acquisition or strategic review; PE fund deploying into financial services
9  — Earnings with clear M&A or capital implication; bank stress test result; major regulatory enforcement; senior banker move between institutions
8  — PE fundraising (financial services); fintech valuation event; credit market signal affecting FIG deal flow; FDIC/OCC policy change
7  — Sector trend with deal-flow read-through; RIA M&A; insurance consolidation
≤4 — Opinion, evergreen, generic macro with no FIG angle
For these, the highlight MUST extract the deal/regulatory/capital detail: size and structure, acquirer/target, regulatory trigger, capital terms, or banker move.

=== LANE B — Markets & Macro (section: Markets & Macro) ===
Score on decision-usefulness for someone running FIG/credit/rates exposure, not on whether a deal is named.
10 — Rates/credit/liquidity signal that changes the FIG deal or financing environment; bank-sector data with clear read-through
8-9 — Sharp macro analysis that reframes the cycle, credit conditions, or a sector he covers
6-7 — Solid market context worth knowing; good data with a clear takeaway
≤4 — Routine market recap, price-action noise, horoscope-style commentary

=== LANE C — Newsletters (section: Newsletters) ===
These are hand-picked sharp finance voices (Net Interest, The Diff, Daily Upside). Default to valuing them — they are pre-filtered.
8-10 — Original analysis on banks, fintech, capital markets, or business strategy with a non-obvious insight
6-7 — Good explainer or roundup worth a skim
≤4 — Pure rehash of a headline he'd see elsewhere

=== LANE D — Career Intel (section: Career Intel) ===
Score for an analyst targeting a lateral move to a top FIG team or financial-services PE.
8-10 — Comp data, hiring/layoff trends at banks or PE, lateral-market movement, bonus numbers, interview/recruiting signal
6-7 — Useful career or industry-labor context
≤4 — Generic careers fluff, unrelated job listings

=== LANE E — Learn (section: Learn) ===
These are hand-picked for durable insight (Stratechery, The Generalist, Big Technology, Noahpinion, Marginal Revolution, Construction Physics). Judge by quality of thinking, not finance proximity.
8-10 — Genuinely makes you think differently about business strategy, economics, technology, or how the world works; a frame he can reuse
6-7 — Solid, well-argued piece worth reading
≤4 — Thin take, pure news rehash, off-topic personal post

Be terse and ruthless WITHIN each lane. The goal is signal: a 9 should be rare in any lane and mean "read this today.\""""


def build_user_prompt(article: dict) -> str:
    title   = article.get("title", "")
    raw     = article.get("summary_raw", "")
    section = article.get("section", "")
    source  = article.get("source", "")
    is_fig  = section in FIG_SECTIONS

    content = f"Title: {title}\nSource: {source}\nSection: {section}\n"
    if raw:
        content += f"Excerpt: {raw[:400]}\n"
    if is_fig:
        content += "\nThis is a FIG-specific article. Extract deal/regulatory/capital highlights."
    return content


def parse_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def summarize_one(client: anthropic.Anthropic, article: dict, system: str) -> dict:
    """Summarize a single article with exponential-backoff retry."""
    title = article.get("title", "")

    # Skip short titles
    if len(title) < MIN_TITLE_LEN:
        article["summary_ai"] = {
            "digest": title, "summary_long": "", "talking_points": [],
            "topics": [], "highlight": None, "relevance": 3,
        }
        return article

    # Skip already-summarized articles (incremental mode)
    existing = article.get("summary_ai")
    if INCREMENTAL and existing and existing.get("summary_long") and existing.get("talking_points") and existing.get("topics"):
        return article

    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=700,
                system=system,
                messages=[{"role": "user", "content": build_user_prompt(article)}],
            )
            article["summary_ai"] = parse_response(response.content[0].text)
            return article
        except json.JSONDecodeError:
            # Bad JSON from model — use raw excerpt as fallback, don't retry
            article["summary_ai"] = {
                "digest": article.get("summary_raw", title)[:200],
                "summary_long": "", "talking_points": [], "topics": [],
                "highlight": None, "relevance": 5,
            }
            return article
        except anthropic.RateLimitError:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"  [RATE LIMIT] retrying in {delay:.0f}s — {title[:40]}")
                time.sleep(delay)
            else:
                print(f"  [RATE LIMIT] giving up after {MAX_RETRIES} attempts — {title[:40]}")
                article["summary_ai"] = {
                    "digest": title, "summary_long": "", "talking_points": [],
                    "topics": [], "highlight": None, "relevance": 5,
                }
                return article
        except Exception as e:
            print(f"  [AI ERROR] {title[:50]}: {e}")
            article["summary_ai"] = {
                "digest": title, "summary_long": "", "talking_points": [],
                "topics": [], "highlight": None, "relevance": 5,
            }
            return article

    return article


def summarize_all(client: anthropic.Anthropic, articles: list[dict], notes_ctx: str = "") -> list[dict]:
    """Summarize all articles concurrently, preserving original order."""
    system = SYSTEM_PROMPT + notes_ctx

    # Separate articles that need summarization from those that don't
    to_summarize = []
    skip_indices = {}
    for i, article in enumerate(articles):
        existing = article.get("summary_ai")
        short    = len(article.get("title", "")) < MIN_TITLE_LEN
        if short:
            article["summary_ai"] = {
                "digest": article.get("title", ""), "summary_long": "",
                "talking_points": [], "topics": [], "highlight": None, "relevance": 3,
            }
            skip_indices[i] = article
        elif INCREMENTAL and existing and existing.get("summary_long") and existing.get("talking_points") and existing.get("topics"):
            skip_indices[i] = article
        else:
            to_summarize.append((i, article))

    print(f"  {len(skip_indices)} already summarized / skipped, {len(to_summarize)} to process")

    if not to_summarize:
        return articles

    results = {}
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_idx = {
            executor.submit(summarize_one, client, article, system): idx
            for idx, article in to_summarize
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                print(f"  [THREAD ERROR] index {idx}: {e}")
                results[idx] = articles[idx]
            completed += 1
            if completed % 10 == 0:
                print(f"  Summarized {completed}/{len(to_summarize)}")

    # Reconstruct in original order
    out = []
    for i, article in enumerate(articles):
        if i in skip_indices:
            out.append(skip_indices[i])
        else:
            out.append(results.get(i, article))
    return out


def load_previous_summaries() -> dict:
    """Load summary_ai from the last published docs/data/feeds.json, keyed by article id.

    data/raw_articles.json and data/feeds.json are both gitignored and regenerated
    from scratch on every CI run, so INCREMENTAL has nothing to compare against in
    production -- every article gets re-summarized on every run regardless of the
    flag. docs/data/feeds.json IS committed and survives the checkout, so it's the
    only place we can recover prior summaries from.
    """
    if not DOCS_FEEDS_PATH.exists():
        return {}
    try:
        with open(DOCS_FEEDS_PATH) as f:
            prev_articles = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    summaries = {}
    for a in prev_articles:
        aid = a.get("id")
        summary = a.get("summary_ai")
        if aid and summary and summary.get("summary_long") and summary.get("talking_points") and summary.get("topics"):
            summaries[aid] = summary
    return summaries


def load_notes_context() -> str:
    """Return notes.md content as a prompt suffix, or empty string if not found."""
    if not NOTES_PATH.exists():
        return ""
    text = NOTES_PATH.read_text().strip()
    if not text:
        return ""
    return (
        "\n\n=== USER RESEARCH NOTES ===\n"
        "The user has written these annotations on recent articles. "
        "They reveal what is capturing their attention right now. "
        "Weight articles that connect to these themes, deals, or trends proportionally higher:\n\n"
        + text
    )


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)

    with open(RAW_PATH) as f:
        articles = json.load(f)

    # Carry forward existing summaries so INCREMENTAL actually has something to
    # skip against -- see load_previous_summaries() for why this is necessary.
    previous_summaries = load_previous_summaries()
    if previous_summaries:
        carried = 0
        for article in articles:
            if article.get("summary_ai") is None and article["id"] in previous_summaries:
                article["summary_ai"] = previous_summaries[article["id"]]
                carried += 1
        print(f"Carried forward {carried}/{len(articles)} summaries from docs/data/feeds.json")

    notes_ctx = load_notes_context()
    if notes_ctx:
        print("Notes context loaded — injecting into scoring prompt.")

    print(f"Summarizing {len(articles)} articles with {MAX_WORKERS} workers...")
    articles = summarize_all(client, articles, notes_ctx)

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
