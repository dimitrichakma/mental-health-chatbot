"""Turn a follow-up question into a standalone one using the chat history.

Split out of agent.py so the pipeline (planner.run_pipeline) and the eval
harness can condense without importing the whole LangGraph/Postgres agent.
"""
from pydantic import BaseModel, Field

from .llm import fast_llm


class ConversationalQuestion(BaseModel):
    standalone_question: str = Field(
        description="The user's latest question rewritten to be fully understandable on its own, resolving any pronouns or implicit references using the conversation history. If the question is already standalone, return it unchanged."
    )


condenser_llm = fast_llm.with_structured_output(ConversationalQuestion)


def condense_question(question, chat_history):
    if not chat_history:
        return question
    history_text = "\n".join(
        [f"Q: {h['question']}\nA: {h['answer']}" for h in chat_history[-3:]]
    )
    try:
        result = condenser_llm.invoke(
            f"Conversation history:\n{history_text}\n\nLatest question: {question}\n\n"
            "Rewrite the latest question to be fully standalone, resolving any references to the conversation above."
        )
        return result.standalone_question
    except Exception:
        return question
