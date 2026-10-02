"""The Fashion Business - content pipeline.

Usage:
    python pipeline.py run          collect, filter, group, summarise, then export
    python pipeline.py review       list drafts waiting for approval
    python pipeline.py approve 3 5  publish drafts by id
    python pipeline.py reject 4     reject drafts by id
    python pipeline.py export       rewrite content/news/*.json from published items
"""
import datetime as dt
import difflib
import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import feedparser
import yaml

ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "fashion.db"
OUT_DIR = ROOT / "content" / "news"


def load_env():
    """Read KEY=value lines from a local .env file (kept out of git). Real environment variables win."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()

PROVIDER = os.getenv("FB_PROVIDER", "gemini").lower()  # gemini (free tier), ollama (local, free), anthropic (paid)
DEFAULT_MODELS = {"gemini": "gemini-flash-lite-latest", "ollama": "llama3.2", "anthropic": "claude-haiku-4-5-20251001"}
MODEL = os.getenv("FB_MODEL", DEFAULT_MODELS.get(PROVIDER, ""))
CALL_DELAY = float(os.getenv("FB_CALL_DELAY", "6"))  # seconds between AI calls, keeps free tiers under their per-minute limit
MAX_CALLS = int(os.getenv("FB_MAX_LLM_CALLS", "40"))  # daily-cost safety cap per run
AUTO_PUBLISH = {c.strip() for c in os.getenv("FB_AUTO_PUBLISH", "").split(",") if c.strip()}
SIMILARITY = 0.72  # title similarity above which two items count as the same story
CATEGORIES = ["funding", "retail", "d2c", "textiles", "fashion-week", "policy", "brand-moves", "other-business"]


def connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute(
        """CREATE TABLE IF NOT EXISTS items(
            id INTEGER PRIMARY KEY, url_hash TEXT UNIQUE, title TEXT, headline TEXT,
            summary TEXT, category TEXT, brands TEXT, sources TEXT,
            published_at TEXT, created_at TEXT, status TEXT)"""
    )
    return con


def clean(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(text or ""))).strip()


def collect(cfg):
    for feed in cfg["feeds"]:
        parsed = feedparser.parse(feed["url"])
        for e in parsed.entries[: cfg.get("per_feed", 30)]:
            title = clean(e.get("title", ""))
            publisher = (e.get("source") or {}).get("title", "")
            if publisher and title.endswith(f" - {publisher}"):
                title = title[: -len(publisher) - 3]  # drop the " - Publisher" suffix Google News adds
            snippet = clean(e.get("summary", ""))[:600]
            if snippet.startswith(title[:40]):
                snippet = ""  # Google News snippets only repeat the headline
            yield {
                "title": title,
                "url": e.get("link", ""),
                "snippet": snippet,
                "source": publisher or feed["name"],
                "published": e.get("published", ""),
                "trusted": feed.get("trust_query", False),
            }


def passes_prefilter(item, cfg):
    text = f"{item['title']} {item['snippet']}".lower()
    if any(w in text for w in cfg.get("block_any", [])):
        return False
    if item.get("trusted"):
        return True
    return any(w in text for w in cfg.get("must_match_any", []))


class ApiError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _post(url, body, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        raise ApiError(err.read().decode(errors="replace")[:300], err.code)
    except urllib.error.URLError as err:
        raise ApiError(f"connection problem: {err.reason}")


def make_completer():
    """Return complete(prompt) -> text for the chosen provider."""
    if PROVIDER == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            sys.exit("Set GEMINI_API_KEY (free key from aistudio.google.com).")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

        def complete(prompt):
            data = _post(url, {"contents": [{"parts": [{"text": prompt}]}],
                               "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 800}},
                         {"x-goog-api-key": key})
            return data["candidates"][0]["content"]["parts"][0]["text"]
        return complete
    if PROVIDER == "ollama":
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")

        def complete(prompt):
            return _post(f"{host}/api/generate",
                         {"model": MODEL, "prompt": prompt, "stream": False, "format": "json"})["response"]
        return complete
    if PROVIDER == "anthropic":
        import anthropic

        client = anthropic.Anthropic()

        def complete(prompt):
            msg = client.messages.create(model=MODEL, max_tokens=400, messages=[{"role": "user", "content": prompt}])
            return msg.content[0].text
        return complete
    sys.exit(f"Unknown FB_PROVIDER '{PROVIDER}'. Use gemini, ollama or anthropic.")


def with_retry(complete):
    """On a rate-limit (429) wait once and retry; free tiers allow only a few calls per minute."""
    def wrapped(prompt):
        try:
            return complete(prompt)
        except ApiError as err:
            if err.status != 429:
                raise
            print("  rate limited; waiting 30s then retrying once")
            time.sleep(30)
            return complete(prompt)
    return wrapped


def analyse(complete, item):
    """One LLM call: relevance check, category, brands, headline and summary from the feed text only."""
    prompt = f"""You edit "The Fashion Business", a site about the business of fashion in India only:
funding, retail, D2C, textiles and exports, fashion-week commerce, policy, brand strategy.
No celebrity, red-carpet or style-tip content.

Using ONLY the text below, decide whether it is relevant and write a summary.
Never add facts, numbers or names that are not in the text.

Title: {item['title']}
Snippet: {item['snippet']}

