from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import os
from .safety import check_safety
from .planner import plan_subquestions, synthesize_answer
from .router import route_all
from .llm import fast_llm

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

class AgentState(TypedDict):
    question: str
    standalone_question: str
    chat_history: list[dict]
    safety_response: Optional[str]
    subquestions: list[str]
    results: list[dict]
    answer: Optional[str]

class ConversationalQuestion(BaseModel):
    standalone_question: str = Field(
        description="The user's latest question rewritten to be fully understandable on its own, resolving any pronouns or implicit references using the conversation history. If the question is already standalone, return it unchanged."
    )

condenser_llm = fast_llm.with_structured_output(ConversationalQuestion)

def condense_question(question, chat_history):
    if not chat_history:
        return question
    history_text = "\n".join([f"Q: {h['question']}\nA: {h['answer']}" for h in chat_history[-3:]])
    try:
        result = condenser_llm.invoke(
            f"Conversation history:\n{history_text}\n\nLatest question: {question}\n\nRewrite the latest question to be fully standalone, resolving any references to the conversation above."
        )
        return result.standalone_question
    except Exception:
        return question

def safety_node(state: AgentState) -> dict:
    return {"safety_response": check_safety(state["question"])}

def route_after_safety(state: AgentState) -> str:
    if state["safety_response"] is not None:
        return "end_early"
    return "continue"

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

def run_agent(question, thread_id="default"):
    config = {"configurable": {"thread_id": thread_id}}
    result = agent.invoke({"question": question}, config=config)
    if result["safety_response"] is not None:
        return {"answer": result["safety_response"], "results": []}
    return {"answer": result["answer"], "results": result["results"]}
