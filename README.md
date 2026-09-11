# CBT & Mental Health Companion

A production-shaped **RAG agent** that answers CBT / mental-health questions
strictly from a curated knowledge base — never the model's own knowledge —
with hybrid graph + vector retrieval, a self-correcting retrieval loop, a
safety gate that catches crisis messages before any retrieval happens, and
real user accounts.

Built solo, end to end: data pipeline → retrieval → agent orchestration →
safety/cost engineering → auth → two deployed services.

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-agent-1C3C3C)](https://www.langchain.com/langgraph)
[![Neo4j](https://img.shields.io/badge/Neo4j-graph-4581C3?logo=neo4j&logoColor=white)](https://neo4j.com/)
[![Pinecone](https://img.shields.io/badge/Pinecone-vector%20store-000000)](https://www.pinecone.io/)
[![Claude](https://img.shields.io/badge/Claude-Anthropic-D97757?logo=anthropic&logoColor=white)](https://www.anthropic.com/)
[![Railway](https://img.shields.io/badge/Railway-deployed-0B0D0E?logo=railway&logoColor=white)](https://railway.app/)

**Live app:** https://mental-health-chatbot.up.railway.app
**API:** https://backend-production-63da.up.railway.app/docs

> Educational / portfolio project. Not medical advice.

![demo](assets/demo.gif)

*Knowledge-base answer → memory follow-up ("how is **it** used for OCD") → knowledge-graph answer → safety gate.*

## Why this exists

Most RAG demos stop at "retrieve chunks, stuff them in a prompt." This one
is built the way a real internal tool would need to be: it has to know when
its own retrieval failed and *do something about it* before answering,
handle a domain where a wrong or hallucinated answer isn't just embarrassing
but potentially harmful, and run under a real budget instead of an unlimited
API key.

## Highlights

- **Corrective retrieval, not single-shot RAG.** A router classifies each
  sub-question (`graph_rag` / `naive_rag` / `both`), retrieves, *grades its
  own retrieval quality*, and falls back — first to the other retrieval
  path, then to a live web search that vets, chunks, and embeds new sources
  on the fly — before ever answering "I don't know."
- **Safety-first request path.** A front-door gate screens every message for
  crisis risk *before* retrieval runs, using conversation history so a bare
  follow-up ("what about for kids?") is still classified in context. Crisis
  replies resolve the country from the visitor's real IP for localized
  helplines and always carry an international-directory fallback.
- **Defense-in-depth auth**, added after the app already worked: Google
  OAuth on the frontend, a short-lived signed token (not the session cookie
  itself) proves identity to a separately-deployed backend, and every
  thread/history/feedback lookup is ownership-checked server-side — not just
  filtered client-side.
- **Cost and abuse engineering that isn't an afterthought**: a shared rate
  limiter across every model call, Postgres-backed response caching, a hard
  daily spend ceiling with graceful 503s, per-IP rate limiting, and prompt-
  injection hardening (delimited user input, explicit "treat as data"
  framing, a tightened message cap).
- **A real evaluation harness**, not spot-checking in a chat window: Ragas
  RAG metrics (faithfulness, a custom clinical-safety critic, context
  recall/precision) plus a custom harness that checks graph answers against
  live Cypher queries and confirms the crisis gate fires exactly when it
  should — both cost-guarded with a hard spend ceiling.
- **Two independently deployed services with clean separation of concerns**:
  the Next.js frontend never touches the backend's Python code or secrets,
  and the backend never sees the frontend's session cookie.

## Architecture

```
question
  │
  ├─ front-door gate ─────────────────► one Haiku call: crisis risk + on-topic?
  │      • high risk  → localized crisis helplines (IP-resolved country), stop
  │      • off-topic  → polite "I only cover mental health / CBT" decline, stop
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

`condense` + `plan` are one `fast_llm` call (`prepare`). The backend streams
the synthesized answer token-by-token over SSE (`POST /chat/stream`).

- **Graph** (`src/retrieval.py`): relation-tiered traversal — specific facts
  (contraindication, has_symptom, exhibits, reflects…) ranked above vague
  disease links above plain hierarchy; round-robin diversify so one relation
  can't crowd out the rest.
- **Vector store**: `voyage-3.5` embeddings, contextual `[title — section]`
  prefix on every chunk, counsel-chat Q&A kept whole, long docs semantically
  chunked.
- **Memory**: LangGraph checkpointer over Postgres, keyed by `thread_id`.
- **Agent graph**: `START → {safety, prepare}` run concurrently → a join
  node (`gate`) → conditional `{END | retrieve}` → `synthesize` → `END`.
  (A naive parallel-branch-into-conditional-exit graph is broken in
  LangGraph — a node fires if *any* incoming edge does — so the join node
  is load-bearing, not decorative.)

## Tech stack

| Layer | Choice |
|---|---|
| Agent orchestration | LangGraph (`StateGraph`), Postgres checkpointer |
| LLMs | Claude (Anthropic) — Haiku for classifiers/gates, Sonnet/Opus for synthesis & eval judging |
| Knowledge graph | Neo4j + APOC |
| Vector store | Pinecone, Voyage AI embeddings |
| Web fallback | Tavily search |
| Backend | FastAPI, SSE streaming, `slowapi` rate limiting |
| Frontend | Next.js 16 (App Router), Tailwind v4, TypeScript |
| Auth | Auth.js v5 (Google OAuth), short-lived JWT bridge to the backend |
| Database | Postgres (checkpoints, threads, conversation log, response cache, daily spend) |
| Eval | Ragas + a custom harness against a hand-built golden set |
| Deploy | Railway, two services, Docker |

## Engineering deep-dives

**Corrective retrieval router.** Every sub-question is graded after
retrieval, not just routed once — if the graph comes back thin, it tries the
vector store; if both are weak, it falls back to a live web search that
checks source worthiness, semantically chunks, and embeds the result into
Pinecone so the same question is faster next time. Nothing gets answered
from context the router itself flagged as weak — the synthesizer is
instructed to say it doesn't know rather than paper over a bad retrieval.

**Safety gate.** Runs concurrently with question preparation (not serially,
to avoid stacking latency), and always resolves before retrieval starts. It
classifies crisis risk *and* topicality using conversation history, so a
one-word follow-up doesn't get false-flagged as off-topic just because it
has no context on its own — a real bug this project's eval suite caught and
fixed. Crisis replies resolve a country from the browser's real public IP
(`src/geoip.py`) and always include an international-directory fallback,
because geolocation is best-effort and a fallback with no way to reach help
isn't acceptable.

**Auth model.** The frontend and backend are two independently deployed
services with no shared infrastructure. Rather than share the frontend's
session secret with the backend (coupling two services' security to one
secret) or relay every request through the frontend server (which would
hide the visitor's real IP from the backend, breaking crisis geolocation),
the frontend's own server verifies the session, then mints a *separate*,
short-lived (10 min), narrowly-scoped token the backend can verify
independently. The backend trusts nothing else — every thread, history
lookup, and feedback write is checked against the token's verified user id,
not a client-supplied one.

**Cost & abuse controls.** `src/llm.py` is the single choke point for every
model call: a shared rate limiter across all concurrent sub-question
routing, an exact-match Postgres response cache, and `max_tokens` capped
everywhere. A daily spend ceiling returns a friendly 503 instead of an
unbounded bill; `slowapi` caps `/chat` per client IP. Prompt-injection
hardening delimits all user-controlled text and explicitly instructs models
to treat it as data, including text ingested from the live web fallback
(the indirect-injection surface most RAG demos ignore).

**Evaluation.** Two layers: Ragas for industry-standard RAG metrics
(faithfulness judged by Opus — nuance moves the score; a custom clinical-
safety critic; context recall/precision), and a custom harness for what
Ragas can't score — graph answers checked against **live** Cypher queries
(not just "did retrieval find something"), and a hard pass/fail on whether
the crisis gate fired exactly when it should. Both are cost-guarded with a
hard spend ceiling that aborts with a partial report rather than run away.

## Project structure

```
src/                    runtime package - agent, router, planner, retrieval,
                         grading, safety, auth, geoip, threads, llm/caching/budget
backend/backend.py       FastAPI: /chat, /chat/stream (SSE), /threads, /history,
                         /feedback, /health, /usage
frontend/                Next.js + Tailwind chat UI
  app/                   page + layout + api/auth, api/backend-token route handlers
  components/            Header, Sidebar, SignInGate, MessageBubble, FeedbackRow, ...
  lib/                   API client, constants/types
  auth.ts                Auth.js config (Google provider)
data_prep/               one-off build scripts: chunk, embed, load the graph
eval/                    golden_eval_set.json (+ evaluate.py, ragas_eval.py at root)
docs/                    BUILD_GUIDE.md, FIXES.md
Dockerfile               backend image
Dockerfile.frontend      frontend image (multi-stage Node build)
```

## Getting started

```bash
cp .env.example .env          # fill in the keys
uv sync                       # or: pip install -r requirements.txt
```

Needs: Anthropic, Voyage, Pinecone, Tavily API keys; a Neo4j instance with
APOC; a Postgres database.

**Build the knowledge stores** (one-time):
```bash
python -m data_prep.merge_authoritative_sources   # add curated CBT docs to the corpus
python -m data_prep.chunk_vector_sources          # chunk → data/processed/vector_chunks_final.json
python -m data_prep.build_vector_store            # embed → Pinecone
python -m data_prep.load_neo4j                    # filtered + canonicalized graph load, with indexes
```

**Run:**
```bash
uvicorn backend.backend:app --port 8000     # API
cd frontend && npm install && npm run dev   # UI -> http://localhost:3000
```
The frontend calls the backend directly from the browser, so the backend's
`ALLOWED_ORIGINS` CORS setting must include wherever the frontend is served
from. Signing in locally needs `frontend/.env.local` (copy
`.env.local.example`) with `AUTH_SECRET`, `AUTH_GOOGLE_ID`,
`AUTH_GOOGLE_SECRET`, and `BACKEND_JWT_SECRET` (must match the backend
process's own env).

**Library use:**
```python
from src.agent import run_agent
run_agent("what is exposure and response prevention?", thread_id="demo")
run_agent("what about for OCD specifically?", thread_id="demo")   # uses conversation memory
```

## Conversation logging & feedback

When `DATABASE_URL` is set, the backend logs every `/chat` (question,
answer, retrieval paths, latency, crisis flag) to `conversation_log`, and
the UI collects 👍/👎 + an optional note per answer. Review with:
```bash
python review_logs.py            # summary + newest conversations
python review_logs.py --flagged  # only 👎 / noted
python review_logs.py --csv out.csv
```

## Evaluation

Install eval deps first: `uv sync --group eval`.

```bash
python ragas_eval.py             # primary - Ragas RAG metrics, ~$3-4/full run
python ragas_eval.py --category graph --limit 5   # cheap targeted iteration
python evaluate.py               # companion harness, well under $1/full run
```

Default Ragas metrics: `faithfulness` on Opus (nuance moves the score);
`clinical_safety` (custom critic), `answer_relevancy`, `context_recall` on
Sonnet. `evaluate.py` scores `concept`/`combined` on answer quality +
routing, `graph` against the live graph, `safety` on whether the crisis gate
fired exactly when it should, and `abstain` on whether the bot declined
instead of answering from thin context. Both are metered per call and abort
with a partial report if they pass `EVAL_MAX_USD` (default $5).

## Deployment

Two Railway services, both auto-deploying from `main`:
- **Backend** → `Dockerfile` + Railway Postgres.
- **Frontend** → `Dockerfile.frontend`, a standalone Next.js app; the
  browser calls the backend directly (no server-side relay), which is also
  what makes IP-based crisis-helpline geolocation work — the backend sees
  the visitor's real IP on its own, no forwarding hack required.

```bash
railway init
railway add --database postgres
# backend service: ANTHROPIC_API_KEY, VOYAGE_API_KEY, PINECONE_API_KEY, NEO4J_URI,
# NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE, TAVILY_API_KEY, BACKEND_JWT_SECRET
railway up --service backend && railway domain --service backend
railway service source connect --repo <owner>/<repo> --branch main --service backend

# frontend service: BACKEND_URL, BACKEND_JWT_SECRET (same value as backend's),
# AUTH_SECRET, AUTH_TRUST_HOST=true, AUTH_GOOGLE_ID, AUTH_GOOGLE_SECRET
railway up --service frontend --ci && railway domain --service frontend

# then set ALLOWED_ORIGINS on the backend to the frontend's domain
```

## Status

Deployed and working end-to-end: safety gate, condense/plan/retrieve/
synthesize agent, corrective retrieval router, graph + vector retrieval,
web fallback, Postgres memory, Google auth, FastAPI backend, Next.js chat
UI, eval harness.
