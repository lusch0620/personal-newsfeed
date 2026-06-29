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

ROOT        = Path(__file__).parent.parent
RAW_PATH    = ROOT / "data" / "raw_articles.json"
OUTPUT_PATH = ROOT / "data" / "feeds.json"
NOTES_PATH  = ROOT / "data" / "notes.md"

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


def summarize_batch(client: anthropic.Anthropic, articles: list[dict], notes_ctx: str = "") -> list[dict]:
    """Summarize articles. Each call is individual to keep prompts focused."""
    system = SYSTEM_PROMPT + notes_ctx
    results = []
    for i, article in enumerate(articles):
        existing = article.get("summary_ai")
        if INCREMENTAL and existing and existing.get("summary_long") and existing.get("talking_points") and existing.get("topics"):
            results.append(article)
            continue

        title = article.get("title", "")
        if len(title) < MIN_TITLE_LEN:
            article["summary_ai"] = {"digest": title, "summary_long": "", "talking_points": [], "topics": [], "highlight": None, "relevance": 3}
            results.append(article)
            continue

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=700,
                system=system,
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
                "summary_long": "",
                "talking_points": [],
                "topics": [],
                "highlight": None,
                "relevance": 5,
            }
        except Exception as e:
            print(f"  [AI ERROR] {title[:50]}: {e}")
            article["summary_ai"] = {
                "digest": title,
                "summary_long": "",
                "talking_points": [],
                "topics": [],
                "highlight": None,
                "relevance": 5,
            }

        results.append(article)
        if (i + 1) % 10 == 0:
            print(f"  Summarized {i + 1}/{len(articles)}")

    return results


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

    notes_ctx = load_notes_context()
    if notes_ctx:
        print("Notes context loaded — injecting into scoring prompt.")

    print(f"Summarizing {len(articles)} articles...")
    articles = summarize_batch(client, articles, notes_ctx)

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
