"""Review logged conversations + tester feedback from the backend's Postgres.

Needs DATABASE_URL pointing at the database the deployed backend writes to.
On Railway, the Postgres DATABASE_URL is internal-only, so either:

  * enable Public Networking (TCP proxy) on the Postgres service, then:
      DATABASE_URL='<public connection string>' python review_logs.py

  * or run ad-hoc SQL:  railway connect Postgres   (see review_logs.sql)

Locally (backend writing to your own Postgres), DATABASE_URL from .env works.

    python review_logs.py                 # summary + newest 30
    python review_logs.py --flagged       # only 👎 or noted
    python review_logs.py --csv out.csv   # dump everything to CSV
"""
import argparse
import csv
import os
import sys

import psycopg
from dotenv import load_dotenv

load_dotenv()

QUERY = """
SELECT id, ts, thread_id, question, answer, paths_used, is_crisis,
       latency_ms, feedback, feedback_note
FROM conversation_log
ORDER BY ts DESC
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", metavar="PATH", help="write every row to this CSV file")
    ap.add_argument("--flagged", action="store_true", help="only show 👎 or noted conversations")
    ap.add_argument("--limit", type=int, default=30, help="how many to print (default 30)")
    args = ap.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set — see the module docstring.")

    with psycopg.connect(url) as conn:
        rows = conn.execute(QUERY).fetchall()
        cols = [d.name for d in conn.cursor().execute(QUERY + " LIMIT 0").description]

    if not rows:
        print("No conversations logged yet.")
        return

    total = len(rows)
    up = sum(1 for r in rows if r[8] == 1)
    down = sum(1 for r in rows if r[8] == -1)
    noted = sum(1 for r in rows if r[9])
    crisis = sum(1 for r in rows if r[6])
    lat = [r[7] for r in rows if r[7] is not None]
    med_lat = sorted(lat)[len(lat) // 2] if lat else 0
    print(
        f"{total} conversations  ·  👍 {up}  👎 {down}  (unrated {total - up - down})  "
        f"·  {noted} with notes  ·  {crisis} crisis  ·  median {med_lat} ms\n"
    )

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        print(f"Wrote {total} rows to {args.csv}")
        return

    shown = [r for r in rows if (r[8] == -1 or r[9])] if args.flagged else rows
    for r in shown[: args.limit]:
        _id, ts, thread, q, a, paths, is_c, latency, fb, note = r
        mark = {1: "👍", -1: "👎"}.get(fb, "  ")
        tag = "CRISIS" if is_c else ",".join(paths or [])
        print(f"[{_id}] {ts:%Y-%m-%d %H:%M}  {mark}  {tag}  ({latency} ms)  thread {(thread or '')[:8]}")
        print(f"  Q: {q}")
        print(f"  A: {a[:280]}{'…' if len(a) > 280 else ''}")
        if note:
            print(f"  📝 {note}")
        print()


if __name__ == "__main__":
    main()
