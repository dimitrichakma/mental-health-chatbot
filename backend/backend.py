import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.agent import run_agent, pool

logger = logging.getLogger("backend")

# allowed browser origins for the Streamlit frontend; add the deployed URL here
ALLOWED_ORIGINS = ["http://localhost:8501"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if pool is not None:          # pool is None when running without DATABASE_URL
        pool.close()


app = FastAPI(title="mental-health-chatbot", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = None


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/chat")
def chat(request: ChatRequest):
    thread_id = request.thread_id or str(uuid4())
    try:
        output = run_agent(request.question, thread_id=thread_id)
    except Exception:
        logger.exception("run_agent failed")
        raise HTTPException(503, "The assistant is temporarily unavailable. Please try again.")

    paths_used = sorted({r["path"] for r in output["results"]}) if output["results"] else []
    return {"answer": output["answer"], "paths_used": paths_used, "thread_id": thread_id}
