"""Compare chunk sizes and chunking methods: which finds the answer most often?

For every method and size the documents are cut into chunks, embedded, and searched with the questions. No database is used,
so this does not touch your stored index. Embeddings are saved in worker/.cache, so a second run is fast.

Run from the worker folder (Ollama must be running):

    python -m 4_evaluation.chunk_sweep ../evals/contracts-dev.json --docs ../data/raw/cuad-dev
    python -m 4_evaluation.chunk_sweep ../evals/technical.json --docs ../data/samples/technical --sizes 50,100,200,400

    # compare methods at one size, each with and without the context line in front of the chunk
    python -m 4_evaluation.chunk_sweep ../evals/contracts-dev.json --docs ../data/raw/cuad-dev --sizes 300 \
        --methods fixed,recursive,clauses --context both

The methods are described in 1_indexing/3_chunk.py. Compare them at the same size and read hit@budget and MRR:
the structure-aware methods make slightly smaller chunks on average, so plain hit@5 slightly favours fixed.

What is measured, for each method and size (only over questions the documents can answer):

    answer hit@k   one of the top k chunks, from the right file, contains the correct answer
    answer MRR     1 / (position of the first such chunk, within the top 10), averaged
    file hit@5     one of the top 5 chunks is from the right file (the same check phase 4 uses)
    hit@budget     like hit@k, but the search may return chunks until about BUDGET words are collected. Big chunks
                   fill the top 5 with far more text than small chunks, so this is the fairer comparison.
    context words  how many words the top 5 chunks add up to, i.e. how much text the answering model must read

"Contains the answer" means the answer written in the question file appears in the chunk, ignoring case and
punctuation (dates such as 1/22/07 also match "January 22, 2007"). Questions whose answer is a sentence, or does not
appear word for word in the document, cannot be checked this way; they count only in file hit.
"""
import argparse
import csv
import hashlib
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import numpy as np

from common.config import REPO_DIR
from common.loader import load
from common.models import embed_query, embed_texts
from common.settings import load_settings

load_documents = load("1_indexing.1_load", "load_documents")
clean_text = load("1_indexing.2_clean", "clean_text")
make_chunks, title_from_name, METHODS = load("1_indexing.3_chunk", "make_chunks", "title_from_name", "METHODS")
text_to_embed = load("1_indexing.4_embed", "text_to_embed")
load_questions = load("4_evaluation.1_questions", "load_questions")

DEFAULT_SIZES = (50, 100, 200, 300, 500, 800)
KS = (1, 3, 5)
MAX_RANK = 10
RESULTS_FILE = REPO_DIR / "evals" / "chunk-sweep.csv"
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


# ----- matching answers -----


def normalise(text):
    """Lower case, no accents, only letters and digits separated by single spaces, with a space at each end."""
    text = unicodedata.normalize("NFKC", text).lower()
    return " " + " ".join(re.findall(r"[^\W_]+", text)) + " "


def answer_variants(answer):
    """The ways the answer may appear in a document. A date like 1/22/07 is also written 'January 22, 2007'."""
    variants = {normalise(answer)}
    date = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\s*", answer)
    if date:
        month, day, year = int(date.group(1)), int(date.group(2)), date.group(3)
        if 1 <= month <= 12 and 1 <= day <= 31:
            years = [year] if len(year) == 4 else [("20" if int(year) < 50 else "19") + year, year]
            for y in years:
                variants.add(normalise(f"{MONTHS[month - 1]} {day} {y}"))
                variants.add(normalise(f"{day} {MONTHS[month - 1]} {y}"))
                variants.add(normalise(f"{month}/{day}/{y}"))
                variants.add(normalise(f"{month:02d}/{day:02d}/{y}"))
    variants.discard("  ")
    return sorted(variants)


def files_named_in(source, names):
    """Which of the document names are mentioned in a question's 'source' text. (Contract file names contain spaces and
    commas, so they are looked up by name instead of being cut out of the text.)"""
    return {name for name in names if name in source}


def prepare_questions(questions, documents):
    """Keeps the questions that have an answer and a document in this folder.

    Adds: files (the right documents), variants (how the answer may be written, or [] when it cannot be checked
    because it does not appear word for word in the document).
    """
    texts = {d["name"]: normalise(d["text"]) for d in documents}
    prepared = []
    for question in questions:
        if not question.get("answerable", True):
            continue
        files = files_named_in(question.get("source", ""), texts)
        if not files:
            continue
        variants = [v for v in answer_variants(question.get("answer", "")) if any(v in texts[f] for f in files)]
        prepared.append({**question, "files": files, "variants": variants})
    return prepared


