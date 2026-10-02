# The Fashion Business - content pipeline

Collects Indian fashion-business news, filters it, groups duplicate stories, writes short factual summaries with an AI model, and exports JSON files any frontend can read.

## Setup (Git Bash on Windows)

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
export GEMINI_API_KEY="your-free-key"     # from aistudio.google.com, no card needed
```

## Daily use

```bash
python pipeline.py run          # fetch, filter, group, summarise, export
python pipeline.py review       # see drafts waiting for you
python pipeline.py approve 3 5  # publish drafts by id
python pipeline.py reject 4     # discard a draft
```

Output lands in `content/news/` (one JSON file per story plus `index.json`).

## Choosing the AI provider (FB_PROVIDER)

| Provider | Cost | Setup |
|---|---|---|
| `gemini` (default) | Free tier | Key from Google AI Studio in `GEMINI_API_KEY` |
| `ollama` | Free, runs on your laptop | Install Ollama, run `ollama pull llama3.2`, then `export FB_PROVIDER=ollama` |
| `anthropic` | Paid | `pip install anthropic`, set `ANTHROPIC_API_KEY` and `FB_PROVIDER=anthropic` |

Free tiers have per-minute and per-day limits that Google can change, so check your live quota in AI Studio. The pipeline waits between calls (`FB_CALL_DELAY`) and retries once on a rate limit. Google may use free-tier requests to improve its products; the pipeline only sends public headlines.

## Settings (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `FB_PROVIDER` | `gemini` | gemini, ollama or anthropic |
| `FB_MODEL` | per provider | Override the model name |
| `FB_MAX_LLM_CALLS` | `40` | Cap per run |
| `FB_CALL_DELAY` | `6` | Seconds between calls |
| `FB_AUTO_PUBLISH` | empty | Categories that skip review, e.g. `fashion-week,textiles` |

Everything starts as a draft. Keep `funding` and `brand-moves` out of `FB_AUTO_PUBLISH`, since wrong numbers there hurt credibility most.

## How it avoids copying

It works only from the feed headline and snippet, never fetches full articles, writes its own short summary, and links every story to its sources.

## Before going live

Google News RSS is convenient for building, but for a commercial site use publisher feeds you have checked the terms for, or a licensed news API. Add them in `sources.yaml`.
