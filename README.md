# The Fashion Business

An automated news engine for **the business of fashion in India**: funding, retail, D2C, textiles and exports, fashion-week commerce, policy and brand strategy. No celebrity or red-carpet content.

A scheduled GitHub Actions job collects stories, filters out what is off-topic, groups duplicates, writes short factual summaries with a free AI model, and publishes the result as plain JSON files that any frontend can read. It runs every 4 hours without anyone touching it.

> **Status:** backend complete and running in the cloud. The frontend (planned: Astro, deployed free on Vercel) and the hand-written sections (weekly "global influence" features, Indian brand histories) are the next phase.

---

## How it works

```
 Google News RSS feeds  ──►  keyword filter  ──►  duplicate grouping  ──►  AI summary
 (sources.yaml)              (block celebrity)    (similar headlines       (relevance, category,
                                                   become one story)        brands, headline, summary)
                                                                                  │
 content/news/*.json  ◄──  approve / auto-publish  ◄──  draft  ◄─────────────────┘
 content/drafts.txt        (data/decisions.json)
```

1. **Collect:** reads the RSS feeds in `sources.yaml`.
2. **Filter:** drops celebrity items by keyword before any AI cost is spent. Topic-scoped feeds are marked `trust_query: true`, so the AI judges their relevance.
3. **Group:** headlines at least 72% similar are merged into one story with several source links.
4. **Summarise:** the AI sees only the feed headline and snippet. It decides relevance, assigns one of 8 categories, extracts brand names, and writes a neutral headline and a 2 to 3 sentence summary.
5. **Publish:** stories start as drafts. Approve them by id in `data/decisions.json`, or let chosen categories publish automatically with `FB_AUTO_PUBLISH`.
6. **Export:** published stories are written to `content/news/`, one JSON file per story plus `index.json`.

