"""Offline evaluation for the retrieval pipeline.

Runs the full pipeline (safety -> condense -> plan -> route/retrieve ->
synthesize) over eval/golden_eval_set.json and scores each item by its
category:

  concept / combined  answer quality (LLM judge vs a reference answer) + routing
  graph               answer quality + retrieval hit, both scored against the
                      LIVE graph - the harness runs Cypher to get every valid
                      answer for the item's entity+relation, so it does not
                      matter which valid edge retrieval happened to surface
  safety              did the crisis gate fire exactly when it should
  abstain             did the bot decline instead of answering from thin context

The web-search fallback is OFF by default here (pass --web to enable) so the
abstain cases measure pure corpus+graph behaviour.

The judge is Opus 5 (JUDGE_MODEL). Its spend is metered and the run aborts if
it passes EVAL_MAX_USD (default $5) - a partial report still prints.

Usage:
  python evaluate.py                          # whole set, no web fallback
  python evaluate.py --category safety,graph  # just those categories
  python evaluate.py --limit 5                # first 5 items
  python evaluate.py --web                    # allow the web-search fallback
  python evaluate.py --out eval/last_run.json # dump per-item results
"""
import argparse
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from src import router
from src.usage import EVAL_USAGE as COST_TRACKER, BudgetExceeded
from src.llm import judge_llm
from src.planner import run_pipeline

GOLDEN_SET_PATH = Path(__file__).resolve().parent / "eval" / "golden_eval_set.json"

# same fuzzy entity match retrieval.py uses, so the "valid answers" the judge
# sees line up with what the pipeline could actually have retrieved
_FUZZY_MATCH = (
    "toLower(a.name) CONTAINS toLower($e) "
    "OR (size(a.name) > 4 AND toLower($e) CONTAINS toLower(a.name))"
)


# ---------------------------------------------------------------- graph checks

def _get_graph():
    from langchain_neo4j import Neo4jGraph

    return Neo4jGraph()


def resolve_graph_check(graph, check):
    """Every valid answer for this item, straight from the live graph.

    check = {entity, relation (str or list), direction "out"|"in", exact? bool}
    direction "out": entity is the head, we want the tails.
    direction "in":  entity is the tail, we want the heads.
    With exact=True we first try a strict name match and only fall back to the
    fuzzy match if that finds nothing.
    """
    relations = check["relation"]
    if isinstance(relations, str):
        relations = [relations]
    arrow = "-[r:RELATION]->" if check.get("direction", "out") == "out" else "<-[r:RELATION]-"
    other = "b" if check.get("direction", "out") == "out" else "b"  # always return b

    name_clauses = ["toLower(a.name) = toLower($e)"] if check.get("exact") else []
    name_clauses.append(_FUZZY_MATCH)

    for clause in name_clauses:
        rows = graph.query(
            f"MATCH (a){arrow}(b) WHERE ({clause}) AND r.type IN $rels "
            f"RETURN collect(DISTINCT {other}.name) AS names",
            params={"e": check["entity"], "rels": relations},
        )
        names = [n for n in (rows[0]["names"] if rows else []) if n]
        if names:
            return names
    return []


# --------------------------------------------------------------------- judges

class Judgement(BaseModel):
    verdict: Literal["correct", "partial", "incorrect"] = Field(
        description=(
            "correct   = the answer captures the key facts of the reference. "
            "partial   = some correct content but missing or muddling important parts. "
            "incorrect = wrong, or fails to answer."
        )
    )


class YesNo(BaseModel):
    declines: bool = Field(
        description="True if the answer says it lacks reliable information / cannot answer from its sources, rather than giving a substantive answer."
    )


# the judge is Opus 5 (src/llm.py); its spend counts against COST_TRACKER
_verdict_llm = judge_llm.with_structured_output(Judgement)
_abstain_llm = judge_llm.with_structured_output(YesNo)


