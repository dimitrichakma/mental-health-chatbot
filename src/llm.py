"""Shared Claude models, in two tiers.

fast_llm   - Haiku: the classifier-style calls (routing, relevance grading,
             sub-question planning, question condensing). Cheap and quick;
             these are simple, well-scoped judgments.
smart_llm  - Sonnet: answer synthesis, the safety/crisis classifier, and the
             offline eval judge - the calls where quality matters most.

Override the model ids with the FAST_MODEL / SMART_MODEL env vars.
"""
import os

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()

FAST_MODEL = os.getenv("FAST_MODEL", "claude-haiku-4-5")
SMART_MODEL = os.getenv("SMART_MODEL", "claude-sonnet-5")

fast_llm = ChatAnthropic(model=FAST_MODEL, timeout=60)

# Sonnet 5 thinks by default; synthesis is "answer from the given context", not
# a reasoning task, so turn thinking off - it only adds latency and cost here.
smart_llm = ChatAnthropic(model=SMART_MODEL, timeout=90, thinking={"type": "disabled"})
