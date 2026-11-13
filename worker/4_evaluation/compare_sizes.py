"""Compare chunk sizes on real answers: index, answer every question and have the judge grade it, once per size.

Run from the worker folder (Postgres/Docker and Ollama must be running, and your answering model's key set in .env):

    python -m 4_evaluation.compare_sizes
    python -m 4_evaluation.compare_sizes --sizes 200,300,500 --limit 20

By default it uses the contract questions and the 300, 500 and 800 word sizes that did best in chunk_sweep. Add 200 (the
current setting) to see whether a new size beats what you have now.

Each size gets its own index in the database (named size-300w and so on), so your normal index is not touched.
Answers and grades are saved on disk: if the daily call limit stops a run, run the same command again tomorrow and it
carries on, because everything already answered is free. Cost: about two model calls per question per size.
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from common.config import REPO_DIR
from common.loader import load

summarise = load("4_evaluation.4_report", "summarise")

DEFAULT_SIZES = (300, 500, 800)
DEFAULT_QUESTIONS = REPO_DIR / "evals" / "contracts-dev.json"
DEFAULT_DOCS = REPO_DIR / "data" / "raw" / "cuad-dev"
RESULTS_FILE = REPO_DIR / "evals" / "size-comparison.csv"
WORKER_DIR = Path(__file__).resolve().parents[1]


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def summarise_size(rows):
    """The numbers for one size, from the result rows of one evaluation."""
    answerable = [r for r in rows if r["answerable"]]
    missing = [r for r in rows if not r["answerable"]]
    headline = summarise(rows)
    return {
        "questions": len(rows),
        "pass_rate": headline["pass_rate"],
        "answerable_pass_rate": mean(r["passed"] for r in answerable),
        "correct": mean(r["correctness"] == 2 for r in answerable),
        "faithful": mean(r["faithfulness"] == 2 for r in answerable),
        "citation_avg": mean(r["citation"] for r in answerable),
        "not_found_ok": mean(r["passed"] for r in missing),
        "right_file@k": headline["hit_at_k"],
    }


def differences(results):
    """Questions that pass at some sizes and fail at others. results: {size: rows}. Returns [(id, question, {size: passed})]."""
    sizes = list(results)
    by_size = {size: {r["id"]: r for r in rows} for size, rows in results.items()}
    ids = [r["id"] for r in results[sizes[0]]]
    found = []
    for question_id in ids:
        outcomes = {size: bool(by_size[size][question_id]["passed"]) for size in sizes if question_id in by_size[size]}
        if len(set(outcomes.values())) > 1:
            found.append((question_id, by_size[sizes[0]][question_id]["question"], outcomes))
    return found


def failures(results):
    """Every failed question with the judge's reason. Returns [(size, id, question, reason, answer)]."""
    return [(size, r["id"], r["question"], r.get("reason", ""), r.get("answer", "")) for size, rows in results.items() for r in rows if not r["passed"]]


def compare(sizes, index_size, evaluate_size):
    """Runs every size. index_size(size) builds the index; evaluate_size(size) returns the result rows. Returns {size: rows}."""
    results = {}
    for size in sizes:
        print(f"\n===== {size} words =====", flush=True)
        index_size(size)
        results[size] = evaluate_size(size)
    return results


def percent(value):
    return "-" if value is None else f"{value:.0%}"


def print_table(summaries):
    columns = [
        ("size", lambda size, s: str(size)), ("pass rate", lambda size, s: percent(s["pass_rate"])),
        ("answerable passed", lambda size, s: percent(s["answerable_pass_rate"])), ("correct", lambda size, s: percent(s["correct"])),
        ("faithful", lambda size, s: percent(s["faithful"])), ("citation (0-2)", lambda size, s: "-" if s["citation_avg"] is None else f"{s['citation_avg']:.2f}"),
        ("not-found ok", lambda size, s: percent(s["not_found_ok"])), ("right file", lambda size, s: percent(s["right_file@k"])),
    ]
    table = [[title for title, _ in columns]] + [[fn(size, s) for _, fn in columns] for size, s in summaries.items()]
    widths = [max(len(row[i]) for row in table) for i in range(len(columns))]
    print("\nAnswer quality by chunk size (graded by the judge model)\n")
    for row in table:
        print("  ".join(cell.rjust(w) for cell, w in zip(row, widths)))
    print("\npass rate = share of ALL questions passed (correct, faithful, cited; 'not found' questions must be admitted as not found).")


