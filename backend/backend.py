import json
import logging
import os
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.agent import run_agent, pool

logger = logging.getLogger("backend")

# allowed browser origins for the Streamlit frontend. defaults to local dev;
# in deploy set ALLOWED_ORIGINS to a comma-separated list of frontend URLs.
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:8501").split(",")
    if o.strip()
]

# conversation logging + feedback, for reviewing test sessions. reuses the
# checkpointer's connection pool (pool is None -> logging disabled, e.g. local
# dev without DATABASE_URL).
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
    feedback      SMALLINT,          -- 1 = up, -1 = down, NULL = none
    feedback_note TEXT,
    feedback_ts   TIMESTAMPTZ
)
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    if pool is not None:
        try:
            with pool.connection() as conn:
                conn.execute(_LOG_TABLE_SQL)
        except Exception:
            logger.exception("could not create conversation_log table")
    yield
    if pool is not None:
        pool.close()


app = FastAPI(title="mental-health-chatbot", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _log_conversation(thread_id, question, answer, paths_used, is_crisis, latency_ms):
    if pool is None:
        return None
    try:
        with pool.connection() as conn:
            row = conn.execute(
                """INSERT INTO conversation_log
                       (thread_id, question, answer, paths_used, is_crisis, latency_ms)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (thread_id, question, answer, json.dumps(paths_used), is_crisis, latency_ms),
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


@app.post("/chat")
def chat(request: ChatRequest):
    thread_id = request.thread_id or str(uuid4())
    t0 = time.perf_counter()
    try:
        output = run_agent(request.question, thread_id=thread_id)
    except Exception:
        logger.exception("run_agent failed")
        raise HTTPException(503, "The assistant is temporarily unavailable. Please try again.")
    latency_ms = int((time.perf_counter() - t0) * 1000)

    paths_used = sorted({r["path"] for r in output["results"]}) if output["results"] else []
    is_crisis = not output["results"]              # safety gate returns no retrieval results
    log_id = _log_conversation(
        thread_id, request.question, output["answer"], paths_used, is_crisis, latency_ms
    )

    return {
        "answer": output["answer"],
        "paths_used": paths_used,
        "thread_id": thread_id,
        "log_id": log_id,
    }


@app.post("/feedback")
def feedback(fb: Feedback):
    if pool is None:
        raise HTTPException(503, "feedback storage unavailable")
    try:
        with pool.connection() as conn:
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
