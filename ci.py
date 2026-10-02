"""Glue for the GitHub Actions run.

    python ci.py before   restore saved state (if needed) and apply your approve/reject decisions
    python ci.py after    save state as text and write a readable list of drafts
"""
import contextlib
import io
import json
import sqlite3
import sys
from pathlib import Path

import pipeline

ROOT = Path(__file__).parent
SQL = ROOT / "data" / "fashion.sql"
DECISIONS = ROOT / "data" / "decisions.json"
DRAFTS = ROOT / "content" / "drafts.txt"


def before():
    if SQL.exists() and not pipeline.DB_PATH.exists():
        pipeline.DB_PATH.parent.mkdir(exist_ok=True)
        con = sqlite3.connect(pipeline.DB_PATH)
        con.executescript(SQL.read_text(encoding="utf-8"))
        con.close()
        print("State restored from data/fashion.sql")
    if DECISIONS.exists():
        decisions = json.loads(DECISIONS.read_text(encoding="utf-8"))
        if decisions.get("approve"):
            pipeline.set_status(decisions["approve"], "published")
        if decisions.get("reject"):
            pipeline.set_status(decisions["reject"], "rejected")


def after():
    pipeline.connect().close()  # make sure the database and table exist
    con = sqlite3.connect(pipeline.DB_PATH)
    SQL.parent.mkdir(exist_ok=True)
    SQL.write_text("\n".join(con.iterdump()) + "\n", encoding="utf-8")
    con.close()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        pipeline.review()
    DRAFTS.parent.mkdir(parents=True, exist_ok=True)
    DRAFTS.write_text(buf.getvalue().strip() + "\n", encoding="utf-8")
    print("State saved to data/fashion.sql, drafts listed in content/drafts.txt")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "before":
        before()
    elif cmd == "after":
        after()
    else:
        print(__doc__)
