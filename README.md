# mental-health-chatbot

A CBT / mental-health question-answering agent with **hybrid retrieval** (a Neo4j
knowledge graph + a Pinecone vector store), a **corrective-retrieval router**, a
**LangGraph agent** with conversation memory, and a **live web-search fallback**
that vets, chunks, and ingests new sources on the fly.

**Live app:** https://mental-health-chatbot-dimitri.streamlit.app · **API:** https://backend-production-63da.up.railway.app

> Personal learning project. Not medical advice.

![demo](assets/demo.gif)

*Knowledge-base answer → memory follow-up ("how is **it** used for OCD") → knowledge-graph answer → safety gate.*

## How it works

```
question
  │
  ├─ safety gate ─────────────────────► LLM crisis classifier; returns a crisis
  │                                     response and stops if risk is high
  ▼
condense ──► rewrite into a standalone question using chat history
  ▼
plan ──────► split into 1–3 sub-questions
  ▼
retrieve ──► per sub-question, the router:
  │            1. classifies path: graph_rag / naive_rag / both, extracts an entity
  │            2. retrieves (graph traversal and/or vector search)
  │            3. grades relevance; if weak, tries the other path
  │            4. still weak → web_search_and_ingest: search → worthiness check →
  │               semantic chunk → embed into Pinecone → use the text this turn
  │            5. nothing works → "no_answer" (synthesizer says it doesn't know)
  ▼
synthesize ► answer from retrieved context only; refuses to guess
```

- **Graph** (`src/retrieval.py`): relation-tiered traversal — specific facts
  (contraindication, has_symptom, exhibits, reflects…) ranked above vague
  disease links above plain hierarchy; round-robin diversify so one relation
  can't crowd out the rest.
- **Vector store**: `voyage-3.5` embeddings, contextual `[title — section]`
  prefix on every chunk, counsel-chat Q&A kept whole, long docs semantically
  chunked.
- **Memory**: LangGraph checkpointer over Postgres (`DATABASE_URL`), keyed by
  `thread_id`.

## Layout

```
src/                 runtime package (agent, router, planner, retrieval,
                     grading, safety, web_search_fallback)
backend/backend.py   FastAPI: POST /chat, GET /health
frontend/frontend.py Streamlit chat UI
data_prep/           one-off build scripts (chunk, embed, load graph)
data/                source datasets + generated artifacts — NOT in the repo,
                     rebuild with data_prep/ (see below)
eval/                golden_eval_set.json  (+ evaluate.py at repo root)
docs/                BUILD_GUIDE.md, FIXES.md
Dockerfile           builds the backend image (backend deps only)
```

## Setup

```bash
cp .env.example .env          # fill in the keys
uv sync                       # or: pip install -r requirements.txt
```

Needs: Anthropic, Voyage, Pinecone, Tavily API keys; a Neo4j instance with APOC;
a Postgres database.

## Build the stores (one-time)

```bash
# run from the repo root
python -m data_prep.merge_authoritative_sources   # add curated CBT docs to the corpus
python -m data_prep.chunk_vector_sources          # chunk → data/processed/vector_chunks_final.json
python -m data_prep.build_vector_store            # embed → Pinecone
python -m data_prep.load_neo4j                    # filtered + canonicalized graph load, with indexes
```

The source data (`vector_source_merged.csv`, `data/raw/authoritative_cbt/docs.json`)
is kept local. `merge_authoritative_sources.py` expects `docs.json`; the base
CSV must be supplied separately.

## Run

```bash
uvicorn backend.backend:app --port 8000     # API  (POST /chat, /feedback, GET /health)
streamlit run frontend/frontend.py          # chat UI  ->  http://localhost:8501
```

The Streamlit app reads `BACKEND_URL` (default `http://localhost:8000`).

## Conversation logging & feedback

When `DATABASE_URL` is set, the backend logs every `/chat` (question, answer,
retrieval paths, latency, crisis flag) to a `conversation_log` table, and the
UI shows a 👍/👎 + optional note under each answer (`POST /feedback`). Review
tester sessions with:

```bash
python review_logs.py            # summary + newest conversations
python review_logs.py --flagged  # only 👎 / noted
python review_logs.py --csv out.csv
```

or ad-hoc SQL via `railway connect Postgres` + `review_logs.sql`.

Library use / eval:

```python
from src.agent import run_agent
run_agent("what is exposure and response prevention?", thread_id="demo")
run_agent("what about for OCD specifically?", thread_id="demo")   # uses conversation memory
```

Evaluation has two layers. Install the eval deps first: `uv sync --group eval`.

**Primary — Ragas RAG metrics** (`ragas_eval.py`), the industry-standard layer:

```bash
python ragas_eval.py                     # concept / graph / combined / memory items
python ragas_eval.py --category graph
python ragas_eval.py --limit 5           # quick smoke
python ragas_eval.py --all-opus          # every metric on Opus (pricier)
python ragas_eval.py --strict            # + factual_correctness (recall)
```

Metrics: `faithfulness` on **Opus 5** (the one metric where the judge's nuance
moves the score); `clinical_safety` (custom critic), `answer_relevancy`,
`llm_context_precision`, `context_recall` on Sonnet 5. `--all-opus` runs
everything on Opus. Per-item scores land in `eval/ragas_run.csv`.

**Companion — custom harness** (`evaluate.py`) for what Ragas can't score:

```bash
python evaluate.py                          # whole golden set
python evaluate.py --category safety,graph   # one or more categories only
python evaluate.py --limit 5                 # quick smoke
python evaluate.py --web                     # also allow the live web-search fallback
```

The golden set (`eval/golden_eval_set.json`) tags every item with a `category`.
`evaluate.py` scores `concept` / `combined` on answer quality + routing, `graph`
against the **live** graph (Cypher for every valid edge, so it doesn't matter
which one retrieval surfaced) plus a retrieval-hit check, `safety` on whether the
crisis gate fired exactly when it should, and `abstain` on whether the bot
declined instead of answering from thin context. Web-search fallback is off by
default so `abstain` stays honest.

**Judge & cost.** Opus 5 for the nuanced calls (`JUDGE_MODEL`), Sonnet 5 for
the rest (`JUDGE_FAST_MODEL`). Spend is metered per call and the run aborts with
a partial report once it passes `EVAL_MAX_USD` (default $5). A full Ragas pass
runs roughly $3–4 with the default split (more with `--all-opus` / `--strict`);
the custom harness is well under $1. Use `--category` / `--limit` while iterating.

## Deployment

- **Backend** → Railway (`Dockerfile`, backend deps only) + Railway Postgres.
  `railway.toml` sets the Docker builder and a `/health` check. Auto-deploys
  from `main`.
- **Frontend** → Streamlit Community Cloud (`frontend/frontend.py`,
  `frontend/requirements.txt`). `BACKEND_URL` is set in the app's Secrets.
  Auto-deploys from `main`.

First-time setup:

```bash
railway init
railway add --database postgres           # injects DATABASE_URL
# set ANTHROPIC_API_KEY, VOYAGE_API_KEY, PINECONE_API_KEY, NEO4J_URI,
# NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE, TAVILY_API_KEY on the service
railway up && railway domain
railway service source connect --repo <owner>/<repo> --branch main --service backend
# then set ALLOWED_ORIGINS to the deployed Streamlit URL
```

## Status

Deployed and working end-to-end: safety gate, condense/plan/retrieve/synthesize
agent, corrective router, graph + vector retrieval, web fallback, Postgres
memory, FastAPI backend, Streamlit chat UI, eval harness.
