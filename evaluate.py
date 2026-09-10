import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from src.planner import run_pipeline
from src.llm import smart_llm

GOLDEN_SET_PATH = Path(__file__).resolve().parent / "eval" / "golden_eval_set.json"


def path_matches(expected, actual_paths):
    """Did routing land where the golden set expected?

    run_pipeline splits a question into subquestions and routes each one, so
    `actual_paths` is a list (one path per subquestion). For an expected value
    of "both" we accept either a subquestion explicitly routed "both", or the
    combination of a naive_rag and a graph_rag subquestion covering it.
    """
    actual = set(actual_paths)
    if expected == "both":
        return "both" in actual or {"naive_rag", "graph_rag"}.issubset(actual)
    return expected in actual


class Judgement(BaseModel):
    verdict: Literal["correct", "partial", "incorrect"] = Field(
        description=(
            "correct   = the answer captures the key facts of the reference answer. "
            "partial   = some correct content but missing or muddling important parts. "
            "incorrect = wrong, or fails to answer."
        )
    )


judge_llm = smart_llm.with_structured_output(Judgement)


def judge_answer(question, golden_answer, actual_answer):
    try:
        result = judge_llm.invoke(
            "Compare a chatbot's answer against a reference answer for a mental health question. "
            "Judge only whether the key facts match, not wording or length.\n\n"
            f"Question: {question}\n\n"
            f"Reference answer: {golden_answer}\n\n"
            f"Chatbot answer: {actual_answer}"
        )
        return result.verdict
    except Exception as e:
        print(f"   judge failed: {e}")
        return "incorrect"


def main():
    with open(GOLDEN_SET_PATH) as f:
        golden_set = json.load(f)

    path_correct = 0
    answer_correct = 0
    answer_partial = 0
    failures = []

    for item in golden_set:
        try:
            output = run_pipeline(item["question"])
        except Exception as e:
            print(item["question"], "-> ERROR:", e)
            failures.append(item["question"])
            continue

        actual_paths = [r["path"] for r in output["results"]]
        p_ok = path_matches(item["expected_path"], actual_paths)
        verdict = judge_answer(item["question"], item["golden_answer"], output["answer"])

        path_correct += p_ok
        answer_correct += verdict == "correct"
        answer_partial += verdict == "partial"

        print(item["question"])
        print(f"   path: expected {item['expected_path']}, got {actual_paths}  -> {'OK' if p_ok else 'MISS'}")
        print(f"   answer: {verdict}")
        print(f"   {output['answer'][:150]}")

    scored = len(golden_set) - len(failures)
    print()
    print(f"Router path accuracy:   {path_correct}/{scored}")
    print(f"Answer correct:         {answer_correct}/{scored}")
    print(f"Answer correct+partial: {answer_correct + answer_partial}/{scored}")
    if failures:
        print(f"Errored questions ({len(failures)}): {failures}")


if __name__ == "__main__":
    main()
