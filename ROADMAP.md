# Personal NewsFeed — Build Roadmap

*Last updated: 2026-06-29. Companion to `CLAUDE.md`. Read both before starting.*

---

## 0. TL;DR + build status

| Phase | Scope | Status |
|------|-------|--------|
| P1 | Bento deck + focus mode + lanes + read-recede + bounded edition | ✅ done |
| P2 | Richer summaries: `summary_long`, `talking_points`, `topics` | ✅ done |
| P3 | Persistence: read-state + read-later via localStorage | ✅ done |
| P3.5 | Learning algorithm: signal capture → profile → re-ranking | ✅ done |
| P5 | Responsive, a11y, iOS fixes, mobile lane chips | ✅ done |
| — | Cross-device Gist sync + magic setup URL | ✅ done |
| — | Like/dislike reactions (+3.0 / -2.0 weights), tile indicators | ✅ done |
| — | Personal notes in reader → Gist sync → `data/notes.md` → scoring | ✅ done |
| — | Auto-archive notes > 90 days → `data/notes_archive/YYYY-MM.md` | ✅ done |
| — | ↻ Pipeline refresh button (workflow_dispatch via GitHub API) | ✅ done — needs PAT `repo` scope |
| — | **Ask Claude inline Q&A in reader (Cloudflare Worker deployed)** | ✅ 2026-06-29 |
| — | **Async summarization: 8 workers + retry** | ✅ 2026-06-29 |
| — | **Gist sync fully wired (ID + SYNC_GIST_PAT confirmed)** | ✅ 2026-06-29 |
| P6 F7 | Daily/lane overview brief pre-baked in pipeline | **next** |
| P6 F8 | Live indices strip (pipeline snapshot) | **next** |
| P4 | Brief Me backend: web search + citations (Worker already deployed) | deferred |

**Next up: P6 F7 (daily brief generation in `summarize.py`) → P6 F8 (live indices) → P4 (Brief Me web search, Cloudflare Worker already deployed).**

---

## 1. Current architecture (do not break)

```
GitHub Actions (cron, update-feed.yml)
  -> scripts/fetch_feeds.py    reads config/sources.yaml, pulls RSS, writes data/raw_articles.json
  -> scripts/summarize.py      reads raw_articles.json, calls Claude Haiku, writes data/feeds.json
  -> copies data/feeds.json -> docs/data/feeds.json
  -> commits, GitHub Pages serves docs/
```

`config/sources.yaml` sections: `fig_banks, fig_asset_wealth, fig_insurance, fig_specialty_finance, pe_deals, markets_broad, newsletters, career, learn`. Section labels are mapped in `fetch_feeds.py` `section_map` and must match the labels the site filters on.

Current `feeds.json` item shape:
```json
{
  "id": "12hexchars",
  "title": "...",
  "url": "https://...",
  "source": "CNBC Finance",
  "section": "FIG — Banks",
  "date": "2026-06-26T12:32:02+00:00",
  "summary_raw": "raw RSS blurb (<=500 chars)",
  "summary_ai": { "digest": "...", "highlight": "...", "relevance": 9 }
}
```

---

## 2. Design source of truth

`prototypes/Direction 1+3 — Briefing Deck + Focus Mode (2026.06.27)_v3.html`