# ----- chunks and embeddings -----


def build_chunks(documents, size, overlap_ratio, method="fixed", with_context=False):
    """Cut every document into chunks of about `size` words with one method.

    Returns dictionaries: name, position, text, context, words, norm, and embed (the text that gets embedded: the chunk,
    with its context line in front when with_context). Answers are only looked for in the chunk text itself.
    """
    overlap = int(size * overlap_ratio)
    chunks = []
    for document in documents:
        pieces = make_chunks(document["text"], method, size, overlap, title_from_name(document["name"]))
        for position, piece in enumerate(pieces):
            text = piece["text"]
            chunks.append({
                "name": document["name"], "position": position, "text": text, "context": piece["context"],
                "words": len(text.split()), "norm": normalise(text), "embed": text_to_embed(piece, with_context),
            })
    return chunks


def embed_cached(texts, embed, cache_dir, tag):
    """Vectors for the texts (as unit length rows). Saved on disk, so the same texts are never embedded twice."""
    key = hashlib.sha256((tag + "\x00" + "\x00".join(texts)).encode("utf-8")).hexdigest()
    path = Path(cache_dir) / f"chunk_sweep_{key}.npy"
    if path.exists():
        return np.load(path)
    vectors = np.array(embed(texts), dtype=np.float32)
    vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, vectors)
    return vectors


# ----- scoring -----


def rank_of_first(order, chunks, question, need_answer):
    """Position (1 = best) of the first chunk from the right file, that also holds the answer if need_answer."""
    for rank, index in enumerate(order, start=1):
        chunk = chunks[index]
        if chunk["name"] not in question["files"]:
            continue
        if not need_answer or any(v in chunk["norm"] for v in question["variants"]):
            return rank
    return None


def words_for_budget(order, chunks, budget):
    """How many of the best chunks are needed to collect `budget` words (the last chunk may go over)."""
    total = 0
    for count, index in enumerate(order, start=1):
        total += chunks[index]["words"]
        if total >= budget:
            return count
    return len(order)


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def score_size(chunks, vectors, questions, query_vectors, budget):
    """Scores one chunk size. Returns one row of numbers."""
    scores = vectors @ query_vectors.T  # chunks x questions
    file_ranks, answer_ranks, budget_hits, context = [], [], [], []
    for column, question in enumerate(questions):
        order = np.argsort(-scores[:, column], kind="stable")
        file_ranks.append(rank_of_first(order, chunks, question, need_answer=False))
        context.append(sum(chunks[i]["words"] for i in order[:5]))
        if question["variants"]:
            rank = rank_of_first(order, chunks, question, need_answer=True)
            answer_ranks.append(rank)
            used = words_for_budget(order, chunks, budget)
            budget_hits.append(rank is not None and rank <= used)

    def at(ranks, k):
        return mean(r is not None and r <= k for r in ranks)

    row = {
        "chunks": len(chunks),
        "avg_words": mean(c["words"] for c in chunks),
        "max_words": max(c["words"] for c in chunks),
        "graded": len(answer_ranks),
        "questions": len(questions),
        "file_hit@5": at(file_ranks, 5),
        "hit@budget": mean(budget_hits),
        "mrr": mean(1 / r if r and r <= MAX_RANK else 0.0 for r in answer_ranks),
        "context_words": mean(context),
    }
    for k in KS:
        row[f"answer_hit@{k}"] = at(answer_ranks, k)
    return row


def run_sweep(documents, questions, sizes, overlap_ratio, embed_documents, embed_one, cache_dir, tag, budget=1000,
              methods=("fixed",), contexts=(False,)):
    """Runs every method, with and without context lines as asked, at every size. documents are already cleaned.
    Returns a list of rows (dictionaries), one per method, context setting and size."""
    questions = prepare_questions(questions, documents)
    if not questions:
        raise ValueError("None of the questions name a document in this folder. Check the --docs folder.")
    query_vectors = embed_cached([q["question"] for q in questions], lambda texts: [embed_one(t) for t in texts], cache_dir, tag + "|query")
    rows = []
    for method in methods:
        for with_context in contexts:
            for size in sizes:
                chunks = build_chunks(documents, size, overlap_ratio, method, with_context)
                label = f"{method}{' + context' if with_context else ''}, size {size} words"
                print(f"{label}: {len(chunks)} chunks. Embedding (saved afterwards, so a rerun is quick)...", flush=True)
                vectors = embed_cached([c["embed"] for c in chunks], embed_documents, cache_dir, f"{tag}|doc")
                scores = score_size(chunks, vectors, questions, query_vectors, budget)
                rows.append({"method": method, "context": "yes" if with_context else "no", "size": size,
                             "overlap": int(size * overlap_ratio), **scores})
    return rows


