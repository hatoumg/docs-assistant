"""Pick contracts from the CUAD download, split them into dev and test, and write eval questions.

    python scripts/prepare_cuad.py PATH_TO_UNZIPPED_CUAD --dev 25 --test 25

PATH_TO_UNZIPPED_CUAD is the folder holding master_clauses.csv and the full_contract_txt folder
(download from Kaggle, Hugging Face or https://www.atticusprojectai.org/cuad). CUAD is CC BY 4.0
(The Atticus Project). Outputs:

    data/raw/cuad-dev/   data/raw/cuad-test/            contract text files, split by document
    evals/contracts-dev.json  evals/contracts-test.json  questions with answers taken from the CSV

The test set is for the end of a milestone. Do not tune against it.
"""
import argparse
import csv
import json
import random
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIELDS = {  # question topic -> the CSV column holding the human-checked short answer
    "doc": "Document Name-Answer",
    "parties": "Parties-Answer",
    "agreement_date": "Agreement Date-Answer",
    "expiration": "Expiration Date-Answer",
    "law": "Governing Law-Answer",
}
NOT_FOUND = [
    "How do I configure rate limiting on a FastAPI route?",
    "What is the cafeteria menu for next Tuesday?",
    "Which database index type does the system use for vector search?",
]


def normalise(header: str) -> str:
    return re.sub(r"\s+", " ", header.strip().lower())


def clean_value(value: str) -> str:
    """CSV answers sometimes look like "['A', 'B']". Turn that into "A and B"."""
    value = (value or "").strip()
    if value.startswith("[") and value.endswith("]"):
        items = [part.strip(" '\"") for part in value[1:-1].split("', '")]
        value = " and ".join(item for item in items if item)
    return re.sub(r"\s+", " ", value).strip(" '\"")


def match_key(name: str) -> str:
    """A file name reduced to lower-case letters and digits, without its .pdf/.txt ending.

    The spreadsheet says "X.PDF" or "X.pdf" while the text folder has "X.txt", so only this reduced form is compared.
    """
    name = re.sub(r"\.(pdf|txt)['\"]?$", "", name.strip(), flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]", "", name.lower())


def find_files(root: Path):
    """Locate the spreadsheet and the folder of contracts, ignoring hidden folders such as .cache."""

    def visible(path: Path) -> bool:
        return not any(part.startswith(".") for part in path.relative_to(root).parts)

    csv_path = next((p for p in sorted(root.rglob("master_clauses.csv")) if visible(p)), None)
    folders = [
        d for d in root.rglob("*")
        if d.is_dir() and visible(d) and d.name.lower().startswith("full_contract") and d.name.lower().endswith("txt")
    ]
    txt_dir = max(folders, key=lambda d: sum(1 for _ in d.rglob("*.txt")), default=None)
    if not csv_path or not txt_dir:
        sys.exit(f"Could not find master_clauses.csv and a full_contract_txt folder under {root}")
    return csv_path, txt_dir


def read_rows(csv_path: Path, txt_dir: Path):
    texts = {match_key(p.name): p for p in txt_dir.rglob("*.txt")}  # the real download splits them into Part_I, Part_II
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = {normalise(h): h for h in reader.fieldnames or []}
        missing = [name for name in FIELDS.values() if normalise(name) not in headers]
        if missing:
            sys.exit(f"These columns are not in {csv_path.name}: {missing}\nColumns found: {list(headers.values())[:20]} ...")
        name_column = (reader.fieldnames or [""])[0]
        rows = []
        for raw in reader:
            key = match_key(raw[name_column])
            if key not in texts:
                continue
            values = {name: clean_value(raw[headers[normalise(column)]]) for name, column in FIELDS.items()}
            rows.append({"file": texts[key], "values": values})
    return rows


def usable(row) -> bool:
    v = row["values"]
    return bool(v["doc"] and v["parties"] and v["law"] and (v["expiration"] or v["agreement_date"]))


def questions_for(row, start_id: int):
    v, name = row["values"], row["file"].name
    who = f"the {v['doc']} between {v['parties']}"
    items = [("What law governs " + who + "?", v["law"], "Governing Law")]
    if v["agreement_date"]:
        items.append(("On what date was " + who + " signed or dated?", v["agreement_date"], "Agreement Date"))
    if v["expiration"]:
        items.append(("When does " + who + " expire?", v["expiration"], "Expiration Date"))
    return [
        {"id": start_id + i, "kind": "direct", "question": q, "answer": a, "source": f"{name}, {topic}"}
        for i, (q, a, topic) in enumerate(items)
    ]


def build(rows, count: int, seed: int):
    rows = [r for r in rows if usable(r)]
    random.Random(seed).shuffle(rows)
    if len(rows) < count * 2:
        sys.exit(f"Only {len(rows)} usable contracts; asked for {count * 2}. Lower --dev/--test.")
    return rows[:count], rows[count : count * 2]


def write_set(rows, label: str, folder: Path, eval_path: Path):
    folder.mkdir(parents=True, exist_ok=True)
    for row in rows:
        shutil.copy(row["file"], folder / row["file"].name)
    questions, next_id = [], 1
    for row in rows:
        made = questions_for(row, next_id)
        questions.extend(made)
        next_id += len(made)
    for text in NOT_FOUND:
        questions.append({"id": next_id, "kind": "not-found", "question": text, "answer": "Not found in these documents.", "source": "none"})
        next_id += 1
    eval_path.parent.mkdir(parents=True, exist_ok=True)
    eval_path.write_text(json.dumps(questions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{label}: {len(rows)} contracts -> {folder}; {len(questions)} questions -> {eval_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cuad_folder")
    parser.add_argument("--dev", type=int, default=25)
    parser.add_argument("--test", type=int, default=25)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out-docs", default=str(REPO / "data" / "raw"))
    parser.add_argument("--out-evals", default=str(REPO / "evals"))
    args = parser.parse_args()
    csv_path, txt_dir = find_files(Path(args.cuad_folder))
    rows = read_rows(csv_path, txt_dir)
    print(f"Found {len(rows)} contracts that have both a text file and a spreadsheet row.")
    dev, test = build(rows, max(args.dev, args.test), args.seed)
    write_set(dev[: args.dev], "dev", Path(args.out_docs) / "cuad-dev", Path(args.out_evals) / "contracts-dev.json")
    write_set(test[: args.test], "test", Path(args.out_docs) / "cuad-test", Path(args.out_evals) / "contracts-test.json")


if __name__ == "__main__":
    main()
