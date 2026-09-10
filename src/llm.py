"""Shared Claude models, in three tiers.

fast_llm   - Haiku: the classifier-style calls (routing, relevance grading,
             sub-question planning, question condensing, safety/crisis
             classifier). Cheap and quick; simple, well-scoped judgments.
smart_llm  - Sonnet: answer synthesis - the production quality-critical call.
judge_llm  - Opus: the offline LLM-as-judge for evaluation only (never on the
             request path). Strongest model, and deliberately a different model
             family than smart_llm so it isn't grading its own output. Its
             spend is capped - see src/eval_budget.py.

Override the model ids with the FAST_MODEL / SMART_MODEL / JUDGE_MODEL env vars.
"""
import os

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

from .eval_budget import COST_TRACKER

load_dotenv()

FAST_MODEL = os.getenv("FAST_MODEL", "claude-haiku-4-5")
SMART_MODEL = os.getenv("SMART_MODEL", "claude-sonnet-5")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "claude-opus-5")

fast_llm = ChatAnthropic(model=FAST_MODEL, timeout=60)

# Sonnet 5 thinks by default; synthesis is "answer from the given context", not
# a reasoning task, so turn thinking off - it only adds latency and cost here.
smart_llm = ChatAnthropic(model=SMART_MODEL, timeout=90, thinking={"type": "disabled"})

# Opus 5 is $5/$25 per M tok (5x Sonnet). The judge does bounded grading calls
# (claim checks, correctness verdicts), not open reasoning, so thinking is off
# by default for predictable cost - set JUDGE_THINKING=1 to turn it back on.
# max_tokens bounds any single call; COST_TRACKER aborts the whole run at
# EVAL_MAX_USD.
_judge_thinking = (
    {"type": "adaptive"} if os.getenv("JUDGE_THINKING", "0") == "1" else {"type": "disabled"}
)
judge_llm = ChatAnthropic(
    model=JUDGE_MODEL,
    timeout=120,
    max_tokens=8192,
    thinking=_judge_thinking,
    callbacks=[COST_TRACKER],
)

# Eval-only second judge for the mechanical Ragas metrics (context precision /
# recall / answer relevancy) - these make one call per retrieved chunk, so
# running them on Opus is most of the bill for little quality gain. Sonnet 5,
# thinking off, metered against the same budget. Not used on the request path.
JUDGE_FAST_MODEL = os.getenv("JUDGE_FAST_MODEL", "claude-sonnet-5")
judge_fast_llm = ChatAnthropic(
    model=JUDGE_FAST_MODEL,
    timeout=90,
    max_tokens=8192,
    thinking={"type": "disabled"},
    callbacks=[COST_TRACKER],
)
