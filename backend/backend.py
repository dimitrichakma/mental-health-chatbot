import json
import logging
import os
import time
from contextlib import asynccontextmanager
from uuid import uuid4

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src import day_budget
from src.agent import pool, run_agent
from src.usage import UsageTracker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend")

DATABASE_URL = os.getenv("DATABASE_URL")

# allowed browser origins for the Streamlit frontend. defaults to local dev;
# in deploy set ALLOWED_ORIGINS to a comma-separated list of frontend URLs.
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:8501").split(",")
    if o.strip()
]

# per-client request cap on /chat (abuse / runaway protection). slowapi syntax.
CHAT_RATE_LIMIT = os.getenv("CHAT_RATE_LIMIT", "20/minute")

# conversation logging + feedback, for reviewing test sessions. uses its own
# short-lived connections (isolated from the LangGraph checkpointer's pool);
# disabled entirely when DATABASE_URL is unset.
_LOG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS conversation_log (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
    thread_id     TEXT,
    question      TEXT NOT NULL,
    answer        TEXT NOT NULL,
    paths_used    JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_crisis     BOOLEAN NOT NULL DEFAULT false,
    latency_ms    INTEGER,
    cost_usd      NUMERIC(12, 6),
    feedback      SMALLINT,          -- 1 = up, -1 = down, NULL = none
    feedback_note TEXT,
    feedback_ts   TIMESTAMPTZ
)
"""
_LOG_TABLE_MIGRATE = "ALTER TABLE conversation_log ADD COLUMN IF NOT EXISTS cost_usd NUMERIC(12, 6)"


def _client_ip(request: Request) -> str:
    # Railway (and most PaaS) sit behind a proxy; the real client is the first
    # hop in X-Forwarded-For, not request.client.host.
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else get_remote_address(request)


limiter = Limiter(key_func=_client_ip)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if DATABASE_URL:
        try:
            with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
                conn.execute(_LOG_TABLE_SQL)
                conn.execute(_LOG_TABLE_MIGRATE)
            day_budget.setup()
            logger.info("conversation_log + daily_usage tables ready")
        except Exception:
            logger.exception("could not create backend tables")
    yield
    if pool is not None:
        pool.close()


app = FastAPI(title="mental-health-chatbot", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _log_conversation(thread_id, question, answer, paths_used, is_crisis, latency_ms, cost_usd):
    if not DATABASE_URL:
        return None
    try:
        with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
            row = conn.execute(
                """INSERT INTO conversation_log
                       (thread_id, question, answer, paths_used, is_crisis, latency_ms, cost_usd)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (thread_id, question, answer, json.dumps(paths_used), is_crisis,
                 latency_ms, cost_usd),
            ).fetchone()
            return row[0]
    except Exception:
        logger.exception("conversation logging failed")
        return None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = None


class Feedback(BaseModel):
    log_id: int
    rating: int | None = None                      # 1 = up, -1 = down
    note: str | None = Field(default=None, max_length=4000)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/usage")
def usage():
    spent, limit, over = day_budget.status()
    return {"today_usd": round(spent, 4), "daily_limit_usd": limit, "over_budget": over}


@app.post("/chat")
@limiter.limit(CHAT_RATE_LIMIT)
def chat(request: Request, body: ChatRequest):
    spent, limit, over = day_budget.status()
    if over:
        raise HTTPException(
            503,
            "The assistant has reached its usage limit for today. Please try again tomorrow.",
        )

    thread_id = body.thread_id or str(uuid4())
    tracker = UsageTracker()  # no ceiling - meter only
    t0 = time.perf_counter()
    try:
        output = run_agent(body.question, thread_id=thread_id, callbacks=[tracker])
    except Exception:
        logger.exception("run_agent failed")
        raise HTTPException(503, "The assistant is temporarily unavailable. Please try again.")
    latency_ms = int((time.perf_counter() - t0) * 1000)

    snap = tracker.snapshot()
    day_budget.record(snap)
    logger.info(
        "chat done: %d ms, $%.5f, %d model calls, day $%.3f/$%.2f",
        latency_ms, snap["cost_usd"], snap["calls"], spent + snap["cost_usd"], limit,
    )

    paths_used = sorted({r["path"] for r in output["results"]}) if output["results"] else []
    is_crisis = not output["results"]              # safety gate returns no retrieval results
    log_id = _log_conversation(
        thread_id, body.question, output["answer"], paths_used, is_crisis,
        latency_ms, snap["cost_usd"],
    )

    return {
        "answer": output["answer"],
        "paths_used": paths_used,
        "thread_id": thread_id,
        "log_id": log_id,
    }


@app.post("/feedback")
def feedback(fb: Feedback):
    if not DATABASE_URL:
        raise HTTPException(503, "feedback storage unavailable")
    try:
        with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
            n = conn.execute(
                """UPDATE conversation_log
                   SET feedback      = COALESCE(%(rating)s, feedback),
                       feedback_note = COALESCE(NULLIF(%(note)s, ''), feedback_note),
                       feedback_ts   = now()
                   WHERE id = %(log_id)s""",
                {"rating": fb.rating, "note": fb.note, "log_id": fb.log_id},
            ).rowcount
    except Exception:
        logger.exception("feedback write failed")
        raise HTTPException(500, "could not save feedback")
    if not n:
        raise HTTPException(404, "log_id not found")
    return {"ok": True}
