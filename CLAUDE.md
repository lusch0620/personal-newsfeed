# Personal NewsFeed — Project Context

*For Claude Code. Read this first, then `ROADMAP.md`.*

## Live site

https://lusch0620.github.io/personal-newsfeed/

## What this is

A personal, FIG-focused news aggregator for Lucius Gao (FIG investment banker, targeting a lateral IB / PE move). It pulls ~48 RSS sources (and growing — source curation is ongoing) across banks, asset/wealth, insurance, specialty finance, PE/deals, markets/macro, plus independent newsletters, career intel, and "learn" sources. Claude (Haiku) summarizes each story and scores it 1–10 for relevance. Output is a static site, refreshed every ~2h via GitHub Actions, hosted free on GitHub Pages.

## Current state (working)

```
config/sources.yaml        # 40 sources across 9 sections (validated 2026-06-27)
scripts/fetch_feeds.py      # RSS -> data/raw_articles.json
scripts/summarize.py        # Claude Haiku -> data/feeds.json (digest, highlight, relevance, section-aware scoring)
data/feeds.json             # final output the site reads
docs/index.html             # the live site (current UI = simple list, dark, lane tabs)
docs/data/feeds.json        # served copy (CI copies data/ -> docs/data/)
.github/workflows/update-feed.yml   # cron: fetch -> summarize -> copy -> commit
prototypes/                 # design prototypes (NOT wired to the pipeline yet)
```

The pipeline runs. The current `docs/index.html` works but is a plain list. The job is to replace that UI and add four features.

## The decision

Adopt the design in:
`prototypes/Direction 1+3 — Briefing Deck + Focus Mode (2026.06.27)_v3.html`

This is the **visual + interaction source of truth** for the new `docs/index.html`. It is a self-contained mock with sample data; the production build wires the same UI to real `feeds.json` and adds persistence + a brief backend. See `ROADMAP.md` for the full spec, schema, phased plan, and estimates.

Other prototypes (`Direction 2 — The Terminal`, `Direction 4 — The Daily Edition`) are rejected alternatives kept for reference only.

## Hard rules

- Do not commit the Anthropic API key to the repo or to any client-side file. It lives only in the GitHub Actions secret `ANTHROPIC_API_KEY` (and, for the Brief feature, in a serverless env var).
- Keep it free to run: GitHub Actions + Pages, Haiku for summaries. Stay within free tiers.
- The site is static. Anything needing the API key at request time (the Brief feature) must go through a separate serverless function, not the page.
- Preserve the existing pipeline contract: `fetch_feeds.py` -> `data/raw_articles.json` -> `summarize.py` -> `data/feeds.json`. Extend the schema; don't break it.

## Owner preferences

Direct, commercial, no fluff. Lucius is technically fluent (Python, JS) — don't over-explain. Give a recommendation, not a menu. Flag problems early.
