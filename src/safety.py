from typing import Literal

from pydantic import BaseModel, Field

from .llm import fast_llm

CRISIS_RESPONSE = """It sounds like you might be going through something very difficult right now.
Please reach out to a crisis line in your area, or a trusted person near you, for immediate support."""

# Fallback only. Used when the LLM classifier below is unreachable. Kept
# deliberately broad (we would rather over-trigger the crisis message than
# miss a real one when the model is down).
CRISIS_KEYWORDS = [
    "suicide", "suicidal",
    "kill myself", "killing myself",
    "want to die", "wanna die",
    "end my life", "ending my life", "end it all",
    "better off dead", "no reason to live", "don't want to be here",
    "self harm", "self-harm", "hurt myself", "harm myself",
    "cut myself", "cutting myself",
]


class CrisisCheck(BaseModel):
    risk: Literal["none", "low", "high"] = Field(
        description=(
            "high  = suicidal thoughts or intent, intent to self-harm, a disclosure of current or ongoing self-harm, or being in immediate danger. "
            "low   = the person mentions general distress or past struggles that are resolved, or asks about these topics in the abstract (e.g. how to help someone else). "
            "none  = no indication of self-harm or crisis at all."
        )
    )


# runs once per message and is on the latency-critical path. crisis risk is a
# well-scoped 3-class judgment that Haiku handles, with the keyword screen as a
# backstop. bump FAST_MODEL if a stronger safety classifier is wanted.
_classifier = fast_llm.with_structured_output(CrisisCheck)


def _keyword_hit(text):
    lowered = text.lower()
    return any(k in lowered for k in CRISIS_KEYWORDS)


def check_safety(user_message):
    """Return the crisis response string if the message signals a crisis, else None.

    Primary check is an LLM classifier, because plain keyword matching gets
    both directions wrong: it fires on "I do NOT want to die" (negation) and
    misses "I've been thinking about ending it all" (no keyword). If the
    classifier call fails we fall back to the keyword screen and err toward
    showing the crisis message.
    """
    try:
        verdict = _classifier.invoke(
            "You are a safety classifier for a mental health chatbot. "
            "Classify the crisis risk in the user's message.\n\n"
            f"Message: {user_message}"
        )
        return CRISIS_RESPONSE if verdict.risk == "high" else None
    except Exception:
        return CRISIS_RESPONSE if _keyword_hit(user_message) else None
