"""Phase 4: score the system on a file of questions.

Run from the worker folder:

    python -m 4_evaluation.main ../evals/contracts-dev.json --source cuad-dev --retrieval-only
    python -m 4_evaluation.main ../evals/contracts-dev.json --source cuad-dev
    python -m 4_evaluation.main ../evals/technical.json --limit 3 --no-save

--retrieval-only checks only the search (no answer or judge calls, so it is fast and free).
"""
import argparse

from common.config import RESULTS_FILE
from common.loader import load

# The step files start with a number, so they are imported with load() instead of 'from ... import'.
retrieve = load("2_retrieval.main", "retrieve")
answer_from_chunks = load("3_generation.main", "answer_from_chunks")
load_questions = load("4_evaluation.1_questions", "load_questions")
score_retrieval = load("4_evaluation.2_retrieval_scores", "score_retrieval")
did_pass, judge_answer = load("4_evaluation.3_judge", "did_pass", "judge_answer")
print_report, save_rows = load("4_evaluation.4_report", "print_report", "save_rows")


def evaluate_question(question, sources, retrieval_only):
    """Runs one question through the system and returns its result row."""
    chunks = retrieve(question["question"], sources)

    # Step 2: Did the search find the right file?
    row = {"id": question["id"], "kind": question["kind"], "question": question["question"],
           "answerable": question["answerable"], "passed": None, "found": None,
           "correctness": None, "faithfulness": None, "citation": None}
    row.update(score_retrieval(question, chunks))
    if retrieval_only:
        return row

    # Write the answer (phase 3)
    answer = answer_from_chunks(question["question"], chunks)
    row["found"] = answer["found"]

    # Step 3: Grade the answer (questions with no answer are graded by whether the system admitted it)
    scores = {"correctness": 0, "faithfulness": 0, "citation": 0}
    if question["answerable"] and answer["found"]:
        scores = judge_answer(question, answer)
    row.update({k: scores[k] for k in ("correctness", "faithfulness", "citation")})
    row["passed"] = did_pass(question, answer, scores)
    return row


def run_evaluation(path, sources=None, retrieval_only=False, limit=0, save=True):
    # Step 1: Load the questions
    questions = load_questions(path, limit)
    if retrieval_only:
        questions = [q for q in questions if q["answerable"]]  # nothing to look for in 'not-found' questions

    rows = []
    for question in questions:
        rows.append(evaluate_question(question, sources, retrieval_only))

    # Step 4: Show and save the results
    print_report(rows)
    if save:
        save_rows(rows, RESULTS_FILE, path.split("/")[-1].split("\\")[-1])
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score the system on a question file.")
    parser.add_argument("questions", help="a JSON file such as ../evals/contracts-dev.json")
    parser.add_argument("--source", nargs="+", default=None, help="only search these datasets")
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="only the first N questions")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()
    run_evaluation(args.questions, args.source, args.retrieval_only, args.limit, not args.no_save)