def judge_prose(question, reference, actual):
    try:
        return _verdict_llm.invoke(
            "Compare a chatbot's answer against a reference answer for a mental health question. "
            "Judge only whether the key facts match, not wording or length.\n\n"
            f"Question: {question}\n\nReference answer: {reference}\n\nChatbot answer: {actual}"
        ).verdict
    except BudgetExceeded:
        raise
    except Exception as e:
        print(f"   judge failed: {e}")
        return "incorrect"


def judge_graph(question, valid_answers, actual):
    """Graph items: any of the live graph's valid entities counts as correct."""
    try:
        return _verdict_llm.invoke(
            "A chatbot answered a question that is backed by a knowledge graph. "
            "These are ALL the valid answer entities from the graph (any one or more is acceptable):\n"
            f"{valid_answers}\n\n"
            "Mark 'correct' if the chatbot names at least one valid entity and does not assert "
            "clearly wrong ones; 'partial' if it is vaguely in the area but names none; "
            "'incorrect' if it is wrong, declines to answer, or says it lacks information.\n\n"
            f"Question: {question}\n\nChatbot answer: {actual}"
        ).verdict
    except BudgetExceeded:
        raise
    except Exception as e:
        print(f"   judge failed: {e}")
        return "incorrect"


def judge_abstain(actual):
    try:
        return _abstain_llm.invoke(
            "Does this chatbot answer decline to answer - saying it lacks reliable information "
            "or can only answer from its own sources - rather than giving a substantive answer?\n\n"
            f"Answer: {actual}"
        ).declines
    except BudgetExceeded:
        raise
    except Exception as e:
        print(f"   judge failed: {e}")
        return False


# ------------------------------------------------------------------- scoring

def path_matches(expected, actual_paths):
    """Did routing land somewhere acceptable?

    `expected` is a path name or a list of acceptable ones - some questions are
    genuinely answerable from either the graph or the text, so more than one
    route is a pass. "both" is satisfied by an explicit "both" route or by the
    combination of a naive_rag and a graph_rag subquestion.
    """
    actual = set(actual_paths)
    for exp in [expected] if isinstance(expected, str) else expected:
        if exp == "both":
            if "both" in actual or {"naive_rag", "graph_rag"}.issubset(actual):
                return True
        elif exp in actual:
            return True
    return False


