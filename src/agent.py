from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv
import os
from .safety import screen_message
from .planner import plan_subquestions, synthesize_answer
from .router import route_all
from .condense import condense_question

load_dotenv()

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
    kind, response = screen_message(state["question"], state.get("country"))
    return {"block_kind": kind, "block_response": response}

def route_after_safety(state: AgentState) -> str:
    return "end_early" if state.get("block_kind") else "continue"

def condense_node(state: AgentState) -> dict:
    chat_history = state.get("chat_history", [])
    return {"standalone_question": condense_question(state["question"], chat_history)}

def plan_node(state: AgentState) -> dict:
    return {"subquestions": plan_subquestions(state["standalone_question"])}

def retrieve_node(state: AgentState) -> dict:
    return {"results": route_all(state["subquestions"])}

def synthesize_node(state: AgentState) -> dict:
    answer = synthesize_answer(state["standalone_question"], state["results"])
    # build a new list rather than mutating the one LangGraph handed us
    history = state.get("chat_history", []) + [
        {"question": state["question"], "answer": answer}
    ]
    return {"answer": answer, "chat_history": history[-10:]}  # cap so it doesn't grow forever

graph = StateGraph(AgentState)
graph.add_node("safety", safety_node)
graph.add_node("condense", condense_node)
graph.add_node("plan", plan_node)
graph.add_node("retrieve", retrieve_node)
graph.add_node("synthesize", synthesize_node)

graph.add_edge(START, "safety")
graph.add_conditional_edges("safety", route_after_safety, {
    "end_early": END,
    "continue": "condense"
})
graph.add_edge("condense", "plan")
graph.add_edge("plan", "retrieve")
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

def run_agent(question, thread_id="default", country=None, callbacks=None):
    config = {"configurable": {"thread_id": thread_id}}
    if callbacks:
        # LangGraph propagates these to every node's LLM call - lets the backend
        # meter one request's token cost with a per-request UsageTracker
        config["callbacks"] = callbacks
    result = agent.invoke({"question": question, "country": country}, config=config)
    if result.get("block_kind"):
        return {"answer": result["block_response"], "results": [], "kind": result["block_kind"]}
    return {"answer": result["answer"], "results": result["results"], "kind": "answer"}