Reply with JSON only:
{{"relevant": true or false, "category": one of {CATEGORIES},
 "brands": [brand or company names mentioned],
 "headline": "neutral factual headline under 90 characters",
 "summary": "2-3 factual sentences"}}"""
    try:
        match = re.search(r"\{.*\}", complete(prompt), re.S)
        return json.loads(match.group(0)) if match else None
    except Exception as err:  # network, rate limit, bad JSON: skip and retry next run
        print(f"  analysis failed: {str(err)[:200]}")
        status = getattr(err, "status", None) or getattr(err, "status_code", None)
        text = str(err).lower()
        if "credit balance" in text or "api key not valid" in text or status in (401, 403):
            raise SystemExit("Stopping: the provider rejected the key or the account has no credit/quota. "
                             "Check your API key, then run again.")
        if status == 404:
            raise SystemExit(f"Stopping: model '{MODEL}' was not found. Set FB_MODEL to a model name your provider lists.")
        return None


def run(complete=None):
    cfg = yaml.safe_load((ROOT / "sources.yaml").read_text(encoding="utf-8"))
    if complete is None:
        complete = with_retry(make_completer())
    con = connect()
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = (now - dt.timedelta(days=3)).isoformat()
    recent = [dict(r) for r in con.execute(
        "SELECT id, title, sources FROM items WHERE created_at > ? AND status IN ('draft','published')", (cutoff,))]
    calls = added = merged = filtered = irrelevant = seen = failures = 0

    for item in collect(cfg):
        if not item["url"] or not item["title"]:
            continue
        url_hash = hashlib.sha1(item["url"].encode()).hexdigest()
        if con.execute("SELECT 1 FROM items WHERE url_hash=?", (url_hash,)).fetchone():
            seen += 1
            continue
        if not passes_prefilter(item, cfg):
            filtered += 1
            continue
        source = {"name": item["source"], "url": item["url"]}
        stamp = now.isoformat()

        # Same story already stored? Attach this link as another source instead of a new item.
        twin = next((r for r in recent if difflib.SequenceMatcher(
            None, r["title"].lower(), item["title"].lower()).ratio() >= SIMILARITY), None)
        if twin:
            sources = json.loads(twin["sources"]) + [source]
            con.execute("UPDATE items SET sources=? WHERE id=?", (json.dumps(sources), twin["id"]))
            twin["sources"] = json.dumps(sources)
            con.execute("INSERT INTO items(url_hash,title,created_at,status) VALUES(?,?,?,'merged')",
                        (url_hash, item["title"], stamp))
            merged += 1
            continue

        if calls >= MAX_CALLS:
            print("Call cap reached; remaining items wait for the next run.")
            break
        calls += 1
        result = analyse(complete, item)
        time.sleep(CALL_DELAY)
        if result is None:
            failures += 1
            if failures >= 3:
                print("3 analysis failures in a row; stopping this run.")
                break
            continue
        failures = 0
        if not result.get("relevant"):
            con.execute("INSERT INTO items(url_hash,title,created_at,status) VALUES(?,?,?,'irrelevant')",
                        (url_hash, item["title"], stamp))
            irrelevant += 1
            continue
        category = result.get("category") if result.get("category") in CATEGORIES else "other-business"
        status = "published" if category in AUTO_PUBLISH else "draft"
        cur = con.execute(
            "INSERT INTO items(url_hash,title,headline,summary,category,brands,sources,published_at,created_at,status)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (url_hash, item["title"], result.get("headline") or item["title"], result.get("summary", ""),
             category, json.dumps(result.get("brands", [])), json.dumps([source]), item["published"], stamp, status))
        recent.append({"id": cur.lastrowid, "title": item["title"], "sources": json.dumps([source])})
        added += 1

    con.commit()
    print(f"Added {added}, merged {merged}, LLM calls {calls}. "
          f"Dropped by keyword filter: {filtered}. Judged irrelevant by AI: {irrelevant}. Already seen: {seen}.")
    export(con)


def export(con=None):
    con = con or connect()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.json"):
        old.unlink()
    index = []
    rows = con.execute("SELECT * FROM items WHERE status='published' ORDER BY created_at DESC").fetchall()
    for r in rows:
        slug = re.sub(r"[^a-z0-9]+", "-", (r["headline"] or "").lower()).strip("-")[:60]
        entry = {
            "id": r["id"], "slug": slug, "headline": r["headline"], "summary": r["summary"],
            "category": r["category"], "brands": json.loads(r["brands"] or "[]"),
            "sources": json.loads(r["sources"] or "[]"), "published_at": r["published_at"],
            "created_at": r["created_at"],
        }
        (OUT_DIR / f"{r['id']}-{slug}.json").write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
        index.append(entry)
    (OUT_DIR / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exported {len(index)} published items to {OUT_DIR}")


def review():
    con = connect()
    drafts = con.execute("SELECT * FROM items WHERE status='draft' ORDER BY created_at DESC").fetchall()
    if not drafts:
        print("No drafts waiting.")
    for r in drafts:
        links = ", ".join(s["name"] for s in json.loads(r["sources"]))
        print(f"\n[{r['id']}] ({r['category']}) {r['headline']}\n    {r['summary']}\n    sources: {links}")


def set_status(ids, status):
    con = connect()
    for i in ids:
        con.execute("UPDATE items SET status=? WHERE id=? AND status='draft'", (status, int(i)))
    con.commit()
    export(con)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "run":
        run()
    elif cmd == "review":
        review()
    elif cmd == "approve":
        set_status(sys.argv[2:], "published")
    elif cmd == "reject":
        set_status(sys.argv[2:], "rejected")
    elif cmd == "export":
        export()
    else:
        print(__doc__)