def evaluate_item(item, graph):
    rec = {"id": item["id"], "category": item["category"]}
    t0 = time.perf_counter()
    try:
        out = run_pipeline(item["question"], chat_history=item.get("chat_history"))
    except Exception as e:
        rec["error"] = str(e)
        rec["pass"] = False
        return rec
    rec["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    rec["paths"] = [r["path"] for r in out["results"]]
    rec["answer"] = out["answer"][:300]

    # safety: crisis gate fired iff it should have
    if "expect_crisis_gate" in item:
        gated = bool(out.get("crisis"))
        rec["metric"] = "crisis_gate"
        rec["expected_gate"] = item["expect_crisis_gate"]
        rec["actual_gate"] = gated
        rec["pass"] = gated == item["expect_crisis_gate"]
        # a "should not gate" item may also carry a reference answer / path
        if not item["expect_crisis_gate"] and not gated and "golden_answer" in item:
            rec["verdict"] = judge_prose(item["question"], item["golden_answer"], out["answer"])
        return rec

    # abstain: bot should decline
    if item.get("expect_abstain"):
        rec["metric"] = "abstain"
        rec["pass"] = judge_abstain(out["answer"])
        return rec

    # everything else: routing + answer quality
    rec["metric"] = "answer"
    rec["path_ok"] = path_matches(item["expected_path"], rec["paths"])

    if "graph_check" in item:
        valid = resolve_graph_check(graph, item["graph_check"])
        rec["valid_answer_count"] = len(valid)
        ctx = " ".join(str(r["context"]) for r in out["results"]).lower()
        rec["retrieval_hit"] = any(v.lower() in ctx for v in valid) if valid else None
        rec["verdict"] = judge_graph(item["question"], valid, out["answer"]) if valid else "incorrect"
    else:
        rec["verdict"] = judge_prose(item["question"], item["golden_answer"], out["answer"])

    rec["answer_ok"] = rec["verdict"] == "correct"
    rec["pass"] = rec["answer_ok"] and rec["path_ok"]
    return rec


# --------------------------------------------------------------------- report

def report(results):
    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r)

    print("\n" + "=" * 72)
    print(f"{'category':<12} {'n':>3} {'pass':>6} {'answer':>8} {'path':>6} {'retr.hit':>9} {'p50 ms':>8}")
    print("-" * 72)
    for cat in sorted(by_cat):
        rs = by_cat[cat]
        n = len(rs)
        npass = sum(bool(r.get("pass")) for r in rs)
        ans = sum(r.get("verdict") == "correct" for r in rs)
        ans_scored = sum("verdict" in r for r in rs)
        paths = [r["path_ok"] for r in rs if "path_ok" in r]
        hits = [r["retrieval_hit"] for r in rs if r.get("retrieval_hit") is not None]
        lats = sorted(r["latency_ms"] for r in rs if "latency_ms" in r)
        p50 = lats[len(lats) // 2] if lats else 0
        ans_s = f"{ans}/{ans_scored}" if ans_scored else "-"
        path_s = f"{sum(paths)}/{len(paths)}" if paths else "-"
        hit_s = f"{sum(hits)}/{len(hits)}" if hits else "-"
        print(f"{cat:<12} {n:>3} {npass:>4}/{n:<1} {ans_s:>8} {path_s:>6} {hit_s:>9} {p50:>8}")
    print("-" * 72)
    total = len(results)
    tpass = sum(bool(r.get("pass")) for r in results)
    all_lats = sorted(r["latency_ms"] for r in results if "latency_ms" in r)
    print(f"{'TOTAL':<12} {total:>3} {tpass:>4}/{total:<1}"
          f"{'':>8}{'':>6}{'':>9} {all_lats[len(all_lats) // 2] if all_lats else 0:>8}")
    print("=" * 72)

    fails = [r for r in results if not r.get("pass")]
    if fails:
        print(f"\n{len(fails)} failing item(s):")
        for r in fails:
            detail = r.get("error") or r.get("verdict") or (
                f"gate expected {r.get('expected_gate')} got {r.get('actual_gate')}"
                if "expected_gate" in r else "")
            print(f"  [{r['category']}] {r['id']}: {detail}")
            if "answer" in r:
                print(f"      -> {r['answer'][:160]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", help="comma-separated categories to run")
    ap.add_argument("--limit", type=int, help="only the first N (after category filter)")
    ap.add_argument("--web", action="store_true", help="allow the live web-search fallback")
    ap.add_argument("--out", help="write per-item results as JSON here")
    args = ap.parse_args()

    router.set_web_fallback(args.web)

    with open(GOLDEN_SET_PATH) as f:
        golden_set = json.load(f)

    if args.category:
        wanted = {c.strip() for c in args.category.split(",")}
        golden_set = [g for g in golden_set if g["category"] in wanted]
    if args.limit:
        golden_set = golden_set[: args.limit]

    needs_graph = any("graph_check" in g for g in golden_set)
    graph = _get_graph() if needs_graph else None

    results = []
    stopped_early = False
    for i, item in enumerate(golden_set, 1):
        print(f"[{i}/{len(golden_set)}] {item['id']}")
        try:
            rec = evaluate_item(item, graph)
        except BudgetExceeded as e:
            print(f"\n!! {e}\n!! stopping - {len(results)}/{len(golden_set)} items scored")
            stopped_early = True
            break
        flag = "ok " if rec.get("pass") else "FAIL"
        print(f"   {flag}  {rec.get('metric', '?')}  {rec.get('latency_ms', 0)} ms")
        results.append(rec)

    report(results)
    print("\n" + COST_TRACKER.report())

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2))
        print(f"wrote {args.out}")

    if stopped_early:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
