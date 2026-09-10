"""A hard spend cap for LLM-as-judge evaluation runs.

The judge is Opus 5 ($5 / $25 per M input / output tokens - 5x Sonnet), and a
full Ragas + custom-harness pass makes hundreds of judge calls. This module is
a LangChain callback that adds up token usage as calls happen, converts it to
USD, and raises `BudgetExceeded` the moment a run crosses its ceiling - so a
misconfigured metric or a retry storm can't quietly run up a bill.

Wire it in by attaching `COST_TRACKER` to a model's `callbacks=[...]`. It keeps
per-model totals, so the same tracker can later cover the pipeline's Haiku and
Sonnet calls too - just attach it to those models as well.

    EVAL_MAX_USD   ceiling for a run (default 5.00)
"""
import os
import threading

from langchain_core.callbacks import BaseCallbackHandler

# USD per 1M tokens: (input, output). Cache reads/writes are billed differently
# but we treat every input token at the base rate, which over-estimates - fine
# for a guard rail. Extend as other models get metered.
MODEL_PRICING = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

DEFAULT_MAX_USD = 5.0


class BudgetExceeded(RuntimeError):
    """Raised mid-run once accumulated judge spend passes the ceiling."""


def _price(model_id):
    # model ids may arrive with a vendor prefix or -latest suffix; match loosely
    for known, pricing in MODEL_PRICING.items():
        if known in model_id:
            return pricing
    return None


class CostTracker(BaseCallbackHandler):
    raise_error = True  # let BudgetExceeded propagate out of the callback

    def __init__(self, max_usd=None):
        self.max_usd = max_usd if max_usd is not None else float(
            os.getenv("EVAL_MAX_USD", DEFAULT_MAX_USD)
        )
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        with self._lock:
            # model_id -> [input_tokens, output_tokens, calls]
            self.by_model = {}
            self.calls = 0
            self._tripped = False

    # ------------------------------------------------------------------ usage

    def _record(self, model_id, in_tok, out_tok):
        with self._lock:
            row = self.by_model.setdefault(model_id, [0, 0, 0])
            row[0] += in_tok
            row[1] += out_tok
            row[2] += 1
            self.calls += 1
            cost = self._cost_usd_locked()
            if cost > self.max_usd and not self._tripped:
                self._tripped = True
                raise BudgetExceeded(
                    f"judge spend ${cost:.2f} exceeded EVAL_MAX_USD ${self.max_usd:.2f} "
                    f"after {self.calls} calls"
                )

    def on_llm_end(self, response, **kwargs):
        model_id = "unknown"
        in_tok = out_tok = 0
        try:
            for gen_list in response.generations:
                for gen in gen_list:
                    msg = getattr(gen, "message", None)
                    meta = getattr(msg, "usage_metadata", None) if msg else None
                    if meta:
                        in_tok += meta.get("input_tokens", 0)
                        out_tok += meta.get("output_tokens", 0)
                    rmeta = getattr(msg, "response_metadata", {}) if msg else {}
                    model_id = rmeta.get("model_name") or rmeta.get("model") or model_id
            if in_tok == 0 and out_tok == 0:
                usage = (response.llm_output or {}).get("usage", {})
                in_tok = usage.get("input_tokens", 0)
                out_tok = usage.get("output_tokens", 0)
                model_id = (response.llm_output or {}).get("model", model_id)
        except Exception:
            pass
        self._record(model_id, in_tok, out_tok)

    # ------------------------------------------------------------------- cost

    def _cost_usd_locked(self):
        total = 0.0
        for model_id, (in_tok, out_tok, _calls) in self.by_model.items():
            pricing = _price(model_id)
            if pricing is None:
                continue
            in_rate, out_rate = pricing
            total += in_tok / 1_000_000 * in_rate + out_tok / 1_000_000 * out_rate
        return total

    @property
    def cost_usd(self):
        with self._lock:
            return self._cost_usd_locked()

    def report(self):
        with self._lock:
            lines = [f"judge spend: ${self._cost_usd_locked():.3f}  "
                     f"(ceiling ${self.max_usd:.2f}, {self.calls} calls)"]
            for model_id, (in_tok, out_tok, calls) in sorted(self.by_model.items()):
                priced = "" if _price(model_id) else "  [unpriced]"
                lines.append(
                    f"  {model_id}: {calls} calls, "
                    f"{in_tok:,} in / {out_tok:,} out{priced}"
                )
            return "\n".join(lines)


# shared singleton - attach to every model whose spend should count against one run
COST_TRACKER = CostTracker()
