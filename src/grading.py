"""Relevance grading, shared by the router's corrective loop and the web
search fallback. Kept in its own module so both can import it without a
circular dependency (router <-> web_search_fallback)."""

from typing import Literal

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

load_dotenv()


class RelevanceGrade(BaseModel):
    grade: Literal["correct", "incorrect", "ambiguous"] = Field(
        description="Whether the retrieved context contains enough on-topic information to answer the question well"
    )


_grader = ChatAnthropic(model="claude-sonnet-4-6").with_structured_output(RelevanceGrade)


def grade_relevance(question, context):
    """Return 'correct', 'incorrect', or 'ambiguous' for how well `context`
    answers `question`. Works on prose, on terse graph facts, and on raw web
    search text."""
    context_preview = str(context)[:4000]
    result = _grader.invoke(
        f"""Question: {question}
Retrieved context: {context_preview}

Does this context contain the information needed to answer the question?

The context may be terse structured data (a list of "relation -> entity" facts
from a knowledge graph). Terse is fine: if the relevant facts are present and
on-topic, mark it correct even without explanatory prose. A partial but
genuinely relevant and specific answer also counts as correct.

Only mark it incorrect if the context is truly missing, off topic, or too
vague to answer the question at all."""
    )
    return result.grade
