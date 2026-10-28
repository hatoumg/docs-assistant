"""Step 4: show the results and save them to a CSV file so runs can be compared later."""
import csv
from datetime import datetime
from pathlib import Path


def average(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def summarise(rows):
    """Returns the headline numbers."""
    answerable = [r for r in rows if r["answerable"]]
    judged = [r for r in rows if r["passed"] is not None]
    return {
        "questions": len(rows),
        "hit_at_k": average(r["hit"] for r in answerable),
        "mrr": average(r["reciprocal_rank"] for r in answerable),
        "pass_rate": average(r["passed"] for r in judged),
    }


def percent(value):
    return "-" if value is None else f"{value:.0%}"


def print_report(rows):
    print("\nResults per question:")
    for r in rows:
        mark = "-" if r["passed"] is None else ("ok  " if r["passed"] else "FAIL")
        print(f"  {mark} #{r['id']} {r['kind']:<13} right file at rank: {r['rank'] or 'not found'}")

    s = summarise(rows)
    mrr = "-" if s["mrr"] is None else f"{s['mrr']:.2f}"
    print(f"\nQuestions: {s['questions']}   Hit@k: {percent(s['hit_at_k'])}   MRR: {mrr}   Pass rate: {percent(s['pass_rate'])}")


def save_rows(rows, path, dataset):
    """Add one line per question to the CSV file (the header is written the first time)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["time", "dataset", "id", "kind", "rank", "hit", "reciprocal_rank", "found",
               "correctness", "faithfulness", "citation", "passed", "question"]
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        if is_new:
            writer.writeheader()
        for r in rows:
            writer.writerow({**r, "time": datetime.now().isoformat(timespec="seconds"), "dataset": dataset})
    print(f"Saved {len(rows)} rows to {path}")
