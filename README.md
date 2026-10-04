<div align="center">

# The Fashion Business

**Business news for Indian fashion. Automated, ad-free, and built to be read.**

[**Live site → the-fashion-business.vercel.app**](https://the-fashion-business.vercel.app/)

Astro · Python · GitHub Actions · Gemini · Vercel

</div>

---

## The idea

Indian fashion is a large, fast-moving industry: D2C brands raising rounds, legacy houses opening stores in tier-II cities, handloom clusters, export numbers, wedding-season economics. Most coverage of it is celebrity-led or locked inside trade magazines.

**The Fashion Business** covers the *business* of Indian fashion only: funding, retail, D2C, textiles and exports, fashion-week commerce, policy and brand strategy. No red carpets, no outfit galleries.

It has two layers:

- **Automated news.** A pipeline finds, filters, groups and summarises stories every 4 hours, with no one at a keyboard.
- **Editorial.** A weekly long-form article and, later, deep histories of Indian brands, written by a human.

> **Status:** early stage, live and updating. The news engine and website are complete; accounts, the newsletter and brand histories are next.

## What's live

- **Landing page** with an animated intro and a premium editorial design.
- **News list** fed by the pipeline, with source links on every story.
- **Article of the Week**, a dedicated long-form reading page.
- **Newsletter, contact and Join pages** (see "Not built yet" for what is still a mockup).
- **Fully responsive**, with a mobile menu.
- **Self-updating:** each time the pipeline publishes, the site rebuilds and redeploys on its own.

## How it works

```
 News feeds ─► keyword filter ─► duplicate grouping ─► AI summary ─► review / auto-publish
 (RSS)         (no celebrity)    (same story, many      (headline,     (data/decisions.json)
                                  outlets = one)         category,            │
                                                         brands)              ▼
 Visitors ◄─ Vercel ◄─ Astro site ◄─ content/news/*.json ◄─ commit by news-bot
```

1. **GitHub Actions** wakes up every 4 hours and runs the Python pipeline.
2. The pipeline **collects** headlines from Google News RSS searches, **filters** off-topic items, **groups** near-duplicates, and asks **Gemini** (free tier) to judge relevance and write a short, neutral summary.
3. Stories wait as drafts, or publish straight away for categories you choose. Approvals are a JSON file you can edit from your phone.
4. The bot commits the results to this repo. **Vercel** sees the commit and redeploys the **Astro** site.

Summaries use only the headline and snippet, never the full article, and every story links back to its sources.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Website | Astro | Fast static output, reads the pipeline's JSON and Markdown directly |
| Hosting | Vercel (free) | Auto-deploys on every commit |
| Pipeline | Python, SQLite, `feedparser` | Small, readable, no server to run |
| Scheduling | GitHub Actions | Free cloud cron; state is saved back to the repo |
| AI | Gemini free tier (Ollama or Anthropic optional) | Zero cost; provider is a setting, not a rewrite |

## Project structure

```
The Fashion Business/
├── src/                          # the website
│   ├── layouts/Base.astro        # nav, footer, fonts, global styles
│   ├── pages/
│   │   ├── index.astro           # home, newsletter, news list, contact (one scrolling page)
│   │   ├── article.astro         # article page, likes and comments
│   │   └── join.astro            # log in / sign up
│   └── articles/weekly.md        # the weekly article, written in Markdown
├── public/img/                   # logo wing and flower artwork
├── content/
│   ├── drafts.txt                # drafts waiting for review (generated)
│   └── news/                     # published stories as JSON (generated, read by the site)
├── data/
│   ├── decisions.json            # approve / reject stories by id
│   ├── fashion.sql               # pipeline state, saved as text between runs
│   └── fashion.db                # local database (git-ignored)
├── .github/workflows/news.yml    # the 4-hourly cloud schedule
├── pipeline.py                   # collect, filter, group, summarise, export
├── ci.py                         # cloud glue: restore state, apply decisions, save state
├── sources.yaml                  # feeds and keyword filters
├── package.json, astro.config.mjs, tsconfig.json
└── requirements.txt
```

## Run it yourself

**Website**

```bash
npm install
npm run dev          # http://localhost:4321
npm run build        # production build
```

**News pipeline** (needs a free key from [Google AI Studio](https://aistudio.google.com))

```bash
python -m venv .venv
source .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # add GEMINI_API_KEY inside
python pipeline.py run
```

**In the cloud:** add `GEMINI_API_KEY` as a repository secret, set Workflow permissions to *Read and write*, and run **News pipeline** from the Actions tab. Connect the repo to Vercel to deploy the site.

### Reviewing stories

Read `content/drafts.txt`, then edit `data/decisions.json` on GitHub (works from a phone):

```json
{"approve": [3, 5], "reject": [4]}
```

To publish whole categories automatically, set `FB_AUTO_PUBLISH` in `.github/workflows/news.yml`, for example `"fashion-week,textiles,retail"`. Keep `funding` on manual review, since a wrong number there hurts credibility most.

### Settings

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | none | Key for the default provider |
| `FB_PROVIDER` | `gemini` | `gemini`, `ollama` or `anthropic` |
| `FB_MODEL` | per provider | Override the model name |
| `FB_MAX_LLM_CALLS` | `40` (workflow: 60) | Cap on AI calls per run |
| `FB_CALL_DELAY` | `6` | Seconds between calls, to respect free-tier limits |
| `FB_AUTO_PUBLISH` | empty | Categories that skip review |

## Design decisions

- **Headline-only summaries** keep the site clear of copying publishers' articles.
- **State as a text dump.** A cloud runner forgets everything between runs, and a binary database would bloat git. A text dump stays small and diff-friendly.
- **Review without a server.** Decisions are a JSON file edited in the GitHub web UI, so there is no admin panel to host or secure.
- **Bounded and safe to re-run.** Seen links are never reprocessed, a per-run call cap limits cost, and a bad key stops the run immediately.

## Not built yet (honest status)

- **Accounts.** The Join page is a working interface, but nothing is saved yet. Real log-in and newsletter sign-up need a backend such as Supabase.
- **Likes and comments** are stored in the visitor's own browser until accounts exist.
- **Contact form** opens the visitor's email app rather than sending a message.
- **Better source feeds.** Google News RSS gives headlines only. A commercial launch should use publisher feeds with checked terms, or a licensed news API.

## Roadmap

- [x] Automated news pipeline, running in the cloud
- [x] Website live on Vercel with auto-deploy
- [x] Mobile layout and menu
- [ ] Sharper duplicate grouping and stricter topic filter
- [ ] Real accounts and newsletter subscriptions (Supabase)
- [ ] Weekly email digest
- [ ] Brand pages and Indian brand histories
- [ ] "Global influence" series: global fashion that borrowed from India
- [ ] Direct publisher feeds for richer summaries

## Author

Built by **Avishka Srivastava**.
