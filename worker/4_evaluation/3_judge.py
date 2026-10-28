"""Step 3: have an AI model grade the answer.

The judge reads the question, the correct answer, the retrieved passages and the system's answer, then
gives 0, 1 or 2 for each of:
    correctness   does it match the correct answer?
    faithfulness  is every claim supported by the passages?
    citation      do the cited passages support the answer?
"""
import json
import re

from common.config import JUDGE_PROMPT_FILE
from common.models import ask_judge
from common.loader import load

format_passages = load("3_generation.1_prompt", "format_passages")


def parse_scores(reply):
    """Read the judge's JSON reply. Keeps each score between 0 and 2."""
    match = re.search(r"\{.*\}", reply, re.DOTALL)
    if not match:
        raise ValueError(f"The judge did not reply with JSON: {reply[:200]!r}")
    data = json.loads(match.group(0))

    def score(name):
        return max(0, min(2, int(data.get(name, 0))))

    return {
        "correctness": score("correctness"),
        "faithfulness": score("faithfulness"),
        "citation": score("citation"),
        "reason": str(data.get("reason", "")),
    }


def judge_answer(question, answer):
    """Returns the judge's scores for an answer."""
    template = JUDGE_PROMPT_FILE.read_text(encoding="utf-8")
    prompt = (
        template.replace("{{question}}", question["question"])
        .replace("{{reference}}", question["answer"])
        .replace("{{passages}}", format_passages(answer["chunks"]))
        .replace("{{answer}}", answer["text"])
    )
    return parse_scores(ask_judge(prompt))


def did_pass(question, answer, scores):
    """The pass rule.

    A question with an answer passes if correctness is 2, faithfulness is 2 and citation is at least 1.
    A 'not-found' question passes only if the system said it could not find the answer.
    """
    if not question["answerable"]:
        return not answer["found"]
    return scores["correctness"] == 2 and scores["faithfulness"] == 2 and scores["citation"] >= 1