Story statuses: `draft`, `published`, `rejected`, `merged` (folded into another story) and `irrelevant` (rejected by the AI, remembered so it isn't reprocessed).

---

## Project structure

```
The Fashion Business/
├── .github/workflows/news.yml   # cloud schedule: runs every 4 hours (UTC) and on demand
├── content/
│   ├── drafts.txt               # readable list of drafts waiting for review (generated)
│   └── news/
│       ├── index.json           # all published stories, newest first (frontend reads this)
│       └── <id>-<slug>.json     # one file per published story
├── data/
│   ├── decisions.json           # you edit this: {"approve": [3, 5], "reject": [4]}
│   ├── fashion.sql              # text copy of the database, committed so state survives between runs
│   └── fashion.db               # local SQLite database (git-ignored)
├── pipeline.py                  # collect, filter, group, summarise, review, export
├── ci.py                        # glue for the cloud run: restore state, apply decisions, save state
├── sources.yaml                 # feeds and keyword filters
├── requirements.txt
├── .env.example                 # template for local settings
└── .gitignore
```

---

## Run it in the cloud (GitHub Actions)

1. Push this repo to GitHub.
2. Add your AI key: **Settings → Secrets and variables → Actions → New repository secret**, named `GEMINI_API_KEY`.
3. Allow the bot to commit: **Settings → Actions → General → Workflow permissions → Read and write**.
4. Open the **Actions** tab, choose **News pipeline**, and click **Run workflow** to test it. After that it runs every 4 hours.

Each run restores state from `data/fashion.sql`, applies your decisions, processes new items, saves state again, and commits the changes back to the repo as `news-bot`.

### Reviewing stories (works from a phone, no terminal)

1. Read `content/drafts.txt` on GitHub. Each draft has an id, category, headline, summary and sources.
2. Edit `data/decisions.json` with the pencil icon:
   ```json
   {"approve": [3, 5], "reject": [4]}
   ```
3. Commit. The next run applies it (or start a run manually from the Actions tab).

Decisions are re-applied on every run, which is harmless: only drafts can change status.

### Skipping review

Add `FB_AUTO_PUBLISH` to the workflow's `env:` to publish categories immediately:

```yaml
FB_AUTO_PUBLISH: "fashion-week,textiles,retail,d2c,policy,other-business"
```

I recommend keeping `funding` and `brand-moves` on manual review, since a wrong number there hurts credibility most.

---

## Run it locally

```bash
python -m venv .venv
source .venv/Scripts/activate        # Git Bash on Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # then put your key in .env
```

```bash
python pipeline.py run               # fetch, filter, group, summarise, export
python pipeline.py review            # list drafts
python pipeline.py approve 3 5       # publish drafts by id
python pipeline.py reject 4          # discard drafts
python ci.py before                  # rebuild the local database from data/fashion.sql
python ci.py after                   # save state and refresh content/drafts.txt
```

The cloud is the source of truth. Before working locally, run `git pull`; to rebuild your local database, delete `data/fashion.db` and run `python ci.py before`.

---

## AI providers (free by default)

| `FB_PROVIDER` | Cost | Setup |
|---|---|---|
| `gemini` (default) | Free tier | Key from Google AI Studio in `GEMINI_API_KEY` |
| `ollama` | Free, runs locally | Install Ollama, `ollama pull llama3.2`, set `FB_PROVIDER=ollama` |
| `anthropic` | Paid | `pip install anthropic`, set `ANTHROPIC_API_KEY` and `FB_PROVIDER=anthropic` |

Free tiers have per-minute and per-day limits that the provider can change; check your live quota in AI Studio. The pipeline waits between calls, retries once on a rate limit, and stops with a clear message if the key, quota or model name is wrong.

## Settings

Set as environment variables, in `.env` locally or in the workflow's `env:` in the cloud.

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | none | Key for the default provider |
| `FB_PROVIDER` | `gemini` | `gemini`, `ollama` or `anthropic` |
| `FB_MODEL` | per provider | Override the model name (default `gemini-flash-lite-latest`) |
| `FB_MAX_LLM_CALLS` | `40` (workflow uses 60) | Cap on AI calls per run |
| `FB_CALL_DELAY` | `6` | Seconds between AI calls (keeps free tiers under their rate limit) |
| `FB_AUTO_PUBLISH` | empty | Categories that skip review |

Categories: `funding`, `retail`, `d2c`, `textiles`, `fashion-week`, `policy`, `brand-moves`, `other-business`.

---

## Design decisions

- **Headline-only summaries.** The pipeline never fetches full articles. It summarises the headline and snippet in its own words and links every story to its sources. This keeps it clear of copying publishers' work.
- **State as a text dump.** A cloud runner forgets everything between runs. Committing a binary SQLite file would bloat the repo, so `ci.py` saves a text dump (`data/fashion.sql`) that git stores compactly, and rebuilds the database from it at the start of each run.
- **Review without a server.** Decisions are a JSON file edited in the GitHub web UI, so there is no admin panel to host or secure.
- **Idempotent and bounded.** Seen links are never reprocessed, decisions can be re-applied safely, and a per-run call cap plus a fatal-error stop keep a bad key or quota from burning through requests.
- **Provider-agnostic AI step.** One `complete(prompt)` function per provider, using only the standard library for HTTP, so switching models is a setting, not a rewrite.

## Limitations

- Google News snippets are just the headline, so summaries are short and can only restate what the headline says.
- AI summaries can still be vague or occasionally wrong. Spot-check them, especially anything with numbers.
- Google News RSS is convenient for building. For a commercial launch, use publisher feeds whose terms you have checked, or a licensed news API, and add them to `sources.yaml`.
- Feeds carry no usable images. The frontend should not rely on photos for news cards.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `analysis failed: ... credit balance` | The provider has no credit. Use the free Gemini provider or add credit. |
| `model '...' was not found` | Set `FB_MODEL` to a model name your provider lists. |
| `rate limited; waiting 30s` | Normal on free tiers. Raise `FB_CALL_DELAY` if it repeats. |
| `git add .` hangs and mentions `.venv` | `.gitignore` is missing or misnamed. Fix it, then `git rm -r --cached .venv`. |
| Cloud run fails with `pathspec 'data/fashion.sql' did not match` | `ci.py` is empty or wasn't pushed. Check `wc -l ci.py`. |
| Actions tab shows the file path instead of "News pipeline" | `news.yml` has a syntax error (usually indentation). Open the failed run for the message. |
| Approved stories still appear in `drafts.txt` | Decisions apply at the start of a run and the list refreshes at the end. Start a run manually. |
| Never commit `.env` | If a key was ever pushed, delete it at the provider and create a new one. |

## Roadmap

- [x] Collect, filter, group, summarise, review, export
- [x] Free AI provider with automatic cloud schedule
- [ ] `brands.json`: stories grouped by brand
- [ ] Markdown formats for the weekly "global influence" feature and brand histories
- [ ] Frontend (Astro) deployed on Vercel
- [ ] Weekly newsletter digest
- [ ] Direct publisher feeds for richer summaries