def save_rows(summaries, dataset, path=RESULTS_FILE):
    path = Path(path)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["time", "dataset", "size", *next(iter(summaries.values())).keys()])
        if new:
            writer.writeheader()
        stamp = datetime.now().isoformat(timespec="seconds")
        for size, summary in summaries.items():
            writer.writerow({"time": stamp, "dataset": dataset, "size": size, **summary})
    print(f"Saved to {path}")


# ----- running the existing steps for one size -----


def size_environment(size, collection_prefix="size"):
    """Settings for one size, passed to the steps as environment variables (see common/config.py)."""
    return {**os.environ, "RAG_COLLECTION": f"{collection_prefix}-{size}w", "RAG_CHUNK_WORDS": str(size), "RAG_OVERLAP_WORDS": str(size // 5)}


def run_step(arguments, environment):
    """Runs a python module in its own process so it reads the settings for this size."""
    return subprocess.run([sys.executable, "-m", *arguments], cwd=WORKER_DIR, env=environment, check=False).returncode


def run_child(questions, source, limit, out):
    """Child process: score the questions and write the rows to a file. Settings arrive as environment variables."""
    run_evaluation = load("4_evaluation.main", "run_evaluation")
    rows = run_evaluation(str(questions), [source] if source else None, retrieval_only=False, limit=limit, save=False)
    Path(out).write_text(json.dumps(rows, default=str), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Compare chunk sizes by the quality of the written answers.")
    parser.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    parser.add_argument("--docs", default=str(DEFAULT_DOCS), help="folder with the documents the questions are about")
    parser.add_argument("--sizes", default=",".join(map(str, DEFAULT_SIZES)), help="chunk sizes in words, comma separated")
    parser.add_argument("--limit", type=int, default=0, help="only the first N questions (try 15 to test cheaply)")
    parser.add_argument("--no-save", action="store_true", help="do not add the result to evals/size-comparison.csv")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--out", help=argparse.SUPPRESS)
    args = parser.parse_args()
    source = Path(args.docs).name

    if args.child:
        run_child(args.questions, source, args.limit, args.out)
        return

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    if not sizes or min(sizes) < 50:
        parser.error("sizes must be at least 50 words")
    load_questions = load("4_evaluation.1_questions", "load_questions")
    count = len(load_questions(args.questions, args.limit))
    cap = int(os.environ.get("MAX_REQUESTS_PER_DAY", "200"))
    calls = 2 * count * len(sizes)
    print(f"\nAbout {calls} model calls in total ({count} questions x {len(sizes)} sizes x answer + judge). Daily limit: {cap}.")
    if calls > cap:
        print("That is over the daily limit. The run stops when it is reached; run the same command again tomorrow and it continues.")

    def index_size(size):
        if run_step(["1_indexing.main", args.docs], size_environment(size)) != 0:
            sys.exit(f"Indexing failed for {size} words (is Docker/Postgres and Ollama running?).")

    def evaluate_size(size):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "rows.json"
            command = ["4_evaluation.compare_sizes", "--child", "--questions", args.questions, "--docs", args.docs, "--limit", str(args.limit), "--out", str(out)]
            if run_step(command, size_environment(size)) != 0 or not out.exists():
                sys.exit(f"The evaluation stopped for {size} words, probably at the daily call limit or a missing key. "
                         "Answers so far are saved: run the same command again and it continues.")
            return json.loads(out.read_text(encoding="utf-8"))

    results = compare(sizes, index_size, evaluate_size)
    summaries = {size: summarise_size(rows) for size, rows in results.items()}
    print_table(summaries)
    different = differences(results)
    if different and len(results) > 1:
        print(f"\nQuestions where the sizes disagree ({len(different)}):")
        for question_id, question, outcomes in different:
            marks = "  ".join(f"{size}:{'ok' if ok else 'FAIL'}" for size, ok in outcomes.items())
            print(f"  #{question_id}  {marks}  {question[:80]}")
    failed = failures(results)
    if failed:
        print(f"\nFailed questions and why (judge's reason, then the system's answer):")
        for size, question_id, question, reason, answer in failed:
            print(f"  [{size}] #{question_id} {question[:70]}\n      why:    {reason[:200] or '-'}\n      answer: {answer[:160] or '-'}")
    if not args.no_save:
        save_rows(summaries, Path(args.questions).name)


if __name__ == "__main__":
    main()