# ----- output -----


def percent(value):
    return "-" if value is None else f"{value:.0%}"


def print_table(rows, budget):
    print(f"\nChunking comparison (hit@budget collects about {budget} words per question)\n")
    columns = [
        ("method", "method", str), ("context", "context", str), ("size", "size", str), ("chunks", "chunks", str), ("avg words", "avg_words", lambda v: f"{v:.0f}"), ("max words", "max_words", str),
        ("ans@1", "answer_hit@1", percent), ("ans@3", "answer_hit@3", percent), ("ans@5", "answer_hit@5", percent),
        ("MRR", "mrr", lambda v: "-" if v is None else f"{v:.2f}"), ("@budget", "hit@budget", percent),
        ("file@5", "file_hit@5", percent), ("context words", "context_words", lambda v: f"{v:.0f}"),
    ]
    widths = [max(len(title), *(len(fmt(r[key])) for r in rows)) for title, key, fmt in columns]
    print("  ".join(title.rjust(w) for (title, _, _), w in zip(columns, widths)))
    for r in rows:
        print("  ".join(fmt(r[key]).rjust(w) for (_, key, fmt), w in zip(columns, widths)))
    first = rows[0]
    print(f"\n{first['graded']} of {first['questions']} questions could be checked against the answer text; all {first['questions']} count in file@5.")


def save_rows(rows, dataset, path=RESULTS_FILE):
    """Adds the rows to the CSV. If the file was written with other columns (for example before the method column
    existed), it is rewritten once with all columns; old rows were all fixed-size without context lines."""
    path = Path(path)
    fields = ["time", "dataset", *rows[0].keys()]
    old_rows, changed = [], False
    if path.exists() and path.stat().st_size:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            old_fields = reader.fieldnames or []
            if old_fields != fields:
                changed = True
                old_rows = list(reader)
                fields = [*fields, *[f for f in old_fields if f not in fields]]
    rewrite = changed or not path.exists() or path.stat().st_size == 0
    with path.open("w" if rewrite else "a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, restval="", extrasaction="ignore")
        if rewrite:
            writer.writeheader()
            for old in old_rows:
                writer.writerow({"method": "fixed", "context": "no", **{k: v for k, v in old.items() if v not in (None, "")}})
        stamp = datetime.now().isoformat(timespec="seconds")
        for row in rows:
            writer.writerow({"time": stamp, "dataset": dataset, **row})
    print(f"Saved to {path}")


def main():
    parser = argparse.ArgumentParser(description="Compare chunk sizes and chunking methods on a set of questions.")
    parser.add_argument("questions", help="question file, for example ../evals/contracts-dev.json")
    parser.add_argument("--docs", required=True, help="folder with the documents the questions are about")
    parser.add_argument("--sizes", default=",".join(map(str, DEFAULT_SIZES)), help="chunk sizes in words, comma separated")
    parser.add_argument("--methods", default="fixed", help=f"chunking methods, comma separated: {', '.join(METHODS)}, auto")
    parser.add_argument("--context", choices=("no", "yes", "both"), default="no",
                        help="put each chunk's context line (document title > section) in front of it before embedding")
    parser.add_argument("--overlap", type=float, default=0.2, help="overlap as a share of the size (default 0.2)")
    parser.add_argument("--budget", type=int, default=1000, help="words of context for the hit@budget column")
    parser.add_argument("--no-save", action="store_true", help="do not add the result to evals/chunk-sweep.csv")
    args = parser.parse_args()

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    unknown = [m for m in methods if m not in (*METHODS, "auto")]
    if not methods or unknown:
        parser.error(f"unknown method {', '.join(unknown)}; choose from {', '.join(METHODS)}, auto")
    contexts = {"no": (False,), "yes": (True,), "both": (False, True)}[args.context]
    if not sizes or min(sizes) < 10 or not 0 <= args.overlap < 0.5:
        parser.error("sizes must be at least 10 words and the overlap between 0 and 0.5")
    documents = load_documents(args.docs)
    for document in documents:
        document["text"] = clean_text(document["text"])
    questions = load_questions(args.questions)
    settings = load_settings()
    rows = run_sweep(documents, questions, sizes, args.overlap, embed_texts, embed_query, settings.cache_dir, settings.embed_model, args.budget,
                     methods, contexts)
    print_table(rows, args.budget)
    if not args.no_save:
        save_rows(rows, Path(args.questions).name)


if __name__ == "__main__":
    main()
