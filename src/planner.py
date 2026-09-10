from pydantic import BaseModel, Field

from .llm import fast_llm, smart_llm
from .router import route_all
from .condense import condense_question
from .safety import check_safety

class SubquestionList(BaseModel):
    subquestions: list[str] = Field(
        description="1 to 3 simple subquestions the original question breaks into, or the original question itself in a list of one if it does not need splitting"
    )

planner_llm = fast_llm.with_structured_output(SubquestionList)

def plan_subquestions(question):
    try:
        result = planner_llm.invoke(
            f"Break this question into 1 to 3 simple subquestions if it needs more than one lookup, otherwise return it as is.\n\nQuestion: {question}"
        )
        # hard cap at 3: each subquestion triggers a full route + retrieve +
        # grade cycle, so a model that ignores the instruction and returns 10
        # would fan out into a very expensive request
        return result.subquestions[:3] or [question]
    except Exception:
        return [question]  # fall back to treating it as one single question
def synthesize_answer(question, retrieval_results):
    context_text = ""
    for r in retrieval_results:
        if r["context"]:  # skip subquestions that came back with nothing
            context_text += f"\n[{r['path']}] {r['context']}\n"

    if not context_text.strip():
        return (
            "I don't have reliable information on that in my sources. "
            "I can only answer from the CBT and mental-health knowledge base I was given."
        )

    response = smart_llm.invoke(
        f"""Answer the question using ONLY the context below. Mention which pieces came from the graph versus the text sources if relevant.

If the context does not actually contain enough to answer the question, say "I don't have reliable information on that" instead of guessing or using outside knowledge.

Question: {question}
Context: {context_text}"""
    )
    return response.content

def run_pipeline(question, chat_history=None):
    """Full retrieval pipeline, minus the LangGraph/Postgres wrapper in agent.py.

    Mirrors the agent's node sequence: safety gate -> condense -> plan ->
    route/retrieve -> synthesize. Used by the offline eval and any non-stateful
    caller. On a crisis it short-circuits exactly like the agent does.
    """
    crisis = check_safety(question)
    if crisis:
        return {"answer": crisis, "results": [], "crisis": True, "standalone_question": question}

    standalone = condense_question(question, chat_history) if chat_history else question
    subquestions = plan_subquestions(standalone)
    results = route_all(subquestions)
    answer = synthesize_answer(standalone, results)
    return {"answer": answer, "results": results, "crisis": False, "standalone_question": standalone}
