# LG NewsFeed

Personal FIG-focused news aggregator. Pulls from 25+ sources across banks, asset/wealth management, insurance, specialty finance, and broad markets. Claude summarizes each story and scores relevance (1–10) so you see signal before noise.

**Refreshes every 2 hours on weekdays via GitHub Actions. Hosted free on GitHub Pages.**

---

## Setup (one-time, ~10 minutes)

### 1. Create the GitHub repo

```bash
cd "Personal NewsFeed"
git init
git add .
git commit -m "initial commit"
gh repo create personal-newsfeed --private --push --source=.
```

Or create the repo manually on GitHub and push.

### 2. Add your Anthropic API key

Go to: **GitHub repo → Settings → Secrets and variables → Actions → New repository secret**

- Name: `ANTHROPIC_API_KEY`
- Value: your key from [console.anthropic.com](https://console.anthropic.com) → API keys

Cost: ~$0.10–0.30/month with Claude Haiku at this volume.

### 3. Enable GitHub Pages

Go to: **GitHub repo → Settings → Pages**

- Source: **Deploy from a branch**
- Branch: `main`, folder: `/site`
- Save

Your site will be live at: `https://yourusername.github.io/personal-newsfeed/`

### 4. Run the first feed manually

Go to: **GitHub repo → Actions → Update NewsFeed → Run workflow**

Or run locally:

```bash
pip install -r requirements.txt
python scripts/fetch_feeds.py
ANTHROPIC_API_KEY=your_key python scripts/summarize.py
```

---

## Customizing Sources

Edit `config/sources.yaml`. Each entry:

```yaml
fig_banks:
  - name: "Source Display Name"
    url: "https://example.com/rss.xml"
    type: rss
```

Sections: `fig_banks`, `fig_asset_wealth`, `fig_insurance`, `fig_specialty_finance`, `markets_broad`, `newsletters`

To add a scrape target (for sites without RSS):

```yaml
scrape_targets:
  - name: "Site Name"
    url: "https://example.com/news"
    type: scrape
    enabled: true
```

---

## Cost

- **GitHub Actions + Pages**: Free (within 2,000 min/month — this uses ~5 min/run × ~10 runs/day = ~50 min/day, well within limits)
- **Claude API (Haiku)**: ~$0.25–1.00/month depending on article volume
- **Total**: ~$1–2/month

---

## Architecture

```
GitHub Actions (cron every 2h)
  → scripts/fetch_feeds.py     # Pulls RSS feeds + scrapes niche sources
  → scripts/summarize.py       # Claude Haiku summarizes + scores each article
  → site/data/feeds.json       # Output committed to repo
  → GitHub Pages               # Serves site/index.html + feeds.json
```

---

## Adjusting the Schedule

Edit `.github/workflows/update-feed.yml`. The cron currently runs:
- Weekdays: every 2 hours from 7am–11pm ET
- Weekends: 9am, 1pm, 5pm ET

---

## Adding New Sections

1. Add entries to `config/sources.yaml` under a new section key
2. Add the section to `SECTION_TAG_MAP` in `site/index.html`
3. Add it to `section_map` in `scripts/fetch_feeds.py`
4. Add it to the `SECTIONS` array in the nav (site/index.html)
