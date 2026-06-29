# Personal NewsFeed — Project Context

*For Claude Code. Read this first, then `ROADMAP.md`.*

## Live site

https://lusch0620.github.io/personal-newsfeed/

## What this is

A personal, FIG-focused news aggregator for Lucius Gao (FIG investment banker, targeting a lateral IB / PE move). Pulls ~48 RSS sources across banks, asset/wealth, insurance, specialty finance, PE/deals, markets/macro, newsletters, career intel, and "learn" sources. Claude Haiku summarizes each story and scores it 1–10. Output is a static site, refreshed every ~2h via GitHub Actions, hosted free on GitHub Pages.

## Current state (as of 2026-06-29)

**The UI is fully built and live.** Pipeline + site are working.

```
config/sources.yaml             # 48 sources across 9 sections
scripts/fetch_feeds.py          # RSS -> data/raw_articles.json
scripts/fetch_notes.py          # Gist notes -> data/notes.md (CI only, needs SYNC_GIST_PAT)
scripts/summarize.py            # Claude Haiku -> data/feeds.json (reads notes.md for context)
data/notes.md                   # auto-generated from user annotations; injected into scoring
data/notes_archive/YYYY-MM.md   # notes > 90 days auto-archived here
docs/index.html                 # live site — bento deck + focus + brief + learning algo
docs/data/feeds.json            # served copy (CI copies data/ -> docs/data/)
.github/workflows/update-feed.yml  # cron: fetch_feeds -> fetch_notes -> summarize -> deploy
prototypes/                     # design source of truth (Direction 1+3 v3 is the reference)
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

## What's built (completed phases)

| Phase | Feature | Status |
|-------|---------|--------|
| P1 | Bento deck, focus mode, lane filters, read-recede tray, bounded edition | ✅ |
| P2 | Richer summaries: `summary_long`, `talking_points`, `topics` | ✅ |
| P3 | localStorage persistence (read state, read-later, edition-keyed) | ✅ |
| P3.5 | Learning algorithm: signal capture → decay-weighted profile → re-ranking | ✅ |
| P5 | Responsive (mobile 2-col, scrollable lane chips), a11y, iOS fixes | ✅ |
| — | Cross-device sync via GitHub Gist (PAT stored in localStorage only) | ✅ |
| — | Like/dislike reactions (weights: +3.0 / -2.0) with tile indicators | ✅ |
| — | Personal notes in reader: auto-save, ✏ tile indicator, Gist sync | ✅ |
| — | Notes → pipeline: `fetch_notes.py` → `data/notes.md` → scoring context | ✅ |
| — | Auto-archive: notes > 90 days → `data/notes_archive/YYYY-MM.md` | ✅ |
| — | Pipeline refresh button (↻) in header — triggers workflow_dispatch | ✅ |

## What's still to build

| Phase | Feature | Notes |
|-------|---------|-------|
| P6 F7 | Daily/lane brief in `summarize.py` → `feeds.json.briefs` | `buildTodayBrief()` in JS already renders it; just needs pipeline generation |
| P6 F8 | Live indices strip — snapshot quotes in pipeline | Currently demo data |
| P4 | Brief Me backend (Cloudflare Worker + web search) | Deferred — most complex, nothing depends on it |

## GitHub Actions secrets required

| Secret | Value | Purpose |
|--------|-------|---------|
| `ANTHROPIC_API_KEY` | (set) | Claude Haiku for summarization |
| `SYNC_GIST_PAT` | (set) | Reads user notes from Gist during pipeline |

## Sync setup (cross-device)

Open this URL on any new device to auto-configure sync:
```
https://lusch0620.github.io/personal-newsfeed/#setup=<YOUR_PAT>
```
PAT lives in localStorage only — never in source. Gist ID `8a4b09f2ceb018c3b45460ee40e1ced9` is hardcoded in `index.html`.
The actual PAT is saved in your password manager / personal notes — do not commit it to the repo.

**PAT scope note:** current PAT has `gist` scope. The ↻ refresh button also needs `repo` scope — update at github.com/settings/tokens if the button returns red.

## Hard rules

- Do not commit the Anthropic API key to the repo or any client-side file. Lives only in `ANTHROPIC_API_KEY` secret.
- Do not hardcode the sync PAT in source. Lives in localStorage + `SYNC_GIST_PAT` secret only.
- Keep it free: GitHub Actions + Pages, Haiku for summaries. Stay within free tiers.
- The site is static. Anything needing the API key at request time must go through a serverless function.
- Preserve the pipeline contract: `fetch_feeds.py` -> `raw_articles.json` -> `fetch_notes.py` -> `summarize.py` -> `feeds.json`. Extend the schema; don't break it.

## Owner preferences

Direct, commercial, no fluff. Lucius is technically fluent (Python, JS) — don't over-explain. Give a recommendation, not a menu. Flag problems early.
