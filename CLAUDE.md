# Personal NewsFeed — Project Context

*For Claude. Read this first, then `ROADMAP.md`.*

## Live site

https://lusch0620.github.io/personal-newsfeed/

## What this is

A personal, FIG-focused news aggregator for Lucius Gao (FIG investment banker at Cantor Fitzgerald, targeting a lateral IB / PE move). Pulls ~48 RSS sources across banks, asset/wealth, insurance, specialty finance, PE/deals, markets/macro, newsletters, career intel, and "learn" sources. Claude Haiku summarizes each story and scores it 1–10. Output is a static site, refreshed every ~2h via GitHub Actions, hosted free on GitHub Pages.

## File map

```
config/sources.yaml               # 48 sources across 9 sections
scripts/fetch_feeds.py            # RSS -> data/raw_articles.json
scripts/fetch_notes.py            # Gist notes -> data/notes.md (CI only, needs SYNC_GIST_PAT)
scripts/summarize.py              # Claude Haiku (8 async workers) -> data/feeds.json
scripts/generate_briefs.py        # Claude Haiku -> data/briefs.json (lane briefs + live indices)
data/notes.md                     # auto-generated from user annotations; injected into scoring
data/notes_archive/YYYY-MM.md    # notes > 90 days auto-archived here
docs/index.html                   # live site — full UI
docs/data/feeds.json              # served copy of article data
docs/data/briefs.json             # served copy of lane briefs + indices
.github/workflows/update-feed.yml # cron pipeline
prototypes/                       # design source of truth
```

## Pipeline order

```
fetch_feeds.py -> fetch_notes.py -> summarize.py -> generate_briefs.py -> deploy
```

## feeds.json schema

```json
{
  "id": "12hexchars",
  "title": "...",
  "url": "https://...",
  "source": "CNBC Finance",
  "section": "FIG — Banks",
  "date": "2026-06-29T12:32:02+00:00",
  "summary_raw": "raw RSS blurb (<=500 chars)",
  "summary_ai": {
    "digest": "2-3 sentence lead.",
    "summary_long": "4-6 sentence full context.",
    "talking_points": ["point 1", "point 2", "point 3"],
    "topics": ["regional bank M&A", "Fed regulation"],
    "highlight": "single most actionable detail",
    "relevance": 9
  }
}
```

## briefs.json schema

```json
{
  "FIG — Banks": {
    "lede": "...",
    "bullets": [{"text": "...", "refId": "<articleId>", "source": "WSJ"}]
  },
  "all": { "lede": "...", "bullets": [...] },
  "indices": [
    {"nm": "S&P 500", "v": 6218.4, "base": 6218.4, "bp": false},
    {"nm": "US 10Y",  "v": 4.28,   "base": 4.28,   "bp": true}
  ]
}
```

## What's built (all completed as of 2026-06-29)

| Feature | Status |
|---------|--------|
| Bento deck, focus mode, lane filters, read-recede tray, bounded edition | ✅ |
| Richer summaries: `summary_long`, `talking_points`, `topics` | ✅ |
| localStorage persistence (read state, read-later, edition-keyed) | ✅ |
| Learning algorithm: signal capture → decay-weighted profile → re-ranking | ✅ |
| Responsive (mobile), a11y, iOS fixes | ✅ |
| Cross-device sync via GitHub Gist | ✅ |
| Like/dislike reactions (+3.0 / -2.0 weights) | ✅ |
| Personal notes in reader: auto-save, Gist sync | ✅ |
| Notes → pipeline: `fetch_notes.py` → `data/notes.md` → scoring context | ✅ |
| Auto-archive: notes > 90 days → `data/notes_archive/YYYY-MM.md` | ✅ |
| Pipeline refresh button (↻) — triggers workflow_dispatch | ✅ |
| **Ask Claude inline Q&A in article reader (Cloudflare Worker)** | ✅ 2026-06-29 |
| **Async summarization: 8 concurrent workers + exponential-backoff retry** | ✅ 2026-06-29 |
| **Pipeline-generated lane briefs (P6 F7)** | ✅ 2026-06-29 |
| **Live indices strip: S&P, Nasdaq, Dow, 10Y, VIX, KBW Banks (P6 F8)** | ✅ 2026-06-29 |
| **Brief Me: Claude Sonnet + web search + cited talking points (P4)** | ✅ 2026-06-29 |

## Cloudflare Worker

**URL:** `https://newsfeed-ai.luciusgao2001.workers.dev`  
**Secret:** `ANTHROPIC_API_KEY` set in Cloudflare Worker settings.  
**CORS:** locked to `https://lusch0620.github.io`.

| Route | Model | Purpose |
|-------|-------|---------|
| `POST /` or `/ask` | Haiku | Inline article Q&A in the reader |
| `POST /brief` | Sonnet + web search | Brief Me — cited talking points beyond the feed |

**Input `/ask`:** `{ question, article: { title, source, summary, talking_points } }`  
**Input `/brief`:** `{ topic, articles: [{ title, source, summary }] }`  
**Output both:** `{ answer }` or `{ lede, points: [{claim, source, url}] }`

## GitHub Actions secrets

| Secret | Purpose |
|--------|---------|
| `ANTHROPIC_API_KEY` | Claude Haiku for summarization + briefs; Sonnet for Brief Me |
| `SYNC_GIST_PAT` | Reads user notes from Gist during pipeline |

## Sync setup (cross-device)

Gist ID: `8a4b09f2ceb018c3b45460ee40e1ced9` — hardcoded in `index.html` and `fetch_notes.py`.  
PAT lives in localStorage only — never in source.  
Open ⚙️ in the site header on any new device and enter the PAT + Gist ID.

**PAT scope note:** PAT needs `gist`, `repo`, and `workflow` scope (all set on "Personal Feed" token).

## Notes → algorithm loop

1. User asks a question or writes a note in the article reader
2. Q&A auto-appended to that article's notes in localStorage
3. Gist sync (pushes on every interaction) → `newsfeed-sync.json` in Gist
4. Next pipeline run: `fetch_notes.py` pulls Gist → `data/notes.md`
5. `summarize.py` injects `notes.md` into scoring prompt → influences relevance scores

## Hard rules

- Do not commit the Anthropic API key. Lives only in `ANTHROPIC_API_KEY` secret + Cloudflare Worker secret.
- Do not hardcode the sync PAT in source. Lives in localStorage + `SYNC_GIST_PAT` secret.
- Keep it free: GitHub Actions + Pages + Cloudflare Workers free tier.
- The site is static. Anything needing an API key at request time goes through the Cloudflare Worker.
- Pipeline contract: `fetch_feeds.py` → `raw_articles.json` → `fetch_notes.py` → `summarize.py` → `feeds.json` → `generate_briefs.py` → `briefs.json`. Extend; don't break.

## Owner preferences

Direct, commercial, no fluff. Lucius is technically fluent (Python, JS). Give a recommendation, not a menu. Flag problems early. Always `git pull --rebase` before pushing.
