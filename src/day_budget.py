"""Persistent daily spend cap for the production backend.

A rolling per-day budget kept in Postgres (survives restarts, shared across
workers). The backend checks it before handling a `/chat` request and returns
503 once the day is over budget; each finished request rolls its measured cost
into the day's row.

  DAILY_BUDGET_USD   ceiling per calendar day, UTC (default 5.00)

No-ops gracefully when DATABASE_URL is unset (local dev) - nothing is capped.
"""
import logging
import os

import psycopg

logger = logging.getLogger("day_budget")

DATABASE_URL = os.getenv("DATABASE_URL")
DAILY_BUDGET_USD = float(os.getenv("DAILY_BUDGET_USD", "5.00"))

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS daily_usage (
    day           DATE PRIMARY KEY,
    input_tokens  BIGINT NOT NULL DEFAULT 0,
    output_tokens BIGINT NOT NULL DEFAULT 0,
    cost_usd      NUMERIC(12, 6) NOT NULL DEFAULT 0,
    requests      INTEGER NOT NULL DEFAULT 0
)
"""


def setup():
    if not DATABASE_URL:
        return
    with psycopg.connect(DATABASE_URL, autocommit=True, connect_timeout=5) as conn:
        conn.execute(TABLE_SQL)


def status():
    """(spent_today, limit, is_over). is_over is always False without a DB."""
    if not DATABASE_URL:
        return 0.0, DAILY_BUDGET_USD, False
    try:
        with psycopg.connect(DATABASE_URL, autocommit=True, connect_timeout=5) as conn:
            row = conn.execute(
                "SELECT cost_usd FROM daily_usage WHERE day = (now() AT TIME ZONE 'utc')::date"
            ).fetchone()
        spent = float(row[0]) if row else 0.0
        return spent, DAILY_BUDGET_USD, spent >= DAILY_BUDGET_USD
    except Exception:
        logger.warning("daily budget check failed; allowing request", exc_info=True)
        return 0.0, DAILY_BUDGET_USD, False


def record(snapshot):
    """Roll one request's UsageTracker.snapshot() into today's row."""
    if not DATABASE_URL or not snapshot:
        return
    in_tok = sum(r["input"] + r["cache_read"] + r["cache_write"]
                 for r in snapshot["by_model"].values())
    out_tok = sum(r["output"] for r in snapshot["by_model"].values())
    try:
        with psycopg.connect(DATABASE_URL, autocommit=True, connect_timeout=5) as conn:
            conn.execute(
                """INSERT INTO daily_usage (day, input_tokens, output_tokens, cost_usd, requests)
                   VALUES ((now() AT TIME ZONE 'utc')::date, %(in)s, %(out)s, %(cost)s, 1)
                   ON CONFLICT (day) DO UPDATE SET
                       input_tokens  = daily_usage.input_tokens  + EXCLUDED.input_tokens,
                       output_tokens = daily_usage.output_tokens + EXCLUDED.output_tokens,
                       cost_usd      = daily_usage.cost_usd      + EXCLUDED.cost_usd,
                       requests      = daily_usage.requests      + 1""",
                {"in": in_tok, "out": out_tok, "cost": snapshot["cost_usd"]},
            )
    except Exception:
        logger.warning("daily budget record failed", exc_info=True)
