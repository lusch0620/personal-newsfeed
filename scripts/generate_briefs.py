"""
generate_briefs.py
After summarize.py scores all articles, this generates AI-written lane briefs.
Reads data/feeds.json, writes data/briefs.json.

One Haiku call per lane (+ "all") over the top 5 stories.
~10 extra calls per pipeline run — negligible cost.
"""

import anthropic
import json
import os
from pathlib import Path

ROOT        = Path(__file__).parent.parent
FEEDS_PATH  = ROOT / "data" / "feeds.json"
OUTPUT_PATH = ROOT / "data" / "briefs.json"

TOP_N = 5  # articles per lane to feed into the brief

LANE_LABELS = {
    "FIG — Banks":                  "Banks",
    "FIG — Asset & Wealth Management": "Asset & Wealth",
    "FIG — Insurance":              "Insurance",
    "FIG — Specialty Finance":      "Specialty Finance",
    "PE & Deals":                   "PE & Deals",
    "Markets & Macro":              "Markets & Macro",
    "Newsletters":                  "Newsletters",
    "Career Intel":                 "Career Intel",
    "Learn":                        "Learn",
}

SYSTEM_PROMPT = """You are writing a concise daily briefing panel for Lucius Gao, a FIG investment banker at Cantor Fitzgerald. He reads this before diving into individual articles.

Write 3-4 punchy bullets summarizing what's happening across the stories provided. Each bullet should:
- Lead with the key fact, name, number, or theme
- Be 1-2 sentences max
- Reference the article it's drawn from using its id field

Return a JSON object with exactly these fields:
{
  "lede": "One sentence overview of what's going on (e.g. '5 stories, led by regional bank M&A and a Fed signal').",
  "bullets": [
    {"text": "Bullet text here.", "refId": "<article id>", "source": "<source name>"},
    ...
  ]
}

Be ruthlessly concise. No filler. These bullets are what Lucius reads before he has his coffee."""


def brief_lane(client, articles: list[dict], lane_label: str) -> dict:
    """Generate a brief for a set of articles."""
    if not articles:
        return {"lede": "No stories in this lane today.", "bullets": []}

    context = "\n\n".join([
        f"id: {a['id']}\nsource: {a['source']}\ntitle: {a['title']}\ndigest: {(a.get('summary_ai') or {}).get('digest', '')}"
        for a in articles
    ])

    user_msg = f"Lane: {lane_label}\nTop stories today:\n\n{context}"

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as e:
        print(f"  [BRIEF ERROR] {lane_label}: {e}")
        return {
            "lede": f"{len(articles)} {'story' if len(articles)==1 else 'stories'} in this lane today.",
            "bullets": [
                {"text": a["title"], "refId": a["id"], "source": a["source"]}
                for a in articles[:3]
            ]
        }


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)

    with open(FEEDS_PATH) as f:
        articles = json.load(f)

    # Group by section
    by_section: dict[str, list] = {}
    for a in articles:
        sec = a.get("section", "")
        by_section.setdefault(sec, []).append(a)

    briefs = {}

    # Per-lane briefs
    for section, label in LANE_LABELS.items():
        lane_articles = by_section.get(section, [])[:TOP_N]
        print(f"  Briefing: {label} ({len(lane_articles)} articles)...")
        briefs[section] = brief_lane(client, lane_articles, label)

    # "All" brief — top articles across all lanes
    top_all = sorted(
        articles,
        key=lambda a: (a.get("summary_ai") or {}).get("relevance", 5),
        reverse=True
    )[:TOP_N]
    print(f"  Briefing: All lanes ({len(top_all)} articles)...")
    briefs["all"] = brief_lane(client, top_all, "all lanes")

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(briefs, f, indent=2)

    print(f"Done. Briefs written for {len(briefs)} lanes to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
