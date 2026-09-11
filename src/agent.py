from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv
import os
from .safety import screen_message
from .planner import prepare_query, synthesis_prompt, NO_CONTEXT_ANSWER
from .llm import smart_llm
from .router import route_all

load_dotenv()

# LangSmith tracing is fully env-driven (LANGSMITH_TRACING + LANGSMITH_API_KEY);
# just give traces a project name when one isn't set. Set LANGSMITH_HIDE_INPUTS
# to keep user messages (incl. crisis disclosures) out of the traces.
if os.getenv("LANGSMITH_TRACING", "").lower() in ("1", "true", "yes"):
    os.environ.setdefault("LANGSMITH_PROJECT", "mental-health-chatbot")

DATABASE_URL = os.getenv("DATABASE_URL")

class AgentState(TypedDict):
    question: str
    country: Optional[str]           # 2-letter code from the UI, for crisis resources
    standalone_question: str
    chat_history: list[dict]
    block_kind: Optional[str]        # "crisis" | "off_topic" | None
    block_response: Optional[str]
    subquestions: list[str]
    results: list[dict]
    answer: Optional[str]

def safety_node(state: AgentState) -> dict:
    kind, response = screen_message(
        state["question"], state.get("country"), state.get("chat_history")
    )
    return {"block_kind": kind, "block_response": response}

def prepare_node(state: AgentState) -> dict:
    standalone, subs = prepare_query(state["question"], state.get("chat_history", []))
    return {"standalone_question": standalone, "subquestions": subs}

def gate_node(state: AgentState) -> dict:
    # no-op join point: waits for safety and prepare (which run in parallel),
    # then routes. prepare's ~1s call is wasted on a blocked message, but that's
    # rare and worth it to overlap it with the safety call every other time.
    return {}

def route_after_safety(state: AgentState) -> str:
    return "end_early" if state.get("block_kind") else "continue"

def retrieve_node(state: AgentState) -> dict:
    return {"results": route_all(state["subquestions"])}

def chunk_text(chunk) -> str:
    """AIMessageChunk content -> plain text (handles the content-block list form)."""
    c = getattr(chunk, "content", "")
    if isinstance(c, str):
        return c
    return "".join(b.get("text", "") for b in c if isinstance(b, dict))


def synthesize_node(state: AgentState) -> dict:
    prompt = synthesis_prompt(state["standalone_question"], state["results"])
    if prompt is None:
        answer = NO_CONTEXT_ANSWER
    else:
        # stream the tokens so /chat/stream can forward them as they arrive;
        # /chat just gets the assembled string back
        answer = "".join(chunk_text(c) for c in smart_llm.stream(prompt))
    # build a new list rather than mutating the one LangGraph handed us
    history = state.get("chat_history", []) + [
        {"question": state["question"], "answer": answer}
    ]
    return {"answer": answer, "chat_history": history[-10:]}  # cap so it doesn't grow forever

graph = StateGraph(AgentState)
graph.add_node("safety", safety_node)
graph.add_node("prepare", prepare_node)
graph.add_node("gate", gate_node)
graph.add_node("retrieve", retrieve_node)
graph.add_node("synthesize", synthesize_node)

# safety and prepare both act on the raw question and are independent - run them
# in parallel and join at `gate`, which then decides whether we were blocked.
graph.add_edge(START, "safety")
graph.add_edge(START, "prepare")
graph.add_edge("safety", "gate")
graph.add_edge("prepare", "gate")
graph.add_conditional_edges("gate", route_after_safety, {
    "end_early": END,
    "continue": "retrieve",
})
graph.add_edge("retrieve", "synthesize")
graph.add_edge("synthesize", END)

if DATABASE_URL:
    # autocommit + no prepared statements: required for a pooled connection,
    # and doubly so for Neon's PgBouncer endpoint which rejects prepared statements
    connection_kwargs = {"autocommit": True, "prepare_threshold": 0}
    pool = ConnectionPool(conninfo=DATABASE_URL, max_size=20, kwargs=connection_kwargs)
    checkpointer = PostgresSaver(pool)
    # creates the checkpoint tables if missing; only does real work the first
    # time it runs against a fresh database
    checkpointer.setup()
else:
    # no DATABASE_URL (eval runs, quick REPL checks): keep memory in-process
    from langgraph.checkpoint.memory import MemorySaver
    pool = None
    checkpointer = MemorySaver()

agent = graph.compile(checkpointer=checkpointer)

def agent_config(thread_id="default", country=None, callbacks=None):
    """Shared invoke/stream config: memory thread, per-request callbacks, and a
    readable trace name + non-sensitive metadata for LangSmith."""
    config = {
        "configurable": {"thread_id": thread_id},
        "run_name": "chat",
        "metadata": {"thread_id": thread_id, "country": country or ""},
    }
    if callbacks:
        config["callbacks"] = callbacks
    return config


def run_agent(question, thread_id="default", country=None, callbacks=None):
    config = agent_config(thread_id, country, callbacks)
    result = agent.invoke({"question": question, "country": country}, config=config)
    if result.get("block_kind"):
        return {"answer": result["block_response"], "results": [], "kind": result["block_kind"]}
    return {"answer": result["answer"], "results": result["results"], "kind": "answer"}
