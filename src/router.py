from .retrieval import naive_rag_retrieve, graph_rag_retrieve
from .grading import grade_relevance
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field
from typing import Optional, Literal
from .web_search_fallback import web_search_and_ingest

llm = ChatAnthropic(model="claude-sonnet-4-6")

class RouteDecision(BaseModel):
    path: Literal["graph_rag", "naive_rag", "both"] = Field(
        description="graph_rag for relationships between concepts, causes, symptoms, treatments, or connections between conditions. naive_rag for general explanations or definitions. both if genuinely needed."
    )
    entity: Optional[str] = Field(
        default=None,
        description=(
            "The single most relevant entity to look up in the knowledge graph. "
            "For questions about a condition, symptom, or drug, use the canonical name, "
            "e.g. 'Major Depressive Disorder' not 'depression symptoms'. "
            "For questions about a specific automatic thought, belief statement, or cognitive "
            "distortion EXAMPLE quoted in the question, use that quoted thought text verbatim "
            "as the entity (not the word 'cognitive distortion'). "
            "Try to name one even if path is naive_rag. Null only if there is truly no clear entity."
        ),
    )

router_llm = llm.with_structured_output(RouteDecision)

def classify_and_extract(question):
    try:
        result = router_llm.invoke(
            f"Classify this mental health related question and extract the relevant entity.\n\nQuestion: {question}"
        )
        return result.path, result.entity
    except Exception:
        return "naive_rag", None

def route_question(question):
    path, entity = classify_and_extract(question)

    if path == "graph_rag" and entity:
        context = graph_rag_retrieve(entity)
    elif path == "both" and entity:
        context = naive_rag_retrieve(question) + graph_rag_retrieve(entity)
    else:
        context = naive_rag_retrieve(question)
        path = "naive_rag"  # fell back here since no usable entity came back

    return {"path": path, "context": context, "entity": entity}


def route_with_correction(question):
    result = route_question(question)
    grade = grade_relevance(question, result["context"])

    if grade == "correct":
        result["corrected"] = False
        return result

    if grade == "incorrect":
        fallback_path = "graph_rag" if result["path"] == "naive_rag" else "naive_rag"
        if fallback_path == "graph_rag" and result["entity"] is not None:
            new_context = graph_rag_retrieve(result["entity"])
        elif fallback_path == "naive_rag":
            new_context = naive_rag_retrieve(question)
        else:
            new_context = []

        if new_context:
            second_grade = grade_relevance(question, new_context)
            if second_grade == "correct":
                return {"path": fallback_path, "context": new_context, "entity": result["entity"], "corrected": True}

        # neither your existing graph nor your existing vector store had a good
        # answer. web_search_and_ingest does its own worthiness check on the
        # results before chunking/embedding, so a non-empty return is already
        # vetted, no need to re-grade it here.
        web_context = web_search_and_ingest(question)
        if web_context:
            return {"path": "web_fallback", "context": web_context, "entity": result["entity"], "corrected": True}

        # nothing anywhere actually answers this. return an empty context and
        # mark the path so the synthesizer says it doesn't know, rather than
        # guessing from the weak context it does have
        return {"path": "no_answer", "context": [], "entity": result["entity"], "corrected": True}

    # ambiguous, combine both
    if result["entity"] is None:
        combined = naive_rag_retrieve(question)
    else:
        combined = naive_rag_retrieve(question) + graph_rag_retrieve(result["entity"])
    return {"path": "both", "context": combined, "entity": result["entity"], "corrected": True}