Lift the aesthetic and interactions directly from it. Key tokens (already in that file's `:root`):

- Background `#07080c`; glass cards `rgba(255,255,255,.045)` + `backdrop-filter: blur(14px)`; hairline strokes `rgba(255,255,255,.10)`.
- Animated aurora blobs behind content (respect `prefers-reduced-motion`).
- Per-lane accent colors: banks `#60a5fa`, asset/wealth `#34d399`, insurance `#fb923c`, specialty finance `#a78bfa`, PE `#e879f9`, markets `#7dd3fc`, newsletters `#f472b6`, career `#fcd34d`, learn `#5eead4`. Gold `#f5d23d` for read-later.
- Bento deck: tiles sized by relevance (hero 2×2 for 9–10, wide/tall for 8, small for ≤7).
- **Tile text budget (keep — this prevents the clipping bug):** each size has a fixed `line-clamp` budget and `.c-mid` has `overflow:hidden`. Hero 2-line title / 4-line summary; tall 3/3; wide 2/1; small 2/1. Long text ellipsizes; full text lives in the reader.
- Read state: tile desaturates, scales down, animates into the collapsed "Read · in the background" tray.
- No infinite scroll: a bounded "edition" with a hard endcap + "Load yesterday's edition".
- Focus mode: one card centered with a 3D stack behind; `←/→` move, `R` read, `L` read-later.
- Modes in the header switch: Deck / Focus / Brief, plus a star button (read-later) with a count badge, plus the read-progress ring.

---

## 3. Data contract changes (P2)

Extend `summary_ai` — additive, keep existing fields:

```json
"summary_ai": {
  "digest": "2–3 sentences. Lead with the key fact/number/name.",
  "summary_long": "4–6 sentences. Enough to extract talking points without opening the source.",
  "talking_points": [
    "Punchy, self-contained point a reader can say out loud.",
    "Second point with the supporting number or name.",
    "Optional third."
  ],
  "topics": ["regional bank M&A", "Fed regulation", "deposit flight"],
  "highlight": "single most actionable detail (existing field)",
  "relevance": 9
}
```

`topics` is new — 3–5 short keyword tags per article. Required for the P3.5 learning algorithm; the interest profile trains on these. Keep them concise and consistent (prefer "regional bank M&A" over "mergers and acquisitions in the regional banking sector").

`summarize.py` changes:
- Update `SYSTEM_PROMPT` to produce `summary_long` (4–6 sentences), `talking_points` (2–3 bullets), and `topics` (3–5 keyword tags). Keep the existing five-lane scoring rubric.
- Bump `max_tokens` (~300 -> ~700).
- Keep `INCREMENTAL` skip logic, but invalidate cache entries missing the new fields so a re-run backfills them.
- Cost check: longer output raises Haiku cost modestly; still cents/month at this volume. Confirm after first full run.

---

## 4. Features

### F1 — Briefing Deck (P1)
Render unread items into the bento grid, sorted by relevance, sized per the budget above. Lane filter chips. Tile click opens the reader. "Show more" opens the reader. Bounded edition + endcap. Acceptance: no tile clips text mid-line at any viewport ≥360px; relevance ordering correct; lane filters work.

### F2 — Reader + richer content (P1/P2)
Glass overlay with tag, title, `summary_long`, a "Talking points" bullet list, `highlight`, source link (opens `url`), and actions: Mark read, Read later, Keep. Acceptance: talking points render; external link opens the real article.

### F3 — Read state recedes to background (P1/P3)
Marking read animates the tile out and into the collapsed "Read" tray; clicking a tray chip restores it. Persist read IDs in `localStorage` keyed by edition date so a refresh keeps state; roll state at a new edition. Acceptance: read items survive reload; progress ring reflects count.

### F4 — Focus mode (P1)
Spatial single-card reader over the unread set (or a read-later session — see F5). `←/→`, `R`, `L`, and on-screen buttons. Shows `digest`/`summary_long` + highlight + "Show more". Acceptance: keyboard + buttons work; fly-back animation; empty state at inbox-zero.

### F5 — Read later (P3)
Star toggles on tile, reader, focus. A "Read later" view lists saved items with "Read now" and remove; "Read these now ->" starts a Focus session over only saved items; "Brief me on these" sends the saved set to the Brief. Persist saved IDs in `localStorage` (no edition expiry). Acceptance: saved set persists across reloads; session walks only saved items.

### F5.5 — Learning algorithm (P3.5)

The current scoring is static: Haiku rates 1–10 once at pipeline time. This adds a personal re-ranking layer that adapts to reading behavior.

**Signals** (captured in localStorage on every interaction):
```javascript
{ articleId, action, source, section, topics[], timestamp }
// action: 'read' (+1.0), 'save' (+1.5), 'brief' (+2.0), 'skip' (-0.3)
```

**Interest profile** (built from signals, persisted in localStorage):
```javascript
{
  sources: { "FT Alphaville": 0.87, "WSJ": 0.62 },
  sections: { "FIG — Banks": 0.80, "Markets": 0.55 },
  topics:   { "regional bank M&A": 0.92, "Fed regulation": 0.71 }
}
```
Signals decay with a 14-day half-life — last week matters more than last month. Profile recalculates after every signal.

**Re-ranking** (applied at load time, before rendering):
```javascript
finalScore = (haiku_relevance × 0.5) + (personalScore × 0.5)

personalScore = (sourceWeight × 0.3) + (sectionWeight × 0.3) + (topicOverlap × 0.4)
```
Articles are sorted by `finalScore` before the bento grid renders. Tile sizes follow the new score, not raw Haiku score.

**Source discovery:** when a source's `sourceWeight` crosses 0.75 after 20+ reads, surface a dismissible banner: "You keep reading [Source] — add a similar outlet?" with 1–2 suggested feeds. Suggestions are hardcoded per-source (build a small map in the JS; update `sources.yaml` manually when accepted).

Implementation: ~150 lines of vanilla JS, all client-side, no new infra. Requires `topics` field from P2 to work well — do P2 first.

Acceptance: after 10 reads, the ranking visibly differs from raw Haiku order; skip signals suppress repeated low-engagement sources; interest profile persists across reloads; source discovery fires correctly.

### F6 — Brief me (P4) — deferred
A panel: "What are you curious about today?" with an input and suggestion chips. On submit, return 3–5 talking points, each with a one-line support and a **real cited source link**, plus a sources list.

Why a backend: the page is static and public; the Anthropic key cannot live in it. Need a serverless function.

**Cloudflare Worker already deployed** at `https://newsfeed-ai.luciusgao2001.workers.dev` for Ask Claude Q&A. Extend it with a `/brief` route for web search.

**Original approach note:** a single Cloudflare Worker (free tier, generous) at e.g. `/api/brief`.
- Input: `{ topic, savedItems? }`.
- The Worker calls the Anthropic API with **web search enabled** (server-side tool use) and a prompt that asks for 3–5 talking points with citations, biased toward FIG/markets/PE relevance and toward sources already in `sources.yaml` when applicable.
- Optionally pass the current `feeds.json` items as context so briefs blend today's feed with fresh web results.
- Output: `{ title, points: [{claim, support, sourceTitle, sourceUrl}], sources: [{title,url}] }`.
- Key stored as a Worker secret. Add light abuse protection (it's personal, but the endpoint is public): a shared token in the page, an allowed-origin/referer check, and a daily call cap.

Alternatives: Vercel/Netlify function (fine if already using their hosting) or a GitHub Action that pre-bakes briefs for a fixed topic list (cheaper, but not on-demand — rejected, kills the "ask anything" value).

Acceptance: typing a topic returns cited, clickable talking points within a few seconds; the key never appears client-side; a sensible message on rate-limit or no results.

### F7 — Daily / lane overview ("what's going on") (P6)
A panel between the lane chips and the deck. For "All", an AI-written 3–4 bullet summary of what's going on today across the top stories. Selecting a lane regenerates it as a lane-specific overview (e.g., "What's going on · Banks"). Each bullet links to its source story.

Production approach: after scoring, `summarize.py` makes one extra Haiku call per lane (plus "all") over that lane's top ~5 stories and writes a top-level `briefs` object into `feeds.json`:
```json
"briefs": {
  "all":       { "lede": "14 stories across all lanes…", "bullets": [ {"lane":"FIG — Banks","text":"…","refId":"<articleId>","source":"CNBC"} ] },
  "FIG — Banks": { "lede": "…", "bullets": [ ... ] }
}
```
The page reads `briefs[activeLane]` and renders; switching lanes swaps the bullet set. Cost: ~10 extra short Haiku calls per run — still cents/month. Acceptance: bullets reflect the day's top stories per lane; clicking a bullet opens the source; refreshes each run. (Prototype builds these client-side from article highlights; production pre-bakes them so the page stays static.)

### F8 — Live indices strip + markets view (P6)
A persistent indices strip under the header: S&P 500, Nasdaq, Dow, US 10Y, VIX, and **KBW Banks (^BKX)** — the FIG-relevant one. Optional dedicated "Markets" view with small charts later.

The page is static, so pick a data path:
- **(a) Snapshot in the pipeline (recommended start):** the GitHub Action fetches index quotes each run (~2h cadence) and writes them into `feeds.json` (`"indices": [...]`). Zero new infra, free, "near-live." Good enough unless you need real-time ticking.
- **(b) Real-time via proxy:** reuse the P4 Cloudflare Worker to proxy a free quote API server-side (keeps any key off the client, avoids browser CORS); page polls every 30–60s.

Avoid calling quote APIs directly from the browser with an embedded key (exposed) or via endpoints that block CORS (Yahoo's unofficial API, often Stooq). Free providers: Finnhub, Twelve Data, Alpha Vantage (all key + free tier — use server-side), or Stooq CSV (no key, but proxy it).

Add market-hours awareness (show "closed" outside RTH) and a small "not investment advice / delayed data" note. Acceptance: indices render with correct +/- coloring on the chosen cadence; KBW/BKX included; no key in page source.

---

## 5. Build order (recommended)

1. **P1** — Port the v3 UI into `docs/index.html`, reading the real `docs/data/feeds.json`. Replace the current list UI. Keep lane labels in sync with `section_map`. This is the longest step — the bento tile sizing and read-recede animation will surprise you. Budget half a day just for that.
2. **P2** — Extend `summarize.py` + schema; re-run locally with the key to backfill `summary_long`, `talking_points`, and `topics`; render them in the reader.
3. **P3** — Add `localStorage` persistence for read + read-later; wire the tray and read-later view.
4. **P3.5** — Add the learning algorithm: signal capture on every interaction, interest profile build, re-ranking at load time. Requires `topics` from P2. ~150 lines of JS.
5. **P5** — Responsive + empty states + a11y pass. Ship here — this is a complete, differentiated product.
6. **P6 (F7)** — Add daily/lane brief generation to `summarize.py`; render from `feeds.json.briefs`.
7. **P6 (F8)** — Add index snapshot to the pipeline; render the strip.
8. **P4** — Build + deploy the Cloudflare Worker for Brief Me. Do this last — it's the most complex piece and nothing depends on it.

**Ship after step 5.** P6 and P4 are clean add-ons to a working product.

---

## 6. Testing / QA

- Feed parse: run `python scripts/fetch_feeds.py` (needs network); confirm all 40 sources return without `[RSS ERROR]`. Note: validate feeds with real network — a sandbox without egress will report all feeds dead even when they are fine.
- Summaries: run `summarize.py` on a small slice; assert every item has `digest`, `summary_long`, `talking_points[]`, `relevance`.
- UI: at 360 / 768 / 1280px, confirm no tile clips text mid-line; read-recede works; focus keyboard works; read-later persists across reload.
- Brief: topic returns cited links; bad/empty topic handled; key absent from page source and network tab.

---

## 7. Risks / open decisions

- **Brief abuse:** public endpoint + your API key = cost risk if scraped. Decide on the protection level (shared token + origin check + daily cap is the minimum).
- **Some feeds rate-limit or change RSS paths.** Keep the per-source try/except; log dead feeds; audit `sources.yaml` quarterly.
- **Edition definition for read-state:** confirm "edition" = calendar day in your timezone (ET) for rolling read-state. Currently assumed.
- **Hosting for the Worker:** Cloudflare recommended; confirm you're willing to add a second platform alongside GitHub Pages. If you'd rather stay single-platform, move the whole site to Vercel/Netlify and use their functions.
- **WSJ feeds** are headline+blurb only (paywalled bodies). Reader "open source" still works; just don't expect full text in `summary_raw`.
- **`markets_broad` is now 18 sources** (added niche macro: The Macro Compass, Capital Flows Research, The Last Bear Standing, Concoda, fx:macro). It's the heaviest section — consider splitting "Markets data/news" from "Macro analysis" if it feels noisy, or rely on relevance scoring to sort. `fig_specialty_finance` gained PETITION, Fintech Business Weekly, and Perspective on Risk. Total is now **48 sources** across 9 sections.
- **Source curation is ongoing** (Lucius wants to keep adding niche outlets). Dead feeds found and skipped: Fintech Brainfood, Pari Passu, Litquidity Exec Sum, Wall Street Oasis. Next niches to evaluate if wanted: forensic/accounting (Footnotes Analyst), insurance-specific analysis, and equity-research substacks.
- **Newswire / scrape sources.** Added GlobeNewswire — Banking (clean public RSS) for press-release deal flow — this is the working substitute for **Business Wire**, which has no simple public RSS (only a keyword feed-builder). Business Wire (Financial Services) and **Citywire RIA** are staged in `config/sources.yaml` under `scrape_targets` with `enabled: false`.

**Citywire RIA** actually publishes RSS at `https://citywire.com/ria/latest-news/rss.xml` (200 + 20 items in a logged-in browser) but it returns **empty from an unauthenticated server fetch** — either login-cookie gated or user-agent/WAF blocked. First step: run it through the pipeline as a normal `rss` source (fetch_feeds.py sends a Mozilla UA, which may pass a WAF). If still empty, it's login-gated and automating it requires storing Citywire session cookies as GitHub secrets (fragile, expire-prone, check ToS) — likely not worth it given RIABiz / WealthManagement / InvestmentNews / FA-Mag already cover RIA/wealth with open feeds.

**Business Wire** is JavaScript-rendered with no clean public RSS; use the added GlobeNewswire — Banking feed instead, or implement a Playwright-based scraper path (Playwright is available in Claude Code per the user's global config), then flip `enabled: true`. Also improve scrape→section routing in `fetch_feeds.py` (currently a crude keyword heuristic): Business Wire FS → `FIG — Banks`/`Specialty Finance`, Citywire RIA → `FIG — Asset & Wealth Management`.
